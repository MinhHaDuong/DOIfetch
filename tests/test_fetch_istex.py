"""Tests for the ISTEX licensed-archive fetcher."""

import json
import os

import pytest

from doifetch.sources import istex
from doifetch.sources._http import Response
from doifetch.sources.contract import Request

VALID_PDF = b"%PDF-1.6\n" + b"0" * 2000


def _FakeResp(status_code=200, json_data=None, content=b""):
    if json_data is not None:
        content = json.dumps(json_data).encode()
    return Response(status=status_code, url="", headers={}, content=content)


def _dispatch(search_resp, fulltext_resp):
    """Build an _http.get replacement that routes by URL."""

    def fake_get(url, **kwargs):
        if "/fulltext/" in url:
            return fulltext_resp
        return search_resp

    return fake_get


def _fetch(output_dir, doi="10.1000/x", name="Some Paper.pdf"):
    return istex.fetch(Request("doi", doi, os.path.join(output_dir, name)))


def test_missing_token_fails(monkeypatch, tmp_path):
    monkeypatch.delenv("ISTEX_ACCESSTOKEN", raising=False)
    monkeypatch.setattr(istex, "TOKEN_FILE", str(tmp_path / "absent.env"))
    result = _fetch("/tmp")
    assert result.status == "failed"
    assert "ISTEX_ACCESSTOKEN" in result.error


def test_token_read_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("ISTEX_ACCESSTOKEN", raising=False)
    key_file = tmp_path / "istex.env"
    key_file.write_text("ISTEX_ACCESSTOKEN=filetoken\n")
    monkeypatch.setattr(istex, "TOKEN_FILE", str(key_file))
    monkeypatch.setattr(
        istex._http,
        "get",
        _dispatch(
            _FakeResp(json_data={"hits": [{"id": "ABC123"}]}),
            _FakeResp(content=VALID_PDF),
        ),
    )
    result = _fetch(str(tmp_path))
    assert result.status == "success"


def test_doi_not_in_istex_fails(monkeypatch):
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    monkeypatch.setattr(
        istex._http,
        "get",
        _dispatch(_FakeResp(json_data={"hits": []}), _FakeResp()),
    )
    result = _fetch("/tmp")
    assert result.status == "failed"
    assert "ISTEX" in result.error


def test_success_writes_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    monkeypatch.setattr(
        istex._http,
        "get",
        _dispatch(
            _FakeResp(json_data={"hits": [{"id": "ABC123"}]}),
            _FakeResp(content=VALID_PDF),
        ),
    )
    result = _fetch(str(tmp_path))
    assert result.status == "success"
    written = tmp_path / "Some Paper.pdf"
    assert result.path == str(written)
    assert written.exists()
    assert written.read_bytes().startswith(b"%PDF-")


def test_fulltext_http_error_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    monkeypatch.setattr(
        istex._http,
        "get",
        _dispatch(
            _FakeResp(json_data={"hits": [{"id": "ABC123"}]}),
            _FakeResp(status_code=401),
        ),
    )
    result = _fetch(str(tmp_path))
    assert result.status == "failed"
    assert "401" in result.error


def test_skips_existing_valid_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    from doifetch.pdf_utils import clean_filename

    existing = tmp_path / f"{clean_filename('Some Paper')}.pdf"
    existing.write_bytes(VALID_PDF)
    result = _fetch(str(tmp_path))
    assert result.status == "skipped"


# --- login flow -------------------------------------------------------------


class _Browser:
    """Stub for the browser launcher; records URLs, never opens anything."""

    def __init__(self):
        self.opened = []

    def __call__(self, url):
        self.opened.append(url)


@pytest.fixture(autouse=True)
def _reset_login_state(monkeypatch):
    monkeypatch.setattr(istex, "_login_attempted", False)


def _token_sequence(monkeypatch, tokens):
    seq = iter(tokens)
    monkeypatch.setattr(istex, "_get_token", lambda: next(seq))


def _auth_then_ok(statuses):
    """_http.get stub: search ok, fulltext answers successive statuses."""
    answers = iter(statuses)

    def fake_get(url, **kwargs):
        if "/fulltext/" in url:
            code = next(answers)
            return _FakeResp(
                status_code=code, content=VALID_PDF if code == 200 else b""
            )
        return _FakeResp(json_data={"hits": [{"id": "ABC123"}]})

    return fake_get


def test_auth_needed_interactive_opens_firefox_and_retries(monkeypatch, tmp_path):
    browser = _Browser()
    monkeypatch.setattr(istex, "_is_interactive", lambda: True)
    monkeypatch.setattr(istex, "_open_login_page", browser)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    _token_sequence(monkeypatch, ["old", "old", "new"])
    monkeypatch.setattr(istex._http, "get", _auth_then_ok([401, 200]))
    result = _fetch(str(tmp_path))
    assert result.status == "success"
    assert browser.opened == [istex.LOGIN_URL]


def test_auth_needed_retries_only_once(monkeypatch, tmp_path):
    browser = _Browser()
    monkeypatch.setattr(istex, "_is_interactive", lambda: True)
    monkeypatch.setattr(istex, "_open_login_page", browser)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    _token_sequence(monkeypatch, ["old", "old", "new"])
    monkeypatch.setattr(istex._http, "get", _auth_then_ok([401, 401]))
    result = _fetch(str(tmp_path))
    assert result.status == "failed"
    assert "401" in result.error
    assert len(browser.opened) == 1


def test_auth_needed_non_interactive_prints_one_line(monkeypatch, tmp_path, capsys):
    browser = _Browser()
    monkeypatch.setattr(istex, "_is_interactive", lambda: False)
    monkeypatch.setattr(istex, "_open_login_page", browser)
    _token_sequence(monkeypatch, ["old", "old"])
    monkeypatch.setattr(istex._http, "get", _auth_then_ok([401]))
    result = _fetch(str(tmp_path))
    assert result.status == "failed"
    assert browser.opened == []
    out = capsys.readouterr().out
    assert out == f"ISTEX login needed: {istex.LOGIN_URL}\n"


def test_missing_token_interactive_logs_in(monkeypatch, tmp_path):
    browser = _Browser()
    monkeypatch.setattr(istex, "_is_interactive", lambda: True)
    monkeypatch.setattr(istex, "_open_login_page", browser)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    _token_sequence(monkeypatch, ["", "", "fresh"])
    monkeypatch.setattr(istex._http, "get", _auth_then_ok([200]))
    result = _fetch(str(tmp_path))
    assert result.status == "success"
    assert browser.opened == [istex.LOGIN_URL]


def test_missing_browser_degrades_to_one_line(monkeypatch, tmp_path, capsys):
    def no_firefox(url):
        raise FileNotFoundError("firefox")

    monkeypatch.setattr(istex, "_is_interactive", lambda: True)
    monkeypatch.setattr(istex, "_open_login_page", no_firefox)
    _token_sequence(monkeypatch, ["", ""])
    result = _fetch(str(tmp_path))
    assert result.status == "failed"
    out = capsys.readouterr().out
    assert out == f"ISTEX login needed: {istex.LOGIN_URL}\n"


def test_is_interactive_needs_tty_and_display(monkeypatch):
    monkeypatch.setattr(istex.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(istex.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert istex._is_interactive() is False
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert istex._is_interactive() is True
