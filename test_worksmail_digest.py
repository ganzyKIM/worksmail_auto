# -*- coding: utf-8 -*-
"""worksmail_digest.py 핵심 로직에 대한 회귀 테스트."""

import argparse
import datetime as dt
import email
import json

import pytest

import worksmail_digest as w


# --------------------------------------------------------------------------- #
# decode_mime
# --------------------------------------------------------------------------- #
class TestDecodeMime:
    def test_decodes_korean_mime_header(self):
        encoded = "=?UTF-8?B?7JWI64WV7ZWY7IS47JqU?="  # '안녕하세요'
        assert w.decode_mime(encoded) == "안녕하세요"

    def test_plain_ascii_passthrough(self):
        assert w.decode_mime("Hello World") == "Hello World"

    def test_empty_string_returns_empty(self):
        assert w.decode_mime("") == ""

    def test_none_returns_empty(self):
        assert w.decode_mime(None) == ""


# --------------------------------------------------------------------------- #
# imap_since_str
# --------------------------------------------------------------------------- #
class TestImapSinceStr:
    def test_formats_as_dd_mon_yyyy(self):
        d = dt.datetime(2026, 7, 16, 9, 0, tzinfo=dt.timezone.utc)
        result = w.imap_since_str(d)
        assert result == d.astimezone().strftime("%d-%b-%Y")

    def test_single_digit_day_is_zero_padded(self):
        d = dt.datetime(2026, 3, 5, 0, 0, tzinfo=dt.timezone.utc)
        result = w.imap_since_str(d)
        assert result.split("-")[0] == "05"


# --------------------------------------------------------------------------- #
# parse_date_range
# --------------------------------------------------------------------------- #
class TestParseDateRange:
    def test_returns_local_midnight_to_next_midnight_in_utc(self):
        since_utc, until_utc = w.parse_date_range("2026-07-16")
        since_local = since_utc.astimezone()
        until_local = until_utc.astimezone()
        assert (since_local.year, since_local.month, since_local.day) == (2026, 7, 16)
        assert since_local.hour == 0 and since_local.minute == 0
        assert until_local - since_local == dt.timedelta(days=1)

    def test_since_is_before_until(self):
        since_utc, until_utc = w.parse_date_range("2026-01-01")
        assert since_utc < until_utc

    def test_invalid_format_raises_value_error(self):
        with pytest.raises(ValueError):
            w.parse_date_range("2026/07/16")

    def test_garbage_input_raises_value_error(self):
        with pytest.raises(ValueError):
            w.parse_date_range("not-a-date")


# --------------------------------------------------------------------------- #
# to_utc
# --------------------------------------------------------------------------- #
class TestToUtc:
    def test_none_returns_none(self):
        assert w.to_utc(None) is None

    def test_naive_datetime_is_localized_then_converted(self):
        naive = dt.datetime(2026, 7, 16, 12, 0)
        result = w.to_utc(naive)
        assert result.tzinfo == dt.timezone.utc

    def test_aware_datetime_converted_to_utc(self):
        kst = dt.timezone(dt.timedelta(hours=9))
        aware = dt.datetime(2026, 7, 16, 12, 0, tzinfo=kst)
        result = w.to_utc(aware)
        assert result == dt.datetime(2026, 7, 16, 3, 0, tzinfo=dt.timezone.utc)


# --------------------------------------------------------------------------- #
# strip_html
# --------------------------------------------------------------------------- #
class TestStripHtml:
    def test_removes_tags(self):
        assert w.strip_html("<p>Hello <b>World</b></p>") == " Hello  World  "

    def test_removes_script_and_style_content(self):
        html = "<style>.a{color:red}</style><p>Text</p><script>bad()</script>"
        result = w.strip_html(html)
        assert "color:red" not in result
        assert "bad()" not in result
        assert "Text" in result

    def test_decodes_common_entities(self):
        result = w.strip_html("A&nbsp;B&amp;C&lt;D&gt;E")
        assert result == "A B&C<D>E"


