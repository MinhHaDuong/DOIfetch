"""Fetch fulltext PDFs through an institutional EZproxy by DOI.

This is the scriptable equivalent of clicking a "Click & Read" / BibCNRS button:
it resolves a DOI to the publisher URL, rewrites the host into the institution's
EZproxy host-based form, and downloads the PDF using your authenticated proxy
session cookies. It gets paywalled articles your institution subscribes to —
without a shadow library — but it needs a logged-in session because CNRS/BibCNRS
authenticates via federated SSO (Janus/RENATER), which cannot be scripted blind.

Configuration (environment variables):
  EZPROXY_BASE     The proxy host suffix, e.g. "bib-cnrs-fr.insb.bib.cnrs.fr" or
                   "ezproxy.univ.example.fr". A publisher host is rewritten to
                   <host-with-dots-as-hyphens>.<EZPROXY_BASE> (EZproxy host mode).
  EZPROXY_COOKIES  Path to a Netscape cookies.txt exported from your browser
                   AFTER logging into the proxy (e.g. via the "Get cookies.txt"
                   extension, or Firefox/Chrome cookie export). Required.
  EZPROXY_HYPHENS  "reversible" (default) doubles literal hyphens then maps dots
                   to hyphens (EZproxy HttpsHyphens); "simple" only maps dots to
                   hyphens. Match your institution's scheme.

If EZPROXY_BASE or EZPROXY_COOKIES is unset, this fetcher fails fast with a
message rather than pretending to try — so `--source all` simply skips it.
"""

import argparse
import http.cookiejar
import os
import re
from urllib.parse import urlsplit, urlunsplit

import requests

from config import HEADERS, PAPERS_DIR, TIMEOUT

BASE_ENV = "EZPROXY_BASE"
COOKIES_ENV = "EZPROXY_COOKIES"
HYPHENS_ENV = "EZPROXY_HYPHENS"


def ezproxy_host(host: str, base: str, hyphens: str = "reversible") -> str:
    """Rewrite a publisher host into EZproxy host-based form.

    reversible (EZproxy HttpsHyphens): 'www.tandf-online.com' with base 'p.edu'
    -> 'www-tandf--online-com.p.edu' (literal '-' doubled, '.' -> '-').
    simple: only '.' -> '-'.
    """
    if hyphens == "simple":
        mapped = host.replace(".", "-")
    else:
        mapped = host.replace("-", "--").replace(".", "-")
    return f"{mapped}.{base}"


def ezproxy_url(url: str, base: str, hyphens: str = "reversible") -> str:
    """Rewrite a full URL's host into EZproxy form, preserving path and query."""
    parts = urlsplit(url)
    if not parts.hostname:
        return url
    return urlunsplit((
        parts.scheme or "https",
        ezproxy_host(parts.hostname, base, hyphens),
        parts.path,
        parts.query,
        parts.fragment,
    ))


def _load_cookies(path: str) -> http.cookiejar.MozillaCookieJar:
    jar = http.cookiejar.MozillaCookieJar()
    jar.load(path, ignore_discard=True, ignore_expires=True)
    return jar


def _resolve_publisher_url(doi: str, session: requests.Session) -> str:
    """Follow doi.org to the publisher landing URL (unproxied) for a DOI."""
    try:
        r = session.get(f"https://doi.org/{doi}", allow_redirects=True,
                        timeout=TIMEOUT)
        return r.url or f"https://doi.org/{doi}"
    except requests.RequestException:
        return f"https://doi.org/{doi}"


def _extract_pdf_link(html: str, page_url: str) -> str | None:
    """Best-effort scrape of a PDF link from a publisher landing page."""
    m = re.search(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)',
                  html, re.I) or re.search(
        r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.I)
    if not m:
        return None
    href = m.group(1)
    if href.startswith("http"):
        return href
    parts = urlsplit(page_url)
    if href.startswith("/"):
        return f"{parts.scheme}://{parts.netloc}{href}"
    return f"{parts.scheme}://{parts.netloc}/{href}"


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download one paper PDF through the configured EZproxy by DOI.

    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    from pdf_utils import clean_filename, is_valid_pdf

    safe_title = title if title else f"Unknown_{doi}"
    file_name = f"{clean_filename(safe_title)}.pdf"
    file_path = os.path.join(output_dir, file_name)

    def fail(error):
        return {"status": "failed", "doi": doi, "title": title,
                "file_name": file_name, "error": error}

    if os.path.exists(file_path):
        if is_valid_pdf(file_path):
            return {"status": "skipped", "doi": doi, "title": title,
                    "file_name": file_name}
        os.remove(file_path)

    base = os.environ.get(BASE_ENV, "").strip()
    cookies_path = os.environ.get(COOKIES_ENV, "").strip()
    hyphens = os.environ.get(HYPHENS_ENV, "reversible").strip() or "reversible"
    if not base:
        return fail(f"{BASE_ENV} not set (your institution's EZproxy host suffix)")
    if not cookies_path or not os.path.exists(cookies_path):
        return fail(f"{COOKIES_ENV} not set or missing (export cookies.txt after "
                    "logging into the proxy)")
    if not doi:
        return fail("EZproxy resolution requires a DOI")

    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        session.cookies = _load_cookies(cookies_path)  # type: ignore[assignment]

        publisher_url = _resolve_publisher_url(doi, session)
        target = ezproxy_url(publisher_url, base, hyphens)
        resp = session.get(target, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code != 200:
            return fail(f"proxy fetch failed: {resp.status_code}")

        ctype = resp.headers.get("Content-Type", "")
        content = resp.content
        if "pdf" not in ctype.lower() and not content[:5] == b"%PDF-":
            # landing page — find the PDF link and fetch it (proxied).
            link = _extract_pdf_link(resp.text, resp.url)
            if not link:
                return fail("no PDF link found on landing page (auth expired?)")
            link = ezproxy_url(link, base, hyphens) if base not in link else link
            resp = session.get(link, timeout=TIMEOUT, allow_redirects=True)
            content = resp.content

        with open(file_path, "wb") as fh:
            fh.write(content)
        if not is_valid_pdf(file_path):
            os.remove(file_path)
            return fail("downloaded file is not a valid PDF (auth expired or paywalled)")
        return {"status": "success", "doi": doi, "title": title,
                "file_name": file_name}
    except Exception as e:
        return fail(str(e))


def main():
    parser = argparse.ArgumentParser(
        description="Download a paper PDF through an institutional EZproxy by DOI"
    )
    parser.add_argument("--doi", required=True, help="DOI of the paper")
    parser.add_argument("--title", default="", help="Title of the paper")
    parser.add_argument("--output-dir", default=PAPERS_DIR, help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    result = fetch_pdf(args.doi, args.title, args.output_dir)
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
