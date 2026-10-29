"""Name downloaded files from DOI (Crossref) or ISBN (book providers) metadata and flag title mismatches."""

import html
import logging
import re
import unicodedata
from difflib import SequenceMatcher

import fetch_bookmeta
import fetch_crossref
from pdf_utils import MAX_NAME_LENGTH, clean_filename
from utils import normalize_isbn

logger = logging.getLogger(__name__)

# Similarity at or above which the caller's title is taken to match Crossref's.
MATCH_THRESHOLD = 0.7


def _plain(text):
    """Strip JATS/HTML tags and entities and collapse whitespace."""
    text = html.unescape(re.sub(r"<[^>]+>", "", text or ""))
    return " ".join(text.split())


def _first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def _crossref_titles(message):
    """Return (title, title + subtitle), tags stripped; ("", "") when absent."""
    title = _plain(_first(message.get("title")))
    subtitle = _plain(_first(message.get("subtitle")))
    full = f"{title}: {subtitle}" if title and subtitle else title
    return title, full


def _year(message):
    for key in ("issued", "published-print", "published-online"):
        parts = (message.get(key) or {}).get("date-parts")
        if not (isinstance(parts, list) and parts and isinstance(parts[0], list)):
            continue
        if parts[0] and parts[0][0]:
            return str(parts[0][0])
    return ""


def _first_author(message):
    authors = message.get("author") or []
    if not authors:
        return ""
    first = authors[0]
    return _plain(first.get("family") or first.get("name") or "")


def compose_name(message):
    """Build `<FirstAuthor> <Year> - <Title>` from a Crossref message.

    Returns None when the record has no title. The title is shortened, never the
    author/year prefix, so the result survives clean_filename's length cut.
    """
    _, full = _crossref_titles(message)
    if not full:
        return None
    prefix = " ".join(p for p in (_first_author(message), _year(message)) if p)
    head = clean_filename(f"{prefix} - ") if prefix else ""
    room = max(MAX_NAME_LENGTH - len(head), 0)
    return head + clean_filename(full)[:room].rstrip() if room else head.rstrip()


def _normalise(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", text))


def titles_match(caller_title, message):
    """True when the caller's title plausibly names the same work as Crossref's.

    A caller title shaped `Author Year - Title` is compared by its part after the
    first ` - `. Either a similar ratio or substring containment (for truncated
    or subtitle-less titles) counts as a match.
    """
    title, full = _crossref_titles(message)
    candidate = (
        caller_title.split(" - ", 1)[1] if " - " in caller_title else caller_title
    )
    a = _normalise(candidate)
    if not a:
        return True
    for ref in (title, full):
        b = _normalise(ref)
        if not b:
            continue
        if a in b or b in a:
            return True
        if SequenceMatcher(None, a, b).ratio() >= MATCH_THRESHOLD:
            return True
    return False


def resolve_name(doi, title, keep_title=False):
    """Return the name (without extension) to give the file for `doi`.

    `doi` may also be `isbn:<isbn>`, looked up through fetch_bookmeta's provider chain.

    The caller's `title` is returned byte-identical when it matches Crossref or
    `keep_title` is set. A clear mismatch logs a warning and yields the name built
    from Crossref. Without a title the Crossref name is used. Any lookup failure
    falls back to `title` (possibly empty) with a logged note; never raises.
    """
    title = title or ""
    if keep_title and title:
        return title
    if not doi or doi.startswith(("http://", "https://")):
        return title
    lookup = fetch_crossref.get_metadata
    if doi.startswith("isbn:"):
        doi = normalize_isbn(doi)
        if not doi:
            return title
        lookup = fetch_bookmeta.get_metadata
    try:
        message = lookup(doi)
        composed = compose_name(message) if message else None
    except Exception as exc:  # noqa: BLE001 - naming is best effort; fall back to the caller name
        logger.info("No DOI metadata for %s (%s); keeping caller name", doi, exc)
        return title
    if composed is None:
        logger.info("No usable DOI metadata for %s; keeping caller name", doi)
        return title
    if not title:
        return composed
    if titles_match(title, message):
        return title
    logger.warning(
        "Title mismatch for %s: caller gave %r, metadata has %r; naming file %r "
        "(pass --keep-title to force the caller's name)",
        doi,
        title,
        _crossref_titles(message)[1],
        composed,
    )
    return composed
