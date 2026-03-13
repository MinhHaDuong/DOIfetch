"""Fetch book PDFs from Library Genesis by ISBN."""

import argparse
import os
import re

import requests
from bs4 import BeautifulSoup

from config import HEADERS, PAPERS_DIR, TIMEOUT

SEARCH_MIRRORS = [
    "https://libgen.rs",
    "https://libgen.is",
    "https://libgen.gs",
]
DOWNLOAD_MIRROR = "https://libgen.li"

_MD5_RE = re.compile(r"[Mm][Dd]5[=:]([a-fA-F0-9]{32})")


def _extract_md5(soup):
    """Extract MD5 from any anchor tag whose href contains an md5 parameter."""
    for a in soup.find_all("a", href=True):
        m = _MD5_RE.search(a["href"])
        if m:
            return m.group(1).lower()
    return None


def _search_isbn(isbn):
    """Search Libgen mirrors by ISBN. Returns MD5 of first result or None."""
    # libgen.li uses index.php with columns[] param
    try:
        resp = requests.get(
            f"{DOWNLOAD_MIRROR}/index.php",
            params={"req": isbn, "columns[]": "identifier"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            md5 = _extract_md5(BeautifulSoup(resp.text, "html.parser"))
            if md5:
                return md5
    except requests.RequestException:
        pass

    # Fallback: mirrors using search.php
    params = {"req": isbn, "column": "identifier", "res": 10, "view": "simple"}
    for mirror in SEARCH_MIRRORS:
        try:
            resp = requests.get(
                f"{mirror}/search.php", params=params, headers=HEADERS, timeout=TIMEOUT
            )
            if resp.status_code != 200:
                continue
            md5 = _extract_md5(BeautifulSoup(resp.text, "html.parser"))
            if md5:
                return md5
        except requests.RequestException:
            continue
    return None


def _resolve_download_url(md5):
    """Fetch libgen.li ads page and return the direct GET download URL."""
    page_url = f"{DOWNLOAD_MIRROR}/ads.php?md5={md5}"
    resp = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")

    def _abs(href):
        return (
            href if href.startswith("http") else f"{DOWNLOAD_MIRROR}/{href.lstrip('/')}"
        )

    # Prefer the explicit "GET" download link
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True).upper() == "GET":
            return _abs(a["href"])
    # Fallback: any link containing the md5 that looks like a file download
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if md5.lower() in href.lower() and "get.php" in href:
            return _abs(href)
    return None


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a book PDF from Libgen by ISBN.

    doi should be in 'isbn:XXXXXXXXXX' format.
    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    from pdf_utils import clean_filename, is_valid_pdf

    safe_title = title if title else f"Unknown_{doi}"
    file_name = f"{clean_filename(safe_title)}.pdf"
    file_path = os.path.join(output_dir, file_name)

    if os.path.exists(file_path):
        if is_valid_pdf(file_path):
            return {
                "status": "skipped",
                "doi": doi,
                "title": title,
                "file_name": file_name,
            }
        os.remove(file_path)

    isbn = doi.removeprefix("isbn:").strip()
    if not isbn:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": "No ISBN provided",
        }

    try:
        md5 = _search_isbn(isbn)
        if not md5:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"ISBN {isbn} not found on Libgen",
            }

        download_url = _resolve_download_url(md5)
        if not download_url:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"Could not resolve download URL for md5={md5}",
            }

        pdf_resp = requests.get(
            download_url, headers=HEADERS, timeout=max(TIMEOUT, 120)
        )
        if pdf_resp.status_code != 200:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"Download failed: HTTP {pdf_resp.status_code}",
            }

        with open(file_path, "wb") as f:
            f.write(pdf_resp.content)

        if not is_valid_pdf(file_path):
            os.remove(file_path)
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "Downloaded file is not a valid PDF",
            }

        return {"status": "success", "doi": doi, "title": title, "file_name": file_name}

    except Exception as e:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Download a book PDF from Library Genesis"
    )
    parser.add_argument("--isbn", required=True, help="ISBN of the book")
    parser.add_argument("--title", default="", help="Title for the output filename")
    parser.add_argument("--output-dir", default=PAPERS_DIR, help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    result = fetch_pdf(f"isbn:{args.isbn}", args.title or args.isbn, args.output_dir)

    if result["status"] == "failed":
        print(f"Download failed: {result['error']}")
        return 1
    if result["status"] == "skipped":
        print(f"Skipped existing file: {result['file_name']}")
    else:
        print(f"Download succeeded: {result['file_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
