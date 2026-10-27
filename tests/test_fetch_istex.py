"""Tests for the ISTEX licensed-archive fetcher."""

import pytest

import fetch_istex

VALID_PDF = b"%PDF-1.6\n" + b"0" * 2000


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = content

    def json(self):
        return self._json


def _dispatch(search_resp, fulltext_resp):
    """Build a requests.get replacement that routes by URL."""

    def fake_get(url, **kwargs):
        if "/fulltext/" in url:
            return fulltext_resp
        return search_resp

    return fake_get


def test_missing_token_fails(monkeypatch, tmp_path):
    monkeypatch.delenv("ISTEX_ACCESSTOKEN", raising=False)
    monkeypatch.setattr(fetch_istex, "TOKEN_FILE", str(tmp_path / "absent.env"))
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir="/tmp")
    assert result["status"] == "failed"
    assert "ISTEX_ACCESSTOKEN" in result["error"]


def test_token_read_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("ISTEX_ACCESSTOKEN", raising=False)
    key_file = tmp_path / "istex.env"
    key_file.write_text("ISTEX_ACCESSTOKEN=filetoken\n")
    monkeypatch.setattr(fetch_istex, "TOKEN_FILE", str(key_file))
    monkeypatch.setattr(
        fetch_istex.requests,
        "get",
        _dispatch(
            _FakeResp(json_data={"hits": [{"id": "ABC123"}]}),
            _FakeResp(content=VALID_PDF),
        ),
    )
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "success"


def test_doi_not_in_istex_fails(monkeypatch):
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    monkeypatch.setattr(
        fetch_istex.requests,
        "get",
        _dispatch(_FakeResp(json_data={"hits": []}), _FakeResp()),
    )
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir="/tmp")
    assert result["status"] == "failed"
    assert "ISTEX" in result["error"]


def test_success_writes_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    monkeypatch.setattr(
        fetch_istex.requests,
        "get",
        _dispatch(
            _FakeResp(json_data={"hits": [{"id": "ABC123"}]}),
            _FakeResp(content=VALID_PDF),
        ),
    )
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "success"
    written = tmp_path / result["file_name"]
    assert written.exists()
    assert written.read_bytes().startswith(b"%PDF-")


def test_fulltext_http_error_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    monkeypatch.setattr(
        fetch_istex.requests,
        "get",
        _dispatch(
            _FakeResp(json_data={"hits": [{"id": "ABC123"}]}),
            _FakeResp(status_code=401),
        ),
    )
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "failed"
    assert "401" in result["error"]


def test_skips_existing_valid_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    from pdf_utils import clean_filename

    existing = tmp_path / f"{clean_filename('Some Paper')}.pdf"
    existing.write_bytes(VALID_PDF)
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "skipped"


# --- login flow -------------------------------------------------------------


class _Browser:
    """Stub for the browser launcher; records URLs, never opens anything."""

    def __init__(self):
        self.opened = []

    def __call__(self, url):
        self.opened.append(url)


@pytest.fixture(autouse=True)
def _reset_login_state(monkeypatch):
    monkeypatch.setattr(fetch_istex, "_login_attempted", False)


def _token_sequence(monkeypatch, tokens):
    seq = iter(tokens)
    monkeypatch.setattr(fetch_istex, "_get_token", lambda: next(seq))


def _auth_then_ok(statuses):
    """requests.get stub: search ok, fulltext answers successive statuses."""
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
    monkeypatch.setattr(fetch_istex, "_is_interactive", lambda: True)
    monkeypatch.setattr(fetch_istex, "_open_login_page", browser)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    _token_sequence(monkeypatch, ["old", "old", "new"])
    monkeypatch.setattr(fetch_istex.requests, "get", _auth_then_ok([401, 200]))
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "success"
    assert browser.opened == [fetch_istex.LOGIN_URL]


def test_auth_needed_retries_only_once(monkeypatch, tmp_path):
    browser = _Browser()
    monkeypatch.setattr(fetch_istex, "_is_interactive", lambda: True)
    monkeypatch.setattr(fetch_istex, "_open_login_page", browser)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    _token_sequence(monkeypatch, ["old", "old", "new"])
    monkeypatch.setattr(fetch_istex.requests, "get", _auth_then_ok([401, 401]))
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "failed"
    assert "401" in result["error"]
    assert len(browser.opened) == 1


def test_auth_needed_non_interactive_prints_one_line(monkeypatch, tmp_path, capsys):
    browser = _Browser()
    monkeypatch.setattr(fetch_istex, "_is_interactive", lambda: False)
    monkeypatch.setattr(fetch_istex, "_open_login_page", browser)
    _token_sequence(monkeypatch, ["old", "old"])
    monkeypatch.setattr(fetch_istex.requests, "get", _auth_then_ok([401]))
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "failed"
    assert browser.opened == []
    out = capsys.readouterr().out
    assert out == f"ISTEX login needed: {fetch_istex.LOGIN_URL}\n"


def test_missing_token_interactive_logs_in(monkeypatch, tmp_path):
    browser = _Browser()
    monkeypatch.setattr(fetch_istex, "_is_interactive", lambda: True)
    monkeypatch.setattr(fetch_istex, "_open_login_page", browser)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    _token_sequence(monkeypatch, ["", "", "fresh"])
    monkeypatch.setattr(fetch_istex.requests, "get", _auth_then_ok([200]))
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "success"
    assert browser.opened == [fetch_istex.LOGIN_URL]


def test_missing_browser_degrades_to_one_line(monkeypatch, tmp_path, capsys):
    def no_firefox(url):
        raise FileNotFoundError("firefox")

    monkeypatch.setattr(fetch_istex, "_is_interactive", lambda: True)
    monkeypatch.setattr(fetch_istex, "_open_login_page", no_firefox)
    _token_sequence(monkeypatch, ["", ""])
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "failed"
    out = capsys.readouterr().out
    assert out == f"ISTEX login needed: {fetch_istex.LOGIN_URL}\n"


def test_is_interactive_needs_tty_and_display(monkeypatch):
    monkeypatch.setattr(fetch_istex.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(fetch_istex.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert fetch_istex._is_interactive() is False
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert fetch_istex._is_interactive() is True
