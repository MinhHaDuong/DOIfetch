"""Fetch paper PDFs from Sci-Hub and its SciDB (Anna's Archive) successor."""

import argparse
import os
import random
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from config import (
    DOI_URL_BASE,
    HEADERS,
    MAX_DELAY,
    MIN_DELAY,
    PAPERS_DIR,
    SCI_HUB_DOMAINS,
    SCIDB_DOMAINS,
    TIMEOUT,
)


def build_query_urls(doi, title):
    """Resolver URLs to try in order, most reliable first.

    With a DOI: classic Sci-Hub pages first (frozen corpus, freely scrapable
    iframe), then SciDB via Anna's Archive (broader/updated corpus). Without a
    DOI: fall back to a Sci-Hub title search, which SciDB does not offer.
    """
    if doi:
        scihub = [f"{domain}{doi}" for domain in SCI_HUB_DOMAINS]
        scidb = [f"{domain}scidb/{doi}" for domain in SCIDB_DOMAINS]
        return scihub + scidb
    return [f"{domain}?s={quote(title)}" for domain in SCI_HUB_DOMAINS]


def extract_pdf_url(content):
    """Return the embedded PDF URL from a Sci-Hub/SciDB viewer page, or None."""
    soup = BeautifulSoup(content, "html.parser")
    node = soup.find("iframe") or soup.find("embed")
    if not node:
        return None
    src = node.get("src")
    if not src:
        return None
    if src.startswith("//"):  # protocol-relative src, common on Sci-Hub
        src = "https:" + src
    return src if src.startswith("http") else None


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF from Sci-Hub, then SciDB (Anna's Archive).

    Returns dict with keys: status, doi, title, file_name, doi_link, error (if failed).
    """
    from pdf_utils import clean_filename, is_valid_pdf

    doi_link = f"{DOI_URL_BASE}{doi}" if doi else "No DOI"
    safe_title = title if title else f"Unknown_{int(time.time())}"
    file_name = f"{clean_filename(safe_title)}.pdf"
    file_path = os.path.join(output_dir, file_name)

    if os.path.exists(file_path):
        if is_valid_pdf(file_path):
            return {
                "status": "skipped",
                "doi": doi,
                "title": safe_title,
                "doi_link": doi_link,
                "file_name": file_name,
            }
        else:
            os.remove(file_path)

    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    last_error = ""

    for query_url in build_query_urls(doi, safe_title):
        try:
            response = requests.get(query_url, headers=HEADERS, timeout=TIMEOUT)
            pdf_url = extract_pdf_url(response.content)

            if not pdf_url:
                last_error = f"{doi or safe_title} | Error: PDF link not found | URL: {query_url}"
                continue

            pdf_response = requests.get(
                pdf_url, headers=HEADERS, stream=True, timeout=TIMEOUT
            )
            with open(file_path, "wb") as file_handle:
                for chunk in pdf_response.iter_content(chunk_size=1024):
                    if chunk:
                        file_handle.write(chunk)
            # PDF verification step
            if not is_valid_pdf(file_path):
                os.remove(file_path)
                last_error = (
                    f"{doi or safe_title} | Error: Broken PDF file | URL: {query_url}"
                )
                continue

            return {
                "status": "success",
                "doi": doi,
                "title": safe_title,
                "doi_link": doi_link,
                "file_name": file_name,
            }
        except Exception as exc:
            last_error = (
                f"{doi or safe_title} | Error: {str(exc)[:50]} | URL: {query_url}"
            )

    return {
        "status": "failed",
        "doi": doi,
        "title": safe_title,
        "doi_link": doi_link,
        "file_name": file_name,
        "error": last_error or f"{doi or safe_title} | Error: Unknown error",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Download a paper PDF from Sci-Hub / SciDB (Anna's Archive)"
    )
    parser.add_argument("--doi", help="DOI of the paper")
    parser.add_argument("--title", help="Title of the paper")
    parser.add_argument("--output-dir", default=PAPERS_DIR, help="Output directory")
    args = parser.parse_args()

    if not args.doi and not args.title:
        parser.error("At least one of --doi or --title is required")

    from utils import validate_doi

    if args.doi and not validate_doi(args.doi):
        raise ValueError(f"Invalid DOI format: {args.doi}")

    os.makedirs(args.output_dir, exist_ok=True)
    result = fetch_pdf(args.doi or "", args.title or "", args.output_dir)

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
