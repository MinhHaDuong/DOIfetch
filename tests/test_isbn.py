"""ISBN validation and ISBN-based naming; all network mocked."""

import logging

import pytest

import fetch
import fetch_bookmeta
import naming
from utils import normalize_isbn

ISBN13 = "9780262033848"
ISBN10 = "0262033844"
SIMON = {
    "title": ["The Sciences of the Artificial"],
    "subtitle": [],
    "author": [{"family": "Simon", "name": "Herbert A. Simon"}],
    "issued": {"date-parts": [[1996]]},
}
SIMON_NAME = "Simon 1996 - The Sciences of the Artificial"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("978-0-262-03384-8", ISBN13),
        ("isbn:0 262 03384 4", ISBN10),
        ("080442957X", "080442957X"),
        ("080442957x", "080442957X"),
    ],
)
def test_valid_isbn_is_normalised(raw, expected):
    assert normalize_isbn(raw) == expected


@pytest.mark.parametrize(
    "raw", ["9780262033849", "0262033845", "123", "", None, "97802620338AB"]
)
def test_invalid_isbn_is_rejected(raw):
    assert normalize_isbn(raw) is None


def test_single_mode_rejects_bad_check_digit():
    args = type("A", (), {"isbn": "9780262033849"})()
    with pytest.raises(ValueError, match="Invalid ISBN"):
        fetch.handle_single_download(args)


def test_batch_skips_invalid_isbn_like_invalid_doi(tmp_path, capsys):
    path = tmp_path / "refs.txt"
    path.write_text(f"isbn:9780262033849\tBad\nisbn:{ISBN13}\tGood\n")
    tasks, skipped = fetch.load_download_tasks([str(path)])
    assert tasks == [(f"isbn:{ISBN13}", "Good")]
    assert skipped == 1
    assert "invalid isbn" in capsys.readouterr().out.lower()


@pytest.fixture()
def books(monkeypatch):
    state = {"message": SIMON, "calls": 0}

    def fake(isbn):
        state["calls"] += 1
        assert isbn == ISBN13
        if isinstance(state["message"], Exception):
            raise state["message"]
        return state["message"]

    monkeypatch.setattr(fetch_bookmeta, "get_metadata", fake)
    return state


def test_isbn_without_title_gets_author_year_title_name(books):
    assert naming.resolve_name("isbn:978-0-262-03384-8", "") == SIMON_NAME


def test_isbn_title_mismatch_is_logged_and_named_from_metadata(books, caplog):
    with caplog.at_level(logging.WARNING):
        assert (
            naming.resolve_name(f"isbn:{ISBN13}", "Wrong Book Entirely") == SIMON_NAME
        )
    assert "Title mismatch" in caplog.text


def test_isbn_matching_title_and_keep_title(books):
    own = "Simon 1996 - Sciences of the Artificial"
    assert naming.resolve_name(f"isbn:{ISBN13}", own) == own
    assert naming.resolve_name(f"isbn:{ISBN13}", "Mine", keep_title=True) == "Mine"


def test_isbn_lookup_failure_falls_back_offline(books):
    books["message"] = RuntimeError("down")
    assert naming.resolve_name(f"isbn:{ISBN13}", "Mine") == "Mine"
    books["message"] = None
    assert naming.resolve_name(f"isbn:{ISBN13}", "") == ""


def test_invalid_isbn_skips_lookup(books):
    assert naming.resolve_name("isbn:123", "Book") == "Book"
    assert books["calls"] == 0


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


OL = {
    f"ISBN:{ISBN13}": {
        "title": "The Sciences of the Artificial",
        "authors": [{"name": "Herbert A. Simon"}],
        "publish_date": "September 1996",
    }
}
GB = {
    "items": [
        {
            "volumeInfo": {
                "title": "The Sciences of the Artificial",
                "authors": ["Herbert A. Simon"],
                "publishedDate": "1996-09-01",
            }
        }
    ]
}


def _route(monkeypatch, ol, gb):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        resp = ol if "openlibrary" in url else gb
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(fetch_bookmeta.requests, "get", fake_get)
    return calls


def test_open_library_first_and_google_not_called(monkeypatch):
    calls = _route(monkeypatch, _Resp(200, OL), _Resp(200, GB))
    msg = fetch_bookmeta.get_metadata(ISBN13)
    assert naming.compose_name(msg) == SIMON_NAME
    assert len(calls) == 1


@pytest.mark.parametrize(
    "ol", [_Resp(200, {}), _Resp(500, {}), ConnectionError("x")], ids=str
)
def test_google_books_is_second_provider(monkeypatch, ol):
    _route(monkeypatch, ol, _Resp(200, GB))
    assert naming.compose_name(fetch_bookmeta.get_metadata(ISBN13)) == SIMON_NAME


def test_all_providers_failing_gives_none(monkeypatch):
    _route(monkeypatch, _Resp(404, {}), _Resp(429, {}))
    assert fetch_bookmeta.get_metadata(ISBN13) is None