# --------------------------------------------------------------------------- #
# extract_body
# --------------------------------------------------------------------------- #
class TestExtractBody:
    def test_plain_text_message(self):
        raw = b"From: a@b.com\nSubject: t\nContent-Type: text/plain; charset=utf-8\n\nHello there"
        msg = email.message_from_bytes(raw)
        assert w.extract_body(msg, 100) == "Hello there"

    def test_html_message_falls_back_to_stripped_text(self):
        raw = (
            b"From: a@b.com\nSubject: t\nContent-Type: text/html; charset=utf-8\n\n"
            b"<html><body><p>Hello&nbsp;<b>World</b></p><script>bad()</script></body></html>"
        )
        msg = email.message_from_bytes(raw)
        result = w.extract_body(msg, 100)
        assert result == "Hello World"
        assert "bad()" not in result

    def test_multipart_prefers_text_plain(self):
        raw = (
            b"From: a@b.com\nSubject: t\n"
            b'Content-Type: multipart/alternative; boundary="B"\n\n'
            b"--B\nContent-Type: text/plain; charset=utf-8\n\nPlain version\n"
            b"--B\nContent-Type: text/html; charset=utf-8\n\n<p>HTML version</p>\n"
            b"--B--\n"
        )
        msg = email.message_from_bytes(raw)
        result = w.extract_body(msg, 100)
        assert "Plain version" in result
        assert "HTML version" not in result

    def test_truncates_to_limit(self):
        raw = b"From: a@b.com\nSubject: t\nContent-Type: text/plain; charset=utf-8\n\n" + b"x" * 500
        msg = email.message_from_bytes(raw)
        result = w.extract_body(msg, 50)
        assert len(result) == 50


# --------------------------------------------------------------------------- #
# get_msg_datetime
# --------------------------------------------------------------------------- #
class TestGetMsgDatetime:
    def test_parses_valid_date_header(self):
        raw = b"From: a@b.com\nSubject: t\nDate: Thu, 16 Jul 2026 09:00:00 +0900\n\nbody"
        msg = email.message_from_bytes(raw)
        result = w.get_msg_datetime(msg)
        assert result is not None
        assert result.year == 2026 and result.month == 7 and result.day == 16

    def test_missing_date_header_returns_none(self):
        raw = b"From: a@b.com\nSubject: t\n\nbody"
        msg = email.message_from_bytes(raw)
        assert w.get_msg_datetime(msg) is None

    def test_malformed_date_header_returns_none(self):
        raw = b"From: a@b.com\nSubject: t\nDate: not-a-real-date\n\nbody"
        msg = email.message_from_bytes(raw)
        assert w.get_msg_datetime(msg) is None


# --------------------------------------------------------------------------- #
# build_prompt
# --------------------------------------------------------------------------- #
class TestBuildPrompt:
    def test_includes_account_name_and_count(self):
        collected = [("info 계정", [{"date": "07-16 09:00", "from": "x@y.com",
                                     "subject": "계약 갱신 안내", "body": "본문내용"}])]
        prompt = w.build_prompt(collected)
        assert "info 계정" in prompt
        assert "신규 1건" in prompt
        assert "계약 갱신 안내" in prompt

    def test_includes_required_report_sections(self):
        prompt = w.build_prompt([("a", [])])
        assert "오늘 꼭 챙길 것" in prompt
        assert "중요도" in prompt and "분류" in prompt and "필요한 조치" in prompt

    def test_handles_multiple_accounts(self):
        collected = [
            ("info", [{"date": "d", "from": "a", "subject": "s1", "body": "b1"}]),
            ("base", [{"date": "d", "from": "a", "subject": "s2", "body": "b2"}]),
        ]
        prompt = w.build_prompt(collected)
        assert "s1" in prompt and "s2" in prompt


# --------------------------------------------------------------------------- #
# parse_anchor_time / compute_next_due
# --------------------------------------------------------------------------- #
class TestParseAnchorTime:
    def test_parses_valid_time(self):
        assert w.parse_anchor_time("08:00") == (8, 0)
        assert w.parse_anchor_time("23:59") == (23, 59)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            w.parse_anchor_time("8am")

    def test_out_of_range_hour_raises(self):
        with pytest.raises(ValueError):
            w.parse_anchor_time("25:00")

    def test_out_of_range_minute_raises(self):
        with pytest.raises(ValueError):
            w.parse_anchor_time("10:60")


