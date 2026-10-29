"""Fetch open-access paper PDFs from the HAL archive by author and title search."""

import json
import os
import re

from doifetch.config import HEADERS, TIMEOUT
from doifetch.sources import _http
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result

NAME = "hal"
ACCEPTS: frozenset[Kind] = frozenset({"doi"})

HAL_SEARCH_URL = "https://api.archives-ouvertes.fr/search/"


def _parse_author_title(title):
    """Extract first author surname and title keywords from reference string.

    Expected format: 'Author et al. Year - Actual Title' or 'Author & Other Year - Title'
    Returns (author_surname, title_keywords) or (None, None) if unparseable.
    """
    match = re.match(r"^([A-Za-zÀ-ÿ]+).*?\d{4}\s*[-–—]\s*(.+)$", title)
    if match:
        return match.group(1), match.group(2)
    return None, None


def _clean_title_keywords(raw):
    """Sanitize title keywords for HAL query: strip special chars and truncation markers."""
    # Remove truncation artifacts like trailing '...' or 'E...'
    raw = re.sub(r"\s*\w{0,3}\.\.\.$", "", raw).strip()
    # Remove characters that break Solr query syntax
    raw = re.sub(r"[`'\"\\(){}[\]^~*?:/]", " ", raw)
    # Collapse whitespace
    return re.sub(r"\s+", " ", raw).strip()


def _search_hal(author, title_keywords):
    """Search HAL for a paper by author surname and title keywords.

    Returns the PDF URL or None.
    """
    title_keywords = _clean_title_keywords(title_keywords)
    query = f"authLastName_t:{author} AND title_t:({title_keywords})"
    params = {
        "q": query,
        "rows": 5,
        "wt": "json",
        "fl": "halId_s,title_s,fileMain_s",
    }
    response = _http.get(HAL_SEARCH_URL, params=params, timeout=TIMEOUT)
    if response.status != 200:
        return None
    data = json.loads(response.text)
    docs = data.get("response", {}).get("docs", [])
    for doc in docs:
        pdf_url = doc.get("fileMain_s")
        if pdf_url:
            return pdf_url
    return None


def _fetch(req: Request) -> Result:
    if (done := already_there(req, NAME)) is not None:
        return done
    # The caller names the file "Author Year - Title"; HAL is searched on that.
    title = os.path.basename(req.path).removesuffix(".pdf")
    author, title_keywords = _parse_author_title(title)
    if not author or not title_keywords:
        return Result("failed", NAME, error="Cannot parse author/title for HAL search")
    pdf_url = _search_hal(author, title_keywords)
    if not pdf_url:
        return Result("failed", NAME, error="No PDF found on HAL")
    pdf_resp = _http.get(pdf_url, headers=HEADERS, timeout=TIMEOUT)
    if pdf_resp.status != 200:
        return Result(
            "failed", NAME, error=f"HAL PDF download failed: {pdf_resp.status}"
        )
    return save_pdf(req, NAME, pdf_resp.content, "Downloaded file is not a valid PDF")


def fetch(req: Request) -> Result:
    """Search HAL on the file name's author and title and fetch the PDF."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))
