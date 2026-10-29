"""OpenAlex access shared by the ``openalex`` source and the naming fallback.

Kept apart from ``sources/openalex.py`` so that naming can look a work up
without importing the source module. Importing this module has no side effect:
the key file is read, and the network touched, only when a lookup runs.

Key: ``OPENALEX_API_KEY`` from the environment, else an ``OPENALEX_API_KEY=...``
line in ``OPENALEX_KEY_FILE`` (default ``~/.config/keys/openalex.env``, see
``config.py``). The key travels as a query parameter and is scrubbed from every
message and log line this module produces.
"""

import json
import logging
import os
import urllib.parse

from doifetch.config import OPENALEX_KEY_FILE, TIMEOUT
from doifetch.sources import _http

logger = logging.getLogger(__name__)

KEY_ENV = "OPENALEX_API_KEY"
KEY_FILE = OPENALEX_KEY_FILE
WORKS_URL = "https://api.openalex.org/works/doi:"
# Statuses OpenAlex answers when it wants a key, or the key's budget is spent.
REFUSED = (401, 402, 403, 429)

_warned = False


class OpenAlexError(Exception):
    """A lookup that gave no work; the message is safe to print (no key)."""


def _key_from_file(path: str) -> str:
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :]
        name, sep, value = line.partition("=")
        if sep and name.strip() == KEY_ENV:
            return value.strip().strip("\"'")
    return ""


def get_key() -> str:
    """The API key from the environment, else the key file; '' when none."""
    return os.environ.get(KEY_ENV, "").strip() or _key_from_file(KEY_FILE)


def _warn_once(message: str) -> None:
    global _warned
    if not _warned:
        _warned = True
        logger.warning("%s", message)


def get_work(doi: str) -> dict:
    """The OpenAlex work record for ``doi``.

    Raises ``OpenAlexError`` (404, a refusal, a bad body, a transport failure).
    A refusal (key required, or the limit reached) is warned about once per run.
    """
    key = get_key()
    url = WORKS_URL + urllib.parse.quote(doi, safe="/")
    try:
        response = _http.get(
            url, params={"api_key": key} if key else None, timeout=TIMEOUT
        )
    except _http.HttpError as exc:
        text = str(exc)
        if key:  # the raw key and its URL-encoded form, as it travels
            for form in {key, urllib.parse.quote_plus(key), urllib.parse.quote(key)}:
                text = text.replace(form, "***")
        raise OpenAlexError(f"OpenAlex request failed: {text}") from None
    if response.status == 404:
        raise OpenAlexError(f"DOI not found in OpenAlex (404): {doi}")
    if response.status in REFUSED:
        hint = (
            "the key was refused or its limit is reached"
            if key
            else f"set {KEY_ENV} or put it in {KEY_FILE}"
        )
        message = f"OpenAlex refused the request ({response.status}): {hint}"
        _warn_once(message)
        raise OpenAlexError(message)
    if response.status != 200:
        raise OpenAlexError(f"OpenAlex API error: {response.status}")
    try:
        work = json.loads(response.text)
    except ValueError:
        raise OpenAlexError("OpenAlex returned a body that is not JSON") from None
    if not isinstance(work, dict):
        raise OpenAlexError("OpenAlex returned a non-object body")
    return work


def as_crossref_message(work: dict) -> dict:
    """The few fields naming reads, in the shape of a Crossref ``message``."""
    message: dict = {}
    title = work.get("title") or work.get("display_name")
    if isinstance(title, str) and title:
        message["title"] = [title]
    year = work.get("publication_year")
    if isinstance(year, int) and year:
        message["issued"] = {"date-parts": [[year]]}
    authors = []
    for authorship in work.get("authorships") or []:
        name = ((authorship or {}).get("author") or {}).get("display_name")
        if isinstance(name, str) and name.split():
            authors.append({"family": name.split()[-1]})
    if authors:
        message["author"] = authors
    return message


def get_metadata(doi: str) -> dict | None:
    """Crossref-shaped metadata for ``doi``, or None when OpenAlex has none.

    The naming fallback: best effort, never raises.
    """
    try:
        return as_crossref_message(get_work(doi))
    except OpenAlexError as exc:
        logger.info("No OpenAlex metadata for %s (%s)", doi, exc)
        return None
