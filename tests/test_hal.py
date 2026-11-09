"""HAL source, offline: a download HAL's bot check accepts.

Recorded shapes (2026-11-09, Briera & Lefevre 2024): the search API answers a
``doiId_s`` query with the deposit and its ``fileMain_s``; the file host serves an
"anti-bot" HTML page with status 200 to a ``Mozilla/...`` User-Agent and the PDF
to any other one.
"""

import json
from types import SimpleNamespace

from doifetch.sources import _http, hal
from doifetch.sources.contract import Request

DOI = "10.1016/j.enpol.2024.114104"
FILE_URL = "https://hal.science/hal-04824002/document"
PDF = b"%PDF-1.4\n" + b"x" * 2000
BOT_PAGE = b"<!doctype html><title>Making sure you're not a bot!</title>"
# The name the CLI really gives this DOI: the title is cut at 120 characters.
TRUNCATED = "Briera 2024 - Reducing the cost of capital through international climate finance to accelerate the renewable energy tran"


def _resp(status=200, body=b""):
    return SimpleNamespace(
        status=status, content=body, text=body.decode("utf-8", "replace")
    )


def _hits(*docs):
    return _resp(body=json.dumps({"response": {"docs": list(docs)}}).encode())


class FakeHal:
    """Stands in for ``_http.get``; the file host applies the bot check on the UA."""

    def __init__(self, monkeypatch, search):
        self.search = search  # callable(query) -> response
        self.queries = []
        self.file_headers = []
        monkeypatch.setattr(_http, "get", self)

    def __call__(self, target, **kwargs):
        if "archives-ouvertes.fr/search" in target:
            query = kwargs["params"]["q"]
            self.queries.append(query)
            return self.search(query)
        headers = kwargs.get("headers") or {}
        self.file_headers.append(headers)
        agent = headers.get("User-Agent", _http.DEFAULT_USER_AGENT)
        return _resp(body=BOT_PAGE if "Mozilla" in agent else PDF)


def _found(query):
    return _hits({"halId_s": "hal-04824002", "fileMain_s": FILE_URL})


def test_download_does_not_present_a_browser_user_agent(monkeypatch, tmp_path):
    fake = FakeHal(monkeypatch, _found)
    req = Request("doi", DOI, str(tmp_path / "Briera 2024 - T.pdf"))
    assert hal.fetch(req).status == "success"
    agent = fake.file_headers[0]["User-Agent"]
    assert "Mozilla" not in agent and "DOIfetch" in agent
    assert (tmp_path / "Briera 2024 - T.pdf").read_bytes() == PDF


def test_bot_check_page_is_reported_as_such(monkeypatch, tmp_path):
    def blocked(target, **kwargs):
        if "search" in target:
            return _found(kwargs["params"]["q"])
        return _resp(body=BOT_PAGE)

    monkeypatch.setattr(_http, "get", blocked)
    req = Request("doi", DOI, str(tmp_path / "Briera 2024 - T.pdf"))
    result = hal.fetch(req)
    assert result.status == "failed" and "not a valid PDF" in result.error
    assert list(tmp_path.iterdir()) == []
