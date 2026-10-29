"""Fetch open-access paper PDFs via the Crossref API."""

import json
import logging

from doifetch.config import TIMEOUT, UNPAYWALL_EMAIL
from doifetch.sources import _http
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result

logger = logging.getLogger(__name__)

NAME = "crossref"
ACCEPTS: frozenset[Kind] = frozenset({"doi"})


class DoiNotFoundError(Exception):
    """Raised when Crossref returns 404 for a DOI."""


def get_metadata(doi):
    """Return the Crossref `message` dict for a DOI.

    Raises DoiNotFoundError if the DOI is not registered in Crossref (404).
    Returns None on any other failure (network error, non-200 status, bad JSON).
    TLS is verified and the request carries a timeout and a contact address
    (Crossref polite pool).
    """
    try:
        response = _http.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": f"DOIfetch/1.0 (mailto:{UNPAYWALL_EMAIL})"},
            timeout=TIMEOUT,
        )
        if response.status == 404:
            raise DoiNotFoundError(f"DOI not found in Crossref (404): {doi}")
        if response.status != 200:
            logger.warning("Crossref API error %s for %s", response.status, doi)
            return None
        body = json.loads(response.text)
        if not isinstance(body, dict):
            logger.warning("Crossref returned a non-object body for %s", doi)
            return None
        return body.get("message", {})
    except DoiNotFoundError:
        raise
    except (_http.HttpError, ValueError) as e:
        logger.warning("Crossref metadata request failed for %s: %s", doi, e)
        return None


def get_pdf_url(doi):
    """Use the Crossref API to get a PDF download link.

    Raises DoiNotFoundError if the DOI is not registered in Crossref.
    Returns None if registered but no open-access PDF link is available.
    """
    message = get_metadata(doi)
    if not message:
        return None
    pdf_links = [
        link["URL"]
        for link in message.get("link", [])
        if link.get("content-type") == "application/pdf"
        and link.get("content-version") == "vor"
    ]
    return pdf_links[0] if pdf_links else None


def _fetch(req: Request) -> Result:
    if (done := already_there(req, NAME)) is not None:
        return done
    try:
        pdf_url = get_pdf_url(req.identifier)
    except DoiNotFoundError as e:
        return Result("failed", NAME, error=str(e))
    if not pdf_url:
        return Result("failed", NAME, error="No open access PDF found in Crossref")
    paper = _http.get(pdf_url, timeout=60)
    if paper.status != 200:
        return Result("failed", NAME, error=f"PDF download failed: {paper.status}")
    return save_pdf(req, NAME, paper.content, "Broken PDF file")


def fetch(req: Request) -> Result:
    """Fetch the DOI's open-access PDF to ``req.path``."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))
