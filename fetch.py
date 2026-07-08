"""Orchestrator: batch-fetch paper PDFs from multiple sources.

Manages table I/O, parallelism, retries across sources, logging, and status updates.
"""

import argparse
import os
import threading
import time
from queue import Queue

import pandas as pd

import fetch_crossref
import fetch_hal
import fetch_istex
import fetch_libgen
import fetch_scihub
import fetch_unpaywall
import fetch_url
import zotero
from config import (
    COL_DOI,
    COL_DOI_LINK,
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
    SUPPORTED_INPUT_FORMATS,
    list_table_files,
    read_table,
    validate_doi,
    write_table,
)

SOURCES = {
    "scihub": fetch_scihub,
    "crossref": fetch_crossref,
    "unpaywall": fetch_unpaywall,
    "hal": fetch_hal,
    "istex": fetch_istex,
    "libgen": fetch_libgen,
    "url": fetch_url,
}

# When --source all, try sources in this order until one succeeds.
# ISTEX (licensed national archive) precedes Sci-Hub: prefer a legitimate
# source over the shadow library as last resort.
SOURCE_ORDER = ["crossref", "unpaywall", "hal", "istex", "scihub"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-fetch paper PDFs from Sci-Hub, Crossref, and/or Unpaywall"
    )
    parser.add_argument("--doi", help="Download a single paper by DOI")
    parser.add_argument("--title", help="Title for a single-paper download")
    parser.add_argument(
        "--source",
        choices=[
            "scihub",
            "crossref",
            "unpaywall",
            "hal",
            "istex",
            "libgen",
            "url",
            "all",
        ],
        default="all",
        help="Source to fetch from (default: all — tries each in order)",
    )
    parser.add_argument(
        "--input-format",
        choices=SUPPORTED_INPUT_FORMATS,
        default="auto",
        help="Choose input files from references/: excel, csv, txt, or auto",
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
            dataframe = read_table(file_path)
            for _, row in dataframe.iterrows():
                doi = row.get(COL_DOI, "")
                title = row.get(COL_TITLE, f"Unknown_{int(time.time())}")

                if pd.isna(doi) or not str(doi).strip():
                    if pd.isna(title) or not str(title).strip():
                        print("Skipping invalid record: both DOI and title are empty")
                        skipped_count += 1
                        continue
                    print(f"Adding record without DOI: {title}")
                    download_tasks.append(("", title))
                    continue

                doi = str(doi).strip()
                if doi.startswith("url:"):
                    doi = doi[len("url:") :]
                if (
                    not _is_url(doi)
                    and not doi.startswith("isbn:")
                    and not validate_doi(doi)
                ):
                    print(f"Skipping invalid DOI format: {doi} | {title}")
                    skipped_count += 1
                    continue

                download_tasks.append((doi, title))
        except Exception as exc:
            print(f"Failed to read file {file_path}: {str(exc)}")

    return download_tasks, skipped_count


def update_source_files(file_paths, successful_records):
    """Write back DOI links and download status to source files."""
    for file_path in file_paths:
        try:
            dataframe = read_table(file_path)

            if COL_DOI_LINK not in dataframe.columns:
                dataframe.insert(2, COL_DOI_LINK, "")
            if COL_DOWNLOAD_STATUS not in dataframe.columns:
                dataframe[COL_DOWNLOAD_STATUS] = ""

            for title, doi_link in successful_records:
                if not doi_link or doi_link == "No DOI":
                    continue
                mask = dataframe[COL_TITLE] == title
                dataframe.loc[mask, COL_DOI_LINK] = doi_link
                dataframe.loc[mask, COL_DOWNLOAD_STATUS] = STATUS_SUCCESS

            write_table(dataframe, file_path)
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


def _zotero_skip(doi, title, zotero_db):
    """Return a 'skipped' result if the paper is already in Zotero, else None."""
    if not zotero_db:
        return None
    match = zotero.zotero_lookup(doi, title, zotero_db)
    if match is None:
        return None
    safe_title = title if title else f"Unknown_{doi}"
    return {
        "status": "skipped",
        "doi": doi,
        "title": title,
        "file_name": f"{clean_filename(safe_title)}.pdf",
        "reason": f"in Zotero ({match['reason']})",
    }


def _fetch_one(doi, title, output_dir, source, zotero_db=None):
    """Fetch a single paper using the specified source strategy."""
    skip = _zotero_skip(doi, title, zotero_db)
    if skip is not None:
        return skip
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
):
    """Thread worker: pull tasks from queue and fetch PDFs."""
    while not queue.empty():
        doi, title = queue.get()
        try:
            result = _fetch_one(doi, title, output_dir, source, zotero_db)
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
                    successful_records.append((result["title"], doi_link))
        except Exception as exc:
            error_msg = f"Download failed: {doi} | Error: {str(exc)}"
            error_log.append(f"[ERROR] {error_msg}\n")
            failed_dois.append((doi, title))
            print(error_msg)
        queue.task_done()


def handle_single_download(args):
    """Handle --doi/--title single-paper mode."""
    if args.doi:
        doi = str(args.doi).strip()
        if not validate_doi(doi):
            raise ValueError(f"Invalid DOI format: {args.doi}")
    else:
        doi = ""

    title = args.title.strip() if args.title else f"Unknown_{int(time.time())}"
    os.makedirs(args.output_dir, exist_ok=True)
    zotero_db = resolve_zotero_db(args.no_check_zotero)
    result = _fetch_one(doi, title, args.output_dir, args.source, zotero_db)

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

    if args.doi or args.title:
        return handle_single_download(args)

    success_log = []
    successful_records = []
    error_log = []
    failed_dois = []

    zotero_db = resolve_zotero_db(args.no_check_zotero)
    input_files = list_table_files(args.data_dir, args.input_format)
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
