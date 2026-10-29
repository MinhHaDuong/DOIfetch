"""Orchestrator: batch-fetch paper PDFs from multiple sources.

Manages table I/O, parallelism, retries across sources, logging, and status updates.
"""

import argparse
import logging
import os
import threading
import time
from queue import Queue

import fetch_crossref
import fetch_ezproxy
import fetch_hal
import fetch_istex
import fetch_libgen
import fetch_scihub
import fetch_unpaywall
import fetch_url
import naming
import zotero
from config import (
    COL_DOI,
    COL_DOWNLOAD_STATUS,
    COL_TITLE,
    DOI_URL_BASE,
    LOGS_DIR,
    MAX_THREADS,
    PAPERS_DIR,
    REFERENCES_DIR,
    STATUS_SUCCESS,
    ZOTERO_DB_PATH,
)
from pdf_utils import clean_filename
from utils import (
    list_table_files,
    normalize_isbn,
    read_table,
    validate_doi,
    write_table,
)

logger = logging.getLogger(__name__)

SOURCES = {
    "scihub": fetch_scihub,
    "crossref": fetch_crossref,
    "unpaywall": fetch_unpaywall,
    "hal": fetch_hal,
    "istex": fetch_istex,
    "ezproxy": fetch_ezproxy,
    "libgen": fetch_libgen,
    "url": fetch_url,
}

# When --source all (the default), try sources in this order until one succeeds.
# Open and institutional sources only: Crossref/Unpaywall/HAL (open access),
# ISTEX (licensed national archive) and EZproxy (institutional subscription;
# fails fast unless EZPROXY_BASE + EZPROXY_COOKIES are configured). Shadow
# libraries (scihub, libgen) are opt-in: pass --source scihub / --source libgen.
SOURCE_ORDER = ["crossref", "unpaywall", "hal", "istex", "ezproxy"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-fetch paper PDFs from open and institutional sources"
    )
    parser.add_argument("--doi", help="Download a single paper by DOI")
    parser.add_argument("--isbn", help="Download a single book by ISBN (via Libgen)")
    parser.add_argument("--title", help="Title for a single-paper download")
    parser.add_argument(
        "--keep-title",
        action="store_true",
        help="Name files from the supplied title even when it does not match "
        "the DOI's Crossref title",
    )
    parser.add_argument(
        "--source",
        choices=[
            "scihub",
            "crossref",
            "unpaywall",
            "hal",
            "istex",
            "ezproxy",
            "libgen",
            "url",
            "all",
        ],
        default="all",
        help="Source to fetch from (default: all — Crossref, Unpaywall, HAL, "
        "ISTEX, EZproxy in order; scihub and libgen only when named here)",
    )
    parser.add_argument(
        "--data-dir",
        default=REFERENCES_DIR,
        help="Directory containing batch input files",
    )
    parser.add_argument(
        "--output-dir",
        default=PAPERS_DIR,
        help="Directory to save downloaded PDFs",
    )
    parser.add_argument(
        "--no-check-zotero",
        action="store_true",
        help="Do not skip papers already in the local Zotero library "
        "(the check is auto-enabled when a Zotero database is found)",
    )
    return parser.parse_args()


def resolve_zotero_db(no_check_zotero):
    """Return the Zotero DB path to dedup against, or None.

    None means the check is off — either disabled via flag or no DB found.
    """
    if no_check_zotero:
        return None
    db_path = zotero.find_zotero_db(ZOTERO_DB_PATH)
    if db_path is not None:
        print(f"Zotero library detected: skipping papers already held ({db_path})")
    return db_path


