"""Optional dedup against a local Zotero library.

DOIfetch consults the user's Zotero SQLite database before downloading, so a
paper already held in the library is skipped rather than refetched. The check
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
    """Return a match dict if the paper is already in Zotero, else None.

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
        if doi and _looks_like_doi(doi):
            hit = _match_by_doi(conn, doi)
            if hit is not None:
                return hit
        if title:
            return _match_by_title(conn, title)
        return None
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


def _match_by_doi(conn: sqlite3.Connection, doi: str) -> dict | None:
    normalized = doi.replace("doi:", "").strip()
    row = conn.execute(
        """
        SELECT v.value
        FROM itemData d
        JOIN fields f ON f.fieldID = d.fieldID
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE f.fieldName = 'DOI'
          AND LOWER(v.value) = LOWER(?)
          AND d.itemID NOT IN (SELECT itemID FROM deletedItems)
        LIMIT 1
        """,
        (normalized,),
    ).fetchone()
    if row is None:
        return None
    return {"reason": "doi", "matched_doi": row[0], "matched_title": None}


def _match_by_title(conn: sqlite3.Connection, title: str) -> dict | None:
    want = _tokenize(title)
    if not want:
        return None
    rows = conn.execute(
        """
        SELECT v.value
        FROM itemData d
        JOIN fields f ON f.fieldID = d.fieldID
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE f.fieldName = 'title'
          AND d.itemID NOT IN (SELECT itemID FROM deletedItems)
        """
    ).fetchall()
    best_score = 0.0
    best_title = None
    for (candidate,) in rows:
        have = _tokenize(candidate or "")
        if not have:
            continue
        score = len(want & have) / len(want | have)
        if score > best_score:
            best_score = score
            best_title = candidate
    if best_score >= TITLE_MATCH_THRESHOLD:
        return {
            "reason": f"title~{best_score:.2f}",
            "matched_doi": None,
            "matched_title": best_title,
        }
    return None


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    return {word for word in cleaned.split() if len(word) > 2}
