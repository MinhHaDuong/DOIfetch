"""Tests for the Zotero-library dedup lookup."""

import sqlite3
from queue import Queue

import pytest

from doifetch import cli, zotero
from doifetch.sources.contract import Result

# (content_type, link_mode, deleted); link modes follow Zotero's own numbering.
STORED_PDF = ("application/pdf", 0, False)
TRASHED_PDF = ("application/pdf", 0, True)
PDF_WEB_LINK = ("application/pdf", 3, False)
HTML_SNAPSHOT = ("text/html", 1, False)


def _build_zotero_db(path, items):
    """Create a minimal Zotero-schema SQLite DB holding the given items.

    items: list of (doi, title) or (doi, title, attachments) tuples. Either
    field may be None. `attachments` lists (content_type, link_mode, deleted)
    children; it defaults to one stored PDF, the usual "held" item.
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
        CREATE TABLE itemAttachments (
            itemID INTEGER PRIMARY KEY, parentItemID INTEGER,
            linkMode INTEGER, contentType TEXT
        );
        """
    )
    cur.execute("INSERT INTO fields (fieldID, fieldName) VALUES (1, 'title')")
    cur.execute("INSERT INTO fields (fieldID, fieldName) VALUES (2, 'DOI')")

    value_id = 0
    attachment_id = 1000
    for item_id, item in enumerate(items, start=1):
        doi, title = item[0], item[1]
        attachments = item[2] if len(item) > 2 else [STORED_PDF]
        cur.execute("INSERT INTO items (itemID) VALUES (?)", (item_id,))
        for content_type, link_mode, deleted in attachments:
            attachment_id += 1
            cur.execute("INSERT INTO items (itemID) VALUES (?)", (attachment_id,))
            cur.execute(
                "INSERT INTO itemAttachments VALUES (?, ?, ?, ?)",
                (attachment_id, item_id, link_mode, content_type),
            )
            if deleted:
                cur.execute("INSERT INTO deletedItems VALUES (?)", (attachment_id,))
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

    for name in cli.SOURCES:
        monkeypatch.setitem(cli.SOURCES, name, _boom)

    result = cli._fetch_one(
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

    def _fake_success(req):
        calls["hit"] = True
        return Result("success", "crossref", path="papers/x.pdf")

    monkeypatch.setitem(cli.SOURCES, "crossref", _fake_success)
    result = cli._fetch_one(
        "10.9999/not.present", "Unrelated words", "papers", "crossref", zotero_db
    )
    assert calls.get("hit") is True
    assert result["status"] == "success"


def test_resolve_zotero_db_disabled_by_flag():
    assert cli.resolve_zotero_db(no_check_zotero=True) is None


# --- Ticket 0033: a Zotero item without a PDF is not a held work -------------

NO_PDF_DOI = "10.1016/j.worlddev.2018.12.011"
NO_PDF_TITLE = "Power and Influence in Global Climate Governance Reporting"


@pytest.fixture()
def mixed_db(tmp_path):
    db = tmp_path / "zotero.sqlite"
    _build_zotero_db(
        db,
        [
            ("10.1371/journal.pone.0001636", "Cognitive Constraints on Group Size"),
            (NO_PDF_DOI, NO_PDF_TITLE, []),
            ("10.5555/snapshot.only", "Snapshot Only Paper Example", [HTML_SNAPSHOT]),
            ("10.5555/trashed.pdf", "Trashed Attachment Paper Example", [TRASHED_PDF]),
            ("10.5555/web.link", "Linked Address Paper Example", [PDF_WEB_LINK]),
            (
                "10.5555/two.files",
                "Snapshot And File Paper Example",
                [HTML_SNAPSHOT, STORED_PDF],
            ),
        ],
    )
    return db


def test_lookup_reports_pdf_held(mixed_db):
    match = zotero.zotero_lookup("10.1371/journal.pone.0001636", "", mixed_db)
    assert match["has_pdf"] is True
    assert zotero.zotero_lookup("10.5555/two.files", "", mixed_db)["has_pdf"] is True


@pytest.mark.parametrize(
    "doi",
    [NO_PDF_DOI, "10.5555/snapshot.only", "10.5555/trashed.pdf", "10.5555/web.link"],
)
def test_lookup_item_without_pdf_file_is_not_held(mixed_db, doi):
    match = zotero.zotero_lookup(doi, "", mixed_db)
    assert match is not None, "the item itself is still matched"
    assert match["has_pdf"] is False


def test_lookup_title_match_without_pdf_is_not_held(mixed_db):
    match = zotero.zotero_lookup("", NO_PDF_TITLE, mixed_db)
    assert match is not None
    assert match["has_pdf"] is False


def test_lookup_prefers_the_copy_with_a_pdf(tmp_path):
    """Two items share a DOI (a duplicate): one PDF among them means held."""
    db = tmp_path / "zotero.sqlite"
    _build_zotero_db(db, [("10.5555/dup", "Dup", []), ("10.5555/dup", "Dup")])
    assert zotero.zotero_lookup("10.5555/dup", "", db)["has_pdf"] is True


def test_fetch_one_fetches_when_zotero_item_has_no_pdf(mixed_db, monkeypatch, capsys):
    calls = []

    def _fake_success(req):
        calls.append(req)
        return Result("success", "crossref", path="papers/x.pdf")

    monkeypatch.setitem(cli.SOURCES, "crossref", _fake_success)
    result = cli._fetch_one(NO_PDF_DOI, NO_PDF_TITLE, "papers", "crossref", mixed_db)
    assert len(calls) == 1
    assert result["status"] == "success"
    assert "no PDF" in capsys.readouterr().out


def _run_worker(monkeypatch, results):
    """Run fetch_worker over `results` ({doi: result dict}); return its lists."""
    monkeypatch.setattr(cli, "_fetch_one", lambda doi, *_a, **_k: results[doi])
    queue = Queue()
    for doi in results:
        queue.put((doi, f"title of {doi}"))
    out = {"success_log": [], "ok": [], "error_log": [], "failed": [], "skipped": []}
    cli.fetch_worker(
        queue,
        "all",
        "papers",
        out["success_log"],
        out["ok"],
        out["error_log"],
        out["failed"],
        skipped_records=out["skipped"],
    )
    return out


def test_worker_counts_skips_apart_from_successes(monkeypatch):
    out = _run_worker(
        monkeypatch,
        {
            "10.1/got": {"status": "success", "doi": "10.1/got", "file_name": "a.pdf"},
            "10.1/held": {
                "status": "skipped",
                "doi": "10.1/held",
                "file_name": "b.pdf",
                "reason": "in Zotero (doi)",
            },
            "10.1/lost": {"status": "failed", "doi": "10.1/lost", "error": "nope"},
        },
    )
    assert [link for _, link in out["ok"]] == ["https://doi.org/10.1/got"]
    assert [link for _, link in out["skipped"]] == ["https://doi.org/10.1/held"]
    assert [doi for doi, _ in out["failed"]] == ["10.1/lost"]


def test_summary_prints_skipped_apart_from_successes():
    line = cli.summary_line(downloaded=3, skipped=2, failed=1)
    assert "Success: 3" in line
    assert "Skipped: 2" in line
    assert "Failed: 1" in line
    # The rate is over attempted downloads; a skip is neither.
    assert "75.0%" in line


def test_batch_keeps_unheld_work_on_retry_list(mixed_db, tmp_path, monkeypatch, capsys):
    """End to end: the no-PDF item is fetched; when that fails it stays listed,
    while the item held with its PDF is skipped and leaves the list."""
    data = tmp_path / "data"
    data.mkdir()
    listing = data / "refs.txt"
    listing.write_text(
        f"doi:{NO_PDF_DOI}\t{NO_PDF_TITLE}\n"
        "doi:10.1371/journal.pone.0001636\tCognitive Constraints on Group Size\n"
    )
    monkeypatch.setenv("ZOTERO_DB_PATH", str(mixed_db))
    monkeypatch.setattr(cli, "ZOTERO_DB_PATH", str(mixed_db))
    monkeypatch.setattr(cli, "LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(
        cli.naming, "resolve_name", lambda doi, title, keep_title=False: title
    )
    for name in cli.SOURCES:
        monkeypatch.setitem(
            cli.SOURCES, name, lambda req: Result("failed", "x", error="no copy")
        )
    monkeypatch.setattr(
        "sys.argv",
        ["doifetch", "--data-dir", str(data), "--output-dir", str(tmp_path / "out")],
    )
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "Success: 0 | Skipped: 1 | Failed: 1" in out
    remaining = listing.read_text()
    assert NO_PDF_DOI in remaining
    assert "10.1371/journal.pone.0001636" not in remaining
