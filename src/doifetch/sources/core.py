"""Fetch open-access full texts through CORE (core.ac.uk, API v3).

CORE aggregates full texts harvested from institutional repositories, including
theses and accepted manuscripts that Unpaywall sometimes misses. The DOI is
looked up with ``/v3/search/works?q=doi:"..."``; a work's ``downloadUrl`` (and
``sourceFulltextUrls``) are tried in order until one yields a valid PDF.

Terms (docs at api.core.ac.uk/docs/v3, checked 2026-10-29): the API is usable
without registration under a token budget (unauthenticated: 100 tokens per day,
at most 10 per minute; a registered key raises it to 1,000 per day, 25 per
minute); the key travels as ``Authorization: Bearer <key>``. Without a key the
request is sent anyway, and a refusal (401, 403, 429) is a ``failed`` result
with the reason.

Key: ``CORE_API_KEY`` from the environment, else a ``CORE_API_KEY=...`` line in
``CORE_KEY_FILE`` (default ``~/.config/keys/core.env``, see ``config.py``). The
key goes to the CORE API only, never to a download host, and is scrubbed from
every message and log line this module produces.
"""

import json
import logging
import os
import urllib.parse

from doifetch.config import CORE_KEY_FILE, TIMEOUT
from doifetch.sources import _http
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result

logger = logging.getLogger(__name__)

NAME = "core"
ACCEPTS: frozenset[Kind] = frozenset({"doi"})

KEY_ENV = "CORE_API_KEY"
KEY_FILE = CORE_KEY_FILE
SEARCH_URL = "https://api.core.ac.uk/v3/search/works"
# Statuses CORE answers when it wants a key, or the token budget is spent.
REFUSED = (401, 402, 403, 429)

_warned = False


class CoreError(Exception):
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


def _scrub(text: str, key: str) -> str:
    if key:  # the raw key and its URL-encoded forms
        for form in {key, urllib.parse.quote_plus(key), urllib.parse.quote(key)}:
            text = text.replace(form, "***")
    return text


def _warn_once(message: str) -> None:
    global _warned
    if not _warned:
        _warned = True
        logger.warning("%s", message)


def _search(doi: str) -> list[dict]:
    key = get_key()
    try:
        response = _http.get(
            SEARCH_URL,
            params={"q": f'doi:"{doi}"', "limit": "5"},
            headers={"Authorization": f"Bearer {key}"} if key else None,
            timeout=TIMEOUT,
        )
    except _http.HttpError as exc:
        raise CoreError(f"CORE request failed: {_scrub(str(exc), key)}") from None
    if response.status in REFUSED:
        hint = (
            "the key was refused or its limit is reached"
            if key
            else f"set {KEY_ENV} or put it in {KEY_FILE}"
        )
        message = f"CORE refused the request ({response.status}): {hint}"
        _warn_once(message)
        raise CoreError(message)
    if response.status != 200:
        raise CoreError(f"CORE API error: {response.status}")
    try:
        body = json.loads(response.text)
    except ValueError:
        raise CoreError("CORE returned a body that is not JSON") from None
    if not isinstance(body, dict):
        raise CoreError("CORE returned a non-object body")
    results = body.get("results")
    return (
        [r for r in results if isinstance(r, dict)] if isinstance(results, list) else []
    )


def download_urls(works: list[dict], doi: str) -> list[str]:
    """Distinct full-text URLs of the works whose DOI is ``doi``, in order."""
    wanted = doi.strip().lower()
    urls: list[str] = []
    for work in works:
        found = work.get("doi")
        if not isinstance(found, str) or found.strip().lower() != wanted:
            continue
        candidates = [work.get("downloadUrl")]
        extra = work.get("sourceFulltextUrls")
        candidates += extra if isinstance(extra, list) else []
        for url in candidates:
            if isinstance(url, str) and url and url not in urls:
                urls.append(url)
    return urls


def _fetch(req: Request) -> Result:
    if (done := already_there(req, NAME)) is not None:
        return done
    try:
        works = _search(req.identifier)
    except CoreError as exc:
        return Result("failed", NAME, error=str(exc))
    if not works:
        return Result("failed", NAME, error=f"DOI not found in CORE: {req.identifier}")
    urls = download_urls(works, req.identifier)
    if not urls:
        return Result("failed", NAME, error="No full text URL in CORE")
    errors = []
    for url in urls:
        try:
            response = _http.get(url, timeout=TIMEOUT * 2)  # never with the key
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
    """Fetch the first working CORE full text of the DOI to ``req.path``."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=_scrub(str(e), get_key()))
