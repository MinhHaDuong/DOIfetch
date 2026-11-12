"""Optional dedup against a local Zotero library.

DOIfetch consults the user's Zotero SQLite database before downloading, so a
paper already held in the library (an item with its PDF) is skipped rather
than refetched. The check
is auto-enabled whenever a Zotero DB can be located and degrades silently to
"no hit" when it cannot (missing, locked, or unreadable DB) — it must never
raise into the fetch loop.
"""

import configparser
import logging
import os
import re
import sqlite3
from configparser import ConfigParser
from pathlib import Path

logger = logging.getLogger(__name__)

# Overridable in tests to fake the user's home directory.
_HOME = Path.home()

# Jaccard threshold for the title fallback. High on purpose: a false positive
# suppresses a legitimate fetch, so we only skip on a near-exact title match.
TITLE_MATCH_THRESHOLD = 0.85

# Zotero's attachment link modes that are not a file in its own storage.
_LINKED_FILE = 2
_LINKED_URL = 3


def find_zotero_db(override: str | None = None) -> Path | None:
    """Locate the Zotero SQLite database, or return None if none is found.

    Precedence: explicit `override`, then `$ZOTERO_DB_PATH`, then
    `$ZOTERO_DATA_DIR`, then the standard per-OS locations, then any dataDir
    declared in a Firefox-style `profiles.ini`.
    """
    candidates: list[Path] = []

    explicit = override or os.environ.get("ZOTERO_DB_PATH")
    if explicit:
        candidates.append(Path(explicit))

    data_dir = os.environ.get("ZOTERO_DATA_DIR")
    if data_dir:
        candidates.append(Path(data_dir) / "zotero.sqlite")

    candidates += [
        _HOME / "Zotero" / "zotero.sqlite",
        _HOME / "data" / "Zotero" / "zotero.sqlite",
        _HOME / "Documents" / "Zotero" / "zotero.sqlite",
    ]

    candidates += _profiles_ini_candidates()

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _profiles_ini_candidates() -> list[Path]:
    """Zotero DB paths declared via a Firefox-style profiles.ini, if any."""
    profiles_ini = _HOME / ".zotero" / "zotero" / "profiles.ini"
    if not profiles_ini.exists():
        return []
    try:
        parser = ConfigParser()
        parser.read(profiles_ini)
    except (OSError, configparser.Error):
        return []

    found: list[Path] = []
    for section in parser.sections():
        rel_path = parser.get(section, "Path", fallback=None)
        if not rel_path:
            continue
        is_relative = parser.getint(section, "IsRelative", fallback=1)
        base = profiles_ini.parent if is_relative else Path("/")
        prefs = base / rel_path / "prefs.js"
        if not prefs.exists():
            continue
        match = re.search(
            r'user_pref\("extensions\.zotero\.dataDir",\s*"([^"]+)"\)',
            prefs.read_text(errors="replace"),
        )
        if match:
            found.append(Path(match.group(1)) / "zotero.sqlite")
    return found


