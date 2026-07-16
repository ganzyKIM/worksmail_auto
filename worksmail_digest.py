#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""네이버 웍스(LINE WORKS) 공용계정 일일 메일 요약 다이제스트.

동작 흐름:
  1) IMAP으로 config.yaml에 등록한 공용 메일함들의 '새로 받은 메일'을 수집
  2) Gemini API로 계정별 요약 리포트(중요도/카테고리/필요조치)를 생성
  3) SMTP로 개인 계정에 요약 리포트를 발송

특징:
  - 메일함은 readonly로 열기 때문에 '읽음' 표시를 건드리지 않습니다.
  - state.json에 마지막 실행 시각을 저장해, 다음 실행 때 그 이후 메일만 가져옵니다.
  - 실행 로그는 worksmail.log 에 남습니다.

사용 예:
  python worksmail_digest.py            # 실제 실행(수집→요약→발송, 즉시)
  python worksmail_digest.py --dry-run  # 발송하지 않고 화면에만 리포트 출력
  python worksmail_digest.py --since-hours 48   # 최근 48시간 강제 수집
  python worksmail_digest.py --date 2026-07-15  # 특정 날짜 메일만 요약해서 발송(테스트용)
  python worksmail_digest.py --date 2026-07-15 --dry-run  # 위와 동일 + 발송은 생략
  python worksmail_digest.py --test     # IMAP/SMTP/Gemini 연결만 점검
  python worksmail_digest.py --watch-once   # 스케줄(취합 간격+발송 시각)에 따라
                                             # 지금이 발송할 때인지 확인하고, 맞으면
                                             # 그때만 실제로 수집·요약·발송한다.
                                             # 작업 스케줄러가 몇 분 간격으로 이 옵션을
                                             # 반복 호출하는 방식으로 자동화한다
                                             # (config.yaml의 schedule 설정을 따름).

참고: --date 로 실행하면 state.json(마지막 실행 시각)을 갱신하지 않습니다.
      다음 자동 실행이 --date 테스트로 인해 메일을 건너뛰지 않도록 하기 위함입니다.
