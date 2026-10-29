"""Book metadata by ISBN (Open Library, then Google Books), as Crossref-shaped messages.

Each provider returns a dict with `title`, `subtitle`, `author` and `issued` keys
(the subset of a Crossref message that `naming` reads), or None when it has no
usable record. Providers never raise.
"""

import logging
import re

import requests

from config import TIMEOUT

logger = logging.getLogger(__name__)

OPEN_LIBRARY_URL = "https://openlibrary.org/api/books"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


def _author(name):
    """Author entry whose `family` is the last word of a personal name."""
    name = " ".join((name or "").split())
    if not name:
        return None
    return {"family": name.split(" ")[-1], "name": name}


def _year(text):
    match = re.search(r"\d{4}", text or "")
    return int(match.group()) if match else None


def _message(title, subtitle, names, date):
    if not title:
        return None
    authors = [a for a in (_author(n) for n in names) if a]
    year = _year(date)
    return {
        "title": [title],
        "subtitle": [subtitle] if subtitle else [],
        "author": authors,
        "issued": {"date-parts": [[year]]} if year else {},
    }


def open_library(isbn):
    """Open Library `api/books?jscmd=data` record for `isbn`, or None."""
    try:
        response = requests.get(
            OPEN_LIBRARY_URL,
            params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            logger.info("Open Library status %s for %s", response.status_code, isbn)
            return None
        record = (response.json() or {}).get(f"ISBN:{isbn}")
        if not record:
            return None
        names = [a.get("name", "") for a in record.get("authors") or []]
        return _message(
            record.get("title"),
            record.get("subtitle"),
            names,
            record.get("publish_date"),
        )
    except Exception as exc:  # noqa: BLE001 - providers never raise into the caller
        logger.info("Open Library lookup failed for %s: %s", isbn, exc)
        return None


def google_books(isbn):
    """Google Books volume for `isbn`, or None. Best effort: the keyless quota is shared."""
    try:
        response = requests.get(
            GOOGLE_BOOKS_URL, params={"q": f"isbn:{isbn}"}, timeout=TIMEOUT
        )
        if response.status_code != 200:
            logger.info("Google Books status %s for %s", response.status_code, isbn)
            return None
        items = (response.json() or {}).get("items") or []
        if not items:
            return None
        info = items[0].get("volumeInfo") or {}
        return _message(
            info.get("title"),
            info.get("subtitle"),
            info.get("authors") or [],
            info.get("publishedDate"),
        )
    except Exception as exc:  # noqa: BLE001 - providers never raise into the caller
        logger.info("Google Books lookup failed for %s: %s", isbn, exc)
        return None


# Ordered: first provider with a record wins.
PROVIDERS = (open_library, google_books)


def get_metadata(isbn):
    """Return a Crossref-shaped message for `isbn` from the first provider that has one."""
    for provider in PROVIDERS:
        message = provider(isbn)
        if message:
            return message
    return None
