"""The isbn source: Crossref book DOIs, then the DOI sources; all network mocked."""

import json
from types import SimpleNamespace

import pytest

from doifetch import api
from doifetch.sources import _http, isbn
from doifetch.sources.contract import Request, Result

ISBN = "9783110586664"


def _json(obj, status=200):
    body = json.dumps(obj).encode()
    return SimpleNamespace(status=status, content=body, text=body.decode())


def _items(*rows):
    return _json({"message": {"items": [{"DOI": d, "type": t} for d, t in rows]}})


@pytest.fixture()
def lookup(monkeypatch):
    """lookup(response) answers the Crossref ISBN query; returns the URLs asked."""
    asked = []

    def install(response):
        def get(url, **_kwargs):
            asked.append(url)
            if isinstance(response, Exception):
                raise response
            return response

        monkeypatch.setattr(_http, "get", get)
        return asked

    return install


def test_lookup_asks_for_book_types_and_keeps_the_preferred_order(lookup):
    asked = lookup(
        _items(
            ("10.1/chapter", "book-chapter"),
            ("10.1/edited", "edited-book"),
            ("10.1/mono", "monograph"),
            ("10.1/book", "book"),
        )
    )
    assert isbn.book_dois(ISBN) == ["10.1/book", "10.1/mono", "10.1/edited"]
    assert f"filter=isbn:{ISBN}," in asked[0] and "type:monograph" in asked[0]


def test_lookup_without_a_book_record_yields_nothing(lookup):
    lookup(_items(("10.1/chapter", "book-chapter")))
    assert isbn.book_dois(ISBN) == []


def test_no_doi_is_a_failure_with_a_reason(lookup, tmp_path):
    lookup(_items())
    result = isbn.fetch(Request("isbn", ISBN, str(tmp_path / "b.pdf")))
    assert result.status == "failed" and "No book-level DOI" in result.error


def test_lookup_error_is_a_failure_with_a_reason(lookup, tmp_path):
    lookup(_json({}, status=429))
    result = isbn.fetch(Request("isbn", ISBN, str(tmp_path / "b.pdf")))
    assert result.status == "failed" and "429" in result.error


def test_every_book_doi_is_tried_and_the_reasons_are_reported(
    lookup, monkeypatch, tmp_path
):
    lookup(_items(("10.1/a", "book"), ("10.1/b", "monograph")))
    seen = []

    def cascade(req, names):
        seen.append((req.kind, req.identifier, req.path))
        return Result("failed", "hal", error=f"nothing for {req.identifier}")

    monkeypatch.setattr(api, "cascade", cascade)
    path = str(tmp_path / "b.pdf")
    result = isbn.fetch(Request("isbn", ISBN, path))
    assert seen == [("doi", "10.1/a", path), ("doi", "10.1/b", path)]
    assert result.status == "failed" and result.source == "isbn"
    assert "No open copy" in result.error
    assert "10.1/a: nothing for 10.1/a; 10.1/b: nothing for 10.1/b" in result.error


def test_first_open_copy_stops_the_search(lookup, monkeypatch, tmp_path):
    lookup(_items(("10.1/a", "book"), ("10.1/b", "monograph")))
    seen = []

    def cascade(req, names):
        seen.append(req.identifier)
        return Result("success", "unpaywall", path=req.path)

    monkeypatch.setattr(api, "cascade", cascade)
    path = str(tmp_path / "b.pdf")
    result = isbn.fetch(Request("isbn", ISBN, path))
    assert (result.status, result.source, result.path) == ("success", "isbn", path)
    assert seen == ["10.1/a"]


@pytest.mark.network
def test_open_access_book_isbn_resolves_to_its_book_doi():
    """Real Crossref: a De Gruyter open-access edited book (chapters are skipped)."""
    assert isbn.book_dois(ISBN) == ["10.1515/9783110586664"]