"""

import argparse
import datetime as dt
import email
import imaplib
import json
import math
import re
import smtplib
import ssl
import sys
import traceback
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, parsedate_to_datetime
from pathlib import Path

# Windows 콘솔의 기본 코드페이지(cp949 등)는 이모지/일부 한글 조합을 인코딩하지
# 못해 print()가 죽는 경우가 있다. 표준출력/표준에러를 UTF-8로 강제 전환한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import requests
import yaml

try:
    import markdown as _md  # 선택적: 있으면 HTML 메일로 예쁘게 보냄
except ImportError:
    _md = None

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.yaml"
STATE_PATH = BASE / "state.json"
LOG_PATH = BASE / "worksmail.log"

# IMAP SINCE 검색은 영문 월 약어를 요구하므로 로케일 영향 없이 직접 만든다.
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------- #
# 유틸
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def decode_mime(value: str) -> str:
    """MIME 인코딩된 헤더(제목/보낸사람 등)를 사람이 읽을 수 있는 문자열로."""
    if not value:
        return ""
    out = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(part.decode("utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out).strip()


def to_utc(d):
    """naive datetime은 로컬 시간으로 간주하고 UTC aware datetime으로 변환."""
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.astimezone()  # 시스템 로컬 타임존 부여
    return d.astimezone(dt.timezone.utc)


def imap_since_str(d: dt.datetime) -> str:
    ld = d.astimezone()  # 로컬 날짜 기준
    return f"{ld.day:02d}-{_MONTHS[ld.month - 1]}-{ld.year}"


def parse_date_range(date_str: str):
    """'YYYY-MM-DD' 형식의 로컬 날짜 하나를 그날 00:00~다음날 00:00(로컬)
    구간의 (since_utc, until_utc) 튜플로 변환한다. 형식이 잘못되면 ValueError."""
    start_naive = dt.datetime.strptime(date_str, "%Y-%m-%d")
    end_naive = start_naive + dt.timedelta(days=1)
    return to_utc(start_naive), to_utc(end_naive)


def parse_anchor_time(anchor_time: str):
    """'HH:MM' 문자열을 (hour, minute) 정수 튜플로. 형식이 잘못되면 ValueError."""
    parts = str(anchor_time).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"'HH:MM' 형식이어야 합니다: {anchor_time!r}")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"시:분 범위를 벗어났습니다: {anchor_time!r}")
    return hh, mm


def compute_next_due(after_utc: dt.datetime, interval_hours: float, anchor_time: str) -> dt.datetime:
    """anchor_time(로컬 HH:MM)을 기준으로 interval_hours 간격으로 반복되는
    시각들 중, after_utc 이후 가장 가까운 다음 시각을 UTC로 돌려준다.
    예) anchor 08:00, interval 12시간 -> 매일 08:00, 20:00.
    PC가 오래 꺼져 있었다면 지나간 슬롯은 건너뛰고 다음 슬롯으로 바로 넘어간다
    (밀린 만큼 몰아서 발송하지 않음)."""
    hh, mm = parse_anchor_time(anchor_time)
    interval_hours = float(interval_hours)
    if interval_hours <= 0:
        raise ValueError("interval_hours 는 0보다 커야 합니다.")

    local_after = after_utc.astimezone()
    base = local_after.replace(hour=hh, minute=mm, second=0, microsecond=0)
    step = dt.timedelta(hours=interval_hours)
    elapsed_steps = (local_after - base) / step
    n = math.floor(elapsed_steps) + 1  # base + n*step 이 local_after보다 뒤가 되는 최소 n
    next_slot = base + n * step
    return to_utc(next_slot)


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return text


def decode_part(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, TypeError):
        return payload.decode("utf-8", errors="replace")


def extract_body(msg, limit: int) -> str:
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                text += decode_part(part) + "\n"
        if not text.strip():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    text += strip_html(decode_part(part)) + "\n"
    else:
        if msg.get_content_type() == "text/html":
            text = strip_html(decode_part(msg))
        else:
            text = decode_part(msg)
    text = " ".join(text.split())  # 공백 정리
    return text[:limit]


def get_msg_datetime(msg):
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None


# --------------------------------------------------------------------------- #
# 설정 / 상태
# --------------------------------------------------------------------------- #
def load_raw_config() -> dict:
    """검증·기본값 채우기 없이 config.yaml을 그대로 읽는다. 파일이 없으면 빈 dict.
    (관리자 UI처럼 아직 불완전한 설정도 다뤄야 하는 경우에 사용)"""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def normalize_config(cfg: dict) -> dict:
    """누락된 섹션에 기본값을 채우고 recipients를 리스트로 정규화한다.
    검증(필수값 존재 확인)은 하지 않는다 — 그건 validate_config()의 역할."""
    cfg = dict(cfg or {})

    recipients = cfg.get("recipients")
    if isinstance(recipients, str):
        recipients = [recipients]
    cfg["recipients"] = [r for r in (recipients or []) if r]

    cfg["accounts"] = cfg.get("accounts") or []
    cfg["sender"] = dict(cfg.get("sender") or {})
    cfg["imap"] = dict(cfg.get("imap") or {})
    cfg["imap"].setdefault("host", "imap.worksmobile.com")
    cfg["imap"].setdefault("port", 993)
    cfg["smtp"] = dict(cfg.get("smtp") or {})
    cfg["smtp"].setdefault("host", "smtp.worksmobile.com")
    cfg["smtp"].setdefault("port", 587)
    cfg["gemini"] = dict(cfg.get("gemini") or {})
    cfg["gemini"].setdefault("model", "gemini-flash-latest")
    cfg["schedule"] = dict(cfg.get("schedule") or {})
    cfg["schedule"].setdefault("interval_hours", 24)
    cfg["schedule"].setdefault("anchor_time", "08:00")
    cfg["admin_ui"] = dict(cfg.get("admin_ui") or {})
    cfg.setdefault("lookback_hours", 24)
    cfg.setdefault("body_char_limit", 2000)
    return cfg


def validate_config(cfg: dict) -> list:
    """정규화된 cfg에 대해 실행에 필요한 필수값이 다 있는지 확인하고
    문제 메시지 목록을 돌려준다(문제 없으면 빈 리스트)."""
    problems = []
    if not cfg.get("accounts"):
        problems.append("accounts(수집할 공용 계정 목록)가 비어 있습니다.")
    if not (cfg.get("sender") or {}).get("email"):
        problems.append("sender.email(발송 계정)이 없습니다.")
    if not cfg.get("recipients"):
        problems.append("recipients(요약을 받을 개인 메일 목록)가 비어 있습니다.")
    if not (cfg.get("gemini") or {}).get("api_key"):
        problems.append("gemini.api_key(제미나이 API 키)가 없습니다.")
    schedule = cfg.get("schedule") or {}
    try:
        parse_anchor_time(schedule.get("anchor_time", "08:00"))
    except ValueError:
        problems.append("schedule.anchor_time 형식이 올바르지 않습니다 ('HH:MM').")
    interval = schedule.get("interval_hours")
    try:
        if interval is None or float(interval) <= 0:
            problems.append("schedule.interval_hours 는 0보다 큰 숫자여야 합니다.")
    except (TypeError, ValueError):
        problems.append("schedule.interval_hours 는 숫자여야 합니다.")
    return problems


def load_config() -> dict:
    """실행에 필요한 완전한 설정을 읽는다. 파일이 없거나 필수값이 빠졌으면
    로그를 남기고 종료한다(배치 스크립트용 — 관리자 UI는 load_raw_config +
    normalize_config + validate_config 를 직접 조합해서 쓴다)."""
    if not CONFIG_PATH.exists():
        log(f"[오류] 설정 파일이 없습니다: {CONFIG_PATH}")
        log("      config.example.yaml 을 config.yaml 로 복사한 뒤 값을 채워주세요.")
        sys.exit(1)

    cfg = normalize_config(load_raw_config())
    problems = validate_config(cfg)
    if problems:
        log("[오류] config.yaml 설정을 확인하세요:")
        for p in problems:
            log("      - " + p)
        sys.exit(1)
    return cfg


def save_config(cfg: dict) -> None:
    """cfg 전체를 config.yaml에 그대로 덮어쓴다. (주의: 사람이 손으로 넣은
    주석은 보존되지 않는다 — 관리자 UI로 저장한 뒤에는 주석이 사라진다.)"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# IMAP 수집
