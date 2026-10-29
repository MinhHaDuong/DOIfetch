"""The default source cascade is open and institutional sources only."""

from doifetch import cli


def test_default_order_is_open_and_institutional():
    assert cli.SOURCE_ORDER == ["crossref", "unpaywall", "hal", "istex", "ezproxy"]


def test_shadow_libraries_stay_opt_in():
    assert "scihub" not in cli.SOURCE_ORDER
    assert "libgen" not in cli.SOURCE_ORDER
    assert "scihub" in cli.SOURCES  # still reachable via --source scihub


def test_default_run_never_calls_scihub(monkeypatch, tmp_path):
    calls = []

    def stub(name):
        def fetch_pdf(doi, title, output_dir):
            calls.append(name)
            return {"status": "failed", "doi": doi, "title": title, "error": "x"}

        return fetch_pdf

    for name, module in cli.SOURCES.items():
        monkeypatch.setattr(module, "fetch_pdf", stub(name))
    cli._fetch_one("10.1000/x", "T", str(tmp_path), "all")
    assert calls == ["crossref", "unpaywall", "hal", "istex", "ezproxy"]