class TestComputeFirstDue:
    """스케줄을 처음 켤 때 딱 한 번만 쓰이는 anchor 기반 계산."""

    def _local(self, y, mo, d, h, mi):
        return w.to_utc(dt.datetime(y, mo, d, h, mi))

    def test_anchor_still_ahead_today_fires_today(self):
        now = self._local(2026, 7, 16, 7, 0)
        local = w.compute_first_due(now, "08:00").astimezone()
        assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 7, 16, 8, 0)

    def test_anchor_already_passed_today_fires_tomorrow(self):
        now = self._local(2026, 7, 16, 9, 0)
        local = w.compute_first_due(now, "08:00").astimezone()
        assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 7, 17, 8, 0)

    def test_exactly_at_anchor_counts_as_passed_fires_tomorrow(self):
        now = self._local(2026, 7, 16, 8, 0)
        local = w.compute_first_due(now, "08:00").astimezone()
        assert (local.year, local.month, local.day) == (2026, 7, 17)

    def test_invalid_anchor_raises(self):
        with pytest.raises(ValueError):
            w.compute_first_due(self._local(2026, 7, 16, 9, 0), "not-a-time")


class TestComputeNextDue:
    """확인/발송한 시각(after) + 간격을 그대로 더하기만 한다 — 특정 분에 스냅하지 않음."""

    def _local(self, y, mo, d, h, mi):
        return w.to_utc(dt.datetime(y, mo, d, h, mi))

    def test_adds_interval_hours_to_the_given_moment(self):
        after = self._local(2026, 7, 16, 12, 10)
        local = w.compute_next_due(after, 1).astimezone()
        assert (local.hour, local.minute) == (13, 10)

    def test_does_not_snap_to_any_fixed_minute(self):
        # 12:37에 확인하고 간격이 2시간이면 14:37이어야지, 다른 분으로 스냅되면 안 된다.
        after = self._local(2026, 7, 16, 12, 37)
        local = w.compute_next_due(after, 2).astimezone()
        assert (local.hour, local.minute) == (14, 37)

    def test_fractional_hours_supported(self):
        after = self._local(2026, 7, 16, 12, 0)
        local = w.compute_next_due(after, 0.5).astimezone()
        assert (local.hour, local.minute) == (12, 30)

    def test_crosses_midnight_correctly(self):
        after = self._local(2026, 7, 16, 23, 30)
        local = w.compute_next_due(after, 1).astimezone()
        assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 7, 17, 0, 30)

    def test_zero_interval_raises(self):
        with pytest.raises(ValueError):
            w.compute_next_due(self._local(2026, 7, 16, 9, 0), 0)

    def test_negative_interval_raises(self):
        with pytest.raises(ValueError):
            w.compute_next_due(self._local(2026, 7, 16, 9, 0), -6)