# --------------------------------------------------------------------------- #
def fetch_account(acct: dict, cfg: dict, since_dt: dt.datetime,
                   until_dt: dt.datetime = None) -> list:
    """since_dt(포함) 이후 메일을 수집한다. until_dt가 주어지면 그 시각
    이전(미포함) 메일까지만 포함한다 — 특정 날짜 하루치만 볼 때 사용."""
    host = cfg["imap"]["host"]
    port = int(cfg["imap"]["port"])
    limit = int(cfg["body_char_limit"])
    mails = []

    M = imaplib.IMAP4_SSL(host, port)
    try:
        M.login(acct["email"], acct["password"])
        M.select("INBOX", readonly=True)  # 읽음 표시를 건드리지 않음
        # 날짜(일) 단위로 1차 필터 후, 아래에서 정확한 시각으로 2차 필터
        search_from = since_dt - dt.timedelta(days=1)
        search_criteria = ["SINCE", imap_since_str(search_from)]
        if until_dt is not None:
            search_criteria += ["BEFORE", imap_since_str(until_dt + dt.timedelta(days=1))]
        typ, data = M.search(None, *search_criteria)
        if typ != "OK":
            log(f"  [{acct['email']}] 검색 실패: {typ}")
            return mails
        ids = data[0].split()
        for num in ids:
            typ, msgdata = M.fetch(num, "(RFC822)")
            if typ != "OK" or not msgdata or not isinstance(msgdata[0], tuple):
                continue
            msg = email.message_from_bytes(msgdata[0][1])
            mdt = to_utc(get_msg_datetime(msg))
            if mdt is not None and mdt < since_dt:
                continue  # 시작 시각 이전 메일은 제외
            if until_dt is not None and mdt is not None and mdt >= until_dt:
                continue  # 종료 시각 이후 메일은 제외
            local_dt = mdt.astimezone() if mdt else None
            mails.append({
                "date": local_dt.strftime("%m-%d %H:%M") if local_dt else "(시각미상)",
                "sort_key": mdt or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
                "from": decode_mime(msg.get("From", "")),
                "subject": decode_mime(msg.get("Subject", "(제목 없음)")),
                "body": extract_body(msg, limit),
            })
    finally:
        try:
            M.logout()
        except Exception:
            pass

    mails.sort(key=lambda m: m["sort_key"])
    return mails


# --------------------------------------------------------------------------- #
# Gemini 요약
# --------------------------------------------------------------------------- #
def build_prompt(collected: list) -> str:
    blocks = []
    for acct_name, mails in collected:
        blocks.append(f"## 계정: {acct_name} (신규 {len(mails)}건)")
        for i, m in enumerate(mails, 1):
            blocks.append(
                f"[{i}] 수신:{m['date']} | 보낸사람:{m['from']} | 제목:{m['subject']}\n"
                f"    본문:{m['body']}"
            )
    data_text = "\n".join(blocks)

    return f"""당신은 회사의 여러 공용 메일함을 대신 관리하는 유능한 비서입니다.
아래는 오늘 각 공용 계정에 새로 도착한 메일 목록입니다. 이를 바탕으로 담당자가
1~2분 안에 훑어보고 놓친 일이 없는지 파악할 수 있는 '일일 요약 리포트'를 한국어
마크다운으로 작성하세요.

작성 규칙:
1. 맨 위에 "## 🔴 오늘 꼭 챙길 것" 섹션을 만들고, 즉시 대응이 필요하거나 놓치면
   안 되는 항목(계약/결제/마감/고객 클레임/보안/장애 등)을 최대 5개까지 굵게 요약.
   해당 항목이 없으면 "특별히 급한 건은 없습니다."라고 적으세요.
2. 그다음 계정별로 "## 📮 <계정명>" 섹션을 만들고, 각 메일을 아래 형식의 표로 정리:
   | 중요도 | 분류 | 보낸사람 | 한줄요약 | 필요한 조치 |
   - 중요도: 🔴높음 / 🟡보통 / ⚪낮음(광고·뉴스레터·자동알림 등)
   - 분류: 계약/결제/고객문의/인프라/보안/내부공지/광고·스팸/기타 중 하나
   - 한줄요약: 메일 핵심을 25자 내외로
   - 필요한 조치: 담당자가 해야 할 일. 없으면 "없음"
3. 광고/스팸/자동알림은 과감히 낮음으로 분류하고 요약을 짧게.
4. 사실만 쓰고 추측·과장하지 마세요. 원문에 없는 내용을 지어내지 마세요.

아래가 수집된 메일 데이터입니다:

{data_text}
"""


