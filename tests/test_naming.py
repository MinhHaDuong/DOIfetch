import logging
import os
from types import SimpleNamespace

import pytest

from doifetch import cli, naming
from doifetch.pdf_utils import clean_filename
from doifetch.sources import crossref as crossref_mod
from doifetch.sources.contract import Result

STERN = {
    "title": ["The Rise and Fall of the Environmental Kuznets Curve"],
    "author": [{"given": "David I.", "family": "Stern"}],
    "issued": {"date-parts": [[2004]]},
}
STERN_NAME = "Stern 2004 - The Rise and Fall of the Environmental Kuznets Curve"
DOI = "10.1016/j.worlddev.2004.03.004"


@pytest.fixture()
def crossref(monkeypatch):
    """Serve a canned Crossref record; no network."""
    state = {"message": STERN, "calls": 0}

    def fake(doi):
        state["calls"] += 1
        if isinstance(state["message"], Exception):
            raise state["message"]
        return state["message"]

    monkeypatch.setattr(crossref_mod, "get_metadata", fake)
    return state


def test_no_title_gets_author_year_title_name(crossref):
    assert naming.resolve_name(DOI, "") == STERN_NAME


def test_mismatch_names_from_crossref_and_warns(crossref, caplog):
    caller = "Stern 2004 - Development Discounting Climate Change"
    with caplog.at_level(logging.WARNING):
        assert naming.resolve_name(DOI, caller) == STERN_NAME
    assert "Title mismatch" in caplog.text


def test_keep_title_forces_caller_name(crossref):
    caller = "Stern 2004 - Development Discounting Climate Change"
    assert naming.resolve_name(DOI, caller, keep_title=True) == caller
    assert crossref["calls"] == 0


@pytest.mark.parametrize(
    "caller",
    [
        "Stern 2004 - The Rise and Fall of the Environmental Kuznets Curve",
        "Stern 2004 - rise and fall of the environmental Kuznets curve",
        "The Rise and Fall of the Environmental Kuznets Curve",
        "Some Odd Prefix 1999 - Rise & Fall of the Environmental Kuznets Curve",
    ],
)
def test_matching_title_is_kept_byte_identical(crossref, caller, caplog):
    with caplog.at_level(logging.WARNING):
        assert naming.resolve_name(DOI, caller) == caller
    assert "mismatch" not in caplog.text


@pytest.mark.parametrize("failure", [None, crossref_mod.DoiNotFoundError("404")])
def test_lookup_failure_falls_back_to_caller_name(crossref, caplog, failure):
    crossref["message"] = failure
    with caplog.at_level(logging.INFO):
        assert naming.resolve_name(DOI, "Mine") == "Mine"
        assert naming.resolve_name(DOI, "") == ""
    assert "caller name" in caplog.text


def test_non_doi_identifiers_skip_lookup(crossref):
    assert naming.resolve_name("isbn:123", "Book") == "Book"
    assert naming.resolve_name("https://x.org/a.pdf", "") == ""
    assert crossref["calls"] == 0


def test_compose_handles_markup_subtitle_and_fallbacks():
    message = {
        "title": ["On <i>Things</i> &amp; Stuff"],
        "subtitle": ["A <sub>2</sub> story"],
        "author": [{"name": "OECD"}],
        "issued": {"date-parts": [[None]]},
        "published-online": {"date-parts": [[2019, 5]]},
    }
    assert naming.compose_name(message) == "OECD 2019 - On Things & Stuff A 2 story"
    assert naming.compose_name({"title": ["Only"]}) == "Only"
    assert naming.compose_name({"author": [{"family": "X"}]}) is None


def test_long_title_is_cut_never_the_prefix():
    message = dict(STERN, title=["Very long " * 30])
    name = naming.compose_name(message)
    assert name.startswith("Stern 2004 - Very long")
    assert len(clean_filename(name)) == len(name) <= 120


def test_metadata_request_is_verified_and_has_timeout(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            status_code=200, json=lambda: {"message": {"title": ["T"]}}
        )

    monkeypatch.setattr(crossref_mod.requests, "get", fake_get)
    assert crossref_mod.get_metadata(DOI) == {"title": ["T"]}
    assert "verify" not in seen and seen["timeout"]
    assert "mailto:" in seen["headers"]["User-Agent"]


def test_metadata_with_non_dict_json_body_returns_none(monkeypatch):
    monkeypatch.setattr(
        crossref_mod.requests,
        "get",
        lambda url, **kw: SimpleNamespace(status_code=200, json=lambda: ["oops"]),
    )
    assert crossref_mod.get_metadata(DOI) is None


def test_single_download_names_file_from_crossref(
    crossref, monkeypatch, tmp_path, caplog
):
    seen = {}

    def fake_istex(req):
        seen["title"] = os.path.basename(req.path)[: -len(".pdf")]
        return Result("success", "istex", path=req.path)

    monkeypatch.setitem(cli.SOURCES, "istex", fake_istex)
    args = SimpleNamespace(
        doi=DOI,
        isbn=None,
        title="Stern 2004 - Development Discounting Climate Change",
        source="istex",
        output_dir=str(tmp_path),
        no_check_zotero=True,
    )
    with caplog.at_level(logging.WARNING):
        assert cli.handle_single_download(args) == 0
    assert seen["title"] == STERN_NAME
    assert "Title mismatch" in caplog.text


def test_batch_round_trip_writes_status_for_renamed_rows(
    crossref, monkeypatch, tmp_path
):
    table = tmp_path / "refs.txt"
    table.write_text(
        f"doi:{DOI}\tWrong Title Entirely\ndoi:10.1000/blank\t\ndoi:10.1000/blank2\t\n",
        encoding="utf-8",
    )
    renamed = {}

    def fake_istex(req):
        renamed[req.identifier] = os.path.basename(req.path)[: -len(".pdf")]
        return Result("success", "istex", path=req.path)

    monkeypatch.setitem(cli.SOURCES, "istex", fake_istex)
    monkeypatch.setattr(cli, "DEFAULT_ORDER", ["istex"])

    tasks, _ = cli.load_download_tasks([str(table)])
    assert tasks == [
        (DOI, "Wrong Title Entirely"),
        ("10.1000/blank", ""),
        ("10.1000/blank2", ""),
    ]

    records = []
    from queue import Queue

    q = Queue()
    for task in tasks:
        q.put(task)
    cli.fetch_worker(q, "all", str(tmp_path), [], records, [], [], None)
    assert renamed[DOI] == STERN_NAME
    assert not renamed["10.1000/blank"].startswith("Unknown_")

    cli.update_source_files([str(table)], records)
    # Every row was fetched: the retry list is empty.
    assert cli.read_table(str(table)) == []


@pytest.mark.parametrize(
    "message",
    [
        {"title": ["T"], "author": "Stern"},
        {"title": ["T"], "author": ["Stern"]},
        {"title": 5},
    ],
)
def test_malformed_record_falls_back_instead_of_raising(crossref, message):
    crossref["message"] = message
    assert naming.resolve_name(DOI, "Mine") == "Mine"


def test_malformed_date_is_ignored_not_misread():
    message = {"title": ["T"], "issued": {"date-parts": "2004"}}
    assert naming.compose_name(message) == "T"
