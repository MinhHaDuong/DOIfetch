"""CORE: key loading, the DOI lookup, the full-text download and key hygiene."""

import json
import logging
import urllib.parse

import pytest

from doifetch.sources import _http, core
from doifetch.sources.contract import Request

PDF = b"%PDF-1.4\n" + b"x" * 2000
DOI = "10.1234/abc.5"
KEY = "sekrit key/123+"
DL = "https://core.ac.uk/download/pdf/42.pdf"


def _resp(status=200, body=b"", ctype="application/octet-stream"):
    return _http.Response(
        status=status, url="", headers={"content-type": ctype}, content=body
    )


def _hits(*results):
    return _resp(
        200, json.dumps({"results": list(results)}).encode(), "application/json"
    )


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("CORE_API_KEY", raising=False)
    monkeypatch.setattr(core, "KEY_FILE", str(tmp_path / "absent.env"))
    monkeypatch.setattr(core, "_warned", False)


@pytest.fixture()
def net(monkeypatch):
    """Fake transport: the search answers ``search``, any other URL ``files``."""
    state = {"search": _hits(), "files": {}, "calls": []}

    def get(url, **kwargs):
        state["calls"].append((url, kwargs))
        answer = (
            state["search"]
            if url.startswith(core.SEARCH_URL)
            else state["files"].get(url, _resp(404))
        )
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(_http, "get", get)
    return state


def _req(tmp_path):
    return Request("doi", DOI, str(tmp_path / "p.pdf"))


def test_contract_names():
    assert core.NAME == "core" and core.ACCEPTS == frozenset({"doi"})


def test_key_from_environment_beats_file(monkeypatch, tmp_path):
    key_file = tmp_path / "core.env"
    key_file.write_text("CORE_API_KEY=from-file\n")
    monkeypatch.setattr(core, "KEY_FILE", str(key_file))
    assert core.get_key() == "from-file"
    monkeypatch.setenv("CORE_API_KEY", "from-env")
    assert core.get_key() == "from-env"


def test_key_file_forms(monkeypatch, tmp_path):
    key_file = tmp_path / "core.env"
    key_file.write_text("# c\nOTHER=1\nexport CORE_API_KEY='quoted'\n")
    monkeypatch.setattr(core, "KEY_FILE", str(key_file))
    assert core.get_key() == "quoted"


def test_no_key_anywhere_is_empty():
    assert core.get_key() == ""


def test_default_key_file_is_configurable_under_config_keys():
    from doifetch import config

    assert config.CORE_KEY_FILE.endswith("/.config/keys/core.env") or (
        "CORE_KEY_FILE" in __import__("os").environ
    )


def test_fetches_the_full_text_with_bearer_key(net, monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_API_KEY", KEY)
    net["search"] = _hits({"doi": DOI, "downloadUrl": DL})
    net["files"][DL] = _resp(200, PDF, "application/pdf")
    result = core.fetch(_req(tmp_path))
    assert result.status == "success" and result.source == "core"
    assert (tmp_path / "p.pdf").read_bytes() == PDF
    search_url, search_kwargs = net["calls"][0]
    assert search_kwargs["params"]["q"] == f'doi:"{DOI}"'
    assert search_kwargs["headers"]["Authorization"] == f"Bearer {KEY}"
    assert KEY not in search_url and KEY not in str(search_kwargs["params"])
    # the key never travels to the download host
    dl_url, dl_kwargs = net["calls"][1]
    assert dl_url == DL and "Authorization" not in (dl_kwargs.get("headers") or {})


def test_works_without_a_key_unauthenticated(net, tmp_path):
    net["search"] = _hits({"doi": DOI, "downloadUrl": DL})
    net["files"][DL] = _resp(200, PDF, "application/pdf")
    assert core.fetch(_req(tmp_path)).status == "success"
    assert "Authorization" not in (net["calls"][0][1].get("headers") or {})


def test_only_the_matching_doi_counts(net, tmp_path):
    other = "https://core.ac.uk/download/pdf/7.pdf"
    net["search"] = _hits(
        {"doi": "10.9999/other", "downloadUrl": other},
        {"doi": DOI.upper(), "downloadUrl": DL},
    )
    net["files"][DL] = _resp(200, PDF)
    assert core.fetch(_req(tmp_path)).status == "success"
    assert all(u != other for u, _ in net["calls"])


def test_falls_through_download_urls(net, tmp_path):
    first = "https://repo.example/dead.pdf"
    net["search"] = _hits(
        {"doi": DOI, "downloadUrl": first, "sourceFulltextUrls": [DL, first]}
    )
    net["files"][first] = _resp(500)
    net["files"][DL] = _resp(200, PDF)
    assert core.fetch(_req(tmp_path)).status == "success"


def test_no_hit_and_no_url_fail_with_a_reason(net, tmp_path):
    result = core.fetch(_req(tmp_path))
    assert result.status == "failed" and "CORE" in result.error
    net["search"] = _hits({"doi": DOI, "downloadUrl": None})
    result = core.fetch(_req(tmp_path))
    assert result.status == "failed" and "full text" in result.error


@pytest.mark.parametrize("status", [401, 403, 429])
def test_refusal_is_failed_with_hint_and_warned_once(net, caplog, tmp_path, status):
    net["search"] = _resp(status, b"<html>no</html>", "text/html")
    with caplog.at_level(logging.WARNING):
        first = core.fetch(_req(tmp_path))
        core.fetch(_req(tmp_path))
    assert first.status == "failed" and str(status) in first.error
    assert "CORE_API_KEY" in first.error
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_refusal_with_key_does_not_echo_it(net, monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_API_KEY", KEY)
    net["search"] = _resp(429)
    result = core.fetch(_req(tmp_path))
    assert result.status == "failed" and KEY not in result.error


def test_transport_error_is_scrubbed_in_every_encoding(net, monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_API_KEY", KEY)
    leak = f"boom {KEY} {urllib.parse.quote_plus(KEY)} {urllib.parse.quote(KEY)}"
    net["search"] = _http.HttpError(leak)
    result = core.fetch(_req(tmp_path))
    assert result.status == "failed" and "boom" in result.error
    for form in (KEY, urllib.parse.quote_plus(KEY), urllib.parse.quote(KEY)):
        assert form not in result.error


def test_bad_json_and_bugs_never_raise(net, monkeypatch, tmp_path):
    net["search"] = _resp(200, b"not json")
    assert core.fetch(_req(tmp_path)).status == "failed"
    net["search"] = _resp(200, b"[1]")
    assert core.fetch(_req(tmp_path)).status == "failed"
    net["search"] = RuntimeError("bug")
    assert core.fetch(_req(tmp_path)).status == "failed"


def test_non_pdf_download_is_rejected(net, tmp_path):
    net["search"] = _hits({"doi": DOI, "downloadUrl": DL})
    net["files"][DL] = _resp(200, b"<html>" + b"x" * 3000, "text/html")
    result = core.fetch(_req(tmp_path))
    assert result.status == "failed"
    assert not (tmp_path / "p.pdf").exists()
