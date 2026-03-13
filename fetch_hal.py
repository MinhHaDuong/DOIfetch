"""Fetch open-access paper PDFs from the HAL archive by author and title search."""

import argparse
import os
import re

import requests

from config import HEADERS, PAPERS_DIR, TIMEOUT

HAL_SEARCH_URL = "https://api.archives-ouvertes.fr/search/"


def _parse_author_title(title):
    """Extract first author surname and title keywords from reference string.

    Expected format: 'Author et al. Year - Actual Title' or 'Author & Other Year - Title'
    Returns (author_surname, title_keywords) or (None, None) if unparseable.
    """
    match = re.match(r"^([A-Za-zÀ-ÿ]+).*?\d{4}\s*[-–—]\s*(.+)$", title)
    if match:
        return match.group(1), match.group(2)
    return None, None


def _search_hal(author, title_keywords):
    """Search HAL for a paper by author surname and title keywords.

    Returns the PDF URL or None.
    """
    query = f"authLastName_t:{author} AND title_t:({title_keywords})"
    params = {
        "q": query,
        "rows": 5,
        "wt": "json",
        "fl": "halId_s,title_s,fileMain_s",
    }
    response = requests.get(HAL_SEARCH_URL, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        return None
    data = response.json()
    docs = data.get("response", {}).get("docs", [])
    for doc in docs:
        pdf_url = doc.get("fileMain_s")
        if pdf_url:
            return pdf_url
    return None


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a paper PDF from HAL by searching author + title.

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
        else:
            os.remove(file_path)

    author, title_keywords = _parse_author_title(title)
    if not author or not title_keywords:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": "Cannot parse author/title for HAL search",
        }

    try:
        pdf_url = _search_hal(author, title_keywords)
        if not pdf_url:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "No PDF found on HAL",
            }
        pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=TIMEOUT)
        if pdf_resp.status_code != 200:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"HAL PDF download failed: {pdf_resp.status_code}",
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
        return {
            "status": "success",
            "doi": doi,
            "title": title,
            "file_name": file_name,
        }
    except Exception as e:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Download a paper PDF from HAL")
    parser.add_argument("--doi", default="", help="DOI of the paper (optional)")
    parser.add_argument(
        "--title", required=True, help="Title in 'Author Year - Title' format"
    )
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
