"""One cascade semantics, shared by the library (api) and the command line (cli)."""

import pytest

from doifetch import api, cli
from doifetch.sources.contract import Request, Result

DOI = Request("doi", "10.1000/x", "x.pdf")
ISBN = Request("isbn", "9780262033848", "b.pdf")


def _registry(outcomes, calls):
    """name -> (kinds, status or exception); returns a ``load`` for api.cascade."""

    def load(name):
        kinds, outcome = outcomes[name]

        def fetch(req):
            calls.append(name)
            if isinstance(outcome, Exception):
                raise outcome
            return Result(outcome, name, error="x" if outcome == "failed" else None)

        return frozenset(kinds), fetch

    return load


@pytest.mark.parametrize("stopper", ["success", "skipped"])
def test_cascade_stops_at_success_or_skipped(stopper):
    calls = []
    load = _registry(
        {
            "a": ({"doi"}, "failed"),
            "b": ({"doi"}, stopper),
            "c": ({"doi"}, "success"),
        },
        calls,
    )
    result = api.cascade(DOI, ["a", "b", "c"], load)
    assert (result.status, result.source) == (stopper, "b")
    assert calls == ["a", "b"]


def test_cascade_returns_the_last_failure_and_passes_over_non_accepting():
    calls = []
    load = _registry(
        {"a": ({"url"}, "success"), "b": ({"doi"}, "failed"), "c": ({"doi"}, "failed")},
        calls,
    )
    result = api.cascade(DOI, ["a", "b", "c"], load)
    assert (result.status, result.source) == ("failed", "c")
    assert result.error == "b: x; c: x"  # every tried source's reason
    assert calls == ["b", "c"]


def test_cascade_never_raises():
    calls = []
    load = _registry(
        {"a": ({"doi"}, RuntimeError("bug")), "b": ({"doi"}, "success")}, calls
    )
    assert api.cascade(DOI, ["a", "b"], load).source == "b"  # bug in a: go on
    only_bad = api.cascade(DOI, ["a", "missing"], load)  # unknown name: KeyError
    assert only_bad.status == "failed" and only_bad.source == "missing"


def test_cascade_without_any_accepting_source_fails_cleanly():
    result = api.cascade(ISBN, ["a"], _registry({"a": ({"doi"}, "success")}, []))
    assert result.status == "failed" and "isbn" in result.error


def _patch_cli(monkeypatch, outcomes, calls):
    load = _registry(outcomes, calls)
    for name in outcomes:
        monkeypatch.setitem(cli.ACCEPTS, name, load(name)[0])
        monkeypatch.setitem(cli.SOURCES, name, load(name)[1])


def test_cli_stops_on_skipped_like_the_library(monkeypatch, tmp_path):
    calls = []
    _patch_cli(
        monkeypatch,
        {"crossref": ({"doi"}, "skipped"), "unpaywall": ({"doi"}, "success")},
        calls,
    )
    monkeypatch.setattr(cli, "DEFAULT_ORDER", ["crossref", "unpaywall"])
    result = cli._fetch_one("10.1000/x", "T", str(tmp_path), "all")
    assert result["status"] == "skipped" and calls == ["crossref"]


def test_cli_explicit_source_runs_only_that_source(monkeypatch, tmp_path):
    calls = []
    _patch_cli(
        monkeypatch,
        {"hal": ({"doi"}, "failed"), "crossref": ({"doi"}, "success")},
        calls,
    )
    result = cli._fetch_one("10.1000/x", "T", str(tmp_path), "hal")
    assert result["status"] == "failed" and calls == ["hal"]


def test_cli_single_mode_survives_a_raising_source(monkeypatch, tmp_path):
    _patch_cli(monkeypatch, {"hal": ({"doi"}, RuntimeError("bug"))}, [])
    result = cli._fetch_one("10.1000/x", "T", str(tmp_path), "hal")
    assert result["status"] == "failed" and "bug" in result["error"]


@pytest.mark.parametrize("source", ["all", "libgen"])
def test_cli_routes_an_isbn_to_libgen(monkeypatch, tmp_path, source):
    """Kept until ticket 0012: under "all", no default source accepts, fall back.

    A named source that does not accept the kind fails instead (PR #34).
    """
    calls = []
    _patch_cli(monkeypatch, {"libgen": ({"isbn"}, "success")}, calls)
    result = cli._fetch_one("isbn:9780262033848", "T", str(tmp_path), source)
    assert result["status"] == "success" and calls == ["libgen"]


def test_library_fetch_has_no_isbn_route(tmp_path):
    result = api.fetch(Request("isbn", "9780262033848", str(tmp_path / "b.pdf")))
    assert result.status == "failed"
