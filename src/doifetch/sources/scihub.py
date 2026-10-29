"""Fetch paper PDFs from Sci-Hub and its SciDB (Anna's Archive) successor."""

import os
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
from doifetch.sources import _http
from doifetch.sources.contract import Kind, Request, Result


def _soup(html):
    """Parse HTML with bs4, which ships in the 'shadow' extra only."""
    from doifetch.utils import require

    return require("bs4", "shadow").BeautifulSoup(html, "html.parser")


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
    """Return the embedded PDF URL from a Sci-Hub/SciDB viewer page, or None."""
    soup = _soup(content)
    node = soup.find("iframe") or soup.find("embed")
    if not node:
        return None
    src = node.get("src")
    if not src:
        return None
    if src.startswith("//"):  # protocol-relative src, common on Sci-Hub
        src = "https:" + src
    return src if src.startswith("http") else None


NAME = "scihub"
ACCEPTS: frozenset[Kind] = frozenset({"doi"})


def fetch(req: Request) -> Result:
    """Download the paper for ``req`` from Sci-Hub, then SciDB (Anna's Archive)."""
    from doifetch.pdf_utils import is_valid_pdf
    from doifetch.utils import require

    try:
        require("bs4", "shadow")
    except ImportError as exc:
        return Result("failed", NAME, error=str(exc))

    doi = req.identifier
    if os.path.exists(req.path):
        if is_valid_pdf(req.path):
            return Result("skipped", NAME, path=req.path)
        os.remove(req.path)

    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    last_error = ""

    for query_url in build_query_urls(doi, ""):
        try:
            response = _http.get(query_url, headers=HEADERS, timeout=TIMEOUT)
            pdf_url = extract_pdf_url(response.content)
            if not pdf_url:
                last_error = f"{doi} | Error: PDF link not found | URL: {query_url}"
                continue

            pdf_response = _http.get(pdf_url, headers=HEADERS, timeout=TIMEOUT)
            if not pdf_response.ok:
                last_error = (
                    f"{doi} | Error: HTTP {pdf_response.status} | URL: {pdf_url}"
                )
                continue
            with open(req.path, "wb") as file_handle:
                file_handle.write(pdf_response.content)
            if not is_valid_pdf(req.path):
                os.remove(req.path)
                last_error = f"{doi} | Error: Broken PDF file | URL: {query_url}"
                continue
            return Result("success", NAME, path=req.path)
        except Exception as exc:  # noqa: BLE001 - a fetcher reports failure, never raises into the fetch loop
            if os.path.exists(req.path) and not is_valid_pdf(req.path):
                os.remove(req.path)
            last_error = f"{doi} | Error: {str(exc)[:50]} | URL: {query_url}"

    return Result("failed", NAME, error=last_error or f"{doi} | Error: Unknown error")
