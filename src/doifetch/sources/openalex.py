"""Fetch open-access PDFs through OpenAlex, trying every known location.

Unpaywall reports one best open-access link; OpenAlex lists every known copy
(``locations[].pdf_url``: publisher, repository, preprint server). The locations
are tried in order until one yields a valid PDF, so a dead or blocked first link
has fallbacks. Key handling lives in ``sources/_openalex.py``.
"""

from doifetch.config import TIMEOUT
from doifetch.sources import _http, _openalex
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result

NAME = "openalex"
ACCEPTS: frozenset[Kind] = frozenset({"doi"})


def pdf_urls(work: dict) -> list[str]:
    """Every distinct ``pdf_url`` of the work's locations, in order."""
    urls: list[str] = []
    for location in work.get("locations") or []:
        url = (location or {}).get("pdf_url")
        if isinstance(url, str) and url and url not in urls:
            urls.append(url)
    return urls


def _fetch(req: Request) -> Result:
    if (done := already_there(req, NAME)) is not None:
        return done
    try:
        work = _openalex.get_work(req.identifier)
    except _openalex.OpenAlexError as exc:
        return Result("failed", NAME, error=str(exc))
    urls = pdf_urls(work)
    if not urls:
        return Result("failed", NAME, error="No open access PDF location in OpenAlex")
    errors = []
    for url in urls:
        try:
            response = _http.get(url, timeout=TIMEOUT * 2)
        except _http.HttpError as exc:
            errors.append(str(exc))
            continue
        if response.status != 200:
            errors.append(f"PDF download failed: {response.status} ({url})")
            continue
        result = save_pdf(req, NAME, response.content, "Broken PDF file")
        if result.status == "success":
            return result
        errors.append(f"{result.error} ({url})")
    return Result("failed", NAME, error="; ".join(errors))


def fetch(req: Request) -> Result:
    """Fetch the first working open-access location of the DOI to ``req.path``."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))