# --------------------------------------------------------------------------- #
# load_raw_config / normalize_config / validate_config / save_config
# --------------------------------------------------------------------------- #
class TestLoadRawConfig:
    def test_missing_file_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w, "CONFIG_PATH", tmp_path / "nope.yaml")
        assert w.load_raw_config() == {}

    def test_empty_file_returns_empty_dict(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("", encoding="utf-8")
        monkeypatch.setattr(w, "CONFIG_PATH", cfg_path)
        assert w.load_raw_config() == {}

    def test_reads_existing_yaml_as_is(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("recipients:\n  - a@x.com\n", encoding="utf-8")
        monkeypatch.setattr(w, "CONFIG_PATH", cfg_path)
        assert w.load_raw_config() == {"recipients": ["a@x.com"]}


class TestNormalizeConfig:
    def test_fills_all_defaults_on_empty_input(self):
        cfg = w.normalize_config({})
        assert cfg["imap"]["host"] == "imap.worksmobile.com"
        assert cfg["smtp"]["port"] == 587
        assert cfg["gemini"]["model"] == "gemini-flash-latest"
        assert cfg["schedule"]["interval_hours"] == 24
        assert cfg["schedule"]["anchor_time"] == "08:00"
        assert cfg["accounts"] == []
        assert cfg["recipients"] == []
        assert cfg["admin_ui"] == {}

    def test_preserves_provided_values(self):
        cfg = w.normalize_config({"schedule": {"interval_hours": 6, "anchor_time": "09:30"}})
        assert cfg["schedule"]["interval_hours"] == 6
        assert cfg["schedule"]["anchor_time"] == "09:30"

    def test_normalizes_string_recipient_to_list(self):
        cfg = w.normalize_config({"recipients": "solo@x.com"})
        assert cfg["recipients"] == ["solo@x.com"]

    def test_does_not_mutate_input_dict(self):
        original = {"recipients": "solo@x.com"}
        w.normalize_config(original)
        assert original == {"recipients": "solo@x.com"}


class TestValidateConfig:
    def _valid_cfg(self):
        return w.normalize_config({
            "accounts": [{"name": "a", "email": "a@x.com", "password": "pw"}],
            "sender": {"email": "a@x.com", "password": "pw"},
            "recipients": ["me@x.com"],
            "gemini": {"api_key": "KEY"},
        })

    def test_valid_config_has_no_problems(self):
        assert w.validate_config(self._valid_cfg()) == []

    def test_missing_accounts_is_a_problem(self):
        cfg = self._valid_cfg()
        cfg["accounts"] = []
        problems = w.validate_config(cfg)
        assert any("accounts" in p for p in problems)

    def test_missing_sender_email_is_a_problem(self):
        cfg = self._valid_cfg()
        cfg["sender"] = {}
        problems = w.validate_config(cfg)
        assert any("sender" in p for p in problems)

    def test_missing_recipients_is_a_problem(self):
        cfg = self._valid_cfg()
        cfg["recipients"] = []
        problems = w.validate_config(cfg)
        assert any("recipients" in p for p in problems)

    def test_missing_gemini_key_is_a_problem(self):
        cfg = self._valid_cfg()
        cfg["gemini"] = {}
        problems = w.validate_config(cfg)
        assert any("gemini" in p for p in problems)

    def test_bad_anchor_time_is_a_problem(self):
        cfg = self._valid_cfg()
        cfg["schedule"]["anchor_time"] = "nope"
        problems = w.validate_config(cfg)
        assert any("anchor_time" in p for p in problems)

    def test_zero_interval_is_a_problem(self):
        cfg = self._valid_cfg()
        cfg["schedule"]["interval_hours"] = 0
        problems = w.validate_config(cfg)
        assert any("interval_hours" in p for p in problems)

    def test_non_numeric_interval_is_a_problem(self):
        cfg = self._valid_cfg()
        cfg["schedule"]["interval_hours"] = "many"
        problems = w.validate_config(cfg)
        assert any("interval_hours" in p for p in problems)


class TestSaveConfig:
    def test_roundtrip_via_load_raw_config(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        monkeypatch.setattr(w, "CONFIG_PATH", cfg_path)
        cfg = w.normalize_config({
            "accounts": [{"name": "a", "email": "a@x.com", "password": "pw"}],
            "recipients": ["me@x.com"],
        })
        w.save_config(cfg)
        reloaded = w.load_raw_config()
        assert reloaded["accounts"] == cfg["accounts"]
        assert reloaded["recipients"] == ["me@x.com"]
        assert reloaded["schedule"]["anchor_time"] == "08:00"


# --------------------------------------------------------------------------- #
# load_config / load_state / save_state
# --------------------------------------------------------------------------- #
class TestLoadConfig:
    def test_missing_file_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w, "CONFIG_PATH", tmp_path / "nope.yaml")
        with pytest.raises(SystemExit):
            w.load_config()

    def test_missing_required_fields_exits(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("accounts: []\n", encoding="utf-8")
        monkeypatch.setattr(w, "CONFIG_PATH", cfg_path)
        with pytest.raises(SystemExit):
            w.load_config()

    def test_valid_config_fills_defaults(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "accounts:\n"
            "  - name: info\n"
            "    email: info@x.com\n"
            "    password: pw\n"
            "sender:\n"
            "  email: info@x.com\n"
            "  password: pw\n"
            "recipients:\n"
            "  - me@x.com\n"
            "gemini:\n"
            "  api_key: KEY\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(w, "CONFIG_PATH", cfg_path)
        cfg = w.load_config()
        assert cfg["imap"]["host"] == "imap.worksmobile.com"
        assert cfg["imap"]["port"] == 993
        assert cfg["smtp"]["host"] == "smtp.worksmobile.com"
        assert cfg["lookback_hours"] == 24
        assert cfg["gemini"]["model"] == "gemini-flash-latest"
        assert cfg["recipients"] == ["me@x.com"]

    def test_recipients_as_single_string_is_normalized_to_list(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "accounts:\n"
            "  - name: info\n"
            "    email: info@x.com\n"
            "    password: pw\n"
            "sender:\n"
            "  email: info@x.com\n"
            "  password: pw\n"
            "recipients: me@x.com\n"
            "gemini:\n"
            "  api_key: KEY\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(w, "CONFIG_PATH", cfg_path)
        cfg = w.load_config()
        assert cfg["recipients"] == ["me@x.com"]

    def test_multiple_recipients_are_kept_as_list(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "accounts:\n"
            "  - name: info\n"
            "    email: info@x.com\n"
            "    password: pw\n"
            "sender:\n"
            "  email: info@x.com\n"
            "  password: pw\n"
            "recipients:\n"
            "  - a@x.com\n"
            "  - b@x.com\n"
            "gemini:\n"
            "  api_key: KEY\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(w, "CONFIG_PATH", cfg_path)
        cfg = w.load_config()
        assert cfg["recipients"] == ["a@x.com", "b@x.com"]

    def test_empty_recipients_list_exits(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "accounts:\n"
            "  - name: info\n"
            "    email: info@x.com\n"
            "    password: pw\n"
            "sender:\n"
            "  email: info@x.com\n"
            "  password: pw\n"
            "recipients: []\n"
            "gemini:\n"
            "  api_key: KEY\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(w, "CONFIG_PATH", cfg_path)
        with pytest.raises(SystemExit):
            w.load_config()


class TestState:
    def test_load_state_missing_file_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w, "STATE_PATH", tmp_path / "state.json")
        assert w.load_state() == {}

    def test_save_then_load_roundtrip(self, tmp_path, monkeypatch):
        state_path = tmp_path / "state.json"
        monkeypatch.setattr(w, "STATE_PATH", state_path)
        w.save_state({"last_run": "2026-07-16T00:00:00+00:00"})
        assert w.load_state() == {"last_run": "2026-07-16T00:00:00+00:00"}

    def test_corrupted_state_file_returns_empty_dict(self, tmp_path, monkeypatch):
        state_path = tmp_path / "state.json"
        state_path.write_text("not valid json", encoding="utf-8")
        monkeypatch.setattr(w, "STATE_PATH", state_path)
        assert w.load_state() == {}


# --------------------------------------------------------------------------- #
# summarize_with_gemini (네트워크는 mock 처리)
# --------------------------------------------------------------------------- #
class TestCliArgs:
    """--date 와 --since-hours 는 동시에 지정할 수 없어야 한다(둘 다 기간 지정 옵션)."""

    def _build_parser(self):
        # main() 내부의 argparse 정의와 동일한 구조를 재현해 파서만 단위 검증한다.
        ap = argparse.ArgumentParser()
        ap.add_argument("--dry-run", action="store_true")
        group = ap.add_mutually_exclusive_group()
        group.add_argument("--since-hours", type=float, default=None)
        group.add_argument("--date", type=str, default=None)
        ap.add_argument("--test", action="store_true")
        return ap

    def test_since_hours_and_date_together_is_rejected(self):
        ap = self._build_parser()
        with pytest.raises(SystemExit):
            ap.parse_args(["--since-hours", "24", "--date", "2026-07-16"])

    def test_date_alone_is_accepted(self):
        ap = self._build_parser()
        args = ap.parse_args(["--date", "2026-07-16"])
        assert args.date == "2026-07-16"
        assert args.since_hours is None


class TestSummarizeWithGemini:
    def test_extracts_text_from_successful_response(self, monkeypatch):
        class FakeResp:
            status_code = 200
            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": "요약 결과"}]}}]}

        monkeypatch.setattr(w.requests, "post", lambda *a, **k: FakeResp())
        cfg = {"gemini": {"api_key": "k", "model": "gemini-2.5-flash"}}
        assert w.summarize_with_gemini("prompt", cfg) == "요약 결과"

    def test_non_200_status_raises(self, monkeypatch):
        class FakeResp:
            status_code = 400
            text = "bad request"

        monkeypatch.setattr(w.requests, "post", lambda *a, **k: FakeResp())
        cfg = {"gemini": {"api_key": "k", "model": "gemini-2.5-flash"}}
        with pytest.raises(RuntimeError, match="Gemini API 오류"):
            w.summarize_with_gemini("prompt", cfg)

    def test_unexpected_response_shape_raises(self, monkeypatch):
        class FakeResp:
            status_code = 200
            def json(self):
                return {"unexpected": "shape"}

        monkeypatch.setattr(w.requests, "post", lambda *a, **k: FakeResp())
        cfg = {"gemini": {"api_key": "k", "model": "gemini-2.5-flash"}}
        with pytest.raises(RuntimeError, match="파싱 실패"):
            w.summarize_with_gemini("prompt", cfg)