def zotero_lookup(doi: str, title: str, db_path: str | Path) -> dict | None:
    """Return a match dict if the paper has an item in Zotero, else None.

    The match's `has_pdf` tells whether the work is actually held: an item
    with no PDF file attached is a reference, not a copy, and the caller
    should still fetch it.

    Matches on DOI first (case-insensitive, authoritative), then falls back to
    a near-exact title match when the DOI is absent or not found. Opens its own
    short-lived read-only connection per call, so it is safe to call from the
    fetch worker threads. Any error (missing/locked/corrupt DB) yields None.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return None

    doi = (doi or "").strip()
    title = (title or "").strip()

    try:
        conn = _open_readonly(db_path)
    except sqlite3.Error as exc:
        logger.debug("Could not open Zotero DB %s: %s", db_path, exc)
        return None

    try:
        by_doi = _match_by_doi(conn, doi) if doi and _looks_like_doi(doi) else None
        if by_doi is not None and by_doi["has_pdf"]:
            return by_doi
        # A DOI match without its file is not the last word: the PDF may sit
        # on a duplicate that carries the title but no DOI.
        by_title = _match_by_title(conn, title) if title else None
        if by_doi is None or (by_title is not None and by_title["has_pdf"]):
            return by_title
        return by_doi
    except sqlite3.Error as exc:
        logger.debug("Zotero lookup failed on %s: %s", db_path, exc)
        return None
    finally:
        conn.close()


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    # immutable=1 reads past the WAL lock held while Zotero is running and
    # guarantees we never write to the user's library.
    uri = f"file:{db_path}?immutable=1"
    return sqlite3.connect(uri, uri=True)


def _looks_like_doi(candidate: str) -> bool:
    return bool(re.match(r"^10\.\d+/.+$", candidate.replace("doi:", "").strip()))


def _holds_pdf(conn: sqlite3.Connection, item_id: int) -> bool:
    """Whether the item is, or has as a child, a PDF file outside the bin.

    Asked per matched item, as two indexed lookups: a correlated subquery
    over every title row walks the whole attachment table each time.
    """
    rows = conn.execute(
        """
        SELECT linkMode, path FROM itemAttachments
        WHERE parentItemID = ?1 AND contentType = 'application/pdf'
          AND itemID NOT IN (SELECT itemID FROM deletedItems)
        UNION ALL
        SELECT linkMode, path FROM itemAttachments
        WHERE itemID = ?1 AND contentType = 'application/pdf'
          AND itemID NOT IN (SELECT itemID FROM deletedItems)
        """,
        (item_id,),
    ).fetchall()
    return any(_is_file(link_mode, path) for link_mode, path in rows)


def _is_file(link_mode: int, path: str | None) -> bool:
    if link_mode == _LINKED_URL:
        return False  # a web address: no file is held, whatever its type
    if link_mode == _LINKED_FILE and path and os.path.isabs(path):
        return os.path.exists(path)  # the one case the database cannot vouch for
    return True


def _match_by_doi(conn: sqlite3.Connection, doi: str) -> dict | None:
    normalized = doi.replace("doi:", "").strip()
    rows = conn.execute(
        """
        SELECT d.itemID, v.value
        FROM itemData d
        JOIN fields f ON f.fieldID = d.fieldID
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE f.fieldName = 'DOI'
          AND LOWER(v.value) = LOWER(?)
          AND d.itemID NOT IN (SELECT itemID FROM deletedItems)
        """,
        (normalized,),
    ).fetchall()
    if not rows:
        return None
    # A library may hold duplicates of one DOI: one PDF among them is enough.
    return {
        "reason": "doi",
        "matched_doi": rows[0][1],
        "matched_title": None,
        "has_pdf": any(_holds_pdf(conn, item_id) for item_id, _ in rows),
    }


def _match_by_title(conn: sqlite3.Connection, title: str) -> dict | None:
    want = _tokenize(title)
    if not want:
        return None
    rows = conn.execute(
        """
        SELECT d.itemID, v.value
        FROM itemData d
        JOIN fields f ON f.fieldID = d.fieldID
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE f.fieldName = 'title'
          AND d.itemID NOT IN (SELECT itemID FROM deletedItems)
        """
    ).fetchall()
    best_score = 0.0
    best: list[tuple[int, str]] = []  # every item sharing the best score
    for item_id, candidate in rows:
        have = _tokenize(candidate or "")
        if not have:
            continue
        score = len(want & have) / len(want | have)
        if score > best_score:
            best_score, best = score, [(item_id, candidate)]
        elif score == best_score:
            best.append((item_id, candidate))
    if best_score < TITLE_MATCH_THRESHOLD:
        return None
    # The best-scoring title is the work; a weaker match holding a PDF may be
    # another work. Among equals (duplicates), one PDF is enough.
    return {
        "reason": f"title~{best_score:.2f}",
        "matched_doi": None,
        "matched_title": best[0][1],
        "has_pdf": any(_holds_pdf(conn, item_id) for item_id, _ in best),
    }


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    return {word for word in cleaned.split() if len(word) > 2}
