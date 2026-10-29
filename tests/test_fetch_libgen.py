"""Tests for the Libgen fetcher; HTTP is stubbed at the _http seam."""

import pytest

from doifetch.sources import _http, libgen
from doifetch.sources.contract import Request

VALID_PDF = b"%PDF-1.6\n" + b"0" * 2000
MD5 = "a" * 32

SEARCH_HTML = f'<a href="/ads.php?md5={MD5}">book</a>'.encode()
ADS_HTML = f'<a href="get.php?md5={MD5}&key=K">GET</a>'.encode()


def _resp(content=b"", status=200, headers=None):
    return _http.Response(status=status, url="", headers=headers or {}, content=content)


def _stub(monkeypatch, download):
    def fake_get(url, **kwargs):
        if "get.php" in url:
            return download
        if "ads.php" in url:
            return _resp(ADS_HTML)
        return _resp(SEARCH_HTML)

    monkeypatch.setattr(libgen._http, "get", fake_get)


def _request(tmp_path):
    return Request("isbn", "9780262033848", str(tmp_path / "Book.pdf"))


def test_contract_names():
    assert libgen.NAME == "libgen"
    assert libgen.ACCEPTS == frozenset({"isbn"})


def test_success_writes_req_path(monkeypatch, tmp_path):
    _stub(monkeypatch, _resp(VALID_PDF))
    req = _request(tmp_path)
    result = libgen.fetch(req)
    assert (result.status, result.path) == ("success", req.path)
    assert (tmp_path / "Book.pdf").read_bytes() == VALID_PDF


def test_existing_valid_pdf_is_skipped(monkeypatch, tmp_path):
    _stub(monkeypatch, _resp(b"never used"))
    (tmp_path / "Book.pdf").write_bytes(VALID_PDF)
    assert libgen.fetch(_request(tmp_path)).status == "skipped"


@pytest.mark.parametrize(
    "download, message",
    [
        (_resp(b"PK" + b"0" * 2000), "not a PDF"),
        (_resp(b"<html>" + b"0" * 2000), "error page"),
        (_resp(b"", status=503), "HTTP 503"),
    ],
)
def test_non_pdf_download_fails_without_leftover(
    monkeypatch, tmp_path, download, message
):
    _stub(monkeypatch, download)
    result = libgen.fetch(_request(tmp_path))
    assert result.status == "failed"
    assert message in result.error
    assert list(tmp_path.iterdir()) == []


def test_transport_error_becomes_failure(monkeypatch, tmp_path):
    def boom(url, **kwargs):
        raise _http.HttpError("down")

    monkeypatch.setattr(libgen._http, "get", boom)
    result = libgen.fetch(_request(tmp_path))
    assert result.status == "failed"
    assert "not found on Libgen" in result.error