def summarize_with_gemini(prompt: str, cfg: dict) -> str:
    api_key = cfg["gemini"]["api_key"]
    model = cfg["gemini"]["model"]
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key}")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
    }
    resp = requests.post(url, json=payload, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API 오류 {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    try:
        cand = data["candidates"][0]
        parts = cand["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Gemini 응답 파싱 실패: {json.dumps(data)[:500]}")


# --------------------------------------------------------------------------- #
# SMTP 발송
# --------------------------------------------------------------------------- #
def send_report(markdown_text: str, cfg: dict, total: int) -> None:
    sender = cfg["sender"]
    recipients = cfg["recipients"]
    subject = f"[공용메일 일일요약] {dt.date.today():%Y-%m-%d} (신규 {total}건)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((sender.get("display_name", "공용메일 일일요약"),
                              sender["email"]))
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)

    msg.attach(MIMEText(markdown_text, "plain", "utf-8"))
    if _md is not None:
        html_body = _md.markdown(markdown_text, extensions=["tables"])
        html = f"""<html><head><meta charset="utf-8"><style>
body{{font-family:'Malgun Gothic',sans-serif;font-size:14px;line-height:1.6;color:#222}}
table{{border-collapse:collapse;width:100%;margin:8px 0}}
th,td{{border:1px solid #ddd;padding:6px 8px;text-align:left;font-size:13px}}
th{{background:#f4f4f4}} h2{{margin-top:22px}}
</style></head><body>{html_body}</body></html>"""
        msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(cfg["smtp"]["host"], int(cfg["smtp"]["port"]), timeout=60) as s:
        s.starttls(context=ctx)
        s.login(sender["email"], sender["password"])
        s.sendmail(sender["email"], recipients, msg.as_string())
    log(f"발송 완료 → {', '.join(recipients)}")


# --------------------------------------------------------------------------- #
# 점검 모드
# --------------------------------------------------------------------------- #
def check_connections(cfg: dict) -> tuple:
    """IMAP(계정별)/SMTP/Gemini를 실제로 접속해보고 (ok: bool, lines: list[str])를
    돌려준다. 종료(sys.exit)하지 않으므로 CLI(run_test)와 관리자 UI 양쪽에서 쓴다."""
    ok = True
    lines = []
    for acct in cfg["accounts"]:
        try:
            M = imaplib.IMAP4_SSL(cfg["imap"]["host"], int(cfg["imap"]["port"]))
            M.login(acct["email"], acct["password"])
            M.select("INBOX", readonly=True)
            M.logout()
            lines.append(f"IMAP 로그인 OK: {acct['email']}")
        except Exception as e:
            ok = False
            lines.append(f"IMAP 로그인 실패: {acct['email']} -> {e}")
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(cfg["smtp"]["host"], int(cfg["smtp"]["port"]), timeout=60) as s:
            s.starttls(context=ctx)
            s.login(cfg["sender"]["email"], cfg["sender"]["password"])
        lines.append(f"SMTP 로그인 OK: {cfg['sender']['email']}")
    except Exception as e:
        ok = False
        lines.append(f"SMTP 로그인 실패: {cfg['sender']['email']} -> {e}")
    try:
        reply = summarize_with_gemini("이 메시지에는 '정상' 이라는 단어 하나로만 답하세요.", cfg)
        lines.append(f"Gemini API OK (모델: {cfg['gemini']['model']}) 응답: {reply[:30]}")
    except Exception as e:
        ok = False
        lines.append(f"Gemini API 실패: {e}")
    lines.append(f"수신자: {', '.join(cfg['recipients'])}")
    try:
        next_due = compute_next_due(dt.datetime.now(dt.timezone.utc),
                                     cfg["schedule"]["interval_hours"],
                                     cfg["schedule"]["anchor_time"])
        lines.append(f"다음 예정 발송 시각: {next_due.astimezone():%Y-%m-%d %H:%M} 로컬 "
                     f"(취합 간격 {cfg['schedule']['interval_hours']}시간, "
                     f"기준 시각 {cfg['schedule']['anchor_time']})")
    except ValueError as e:
        ok = False
        lines.append(f"schedule 설정 오류: {e}")
    return ok, lines


def run_test(cfg: dict) -> None:
    log("=== 연결 점검 시작 ===")
    ok, lines = check_connections(cfg)
    for line in lines:
        log("  " + line)
    log("=== 점검 완료: " + ("모두 정상 ✅" if ok else "실패 항목 있음 ❌") + " ===")
    sys.exit(0 if ok else 1)


# --------------------------------------------------------------------------- #
# 수집 + 요약 (main()과 --watch-once 양쪽이 공유)
# --------------------------------------------------------------------------- #
def collect_and_build_report(cfg: dict, since_dt: dt.datetime, until_dt: dt.datetime = None) -> tuple:
    """since_dt(~until_dt) 구간의 메일을 모든 계정에서 모아 Gemini로 요약한
    마크다운 리포트를 만든다. (report_markdown, total_count) 를 돌려준다."""
    if until_dt is not None:
        log(f"수집 시작 (구간: {since_dt.astimezone():%Y-%m-%d %H:%M} ~ "
            f"{until_dt.astimezone():%Y-%m-%d %H:%M} 로컬)")
    else:
        log(f"수집 시작 (기준 시각 이후: {since_dt.astimezone():%Y-%m-%d %H:%M} 로컬)")

    collected = []
    total = 0
    for acct in cfg["accounts"]:
        name = acct.get("name") or acct["email"]
        try:
            mails = fetch_account(acct, cfg, since_dt, until_dt)
            log(f"  {name}: {len(mails)}건")
            collected.append((name, mails))
            total += len(mails)
        except Exception as e:
            log(f"  {name}: 수집 실패 -> {e}")
            collected.append((name, []))

    if total == 0:
        log("신규 메일이 없습니다.")
        range_desc = (f"{since_dt.astimezone():%Y-%m-%d %H:%M} ~ {until_dt.astimezone():%Y-%m-%d %H:%M}"
                      if until_dt is not None
                      else f"{since_dt.astimezone():%Y-%m-%d %H:%M} 이후")
        report = (f"## 📭 새 메일 없음\n\n"
                  f"{range_desc} 구간에 공용 계정에 도착한 새 메일이 없습니다.")
    else:
        log("Gemini 요약 생성 중...")
        prompt = build_prompt(collected)
        try:
            report = summarize_with_gemini(prompt, cfg)
        except Exception as e:
            log(f"[경고] 요약 실패, 원본 목록으로 대체합니다 -> {e}")
            # 요약이 실패해도 목록만이라도 보낸다
            lines = [f"## ⚠️ 자동 요약 실패 — 수집된 메일 원본 목록 (신규 {total}건)", ""]
            for acct_name, mails in collected:
                lines.append(f"### 📮 {acct_name} ({len(mails)}건)")
                for m in mails:
                    lines.append(f"- **{m['date']}** | {m['from']} | {m['subject']}")
                lines.append("")
            report = "\n".join(lines)

    footer = (f"\n\n---\n_생성: {dt.datetime.now():%Y-%m-%d %H:%M} · "
              f"수집 계정 {len(cfg['accounts'])}개 · 신규 {total}건_")
    report += footer
    return report, total


