"""Tests for the EZproxy institutional fetcher."""

import http.cookiejar
import os

from doifetch.sources import _http, ezproxy
from doifetch.sources.contract import Request

VALID_PDF = b"%PDF-1.6\n" + b"0" * 2000


def _fetch(output_dir):
    path = os.path.join(output_dir, "Some Paper.pdf")
    return ezproxy.fetch(Request("doi", "10.1000/x", path))


def test_host_rewrite_reversible():
    # dots -> hyphens, literal hyphens doubled (EZproxy HttpsHyphens)
    assert (
        ezproxy.ezproxy_host("www.sciencedirect.com", "p.edu")
        == "www-sciencedirect-com.p.edu"
    )
    assert (
        ezproxy.ezproxy_host("link.springer-online.com", "p.edu")
        == "link-springer--online-com.p.edu"
    )


def test_host_rewrite_simple():
    assert (
        ezproxy.ezproxy_host("www.tandfonline.com", "p.edu", hyphens="simple")
        == "www-tandfonline-com.p.edu"
    )


def test_url_rewrite_preserves_path_and_query():
    out = ezproxy.ezproxy_url(
        "https://www.nature.com/articles/s41558-021-00990-2.pdf?x=1", "p.edu"
    )
    assert out == "https://www-nature-com.p.edu/articles/s41558-021-00990-2.pdf?x=1"


def test_missing_base_fails(monkeypatch):
    monkeypatch.delenv("EZPROXY_BASE", raising=False)
    monkeypatch.setenv("EZPROXY_COOKIES", "/tmp/cookies.txt")
    result = _fetch("/tmp")
    assert result.status == "failed"
    assert "EZPROXY_BASE" in result.error


def test_missing_cookies_fails(monkeypatch):
    monkeypatch.setenv("EZPROXY_BASE", "p.edu")
    monkeypatch.setenv("EZPROXY_COOKIES", "/nonexistent/cookies.txt")
    result = _fetch("/tmp")
    assert result.status == "failed"
    assert "EZPROXY_COOKIES" in result.error


def test_success_writes_pdf(monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("EZPROXY_BASE", "p.edu")
    monkeypatch.setenv("EZPROXY_COOKIES", str(cookies))

    def _resp(url, content, ctype="application/pdf"):
        return _http.Response(
            status=200, url=url, headers={"content-type": ctype}, content=content
        )

    seen = []

    class _Session:
        def __init__(self, headers=None):
            self.cookies = http.cookiejar.CookieJar()

        def get(self, url, **kwargs):
            seen.append(url)
            if "doi.org" in url:
                return _resp("https://www.nature.com/articles/x", b"", "text/html")
            return _resp(url, VALID_PDF)

    monkeypatch.setattr(ezproxy._http, "Session", _Session)
    result = _fetch(str(tmp_path))
    assert result.status == "success"
    assert seen[-1] == "https://www-nature-com.p.edu/articles/x"
    assert open(result.path, "rb").read().startswith(b"%PDF-")
    assert sorted(os.listdir(tmp_path)) == ["Some Paper.pdf", "cookies.txt"]


def test_cookies_txt_is_loaded_into_the_session(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(
        "# Netscape HTTP Cookie File\n.p.edu\tTRUE\t/\tFALSE\t0\tezproxy\ttok\n"
    )
    assert [c.name for c in ezproxy._load_cookies(str(cookies))] == ["ezproxy"]
