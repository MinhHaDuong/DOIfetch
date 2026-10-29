"""The public library API and its side-effect-free import."""

import subprocess
import sys
import textwrap

import doifetch
from doifetch import Request, Result, api, fetch

PURITY_SCRIPT = textwrap.dedent(
    """
    import builtins, socket, sys

    sys.modules["bs4"] = None  # the shadow extra is absent: importing it raises

    def refuse(*a, **k):
        raise AssertionError("side effect at import")

    socket.socket = refuse
    socket.create_connection = refuse
    builtins.input = refuse

    import doifetch
    from doifetch import Request, Result, fetch

    assert "doifetch.cli" not in sys.modules
    for shadow in ("scihub", "libgen", "bookmeta", "openalex"):
        assert f"doifetch.sources.{shadow}" not in sys.modules, shadow
    print("pure")
    """
)


def test_import_has_no_side_effects_and_needs_no_extra():
    out = subprocess.run(
        [sys.executable, "-I", "-c", PURITY_SCRIPT],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "pure"


def test_public_names():
    assert doifetch.fetch is api.fetch
    assert doifetch.Request is Request and doifetch.Result is Result
    assert doifetch.DEFAULT_ORDER == [
        "crossref",
        "unpaywall",
        "openalex",
        "hal",
        "core",
        "istex",
        "ezproxy",
        "isbn",
    ]


def _stub(monkeypatch, outcomes, calls):
    import importlib

    for name, (kinds, status) in outcomes.items():
        module = importlib.import_module(f"doifetch.sources.{name}")

        def fake(req, name=name, status=status):
            calls.append(name)
            return Result(status, name, error="x" if status == "failed" else None)

        monkeypatch.setattr(module, "fetch", fake)
        monkeypatch.setattr(module, "ACCEPTS", frozenset(kinds))


def test_fetch_runs_the_cascade_until_success(monkeypatch, tmp_path):
    calls = []
    _stub(
        monkeypatch,
        {
            "crossref": ({"doi"}, "failed"),
            "unpaywall": ({"doi"}, "failed"),
            "openalex": ({"doi"}, "failed"),
            "hal": ({"doi"}, "success"),
            "core": ({"doi"}, "success"),
            "istex": ({"doi"}, "success"),
            "ezproxy": ({"doi"}, "success"),
        },
        calls,
    )
    result = fetch(Request("doi", "10.1000/x", str(tmp_path / "x.pdf")))
    assert result.status == "success" and result.source == "hal"
    assert calls == ["crossref", "unpaywall", "openalex", "hal"]


def test_fetch_returns_last_failure_and_skips_unaccepting_sources(
    monkeypatch, tmp_path
):
    calls = []
    _stub(
        monkeypatch,
        {
            "crossref": ({"url"}, "success"),
            "unpaywall": ({"doi"}, "failed"),
            "openalex": ({"url"}, "success"),
            "hal": ({"doi"}, "failed"),
            "core": ({"doi"}, "failed"),
            "istex": ({"url"}, "success"),
            "ezproxy": ({"doi"}, "failed"),
        },
        calls,
    )
    result = fetch(Request("doi", "10.1000/x", str(tmp_path / "x.pdf")))
    assert result.status == "failed" and result.source == "ezproxy"
    assert calls == ["unpaywall", "hal", "core", "ezproxy"]


def test_fetch_without_an_accepting_source_fails_cleanly(tmp_path):
    result = fetch(Request("title", "A Title", str(tmp_path / "x.pdf")))
    assert result.status == "failed" and "title" in (result.error or "")
