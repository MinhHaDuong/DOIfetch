"""Contract behaviour of the crossref, unpaywall, hal and url sources, offline.

The seam is ``_http.get``: each test replaces it with a router on the URL.
"""

import json
import os
from types import SimpleNamespace

import pytest

from doifetch.sources import _http, crossref, hal, unpaywall, url
from doifetch.sources.contract import Request

PDF = b"%PDF-1.4\n" + b"x" * 2000
PDF_URL = "https://files.example.org/p.pdf"
NAME = "Stern 2004 - Rise and Fall"


def _resp(status=200, body=b""):
    text = body.decode("utf-8", "replace")
    return SimpleNamespace(status=status, content=body, text=text)


def _json(obj, status=200):
    return _resp(status, json.dumps(obj).encode())


def _router(monkeypatch, routes):
    """Serve ``routes`` (substring of URL -> response or exception) from _http.get."""
    seen = []

    def fake_get(target, **kwargs):
        seen.append(target)
        for key, answer in routes.items():
            if key in target:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"unexpected URL {target}")

    monkeypatch.setattr(_http, "get", fake_get)
    return seen


def _happy(name):
    """(module, kind, identifier, routes) for a run that ends in a valid PDF."""
    if name == "crossref":
        message = {
            "message": {
                "link": [
                    {
                        "URL": PDF_URL,
                        "content-type": "application/pdf",
                        "content-version": "vor",
                    }
                ]
            }
        }
        return crossref, "doi", "10.1/x", {"api.crossref.org": _json(message)}
    if name == "unpaywall":
        data = {"best_oa_location": {"url_for_pdf": PDF_URL}}
        return unpaywall, "doi", "10.1/x", {"api.unpaywall.org": _json(data)}
    if name == "hal":
        data = {"response": {"docs": [{"fileMain_s": PDF_URL}]}}
        return hal, "doi", "10.1/x", {"archives-ouvertes.fr/search": _json(data)}
    return url, "url", PDF_URL, {}


SOURCES = ["crossref", "unpaywall", "hal", "url"]


def _setup(monkeypatch, tmp_path, name, **overrides):
    module, kind, ident, routes = _happy(name)
    routes = {**routes, PDF_URL: _resp(body=PDF), **overrides}
    seen = _router(monkeypatch, routes)
    return module, Request(kind, ident, str(tmp_path / f"{NAME}.pdf")), seen


@pytest.mark.parametrize("name", SOURCES)
def test_success_writes_only_req_path(monkeypatch, tmp_path, name):
    module, req, _ = _setup(monkeypatch, tmp_path, name)
    result = module.fetch(req)
    assert (result.status, result.source, result.path) == ("success", name, req.path)
    assert os.listdir(tmp_path) == [os.path.basename(req.path)]


@pytest.mark.parametrize("name", SOURCES)
def test_valid_existing_file_is_skipped_without_network(monkeypatch, tmp_path, name):
    module, req, seen = _setup(monkeypatch, tmp_path, name)
    with open(req.path, "wb") as f:
        f.write(PDF)
    assert module.fetch(req).status == "skipped"
    assert seen == []


@pytest.mark.parametrize("name", SOURCES)
def test_non_pdf_body_fails_and_leaves_no_file(monkeypatch, tmp_path, name):
    module, req, _ = _setup(
        monkeypatch, tmp_path, name, **{PDF_URL: _resp(body=b"<html>")}
    )
    result = module.fetch(req)
    assert result.status == "failed" and result.error
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("name", SOURCES)
def test_http_error_status_fails(monkeypatch, tmp_path, name):
    module, req, _ = _setup(monkeypatch, tmp_path, name, **{PDF_URL: _resp(403)})
    result = module.fetch(req)
    assert result.status == "failed" and "403" in result.error
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("name", SOURCES)
def test_transport_error_never_raises(monkeypatch, tmp_path, name):
    boom = _http.HttpError("offline")
    module, req, _ = _setup(monkeypatch, tmp_path, name, **{PDF_URL: boom})
    for key in list(_happy(name)[3]):
        _router(monkeypatch, {key: boom, PDF_URL: boom})
    result = module.fetch(req)
    # crossref's metadata lookup turns a transport error into "no PDF found"
    assert result.status == "failed" and result.error


def test_crossref_404_names_the_doi(monkeypatch, tmp_path):
    _router(monkeypatch, {"api.crossref.org": _resp(404)})
    req = Request("doi", "10.9/none", str(tmp_path / "t.pdf"))
    result = crossref.fetch(req)
    assert result.status == "failed" and "not found" in result.error


def test_crossref_without_pdf_link_fails(monkeypatch, tmp_path):
    _router(monkeypatch, {"api.crossref.org": _json({"message": {"link": []}})})
    req = Request("doi", "10.9/x", str(tmp_path / "t.pdf"))
    assert "No open access PDF" in crossref.fetch(req).error


def test_unpaywall_without_location_fails(monkeypatch, tmp_path):
    _router(monkeypatch, {"api.unpaywall.org": _json({"best_oa_location": None})})
    req = Request("doi", "10.9/x", str(tmp_path / "t.pdf"))
    assert unpaywall.fetch(req).error == "No open access PDF found"


def test_hal_needs_author_year_title_name(monkeypatch, tmp_path):
    seen = _router(monkeypatch, {})
    req = Request("doi", "10.9/x", str(tmp_path / "Untitled.pdf"))
    result = hal.fetch(req)
    assert result.status == "failed" and "Cannot parse" in result.error
    assert seen == []


def test_broken_leftover_is_replaced(monkeypatch, tmp_path):
    module, req, _ = _setup(monkeypatch, tmp_path, "url")
    with open(req.path, "wb") as f:
        f.write(b"junk")
    assert module.fetch(req).status == "success"
    with open(req.path, "rb") as f:
        assert f.read() == PDF


@pytest.mark.parametrize("module", [crossref, unpaywall, hal, url])
def test_no_requests_import(module):
    assert not hasattr(module, "requests")
