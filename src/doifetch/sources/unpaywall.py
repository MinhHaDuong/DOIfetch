"""Fetch open-access paper PDFs via the Unpaywall API."""

import json

from doifetch.config import UNPAYWALL_EMAIL
from doifetch.sources import _http
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result

NAME = "unpaywall"
ACCEPTS: frozenset[Kind] = frozenset({"doi"})


def _fetch(req: Request) -> Result:
    if (done := already_there(req, NAME)) is not None:
        return done
    url = f"https://api.unpaywall.org/v2/{req.identifier}?email={UNPAYWALL_EMAIL}"
    response = _http.get(url, timeout=30)
    if response.status != 200:
        return Result("failed", NAME, error=f"Unpaywall API error: {response.status}")
    oa = json.loads(response.text).get("best_oa_location")
    if not oa or not oa.get("url_for_pdf"):
        return Result("failed", NAME, error="No open access PDF found")
    pdf_resp = _http.get(oa["url_for_pdf"], timeout=60)
    if pdf_resp.status != 200:
        return Result("failed", NAME, error=f"PDF download failed: {pdf_resp.status}")
    return save_pdf(req, NAME, pdf_resp.content, "Broken PDF file")


def fetch(req: Request) -> Result:
    """Fetch the DOI's best open-access PDF to ``req.path``."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))
