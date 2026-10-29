"""Orchestrator: batch-fetch papers and books (PDFs) from multiple sources.

Manages table I/O, parallelism, fallback across sources, logging, and status updates.
"""

import argparse
import importlib.metadata
import logging
import os
import threading
import time
from queue import Queue

from doifetch import naming, zotero
from doifetch.api import DEFAULT_ORDER, cascade
from doifetch.config import (
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
from doifetch.pdf_utils import clean_filename
from doifetch.sources import (
    crossref,
    ezproxy,
    hal,
    isbn,
    istex,
    libgen,
    openalex,
    scihub,
    unpaywall,
    url,
)
from doifetch.sources.contract import Fetch, Kind, Request, Result
from doifetch.utils import (
    list_table_files,
    normalize_isbn,
    read_table,
    validate_doi,
    write_table,
)

logger = logging.getLogger(__name__)

_MODULES = (
    scihub,
    crossref,
    unpaywall,
    openalex,
    hal,
    istex,
    ezproxy,
    isbn,
    libgen,
    url,
)
SOURCES: dict[str, Fetch] = {m.NAME: m.fetch for m in _MODULES}
ACCEPTS: dict[str, frozenset[Kind]] = {m.NAME: m.ACCEPTS for m in _MODULES}


EPILOG = """\
Examples:
  doifetch --doi 10.1000/example --title "Author 2020 - Title"   one paper
  doifetch --isbn 9780674009691                                  one book
  doifetch --url https://example.com/doc.pdf --title "Doc"       one direct URL
  doifetch                                                       batch: every .txt in the data directory
  doifetch --source hal                                          batch through one named source

Batch input: each .txt file in --data-dir holds one entry per line, an
identifier, a TAB, then the title. Blank lines and lines starting with # are
ignored; a bare DOI is accepted without the doi: prefix.
  doi:10.1080/03085140903020580<TAB>Author 2009 - Title
  isbn:9780674009691<TAB>Author 1998 - Book Title
  url:https://example.com/doc.pdf<TAB>Document Name
After a run each file is rewritten to the works still missing (the retry list).

Configuration (environment variables and key files; unset means that source
is skipped or runs unauthenticated):
  EZPROXY_BASE         EZproxy host suffix of your institution (ezproxy source)
  EZPROXY_COOKIES      cookies.txt exported after logging into the proxy
  EZPROXY_HYPHENS      "reversible" (default) or "simple" host rewriting
  ISTEX_ACCESSTOKEN    ISTEX access token, else ~/.config/keys/istex.env
  OPENALEX_API_KEY     OpenAlex API key, else the OPENALEX_API_KEY= line of
                       OPENALEX_KEY_FILE (default ~/.config/keys/openalex.env)
  ZOTERO_DB_PATH       Zotero database to skip already-held papers against
  ZOTERO_DATA_DIR      Zotero data directory, used to find that database

Exit codes:
  0  success; a batch run that completed (failed items are listed in logs/ and
     kept in the input files; check there), or a batch with nothing to do
  1  a single download (--doi, --isbn, --url, --title) failed, or its
     identifier is invalid
  2  command-line usage error
"""


def _package_version():
    try:
        return importlib.metadata.version("doifetch")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def parse_args():
    parser = argparse.ArgumentParser(
        prog="doifetch",
        description="Batch-fetch papers and books (PDFs) from open and "
        "institutional sources. Run with no identifier to process the .txt "
        "reference lists of the data directory.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_package_version()}"
    )
    parser.add_argument("--doi", help="Download a single paper by DOI")
    parser.add_argument(
        "--isbn",
        help="Download a single book by ISBN: its Crossref book DOI is looked "
        "up and fetched from the open sources; LibGen is used only with "
        "--source libgen",
    )
    parser.add_argument("--url", help="Download a single document from an http(s) URL")
    parser.add_argument(
        "--title", help="Title naming a single download (with --doi, --isbn, --url)"
    )
    parser.add_argument(
        "--keep-title",
        action="store_true",
        help="Name files from the supplied title even when it does not match "
        "the DOI's Crossref title",
    )
    parser.add_argument(
        "--source",
        choices=[*SOURCES, "all"],
        default="all",
        help="Source to fetch from (default: all — Crossref, Unpaywall, OpenAlex, "
        "HAL, ISTEX, EZproxy in order, and ISBNs through their book DOI; "
        "scihub and libgen only when named here)",
    )
    parser.add_argument(
        "--data-dir",
        default=REFERENCES_DIR,
        help=f"Directory containing batch input .txt files (default: {REFERENCES_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        default=PAPERS_DIR,
        help=f"Directory to save downloaded PDFs (default: {PAPERS_DIR})",
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
                    bare = normalize_isbn(doi)
                    if not bare:
                        print(f"Skipping invalid ISBN: {doi} | {title}")
                        skipped_count += 1
                        continue
                    doi = f"isbn:{bare}"
                elif not _is_url(doi) and not validate_doi(doi):
                    print(f"Skipping invalid DOI format: {doi} | {title}")
                    skipped_count += 1
                    continue

                download_tasks.append((doi, title))
        except Exception as exc:  # noqa: BLE001 - unreadable input file is reported and skipped
            print(f"Failed to read file {file_path}: {str(exc)}")

    return download_tasks, skipped_count


def _row_doi(row):
    doi = str(row.get(COL_DOI, "") or "").strip()
    if doi.startswith("url:"):
        doi = doi[len("url:") :]
    if doi.startswith("isbn:"):
        # Match the normalized form that load_download_tasks queued.
        bare = normalize_isbn(doi)
        return f"isbn:{bare}" if bare else doi
    return doi


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
        except Exception as exc:  # noqa: BLE001 - reported, batch continues
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


def _kind(identifier):
    if _is_url(identifier):
        return "url"
    return "isbn" if identifier.startswith("isbn:") else "doi"


def _request(identifier, name, output_dir, title=""):
    """Build the contract request: the caller decides the target file name.

    A row with no identifier becomes a "title" request searching for `title`.
    """
    if not identifier and title:
        return Request(
            "title",
            title,
            os.path.join(output_dir, f"{clean_filename(name or title)}.pdf"),
        )
    kind = _kind(identifier)
    bare = identifier[len("isbn:") :] if kind == "isbn" else identifier
    stem = name or f"Unknown_{hash(bare) if kind == 'url' else bare}"
    path = os.path.join(output_dir, f"{clean_filename(stem)}.pdf")
    return Request(kind, bare, path)


def _candidates(kind, source):
    """Source names to try for `kind`, in order.

    The named source (or the default cascade for "all") when it accepts the
    kind. Under "all" a kind no default source accepts falls back to every
    source that does: only "title" (Sci-Hub, ticket 0023) reaches it.
    """
    names = DEFAULT_ORDER if source == "all" else [source]
    names = [n for n in names if kind in ACCEPTS[n]]
    if source == "all" and not names:
        names = [n for n in SOURCES if kind in ACCEPTS[n]]
    return names


def _load(name):
    """The cascade's view of a source, through this module's registry."""
    return ACCEPTS[name], SOURCES[name]


def _legacy_dict(doi, name, result: Result):
    out = {"status": result.status, "doi": doi, "title": name}
    if result.path:
        out["file_name"] = os.path.basename(result.path)
    if result.error:
        out["error"] = result.error
    return out


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
    req = _request(doi, name, output_dir, title)
    if source != "all" and req.kind not in ACCEPTS[source]:
        result = Result(
            "failed", source, error=f"{source} does not accept {req.kind} identifiers"
        )
        return _legacy_dict(doi, name, result)
    result = cascade(req, _candidates(req.kind, source), _load)
    return _legacy_dict(doi, name, result)  # the deciding result


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
        except Exception as exc:  # noqa: BLE001 - one bad download must not stop the batch
            error_msg = f"Download failed: {doi} | Error: {str(exc)}"
            error_log.append(f"[ERROR] {error_msg}\n")
            failed_dois.append((doi, title))
            print(error_msg)
        queue.task_done()


def handle_single_download(args):
    """Handle --doi/--isbn/--url/--title single-item mode."""
    if getattr(args, "isbn", None):
        bare = normalize_isbn(args.isbn)
        if not bare:
            raise ValueError(f"Invalid ISBN (bad format or check digit): {args.isbn}")
        doi = f"isbn:{bare}"
    elif getattr(args, "url", None):
        doi = str(args.url).strip()
        if not _is_url(doi):
            raise ValueError(f"Invalid URL (expected http:// or https://): {args.url}")
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

    if args.doi or args.isbn or args.url or args.title:
        try:
            return handle_single_download(args)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

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
                f"Remaining: {doi_queue.unfinished_tasks} | Success: {len(successful_records)} | Failed: {len(failed_dois)}"
            )
            time.sleep(10)
    else:
        print(
            f"No records to process. Looked for .txt files in {args.data_dir} "
            f"({len(input_files)} found). Expected one entry per line: an "
            "identifier (doi:, isbn: or url:), a TAB, then the title. "
            "See doifetch --help."
        )
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
