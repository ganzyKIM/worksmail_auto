#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorksMail 관리자 UI — 로컬 전용 웹 화면.

모니터링할 메일주소(계정), 요약을 받을 수신자, 취합 간격/발송 시각을
브라우저에서 편집한다. worksmail_digest.py와 같은 config.yaml을 읽고 쓰므로,
저장하면 다음 --watch-once 틱부터 바로 반영된다(재시작 불필요).

시작:
  python admin_ui.py
  (또는 run_admin_ui.bat 더블클릭)
  브라우저에서 http://127.0.0.1:5000 접속

주의:
  - 127.0.0.1(이 PC)에서만 접속 가능하도록 바인딩한다. 네트워크의 다른 기기에서는
    접속할 수 없다.
  - 첫 실행 시 관리자 비밀번호를 설정해야 로그인할 수 있다.
  - 저장 버튼을 누르면 config.yaml 전체를 다시 쓴다 — 손으로 넣은 주석은 사라진다.
"""

import datetime as dt
import functools
import secrets

from flask import Flask, flash, redirect, render_template, request, session, url_for

import worksmail_digest as core

app = Flask(__name__)
# 서버 프로세스를 새로 시작할 때마다 바뀐다 -> 재시작하면 모두 재로그인 필요.
# "필요할 때만 수동 실행"하는 도구라 지속 세션은 불필요하다고 판단.
app.secret_key = secrets.token_hex(32)


def get_cfg() -> dict:
    return core.normalize_config(core.load_raw_config())


def read_log_tail(n: int = 25) -> list:
    if not core.LOG_PATH.exists():
        return []
    with open(core.LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return [line.rstrip("\n") for line in lines[-n:]]


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        cfg = get_cfg()
        if not cfg.get("admin_ui", {}).get("password"):
            return redirect(url_for("setup"))
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------------------- #
# 로그인 / 초기 설정
# --------------------------------------------------------------------------- #
@app.route("/setup", methods=["GET", "POST"])
def setup():
    cfg = get_cfg()
    if cfg.get("admin_ui", {}).get("password"):
        return redirect(url_for("login"))
    if request.method == "POST":
        pw = request.form.get("password", "").strip()
        pw2 = request.form.get("password2", "").strip()
        if len(pw) < 4:
            flash("비밀번호는 4자 이상으로 설정하세요.", "error")
        elif pw != pw2:
            flash("두 비밀번호가 일치하지 않습니다.", "error")
        else:
            cfg["admin_ui"]["password"] = pw
            core.save_config(cfg)
            session["logged_in"] = True
            flash("관리자 비밀번호가 설정되었습니다. 이제 계정·수신자·스케줄을 등록하세요.", "ok")
            return redirect(url_for("dashboard"))
    return render_template("login.html", mode="setup")


@app.route("/login", methods=["GET", "POST"])
def login():
    cfg = get_cfg()
    admin_password = cfg.get("admin_ui", {}).get("password")
    if not admin_password:
        return redirect(url_for("setup"))
    if request.method == "POST":
        if request.form.get("password", "") == admin_password:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("비밀번호가 올바르지 않습니다.", "error")
    return render_template("login.html", mode="login")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------------- #
# 대시보드
# --------------------------------------------------------------------------- #
@app.route("/")
@login_required
def dashboard():
    cfg = get_cfg()
    problems = core.validate_config(cfg)
    next_due_preview = None
    try:
        next_due_preview = core.compute_next_due(
            dt.datetime.now(dt.timezone.utc),
            cfg["schedule"]["interval_hours"],
        ).astimezone()
    except (ValueError, TypeError):
        pass
    return render_template(
        "admin.html", cfg=cfg, problems=problems,
        log_tail=read_log_tail(), next_due_preview=next_due_preview,
    )


# --------------------------------------------------------------------------- #
# 모니터링 계정 (info, base 등)
# --------------------------------------------------------------------------- #
@app.route("/accounts/add", methods=["POST"])
@login_required
def accounts_add():
    cfg = get_cfg()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    if not email or not password:
        flash("이메일과 비밀번호는 필수입니다.", "error")
    elif any(a["email"] == email for a in cfg["accounts"]):
        flash(f"이미 등록된 계정입니다: {email}", "error")
    else:
        cfg["accounts"].append({"name": name or email, "email": email, "password": password})
        if not cfg["sender"].get("email"):
            cfg["sender"] = {"email": email, "password": password,
                              "display_name": cfg["sender"].get("display_name", "공용메일 요약")}
            flash(f"계정 추가됨: {email} (발송 계정으로도 자동 지정됨)", "ok")
        else:
            flash(f"계정 추가됨: {email}", "ok")
        core.save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/accounts/delete", methods=["POST"])
@login_required
def accounts_delete():
    cfg = get_cfg()
    email = request.form.get("email", "")
    cfg["accounts"] = [a for a in cfg["accounts"] if a["email"] != email]
    if cfg["sender"].get("email") == email:
        if cfg["accounts"]:
            first = cfg["accounts"][0]
            cfg["sender"] = {"email": first["email"], "password": first["password"],
                              "display_name": cfg["sender"].get("display_name", "공용메일 요약")}
            flash(f"계정 삭제됨: {email} (발송 계정이 {first['email']}(으)로 자동 변경됨)", "warn")
        else:
            cfg["sender"] = {}
            flash(f"계정 삭제됨: {email} (남은 계정이 없어 발송 계정이 비었습니다)", "warn")
    else:
        flash(f"계정 삭제됨: {email}", "ok")
    core.save_config(cfg)
    return redirect(url_for("dashboard"))


@app.route("/accounts/password", methods=["POST"])
@login_required
def accounts_password():
    cfg = get_cfg()
    email = request.form.get("email", "")
    new_pw = request.form.get("password", "").strip()
    if not new_pw:
        flash("새 비밀번호를 입력하세요.", "error")
        return redirect(url_for("dashboard"))
    found = False
    for a in cfg["accounts"]:
        if a["email"] == email:
            a["password"] = new_pw
            found = True
    if cfg["sender"].get("email") == email:
        cfg["sender"]["password"] = new_pw
    if found:
        core.save_config(cfg)
        flash(f"비밀번호 변경됨: {email}", "ok")
    else:
        flash("계정을 찾을 수 없습니다.", "error")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------- #
# 수신자
# --------------------------------------------------------------------------- #
@app.route("/recipients/add", methods=["POST"])
@login_required
def recipients_add():
    cfg = get_cfg()
    email = request.form.get("email", "").strip()
    if not email:
        flash("이메일을 입력하세요.", "error")
    elif email in cfg["recipients"]:
        flash("이미 등록된 수신자입니다.", "error")
    else:
        cfg["recipients"].append(email)
        core.save_config(cfg)
        flash(f"수신자 추가됨: {email}", "ok")
    return redirect(url_for("dashboard"))


@app.route("/recipients/delete", methods=["POST"])
@login_required
def recipients_delete():
    cfg = get_cfg()
    email = request.form.get("email", "")
    cfg["recipients"] = [r for r in cfg["recipients"] if r != email]
    core.save_config(cfg)
    flash(f"수신자 삭제됨: {email}", "ok")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------- #
# 발송 계정
# --------------------------------------------------------------------------- #
@app.route("/sender/save", methods=["POST"])
@login_required
def sender_save():
    cfg = get_cfg()
    email = request.form.get("email", "")
    display_name = request.form.get("display_name", "").strip() or "공용메일 요약"
    account = next((a for a in cfg["accounts"] if a["email"] == email), None)
    if not account:
        flash("존재하지 않는 계정입니다.", "error")
    else:
        cfg["sender"] = {"email": account["email"], "password": account["password"],
                          "display_name": display_name}
        core.save_config(cfg)
        flash(f"발송 계정 저장됨: {email}", "ok")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------- #
# 스케줄 (취합 간격 / 발송 시각)
# --------------------------------------------------------------------------- #
@app.route("/schedule/save", methods=["POST"])
@login_required
def schedule_save():
    cfg = get_cfg()
    interval_raw = request.form.get("interval_hours", "24").strip()
    anchor = request.form.get("anchor_time", "08:00").strip()
    try:
        interval_val = float(interval_raw)
        if interval_val <= 0:
            raise ValueError("interval must be positive")
        core.parse_anchor_time(anchor)
    except ValueError:
        flash("취합 간격 또는 발송 시각 형식이 올바르지 않습니다.", "error")
        return redirect(url_for("dashboard"))
    cfg["schedule"] = {"interval_hours": interval_val, "anchor_time": anchor}
    core.save_config(cfg)
    flash("스케줄 저장됨. 다음 --watch-once 실행부터 반영됩니다.", "ok")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------- #
# Gemini
# --------------------------------------------------------------------------- #
@app.route("/gemini/save", methods=["POST"])
@login_required
def gemini_save():
    cfg = get_cfg()
    new_key = request.form.get("api_key", "").strip()
    model = request.form.get("model", "").strip() or "gemini-flash-latest"
    if new_key:
        cfg["gemini"]["api_key"] = new_key
    cfg["gemini"]["model"] = model
    core.save_config(cfg)
    flash("Gemini 설정 저장됨.", "ok")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------- #
# 관리자 UI 비밀번호 변경
# --------------------------------------------------------------------------- #
@app.route("/admin_password/save", methods=["POST"])
@login_required
def admin_password_save():
    cfg = get_cfg()
    pw = request.form.get("password", "").strip()
    pw2 = request.form.get("password2", "").strip()
    if len(pw) < 4:
        flash("비밀번호는 4자 이상으로 설정하세요.", "error")
    elif pw != pw2:
        flash("두 비밀번호가 일치하지 않습니다.", "error")
    else:
        cfg["admin_ui"]["password"] = pw
        core.save_config(cfg)
        flash("관리자 비밀번호가 변경되었습니다.", "ok")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------- #
# 연결 테스트
# --------------------------------------------------------------------------- #
@app.route("/test-connection", methods=["POST"])
@login_required
def test_connection():
    cfg = get_cfg()
    problems = core.validate_config(cfg)
    if problems:
        flash("설정을 먼저 완성하세요: " + " / ".join(problems), "error")
        return redirect(url_for("dashboard"))
    ok, lines = core.check_connections(cfg)
    prefix = "모두 정상 ✅ — " if ok else "실패 항목 있음 ❌ — "
    flash(prefix + " | ".join(lines), "ok" if ok else "error")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    print("관리자 UI 시작: http://127.0.0.1:5000  (창을 닫으면 서버가 종료됩니다)")
    app.run(host="127.0.0.1", port=5000, debug=False)