def load_download_tasks(file_paths):
    """Read DOIs and titles from input files, returning (tasks, skipped_count)."""
    download_tasks = []
    skipped_count = 0

    for file_path in file_paths:
        print(f"Reading file: {file_path}")
        try:
            for row in read_table(file_path):
                doi = row.get(COL_DOI, "")
                title = row.get(COL_TITLE, "")

                if not str(doi).strip():
                    if not str(title).strip():
                        print("Skipping invalid record: both DOI and title are empty")
                        skipped_count += 1
                        continue
                    print(f"Adding record without DOI: {title}")
                    download_tasks.append(("", title))
                    continue

                doi = str(doi).strip()
                if doi.startswith("url:"):
                    doi = doi[len("url:") :]
                if doi.startswith("isbn:"):
                    isbn = normalize_isbn(doi)
                    if not isbn:
                        print(f"Skipping invalid ISBN: {doi} | {title}")
                        skipped_count += 1
                        continue
                    doi = f"isbn:{isbn}"
                elif not _is_url(doi) and not validate_doi(doi):
                    print(f"Skipping invalid DOI format: {doi} | {title}")
                    skipped_count += 1
                    continue

                download_tasks.append((doi, title))
        except Exception as exc:
            print(f"Failed to read file {file_path}: {str(exc)}")

    return download_tasks, skipped_count


def _row_doi(row):
    doi = str(row.get(COL_DOI, "") or "").strip()
    return doi[len("url:") :] if doi.startswith("url:") else doi


def update_source_files(file_paths, successful_records):
    """Rewrite each `.txt` source file to the rows still missing.

    `successful_records` holds (title, DOI link); rows are matched by link.
    """
    for file_path in file_paths:
        try:
            rows = read_table(file_path)
            if not rows:
                continue

            by_link = {
                doi_link
                for _, doi_link in successful_records
                if doi_link and doi_link != "No DOI"
            }
            for row in rows:
                # A row is matched by its own identifier only, never by title:
                # two rows may share a title and only one be fetched.
                row_doi = _row_doi(row)
                if row_doi and f"{DOI_URL_BASE}{row_doi}" in by_link:
                    row[COL_DOWNLOAD_STATUS] = STATUS_SUCCESS

            write_table(rows, file_path)
            print(f"Updated file: {file_path}")
        except Exception as exc:
            print(f"Failed to update file {file_path}: {str(exc)}")


def write_logs(success_log, error_log, failed_dois):
    """Write success/error logs and failed DOI list."""
    timestamp = int(time.time())
    with (
        open(
            f"{LOGS_DIR}/success_{timestamp}.log", "w", encoding="utf-8"
        ) as success_file,
        open(f"{LOGS_DIR}/error_{timestamp}.log", "w", encoding="utf-8") as error_file,
        open(
            f"{LOGS_DIR}/failed_dois.csv", "w", encoding="utf-8", errors="ignore"
        ) as failed_file,
    ):
        success_file.writelines(success_log)
        error_file.writelines(error_log)
        failed_file.write("DOI,Title\n")
        for doi, title in failed_dois:
            failed_file.write(f"{doi},{title}\n")


def _is_url(identifier):
    return identifier.startswith("http://") or identifier.startswith("https://")


def _zotero_skip(doi, title, zotero_db, name):
    """Return a 'skipped' result if the paper is already in Zotero, else None."""
    if not zotero_db:
        return None
    match = zotero.zotero_lookup(doi, title, zotero_db)
    if match is None:
        return None
    safe_title = name if name else f"Unknown_{doi}"
    return {
        "status": "skipped",
        "doi": doi,
        "title": name,
        "file_name": f"{clean_filename(safe_title)}.pdf",
        "reason": f"in Zotero ({match['reason']})",
    }


def _fetch_one(doi, title, output_dir, source, zotero_db=None, keep_title=False):
    """Fetch a single paper using the specified source strategy.

    The file name is resolved once here (from DOI metadata when available) and
    passed to the fetchers in their `title` slot. Zotero is matched on the
    caller's bare title.
    """
    name = naming.resolve_name(doi, title, keep_title)
    skip = _zotero_skip(doi, title, zotero_db, name)
    if skip is not None:
        return skip
    title = name
    if _is_url(doi):
        return fetch_url.fetch_pdf(doi, title, output_dir)
    if doi.startswith("isbn:"):
        return fetch_libgen.fetch_pdf(doi, title, output_dir)
    if source == "all":
        for src_name in SOURCE_ORDER:
            result = SOURCES[src_name].fetch_pdf(doi, title, output_dir)
            if result["status"] == "success":
                return result
        return result  # return last failure
    return SOURCES[source].fetch_pdf(doi, title, output_dir)


