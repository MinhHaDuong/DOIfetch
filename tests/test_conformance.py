"""Contract conformance of every registered source, through one fake transport.

Each source is driven by the same scenarios and must, whatever the transport
does: never raise, leave no stray or partial file, accept only a real PDF, and
report ``skipped`` without a request when a valid file is already there.
Per-source parsing lives in the other test files; this suite pins the contract.
"""

import http.cookiejar
import json
import os

import pytest

from doifetch.sources import (
    _http,
    _openalex,
    crossref,
    ezproxy,
    hal,
    isbn,
    istex,
    libgen,
    openalex,
    scihub,
    unpaywall,
    url,
)
from doifetch.sources.contract import Request

PDF = b"%PDF-1.4\n" + b"x" * 2000
PDF_URL = "https://files.example.org/p.pdf"
HTML = b"<html><body>" + b"nothing here " * 200 + b"</body></html>"
SHORT_PDF = b"%PDF-1.4 tiny"
FILE = "Stern 2004 - Rise and Fall.pdf"


def _resp(status=200, body=b"", ctype="application/octet-stream"):
    return _http.Response(
        status=status, url="", headers={"content-type": ctype}, content=body
    )


def _json(obj):
    return _resp(200, json.dumps(obj).encode(), "application/json")


# --- per-source discovery: (module, kind, identifier, page(url) -> Response|None)
# ``page`` answers the metadata/landing requests; None means "this is the download".


def _crossref():
    link = {"URL": PDF_URL, "content-type": "application/pdf", "content-version": "vor"}
    return lambda u: _json({"message": {"link": [link]}}) if "crossref" in u else None


def _unpaywall():
    data = {"best_oa_location": {"url_for_pdf": PDF_URL}}
    return lambda u: _json(data) if "unpaywall" in u else None


def _openalex_page():
    data = {"locations": [{"pdf_url": None}, {"pdf_url": PDF_URL}]}
    return lambda u: _json(data) if "openalex" in u else None


def _hal():
    data = {"response": {"docs": [{"fileMain_s": PDF_URL}]}}
    return lambda u: _json(data) if "archives-ouvertes" in u else None


def _isbn():
    """Crossref ISBN lookup answers a book DOI; the DOI then resolves as crossref's."""
    books = {"message": {"items": [{"DOI": "10.1/x", "type": "monograph"}]}}
    link = _crossref()
    return lambda u: _json(books) if "filter=isbn" in u else link(u)


def _istex():
    hits = {"hits": [{"id": "ABC"}]}
    return lambda u: None if "/fulltext/" in u else _json(hits)


def _ezproxy():
    return lambda u: _resp(200, b"", "text/html") if "doi.org" in u else None


def _scihub():
    page = b'<iframe src="https://sci-hub.example/p.pdf"></iframe>'
    return lambda u: None if u.endswith(".pdf") else _resp(200, page, "text/html")


def _libgen():
    md5 = "a" * 32
    search = f'<a href="/ads.php?md5={md5}">b</a>'.encode()
    ads = f'<a href="get.php?md5={md5}&key=K">GET</a>'.encode()

    def page(u):
        if "get.php" in u:
            return None
        return _resp(200, ads if "ads.php" in u else search, "text/html")

    return page


SOURCES = {
    "crossref": (crossref, "doi", "10.1/x", _crossref),
    "unpaywall": (unpaywall, "doi", "10.1/x", _unpaywall),
    "openalex": (openalex, "doi", "10.1/x", _openalex_page),
    "hal": (hal, "doi", "10.1/x", _hal),
    "istex": (istex, "doi", "10.1/x", _istex),
    "ezproxy": (ezproxy, "doi", "10.1/x", _ezproxy),
    "scihub": (scihub, "doi", "10.1/x", _scihub),
    "isbn": (isbn, "isbn", "9780262033848", _isbn),
    "libgen": (libgen, "isbn", "9780262033848", _libgen),
    "url": (url, "url", PDF_URL, lambda: lambda u: None),
}


def _boom(exc):
    def raiser():
        raise exc

    return raiser


# Scenario -> (what the download request does, what every request does).
# A callable answers or raises; None defers to the source's own page.
DOWNLOADS = {
    "pdf": lambda: _resp(200, PDF, "application/pdf"),
    "html": lambda: _resp(200, HTML, "text/html"),
    "short_pdf": lambda: _resp(200, SHORT_PDF, "application/pdf"),
    "http_500": lambda: _resp(500),
    "timeout": _boom(_http.HttpError("timed out")),
    "bug": _boom(RuntimeError("unexpected")),
}
EVERYWHERE = {
    "all_timeout": _boom(_http.HttpError("timed out")),
    "all_500": lambda: _resp(500),
    "all_404": lambda: _resp(404),
    "all_html": lambda: _resp(200, HTML, "text/html"),
    "all_bug": _boom(RuntimeError("unexpected")),
}


class Transport:
    """The one fake: serves ``page`` for discovery, ``download`` for the file."""

    def __init__(self, page, download, everywhere=None):
        self.page, self.download, self.everywhere = page, download, everywhere
        self.calls = []

    def get(self, target, **_kwargs):
        self.calls.append(target)
        if self.everywhere is not None:
            return self.everywhere()
        return self.page(target) or self.download()