# --------------------------------------------------------------------------- #
# --watch-once: 스케줄에 따라 "지금이 발송할 때인가"만 확인하고, 맞으면 발송
# --------------------------------------------------------------------------- #
def run_watch_once(cfg: dict, dry_run: bool) -> None:
    state = load_state()
    now = dt.datetime.now(dt.timezone.utc)
    interval_hours = cfg["schedule"]["interval_hours"]
    anchor_time = cfg["schedule"]["anchor_time"]

    next_due_str = state.get("next_due")
    if next_due_str:
        next_due = dt.datetime.fromisoformat(next_due_str)
        if next_due.tzinfo is None:
            next_due = next_due.replace(tzinfo=dt.timezone.utc)
    else:
        # 최초 실행: 아직 스케줄이 없으므로 다음 슬롯만 계산해두고 이번엔 발송하지 않는다
        next_due = compute_next_due(now, interval_hours, anchor_time)
        state["next_due"] = next_due.isoformat()
        save_state(state)
        log(f"[watch] 스케줄 초기화. 다음 발송 예정: {next_due.astimezone():%Y-%m-%d %H:%M} 로컬")
        return

    if now < next_due:
        log(f"[watch] 아직 발송 시각이 아님 (다음 예정: {next_due.astimezone():%Y-%m-%d %H:%M} 로컬)")
        return

    since_dt = next_due - dt.timedelta(hours=float(interval_hours))
    log(f"[watch] 발송 시각 도달 ({next_due.astimezone():%Y-%m-%d %H:%M} 로컬) — 수집 시작")
    report, total = collect_and_build_report(cfg, since_dt)

    if dry_run:
        log("[watch][dry-run] 발송하지 않고 출력만 합니다 (다음 예정 시각도 갱신하지 않음).\n")
        print("=" * 70)
        print(report)
        print("=" * 70)
        return

    try:
        send_report(report, cfg, total)
    except Exception as e:
        log(f"[watch] 발송 실패, 다음 예정 시각을 갱신하지 않고 다음 체크 때 재시도합니다 -> {e}")
        return

    state["next_due"] = compute_next_due(next_due, interval_hours, anchor_time).isoformat()
    save_state(state)
    log(f"[watch] 완료. 다음 발송 예정: {state['next_due']}")


# --------------------------------------------------------------------------- #
# 메인
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="네이버 웍스 공용계정 일일 메일 요약")
    ap.add_argument("--dry-run", action="store_true",
                    help="발송하지 않고 리포트를 화면에만 출력")
    range_group = ap.add_mutually_exclusive_group()
    range_group.add_argument("--since-hours", type=float, default=None,
                    help="최근 N시간 메일을 강제로 수집(state 무시)")
    range_group.add_argument("--date", type=str, default=None,
                    help="YYYY-MM-DD 형식. 지정한 날짜 하루치 메일만 수집·요약·발송"
                         "(테스트용. state.json은 갱신하지 않음)")
    range_group.add_argument("--watch-once", action="store_true",
                    help="config.yaml의 schedule(취합 간격/발송 시각)에 따라 지금이 "
                         "발송할 때인지만 확인하고, 맞으면 그때만 발송(자동화용)")
    ap.add_argument("--test", action="store_true",
                    help="IMAP/SMTP/Gemini 연결만 점검하고 종료")
    args = ap.parse_args()

    cfg = load_config()

    if args.test:
        run_test(cfg)

    if args.watch_once:
        run_watch_once(cfg, args.dry_run)
        return

    state = load_state()
    now = dt.datetime.now(dt.timezone.utc)
    until_dt = None

    if args.date is not None:
        try:
            since_dt, until_dt = parse_date_range(args.date)
        except ValueError:
            log(f"[오류] --date 형식이 올바르지 않습니다. 'YYYY-MM-DD' 형식으로 입력하세요 (예: 2026-07-15). 입력값: {args.date}")
            sys.exit(1)
    elif args.since_hours is not None:
        since_dt = now - dt.timedelta(hours=args.since_hours)
    elif state.get("last_run"):
        since_dt = dt.datetime.fromisoformat(state["last_run"])
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=dt.timezone.utc)
    else:
        since_dt = now - dt.timedelta(hours=float(cfg["lookback_hours"]))

    report, total = collect_and_build_report(cfg, since_dt, until_dt)

    if args.dry_run:
        log("[dry-run] 아래 리포트를 발송하지 않고 출력만 합니다.\n")
        print("=" * 70)
        print(report)
        print("=" * 70)
        return

    send_report(report, cfg, total)

    if args.date is not None:
        log("[정보] --date 테스트 모드였으므로 state.json(마지막 실행 시각)은 갱신하지 않았습니다.")
    else:
        # 성공적으로 발송한 경우에만 상태 갱신
        state["last_run"] = now.isoformat()
        save_state(state)
    log("완료.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log("[치명적 오류]\n" + traceback.format_exc())
        sys.exit(1)
