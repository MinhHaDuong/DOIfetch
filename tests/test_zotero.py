"""Tests for the Zotero-library dedup lookup."""

import sqlite3

import pytest

import fetch
import zotero


def _build_zotero_db(path, items):
    """Create a minimal Zotero-schema SQLite DB holding the given items.

    items: list of (doi, title) tuples. Either field may be None.
    """
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE items (itemID INTEGER PRIMARY KEY);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
        CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
        """
    )
    cur.execute("INSERT INTO fields (fieldID, fieldName) VALUES (1, 'title')")
    cur.execute("INSERT INTO fields (fieldID, fieldName) VALUES (2, 'DOI')")

    value_id = 0
    for item_id, (doi, title) in enumerate(items, start=1):
        cur.execute("INSERT INTO items (itemID) VALUES (?)", (item_id,))
        for field_id, val in ((1, title), (2, doi)):
            if val is None:
                continue
            value_id += 1
            cur.execute(
                "INSERT INTO itemDataValues (valueID, value) VALUES (?, ?)",
                (value_id, val),
            )
            cur.execute(
                "INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?, ?, ?)",
                (item_id, field_id, value_id),
            )
    conn.commit()
    conn.close()


@pytest.fixture()
def zotero_db(tmp_path):
    db = tmp_path / "zotero.sqlite"
    _build_zotero_db(
        db,
        [
            ("10.1371/journal.pone.0001636", "Cognitive Constraints on Group Size"),
            (None, "A Paper With No DOI But A Distinctive Title"),
        ],
    )
    return db


def test_lookup_hit_by_doi(zotero_db):
    match = zotero.zotero_lookup(
        "10.1371/journal.pone.0001636", "irrelevant title", db_path=zotero_db
    )
    assert match is not None
    assert match["reason"] == "doi"


def test_lookup_doi_case_insensitive(zotero_db):
    match = zotero.zotero_lookup(
        "10.1371/JOURNAL.PONE.0001636", None, db_path=zotero_db
    )
    assert match is not None
    assert match["reason"] == "doi"


def test_lookup_miss_by_doi(zotero_db):
    match = zotero.zotero_lookup(
        "10.9999/does.not.exist", "nothing like anything", db_path=zotero_db
    )
    assert match is None


def test_lookup_hit_by_title_when_no_doi(zotero_db):
    match = zotero.zotero_lookup(
        "", "A Paper With No DOI But A Distinctive Title", db_path=zotero_db
    )
    assert match is not None
    assert match["reason"].startswith("title")


def test_lookup_title_below_threshold_is_miss(zotero_db):
    match = zotero.zotero_lookup(
        "", "Completely unrelated words here", db_path=zotero_db
    )
    assert match is None


def test_lookup_missing_db_returns_none(tmp_path):
    assert (
        zotero.zotero_lookup("10.1/x", "t", db_path=tmp_path / "absent.sqlite") is None
    )


def test_lookup_broken_db_degrades_to_none(tmp_path):
    bad = tmp_path / "zotero.sqlite"
    bad.write_bytes(b"this is not a database")
    # Must not raise into the caller; a broken DB means "no hit".
    assert zotero.zotero_lookup("10.1/x", "t", db_path=bad) is None


def test_find_zotero_db_override_env(tmp_path, monkeypatch):
    db = tmp_path / "zotero.sqlite"
    db.write_bytes(b"")
    monkeypatch.setenv("ZOTERO_DB_PATH", str(db))
    monkeypatch.delenv("ZOTERO_DATA_DIR", raising=False)
    assert zotero.find_zotero_db() == db


def test_find_zotero_db_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("ZOTERO_DB_PATH", raising=False)
    monkeypatch.delenv("ZOTERO_DATA_DIR", raising=False)
    monkeypatch.setattr(zotero, "_HOME", tmp_path)
    assert zotero.find_zotero_db() is None


def test_fetch_one_short_circuits_on_zotero_hit(zotero_db, monkeypatch):
    """A Zotero hit must yield 'skipped' without invoking any source module."""

    def _boom(*_args, **_kwargs):
        raise AssertionError("no source should be called when the paper is in Zotero")

    for module in fetch.SOURCES.values():
        monkeypatch.setattr(module, "fetch_pdf", _boom)

    result = fetch._fetch_one(
        "10.1371/journal.pone.0001636",
        "Cognitive Constraints on Group Size",
        "papers",
        "all",
        zotero_db,
    )
    assert result["status"] == "skipped"
    assert "Zotero" in result["reason"]


def test_fetch_one_falls_through_when_not_in_zotero(zotero_db, monkeypatch):
    """A Zotero miss must proceed to the source, which here reports success."""
    calls = {}

    def _fake_success(doi, title, output_dir):
        calls["hit"] = True
        return {"status": "success", "doi": doi, "title": title, "file_name": "x.pdf"}

    monkeypatch.setattr(fetch.fetch_crossref, "fetch_pdf", _fake_success)
    result = fetch._fetch_one(
        "10.9999/not.present", "Unrelated words", "papers", "crossref", zotero_db
    )
    assert calls.get("hit") is True
    assert result["status"] == "success"


def test_resolve_zotero_db_disabled_by_flag():
    assert fetch.resolve_zotero_db(no_check_zotero=True) is None
