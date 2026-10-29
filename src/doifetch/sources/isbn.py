"""Fetch an open-access book by ISBN: Crossref gives its DOI, the DOI sources its PDF.

``works?filter=isbn:`` lists the DOIs registered under an ISBN, the book's own
and one per chapter. Only book-level records are used, so a chapter's PDF is
never saved under the book's name. Each book DOI then goes through the default
cascade as a DOI request, so every open (and configured institutional) DOI
source is tried without this module naming any of them.
"""

import json
import logging

from doifetch import api
from doifetch.config import TIMEOUT, UNPAYWALL_EMAIL
from doifetch.sources import _http
from doifetch.sources._pdf import already_there
from doifetch.sources.contract import Kind, Request, Result

logger = logging.getLogger(__name__)

NAME = "isbn"
ACCEPTS: frozenset[Kind] = frozenset({"isbn"})

# Crossref `type` values of a whole book, preferred first. Seen on real ISBNs
# (2026-10-29): book-chapter (most rows), edited-book, monograph.
BOOK_TYPES = ("book", "monograph", "edited-book", "reference-book")
MAX_DOIS = 3
LOOKUP_URL = (
    "https://api.crossref.org/works?filter=isbn:{isbn},"
    + ",".join(f"type:{t}" for t in BOOK_TYPES)
    + "&rows=10&select=DOI,type"
)


def book_dois(isbn: str) -> list[str]:
    """Book-level DOIs registered for ``isbn``, preferred type first.

    Raises ``_http.HttpError`` or ``ValueError`` when the lookup itself fails.
    """
    response = _http.get(
        LOOKUP_URL.format(isbn=isbn),
        headers={"User-Agent": f"DOIfetch/1.0 (mailto:{UNPAYWALL_EMAIL})"},
        timeout=TIMEOUT,
    )
    if response.status != 200:
        raise ValueError(f"Crossref ISBN lookup error: {response.status}")
    items = json.loads(response.text)["message"]["items"]
    rank = {t: i for i, t in enumerate(BOOK_TYPES)}
    books = sorted(
        (i for i in items if i.get("DOI") and i.get("type") in rank),
        key=lambda i: rank[i["type"]],
    )
    return [i["DOI"] for i in books][:MAX_DOIS]


def _fetch(req: Request) -> Result:
    if (done := already_there(req, NAME)) is not None:
        return done
    dois = book_dois(req.identifier)
    if not dois:
        return Result("failed", NAME, error="No book-level DOI found in Crossref")
    reasons = []
    for doi in dois:
        result = api.cascade(Request("doi", doi, req.path), api.DEFAULT_ORDER)
        if result.status != "failed":
            return Result(result.status, NAME, path=result.path)
        reasons.append(f"{doi}: {result.error}")
    return Result("failed", NAME, error="No open copy; " + "; ".join(reasons))


def fetch(req: Request) -> Result:
    """Fetch the book's open-access PDF to ``req.path``."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))
