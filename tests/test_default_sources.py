"""The default source cascade is open and institutional sources only."""

from doifetch import cli
from doifetch.sources.contract import Result


def test_default_order_is_open_and_institutional():
    assert cli.DEFAULT_ORDER == ["crossref", "unpaywall", "hal", "istex", "ezproxy"]


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
    assert calls == ["crossref", "unpaywall", "hal", "istex", "ezproxy"]


def test_every_source_exposes_the_contract():
    import importlib

    for name in cli.SOURCES:
        module = importlib.import_module(f"doifetch.sources.{name}")
        assert module.NAME == name
        assert isinstance(module.ACCEPTS, frozenset) and module.ACCEPTS
        assert cli.SOURCES[name] is module.fetch


def test_dispatch_follows_accepts():
    assert cli._candidates("url", "all") == ["url"]
    assert cli._candidates("isbn", "scihub") == ["libgen"]
    assert cli._candidates("doi", "scihub") == ["scihub"]
    assert cli._candidates("doi", "all") == cli.DEFAULT_ORDER
