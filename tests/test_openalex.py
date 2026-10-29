"""OpenAlex: key loading, the multi-location source and the naming fallback."""

import json
import logging
import subprocess
import sys
import textwrap
import urllib.parse

import pytest

from doifetch import naming
from doifetch.sources import _http, _openalex, openalex
from doifetch.sources import crossref as crossref_mod
from doifetch.sources.contract import Request

PDF = b"%PDF-1.4\n" + b"x" * 2000
DOI = "10.5281/zenodo.1234"
KEY = "sekrit-key-123"
WORK = {
    "title": "A Dataset of Things",
    "publication_year": 2021,
    "authorships": [{"author": {"display_name": "Jane Q. Doe"}}],
    "locations": [
        {"pdf_url": "https://a.example/1.pdf"},
        {"pdf_url": None},
        {"pdf_url": "https://b.example/2.pdf"},
        {"pdf_url": "https://a.example/1.pdf"},
    ],
}


def _resp(status=200, body=b"", ctype="application/octet-stream"):
    return _http.Response(
        status=status, url="", headers={"content-type": ctype}, content=body
    )


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real key, no real key file, and the once-per-run warning rearmed."""
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(_openalex, "KEY_FILE", str(tmp_path / "absent.env"))
    monkeypatch.setattr(_openalex, "_warned", False)


@pytest.fixture()
def net(monkeypatch):
    """Fake transport: ``routes`` maps a URL to a Response or an exception."""
    state = {"routes": {}, "calls": []}

    def get(url, **kwargs):
        state["calls"].append((url, kwargs))
        answer = state["routes"].get(url, _resp(404))
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(_http, "get", get)
    return state


def _work_url(doi=DOI):
    return _openalex.WORKS_URL + doi


# --- key loading


def test_key_from_environment(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", f" {KEY} ")
    assert _openalex.get_key() == KEY


def test_key_from_file_when_env_is_absent(monkeypatch, tmp_path):
    path = tmp_path / "k.env"
    path.write_text(f"OTHER=1\nexport OPENALEX_API_KEY='{KEY}'\n")
    monkeypatch.setattr(_openalex, "KEY_FILE", str(path))
    assert _openalex.get_key() == KEY


def test_environment_beats_the_file(monkeypatch, tmp_path):
    path = tmp_path / "k.env"
    path.write_text("OPENALEX_API_KEY=from-file\n")
    monkeypatch.setattr(_openalex, "KEY_FILE", str(path))
    monkeypatch.setenv("OPENALEX_API_KEY", "from-env")
    assert _openalex.get_key() == "from-env"


def test_no_key_anywhere_is_empty():
    assert _openalex.get_key() == ""


def test_default_key_file_and_override(monkeypatch):
    import importlib
    import os

    from doifetch import config

    try:
        assert config.OPENALEX_KEY_FILE == os.path.expanduser(
            "~/.config/keys/openalex.env"
        )
        monkeypatch.setenv("OPENALEX_KEY_FILE", "/somewhere/k.env")
        importlib.reload(config)
        assert config.OPENALEX_KEY_FILE == "/somewhere/k.env"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_key_is_sent_as_parameter_and_never_leaks(monkeypatch, net, caplog, capsys):
    monkeypatch.setenv("OPENALEX_API_KEY", KEY)
    net["routes"][_work_url()] = _http.HttpError(f"GET {_work_url()}?api_key={KEY}: x")
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(_openalex.OpenAlexError) as err:
            _openalex.get_work(DOI)
        assert _openalex.get_metadata(DOI) is None
    assert net["calls"][0][1]["params"] == {"api_key": KEY}
    shown = capsys.readouterr()
    assert KEY not in str(err.value) and KEY not in caplog.text
    assert KEY not in shown.out + shown.err
    assert err.value.__cause__ is None and err.value.__suppress_context__


def test_url_encoded_key_is_scrubbed_too(monkeypatch, net):
    key = "k+y/with=chars"
    encoded = urllib.parse.urlencode({"api_key": key})
    monkeypatch.setenv("OPENALEX_API_KEY", key)
    net["routes"][_work_url()] = _http.HttpError(f"GET {_work_url()}?{encoded}: x")
    with pytest.raises(_openalex.OpenAlexError) as err:
        _openalex.get_work(DOI)
    assert key not in str(err.value) and encoded not in str(err.value)


def test_source_result_never_carries_the_key(monkeypatch, net, tmp_path):
    monkeypatch.setenv("OPENALEX_API_KEY", KEY)
    net["routes"][_work_url()] = _http.HttpError(f"GET ...?api_key={KEY}: boom")
    result = openalex.fetch(Request("doi", DOI, str(tmp_path / "x.pdf")))
    assert result.status == "failed" and KEY not in (result.error or "")


# --- refusals: keyless access refused


@pytest.mark.parametrize("status", [401, 403, 429])
def test_refusal_is_a_failure_with_a_reason_warned_once(net, tmp_path, caplog, status):
    net["routes"][_work_url()] = _resp(status)
    with caplog.at_level(logging.WARNING):
        first = openalex.fetch(Request("doi", DOI, str(tmp_path / "a.pdf")))
        second = openalex.fetch(Request("doi", DOI, str(tmp_path / "b.pdf")))
    assert first.status == second.status == "failed"
    assert "OPENALEX_API_KEY" in first.error and str(status) in first.error
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 1


# --- the source


def test_falls_through_to_the_next_location(net, tmp_path):
    net["routes"][_work_url()] = _resp(200, json.dumps(WORK).encode())
    net["routes"]["https://a.example/1.pdf"] = _resp(403)
    net["routes"]["https://b.example/2.pdf"] = _resp(200, PDF)
    req = Request("doi", DOI, str(tmp_path / "x.pdf"))
    result = openalex.fetch(req)
    assert (result.status, result.path) == ("success", req.path)
    downloads = [u for u, _ in net["calls"] if u.endswith(".pdf")]
    assert downloads == ["https://a.example/1.pdf", "https://b.example/2.pdf"]


@pytest.mark.parametrize(
    "first",
    [
        _http.HttpError("timed out"),
        _resp(200, b"<html>" + b"x" * 3000 + b"</html>"),
        _resp(200, b"%PDF-1.4 tiny"),
    ],
)
def test_a_bad_first_location_of_any_kind_falls_through(net, tmp_path, first):
    net["routes"][_work_url()] = _resp(200, json.dumps(WORK).encode())
    net["routes"]["https://a.example/1.pdf"] = first
    net["routes"]["https://b.example/2.pdf"] = _resp(200, PDF)
    result = openalex.fetch(Request("doi", DOI, str(tmp_path / "x.pdf")))
    assert result.status == "success"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.pdf"]


def test_all_locations_failing_lists_each_reason(net, tmp_path):
    net["routes"][_work_url()] = _resp(200, json.dumps(WORK).encode())
    net["routes"]["https://a.example/1.pdf"] = _resp(403)
    net["routes"]["https://b.example/2.pdf"] = _resp(500)
    result = openalex.fetch(Request("doi", DOI, str(tmp_path / "x.pdf")))
    assert result.status == "failed"
    assert "403" in result.error and "500" in result.error
    assert list(tmp_path.iterdir()) == []


def test_work_without_pdf_location_fails(net, tmp_path):
    net["routes"][_work_url()] = _resp(200, b'{"locations": [{"pdf_url": null}]}')
    result = openalex.fetch(Request("doi", DOI, str(tmp_path / "x.pdf")))
    assert result.status == "failed" and "location" in result.error


def test_pdf_urls_keep_order_and_drop_duplicates():
    assert openalex.pdf_urls(WORK) == [
        "https://a.example/1.pdf",
        "https://b.example/2.pdf",
    ]
    assert openalex.pdf_urls({}) == []


# --- naming fallback


def test_unknown_to_crossref_known_to_openalex_gets_an_author_year_title_name(
    monkeypatch, net
):
    def crossref_404(doi):
        raise crossref_mod.DoiNotFoundError("404")

    monkeypatch.setattr(crossref_mod, "get_metadata", crossref_404)
    net["routes"][_work_url()] = _resp(200, json.dumps(WORK).encode())
    assert naming.resolve_name(DOI, "") == "Doe 2021 - A Dataset of Things"


def test_crossref_failure_also_falls_back(monkeypatch, net):
    monkeypatch.setattr(crossref_mod, "get_metadata", lambda doi: None)
    net["routes"][_work_url()] = _resp(200, json.dumps(WORK).encode())
    assert naming.resolve_name(DOI, "") == "Doe 2021 - A Dataset of Things"


def test_crossref_hit_never_asks_openalex(monkeypatch, net):
    monkeypatch.setattr(
        crossref_mod, "get_metadata", lambda doi: {"title": ["From Crossref"]}
    )
    assert naming.resolve_name(DOI, "") == "From Crossref"
    assert net["calls"] == []


def test_openalex_refusal_keeps_the_caller_name(monkeypatch, net):
    monkeypatch.setattr(crossref_mod, "get_metadata", lambda doi: None)
    net["routes"][_work_url()] = _resp(429)
    assert naming.resolve_name(DOI, "Caller Title") == "Caller Title"


def test_openalex_mismatch_still_renames_from_it(monkeypatch, net, caplog):
    monkeypatch.setattr(crossref_mod, "get_metadata", lambda doi: None)
    net["routes"][_work_url()] = _resp(200, json.dumps(WORK).encode())
    name = naming.resolve_name(DOI, "Totally Unrelated Words Here")
    assert name == "Doe 2021 - A Dataset of Things"


def test_as_crossref_message_tolerates_sparse_records():
    assert _openalex.as_crossref_message({}) == {}
    assert _openalex.as_crossref_message({"display_name": "Only"}) == {
        "title": ["Only"]
    }


def test_naming_does_not_import_the_source_module():
    script = textwrap.dedent(
        """
        import sys
        import doifetch.naming
        assert "doifetch.sources.openalex" not in sys.modules
        print("ok")
        """
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"
