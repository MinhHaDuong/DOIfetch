"""Fetch paper PDFs directly from a URL."""

from doifetch.config import HEADERS, TIMEOUT
from doifetch.sources import _http
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result

NAME = "url"
ACCEPTS: frozenset[Kind] = frozenset({"url"})


def _fetch(req: Request) -> Result:
    if (done := already_there(req, NAME)) is not None:
        return done
    response = _http.get(req.identifier, headers=HEADERS, timeout=TIMEOUT)
    if response.status != 200:
        return Result("failed", NAME, error=f"HTTP {response.status}")
    return save_pdf(req, NAME, response.content, "Downloaded file is not a valid PDF")


def fetch(req: Request) -> Result:
    """Download the PDF at ``req.identifier`` to ``req.path``."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))
