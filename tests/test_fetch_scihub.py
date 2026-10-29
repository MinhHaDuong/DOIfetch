"""Tests for the Sci-Hub / SciDB fetcher."""

from doifetch.sources import _http, scihub
from doifetch.sources.contract import Request

VALID_PDF = b"%PDF-1.6\n" + b"0" * 2000


def _resp(content=b"", status=200):
    return _http.Response(status=status, url="", headers={}, content=content)


def test_build_query_urls_tries_scihub_then_scidb():
    urls = scihub.build_query_urls("10.1000/example", "Some Paper")
    # Classic Sci-Hub pages come first (frozen corpus, freely scrapable).
    assert urls[0] == "https://sci-hub.fr/10.1000/example"
    # SciDB (Anna's Archive) uses the /scidb/<doi> path and comes after.
    scidb = [u for u in urls if "annas-archive" in u]
    assert scidb, "expected at least one SciDB candidate"
    assert all(u.endswith("scidb/10.1000/example") for u in scidb)
    # Sci-Hub candidates precede SciDB candidates.
    assert urls.index("https://sci-hub.fr/10.1000/example") < urls.index(scidb[0])


def test_build_query_urls_title_search_when_no_doi():
    urls = scihub.build_query_urls("", "Cognitive Constraints")
    assert urls
    assert all("?s=" in u for u in urls)
    # Title search is a Sci-Hub feature only; SciDB has no search endpoint here.
    assert not any("scidb/" in u for u in urls)


def test_extract_pdf_url_from_iframe():
    html = b'<html><body><iframe src="https://sci-hub.se/downloads/x.pdf"></iframe></body></html>'
    assert scihub.extract_pdf_url(html) == "https://sci-hub.se/downloads/x.pdf"


def test_extract_pdf_url_from_embed():
    html = b'<html><embed src="https://annas-archive.se/scidb/file.pdf"></html>'
    assert scihub.extract_pdf_url(html) == "https://annas-archive.se/scidb/file.pdf"


def test_extract_pdf_url_handles_protocol_relative():
    html = b'<iframe src="//sci-hub.se/downloads/y.pdf"></iframe>'
    assert scihub.extract_pdf_url(html) == "https://sci-hub.se/downloads/y.pdf"


def test_extract_pdf_url_none_when_no_embed():
    assert scihub.extract_pdf_url(b"<html><body>no pdf here</body></html>") is None


def test_extract_pdf_url_none_when_src_not_http():
    assert scihub.extract_pdf_url(b'<iframe src="about:blank"></iframe>') is None


def _dispatch(viewer_html, pdf_bytes):
    """_http.get replacement: viewer pages return HTML, the PDF URL returns bytes."""

    def fake_get(url, **kwargs):
        if url.endswith(".pdf"):
            return _resp(pdf_bytes)
        return _resp(viewer_html)

    return fake_get


def test_fetch_pdf_success_via_embedded_viewer(monkeypatch, tmp_path):
    monkeypatch.setattr(scihub.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        scihub._http,
        "get",
        _dispatch(
            b'<iframe src="https://sci-hub.se/downloads/paper.pdf"></iframe>',
            VALID_PDF,
        ),
    )
    path = tmp_path / "Some Paper.pdf"
    result = scihub.fetch(Request("doi", "10.1000/example", str(path)))
    assert result.status == "success"
    assert result.path == str(path)
    assert path.read_bytes() == VALID_PDF


def test_fetch_pdf_failed_when_no_link(monkeypatch, tmp_path):
    monkeypatch.setattr(scihub.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        scihub._http,
        "get",
        _dispatch(b"<html><body>not available</body></html>", VALID_PDF),
    )
    path = tmp_path / "Some Paper.pdf"
    result = scihub.fetch(Request("doi", "10.1000/example", str(path)))
    assert result.status == "failed"
    assert "PDF link not found" in result.error
    assert not path.exists()
