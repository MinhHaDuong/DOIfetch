"""Fetch book PDFs from Library Genesis by ISBN."""

import os
import re

import requests

from doifetch.config import HEADERS, PAPERS_DIR, TIMEOUT

SEARCH_MIRRORS = [
    "https://libgen.rs",
    "https://libgen.is",
    "https://libgen.gs",
]
DOWNLOAD_MIRROR = "https://libgen.li"

_MD5_RE = re.compile(r"[Mm][Dd]5[=:]([a-fA-F0-9]{32})")


def _soup(html):
    """Parse HTML with bs4, which ships in the 'shadow' extra only."""
    from doifetch.utils import require

    return require("bs4", "shadow").BeautifulSoup(html, "html.parser")


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
            md5 = _extract_md5(_soup(resp.text))
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
            md5 = _extract_md5(_soup(resp.text))
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
    soup = _soup(resp.text)

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


def _detect_ext(content, content_type=""):
    """Return file extension based on magic bytes or content-type."""
    if content[:4] == b"%PDF":
        return ".pdf"
    if content[:2] == b"PK":
        return ".epub"  # EPUB is a ZIP; libgen commonly serves EPUBs
    if b"<html" in content[:256].lower():
        return ".html"
    # Fall back to content-type
    ct = content_type.lower()
    if "epub" in ct:
        return ".epub"
    if "pdf" in ct:
        return ".pdf"
    return ".pdf"  # optimistic default


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a book from Libgen by ISBN (PDF or EPUB).

    doi should be in 'isbn:XXXXXXXXXX' format.
    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    from doifetch.pdf_utils import clean_filename, is_valid_pdf
    from doifetch.utils import require

    try:
        require("bs4", "shadow")
    except ImportError as exc:
        return {"status": "failed", "doi": doi, "title": title, "error": str(exc)}

    safe_title = title if title else f"Unknown_{doi}"
    base_name = clean_filename(safe_title)

    # Check for existing file in any supported format
    for ext in (".pdf", ".epub"):
        existing = os.path.join(output_dir, base_name + ext)
        if os.path.exists(existing) and os.path.getsize(existing) > 1000:
            return {
                "status": "skipped",
                "doi": doi,
                "title": title,
                "file_name": base_name + ext,
            }

    file_name = base_name + ".pdf"  # placeholder; overridden after download
    file_path = os.path.join(output_dir, file_name)

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

        content = pdf_resp.content
        ext = _detect_ext(content, pdf_resp.headers.get("content-type", ""))
        file_name = base_name + ext
        file_path = os.path.join(output_dir, file_name)

        if len(content) < 1000 or ext == ".html":
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "Downloaded file appears to be an error page",
            }

        with open(file_path, "wb") as f:
            f.write(content)

        if ext == ".pdf" and not is_valid_pdf(file_path):
            os.remove(file_path)
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "Downloaded file is not a valid PDF",
            }

        return {"status": "success", "doi": doi, "title": title, "file_name": file_name}

    except Exception as e:  # noqa: BLE001 - a fetcher reports failure, never raises into the fetch loop
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }
