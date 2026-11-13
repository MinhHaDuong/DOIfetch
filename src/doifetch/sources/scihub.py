"""Fetch paper PDFs from Sci-Hub and its SciDB (Anna's Archive) successor."""

import random
import time
from urllib.parse import quote

from doifetch.config import (
    HEADERS,
    MAX_DELAY,
    MIN_DELAY,
    SCI_HUB_DOMAINS,
    SCIDB_DOMAINS,
    TIMEOUT,
)
from doifetch.sources import _html, _http
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result


def build_query_urls(doi, title):
    """Resolver URLs to try in order, most reliable first.

    With a DOI: classic Sci-Hub pages first (frozen corpus, freely scrapable
    iframe), then SciDB via Anna's Archive (broader/updated corpus). Without a
    DOI: fall back to a Sci-Hub title search, which SciDB does not offer.
    """
    if doi:
        scihub = [f"{domain}{doi}" for domain in SCI_HUB_DOMAINS]
        scidb = [f"{domain}scidb/{doi}" for domain in SCIDB_DOMAINS]
        return scihub + scidb
    return [f"{domain}?s={quote(title)}" for domain in SCI_HUB_DOMAINS]


def extract_pdf_url(content):
    """Return the embedded PDF URL from a Sci-Hub/SciDB viewer page, or None.

    ``content`` is ``str`` or the raw response ``bytes``, which are decoded as
    UTF-8 with replacement (see ``_html.parse``). The first iframe wins over any
    embed, even when it carries no ``src``.
    """
    src = _html.parse(content).frame_src
    if not src:
        return None
    if src.startswith("//"):  # protocol-relative src, common on Sci-Hub
        src = "https:" + src
    return src if src.startswith("http") else None


NAME = "scihub"
ACCEPTS: frozenset[Kind] = frozenset({"doi", "title"})


def _fetch(req: Request) -> Result:
    doi = req.identifier if req.kind == "doi" else ""
    title = req.identifier if req.kind == "title" else ""
    label = doi or title
    if (done := already_there(req, NAME)) is not None:
        return done

    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    last_error = ""

    for query_url in build_query_urls(doi, title):
        try:
            response = _http.get(query_url, headers=HEADERS, timeout=TIMEOUT)
            pdf_url = extract_pdf_url(response.content)
            if not pdf_url:
                last_error = f"{label} | Error: PDF link not found | URL: {query_url}"
                continue

            pdf_response = _http.get(pdf_url, headers=HEADERS, timeout=TIMEOUT)
            if not pdf_response.ok:
                last_error = (
                    f"{label} | Error: HTTP {pdf_response.status} | URL: {pdf_url}"
                )
                continue
            saved = save_pdf(req, NAME, pdf_response.content, "Broken PDF file")
            if saved.status == "success":
                return saved
            last_error = f"{label} | Error: {saved.error} | URL: {query_url}"
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            last_error = f"{label} | Error: {str(exc)[:50]} | URL: {query_url}"

    return Result("failed", NAME, error=last_error or f"{label} | Error: Unknown error")


def fetch(req: Request) -> Result:
    """Download the paper for ``req`` from Sci-Hub, then SciDB (Anna's Archive)."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))
