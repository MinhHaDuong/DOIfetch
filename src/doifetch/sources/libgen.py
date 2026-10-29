"""Fetch book PDFs from Library Genesis by ISBN."""

import re

from doifetch.config import HEADERS, TIMEOUT
from doifetch.sources import _http
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result

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
        resp = _http.get(
            f"{DOWNLOAD_MIRROR}/index.php",
            params={"req": isbn, "columns[]": "identifier"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if resp.status == 200:
            md5 = _extract_md5(_soup(resp.text))
            if md5:
                return md5
    except _http.HttpError:
        pass

    # Fallback: mirrors using search.php
    params = {"req": isbn, "column": "identifier", "res": 10, "view": "simple"}
    for mirror in SEARCH_MIRRORS:
        try:
            resp = _http.get(
                f"{mirror}/search.php", params=params, headers=HEADERS, timeout=TIMEOUT
            )
            if resp.status != 200:
                continue
            md5 = _extract_md5(_soup(resp.text))
            if md5:
                return md5
        except _http.HttpError:
            continue
    return None


def _resolve_download_url(md5):
    """Fetch libgen.li ads page and return the direct GET download URL."""
    page_url = f"{DOWNLOAD_MIRROR}/ads.php?md5={md5}"
    resp = _http.get(page_url, headers=HEADERS, timeout=TIMEOUT)
    if resp.status != 200:
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


def _fetch(req: Request) -> Result:
    from doifetch.utils import require

    require("bs4", "shadow")

    if (done := already_there(req, NAME)) is not None:
        return done

    isbn = req.identifier.strip()
    if not isbn:
        return Result("failed", NAME, error="No ISBN provided")

    md5 = _search_isbn(isbn)
    if not md5:
        return Result("failed", NAME, error=f"ISBN {isbn} not found on Libgen")

    download_url = _resolve_download_url(md5)
    if not download_url:
        return Result(
            "failed", NAME, error=f"Could not resolve download URL for md5={md5}"
        )

    resp = _http.get(download_url, headers=HEADERS, timeout=max(TIMEOUT, 120))
    if not resp.ok:
        return Result("failed", NAME, error=f"Download failed: HTTP {resp.status}")

    content = resp.content
    ext = _detect_ext(content, resp.headers.get("content-type", ""))
    if len(content) < 1000 or ext == ".html":
        return Result(
            "failed", NAME, error="Downloaded file appears to be an error page"
        )
    if ext != ".pdf":
        return Result(
            "failed", NAME, error=f"Libgen served {ext[1:].upper()}, not a PDF"
        )
    return save_pdf(req, NAME, content, "Downloaded file is not a valid PDF")


def fetch(req: Request) -> Result:
    """Download the book with ISBN ``req.identifier`` from Libgen.

    Only a PDF is kept: an EPUB or an error page is a failure, since the contract
    writes ``req.path`` and returns success for a checked PDF only.
    """
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))


NAME = "libgen"
ACCEPTS: frozenset[Kind] = frozenset({"isbn"})