def fetch_worker(
    queue,
    source,
    output_dir,
    success_log,
    successful_records,
    error_log,
    failed_dois,
    zotero_db=None,
    keep_title=False,
):
    """Thread worker: pull tasks from queue and fetch PDFs."""
    while not queue.empty():
        doi, title = queue.get()
        try:
            result = _fetch_one(doi, title, output_dir, source, zotero_db, keep_title)
            if result["status"] == "failed":
                failed_dois.append((doi, title))
                error_log.append(f"[FAILED] {result.get('error', 'Unknown error')}\n")
            else:
                status_label = "SKIPPED" if result["status"] == "skipped" else "SUCCESS"
                reason = result.get("reason")
                suffix = f" ({reason})" if reason else ""
                success_log.append(
                    f"[{status_label}] {doi} | {result['file_name']}{suffix}\n"
                )
                if doi:
                    doi_link = result.get("doi_link", f"{DOI_URL_BASE}{doi}")
                    successful_records.append((title, doi_link))
        except Exception as exc:
            error_msg = f"Download failed: {doi} | Error: {str(exc)}"
            error_log.append(f"[ERROR] {error_msg}\n")
            failed_dois.append((doi, title))
            print(error_msg)
        queue.task_done()


def handle_single_download(args):
    """Handle --doi/--isbn/--title single-item mode."""
    if getattr(args, "isbn", None):
        isbn = normalize_isbn(args.isbn)
        if not isbn:
            raise ValueError(f"Invalid ISBN (bad format or check digit): {args.isbn}")
        doi = f"isbn:{isbn}"
    elif args.doi:
        doi = str(args.doi).strip()
        if not validate_doi(doi):
            raise ValueError(f"Invalid DOI format: {args.doi}")
    else:
        doi = ""

    title = args.title.strip() if args.title else ""
    os.makedirs(args.output_dir, exist_ok=True)
    zotero_db = resolve_zotero_db(args.no_check_zotero)
    result = _fetch_one(
        doi,
        title,
        args.output_dir,
        args.source,
        zotero_db,
        getattr(args, "keep_title", False),
    )

    if result["status"] == "failed":
        print(f"Download failed: {result.get('error', 'Unknown error')}")
        return 1
    if result["status"] == "skipped":
        reason = result.get("reason")
        detail = f" ({reason})" if reason else ""
        print(f"Skipped existing file: {result['file_name']}{detail}")
    else:
        print(f"Download succeeded: {result['file_name']}")
    return 0


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    if args.doi or args.isbn or args.title:
        return handle_single_download(args)

    success_log = []
    successful_records = []
    error_log = []
    failed_dois = []

    zotero_db = resolve_zotero_db(args.no_check_zotero)
    input_files = list_table_files(args.data_dir)
    doi_queue = Queue()

    download_tasks, skipped_count = load_download_tasks(input_files)
    for doi, title in download_tasks:
        doi_queue.put((doi, title))

    task_count = doi_queue.qsize()
    print(f"References to fetch: {task_count} | Skipped records: {skipped_count}")

    threads = []
    if doi_queue.qsize() > 0:
        for _ in range(min(MAX_THREADS, doi_queue.qsize())):
            t = threading.Thread(
                target=fetch_worker,
                args=(
                    doi_queue,
                    args.source,
                    args.output_dir,
                    success_log,
                    successful_records,
                    error_log,
                    failed_dois,
                    zotero_db,
                    args.keep_title,
                ),
            )
            t.daemon = True
            t.start()
            threads.append(t)

        num_threads = min(MAX_THREADS, task_count)
        print(f"Starting download of {task_count} papers | Threads: {num_threads}")
        while any(t.is_alive() for t in threads):
            print(
                f"Remaining: {doi_queue.qsize()} | Success: {len(successful_records)} | Failed: {len(failed_dois)}"
            )
            time.sleep(10)
    else:
        print("No records to process. Exiting.")
        return 0

    write_logs(success_log, error_log, failed_dois)
    update_source_files(input_files, successful_records)

    success_count = len(successful_records)
    failed_count = len(failed_dois)
    total_count = success_count + failed_count

    if total_count > 0:
        success_rate = success_count * 100 / total_count
        print(f"Task complete! Success rate: {success_rate:.1f}%")
    else:
        print("Task complete! No tasks to process.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
