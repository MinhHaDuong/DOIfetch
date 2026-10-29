"""Fetch paper PDFs directly from a URL."""

import os

import requests

from doifetch.config import HEADERS, PAPERS_DIR, TIMEOUT
from doifetch.sources._legacy import run_legacy
from doifetch.sources.contract import Kind, Request, Result


def fetch_pdf(url, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF from a direct URL.

    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    from doifetch.pdf_utils import clean_filename, is_valid_pdf

    safe_title = title if title else f"Unknown_{hash(url)}"
    file_name = f"{clean_filename(safe_title)}.pdf"
    file_path = os.path.join(output_dir, file_name)

    if os.path.exists(file_path):
        if is_valid_pdf(file_path):
            return {
                "status": "skipped",
                "doi": url,
                "title": title,
                "file_name": file_name,
            }
        else:
            os.remove(file_path)

    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if response.status_code != 200:
            return {
                "status": "failed",
                "doi": url,
                "title": title,
                "file_name": file_name,
                "error": f"HTTP {response.status_code}",
            }
        with open(file_path, "wb") as f:
            f.write(response.content)
        if not is_valid_pdf(file_path):
            os.remove(file_path)
            return {
                "status": "failed",
                "doi": url,
                "title": title,
                "file_name": file_name,
                "error": "Downloaded file is not a valid PDF",
            }
        return {
            "status": "success",
            "doi": url,
            "title": title,
            "file_name": file_name,
        }
    except Exception as e:  # noqa: BLE001 - a fetcher reports failure, never raises into the fetch loop
        return {
            "status": "failed",
            "doi": url,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }


NAME = "url"
ACCEPTS: frozenset[Kind] = frozenset({"url"})


def fetch(req: Request) -> Result:
    """Contract adapter over `fetch_pdf`."""
    return run_legacy(NAME, fetch_pdf, req)
