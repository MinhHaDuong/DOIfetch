"""Tests for the ISTEX licensed-archive fetcher."""

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


def test_missing_token_fails(monkeypatch):
    monkeypatch.delenv("ISTEX_ACCESSTOKEN", raising=False)
    result = fetch_istex.fetch_pdf("10.1000/x", "Some Paper", output_dir="/tmp")
    assert result["status"] == "failed"
    assert "ISTEX_ACCESSTOKEN" in result["error"]


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
