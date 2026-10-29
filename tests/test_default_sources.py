"""The default source cascade is open and institutional sources only."""

from doifetch import cli
from doifetch.sources.contract import Result


def test_default_order_is_open_and_institutional():
    assert cli.DEFAULT_ORDER == [
        "crossref",
        "unpaywall",
        "openalex",
        "hal",
        "core",
        "istex",
        "ezproxy",
        "isbn",
    ]


def test_shadow_libraries_stay_opt_in():
    assert "scihub" not in cli.DEFAULT_ORDER
    assert "libgen" not in cli.DEFAULT_ORDER
    assert "scihub" in cli.SOURCES  # still reachable via --source scihub


def test_default_run_never_calls_scihub(monkeypatch, tmp_path):
    calls = []

    def stub(name):
        def fetch(req):
            calls.append(name)
            return Result("failed", name, error="x")

        return fetch

    for name in cli.SOURCES:
        monkeypatch.setitem(cli.SOURCES, name, stub(name))
    cli._fetch_one("10.1000/x", "T", str(tmp_path), "all")
    assert calls == [n for n in cli.DEFAULT_ORDER if "doi" in cli.ACCEPTS[n]]


def test_every_source_exposes_the_contract():
    import importlib

    for name in cli.SOURCES:
        module = importlib.import_module(f"doifetch.sources.{name}")
        assert module.NAME == name
        assert isinstance(module.ACCEPTS, frozenset) and module.ACCEPTS
        assert cli.SOURCES[name] is module.fetch


def test_dispatch_follows_accepts():
    assert cli._candidates("url", "all") == ["url"]
    assert cli._candidates("isbn", "all") == ["isbn"]
    assert cli._candidates("isbn", "libgen") == ["libgen"]
    assert cli._candidates("isbn", "scihub") == []  # no silent reroute
    assert cli._candidates("doi", "scihub") == ["scihub"]
    assert cli._candidates("doi", "all") == cli.DEFAULT_ORDER[:-1]  # all but isbn


def test_title_only_row_is_a_title_request_for_title_sources_only(tmp_path):
    from doifetch.sources.contract import Request

    req = cli._request("", "A Title", str(tmp_path), "A Title")
    assert req == Request("title", "A Title", str(tmp_path / "A Title.pdf"))
    assert cli._candidates("title", "all") == ["scihub"]
    assert cli._candidates("title", "crossref") == []
    from doifetch import api

    assert api.fetch(req).status == "failed"  # no default source accepts titles
    assert "title" in api.fetch(req).error
