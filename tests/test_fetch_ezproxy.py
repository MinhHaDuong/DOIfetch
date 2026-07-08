"""Tests for the EZproxy institutional fetcher."""

import fetch_ezproxy

VALID_PDF = b"%PDF-1.6\n" + b"0" * 2000


def test_host_rewrite_reversible():
    # dots -> hyphens, literal hyphens doubled (EZproxy HttpsHyphens)
    assert fetch_ezproxy.ezproxy_host(
        "www.sciencedirect.com", "p.edu"
    ) == "www-sciencedirect-com.p.edu"
    assert fetch_ezproxy.ezproxy_host(
        "link.springer-online.com", "p.edu"
    ) == "link-springer--online-com.p.edu"


def test_host_rewrite_simple():
    assert fetch_ezproxy.ezproxy_host(
        "www.tandfonline.com", "p.edu", hyphens="simple"
    ) == "www-tandfonline-com.p.edu"


def test_url_rewrite_preserves_path_and_query():
    out = fetch_ezproxy.ezproxy_url(
        "https://www.nature.com/articles/s41558-021-00990-2.pdf?x=1", "p.edu"
    )
    assert out == "https://www-nature-com.p.edu/articles/s41558-021-00990-2.pdf?x=1"


def test_missing_base_fails(monkeypatch):
    monkeypatch.delenv("EZPROXY_BASE", raising=False)
    monkeypatch.setenv("EZPROXY_COOKIES", "/tmp/cookies.txt")
    result = fetch_ezproxy.fetch_pdf("10.1000/x", "Some Paper", output_dir="/tmp")
    assert result["status"] == "failed"
    assert "EZPROXY_BASE" in result["error"]


def test_missing_cookies_fails(monkeypatch):
    monkeypatch.setenv("EZPROXY_BASE", "p.edu")
    monkeypatch.setenv("EZPROXY_COOKIES", "/nonexistent/cookies.txt")
    result = fetch_ezproxy.fetch_pdf("10.1000/x", "Some Paper", output_dir="/tmp")
    assert result["status"] == "failed"
    assert "EZPROXY_COOKIES" in result["error"]


def test_success_writes_pdf(monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("EZPROXY_BASE", "p.edu")
    monkeypatch.setenv("EZPROXY_COOKIES", str(cookies))

    class _Resp:
        def __init__(self, url, content, ctype="application/pdf", status=200):
            self.url = url
            self.content = content
            self.headers = {"Content-Type": ctype}
            self.status_code = status
            self.text = ""

    class _Session:
        headers = {}
        cookies = {}

        def get(self, url, **kwargs):
            if "doi.org" in url:
                return _Resp("https://www.nature.com/articles/x", b"", "text/html")
            return _Resp(url, VALID_PDF)

    monkeypatch.setattr(fetch_ezproxy.requests, "Session", lambda: _Session())
    monkeypatch.setattr(fetch_ezproxy, "_load_cookies", lambda p: {})
    result = fetch_ezproxy.fetch_pdf("10.1000/x", "Some Paper", output_dir=str(tmp_path))
    assert result["status"] == "success"
    assert (tmp_path / result["file_name"]).read_bytes().startswith(b"%PDF-")