@pytest.fixture()
def run(monkeypatch, tmp_path):
    """run(name, scenario) -> (result, request, transport) with the fake wired in."""
    key_file = tmp_path / "no-token.env"
    monkeypatch.setattr(istex, "TOKEN_FILE", str(key_file))
    monkeypatch.setenv("ISTEX_ACCESSTOKEN", "tok")
    monkeypatch.setattr(_openalex, "KEY_FILE", str(key_file))
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("EZPROXY_BASE", "p.edu")
    monkeypatch.setenv("EZPROXY_COOKIES", str(cookies))
    monkeypatch.setattr(scihub.time, "sleep", lambda *_: None)
    out = tmp_path / "out"
    out.mkdir()

    def go(name, scenario, prepare=None):
        module, kind, ident, make_page = SOURCES[name]
        if scenario in EVERYWHERE:
            transport = Transport(make_page(), None, EVERYWHERE[scenario])
        else:
            transport = Transport(make_page(), DOWNLOADS[scenario])

        class Session:
            def __init__(self, headers=None, **_kwargs):
                self.cookies = http.cookiejar.CookieJar()

            def get(self, target, **kwargs):
                return transport.get(target, **kwargs)

        monkeypatch.setattr(_http, "get", transport.get)
        monkeypatch.setattr(_http, "Session", Session)
        req = Request(kind, ident, str(out / FILE))
        if prepare:
            prepare(req.path)
        return module.fetch(req), req, transport

    go.out = out
    return go


def _listing(run):
    return sorted(os.listdir(run.out))


ALL = sorted(SOURCES)


@pytest.mark.parametrize("name", ALL)
def test_registered_names_match(name):
    assert SOURCES[name][0].NAME == name


@pytest.mark.parametrize("name", ALL)
def test_valid_pdf_is_the_only_success(run, name):
    result, req, _ = run(name, "pdf")
    assert (result.status, result.source, result.path) == ("success", name, req.path)
    assert _listing(run) == [FILE]
    assert open(req.path, "rb").read() == PDF


@pytest.mark.parametrize("scenario", ["html", "short_pdf"])
@pytest.mark.parametrize("name", ALL)
def test_non_pdf_body_is_rejected_without_leftover(run, name, scenario):
    result, _, _ = run(name, scenario)
    assert result.status == "failed" and result.source == name and result.error
    assert _listing(run) == []


@pytest.mark.parametrize("scenario", ["http_500", "timeout", "bug"])
@pytest.mark.parametrize("name", ALL)
def test_download_failure_never_raises_and_leaves_nothing(run, name, scenario):
    result, _, _ = run(name, scenario)
    assert result.status == "failed" and result.source == name and result.error
    assert _listing(run) == []


@pytest.mark.parametrize("scenario", sorted(EVERYWHERE))
@pytest.mark.parametrize("name", ALL)
def test_transport_failure_never_raises_and_leaves_nothing(run, name, scenario):
    result, _, _ = run(name, scenario)
    assert result.status == "failed" and result.source == name and result.error
    assert _listing(run) == []


@pytest.mark.parametrize("name", ALL)
def test_valid_existing_file_is_skipped_without_a_request(run, name):
    def put(path):
        with open(path, "wb") as f:
            f.write(PDF)

    result, req, transport = run(name, "bug", prepare=put)
    assert (result.status, result.path) == ("skipped", req.path)
    assert transport.calls == []
    assert _listing(run) == [FILE]


@pytest.mark.parametrize("name", ALL)
def test_broken_leftover_is_replaced_by_a_good_download(run, name):
    def put(path):
        with open(path, "wb") as f:
            f.write(b"truncated")

    result, req, _ = run(name, "pdf", prepare=put)
    assert result.status == "success"
    assert open(req.path, "rb").read() == PDF
    assert _listing(run) == [FILE]


@pytest.mark.parametrize("name", ALL)
def test_unremovable_target_is_a_failure_not_a_raise(run, name):
    result, _, _ = run(name, "pdf", prepare=os.mkdir)
    assert result.status == "failed" and result.source == name
    assert _listing(run) == [FILE]  # the directory we planted, nothing else


@pytest.mark.parametrize("name", ["istex", "ezproxy", "scihub"])
def test_setup_errors_before_the_request_are_failures(run, monkeypatch, name):
    """Token, cookie and dependency lookups sit inside the never-raise guard."""

    def explode(*_a, **_k):
        raise PermissionError("unreadable")

    monkeypatch.setattr(istex, "_get_token", explode)
    monkeypatch.setattr(ezproxy, "_load_cookies", explode)
    monkeypatch.setattr(scihub.time, "sleep", explode)
    result, _, _ = run(name, "pdf")
    assert result.status == "failed" and result.source == name and result.error
    assert _listing(run) == []


def test_every_source_is_covered():
    import doifetch.cli as cli

    assert sorted(cli.SOURCES) == ALL


@pytest.mark.parametrize("name", ALL)
def test_failed_write_leaves_no_partial_file(run, monkeypatch, name):
    """A write that dies midway (disk full) is a failure and leaves nothing."""
    real_open = open

    def dying_open(path, mode="r", *a, **k):
        f = real_open(path, mode, *a, **k)
        if str(path).endswith((FILE, FILE + ".part")) and "w" in mode:
            f.write(b"%PDF-")
            f.write = lambda data: (_ for _ in ()).throw(OSError("disk full"))
        return f

    monkeypatch.setattr("builtins.open", dying_open)
    result, _, _ = run(name, "pdf")
    monkeypatch.undo()
    assert result.status == "failed" and "disk full" in result.error
    assert _listing(run) == []
