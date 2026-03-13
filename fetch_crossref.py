"""Fetch open-access paper PDFs via the Crossref API."""

import argparse
import os
import warnings

import requests
import urllib3

from config import PAPERS_DIR

warnings.filterwarnings("ignore", category=FutureWarning, module="pandas")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DoiNotFoundError(Exception):
    """Raised when Crossref returns 404 for a DOI."""


def get_pdf_url(doi):
    """Use the Crossref API to get a PDF download link.

    Raises DoiNotFoundError if the DOI is not registered in Crossref.
    Returns None if registered but no open-access PDF link is available.
    """
    try:
        api_url = f"https://api.crossref.org/works/{doi}"
        response = requests.get(api_url, verify=False)

        if response.status_code == 404:
            raise DoiNotFoundError(f"DOI not found in Crossref (404): {doi}")
        if response.status_code != 200:
            print(f"Crossref API error {response.status_code} for {doi}")
            return None

        data = response.json()
        message = data.get("message", {})

        links = message.get("link", [])
        pdf_links = [
            link["URL"]
            for link in links
            if link.get("content-type") == "application/pdf"
            and link.get("content-version") == "vor"
        ]

        return pdf_links[0] if pdf_links else None

    except DoiNotFoundError:
        raise
    except Exception as e:
        print(f"Error getting PDF link for {doi}: {str(e)}")
        return None


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF via Crossref.

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

    try:
        pdf_url = get_pdf_url(doi)
        if not pdf_url:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "No open access PDF found in Crossref",
            }
    except DoiNotFoundError as e:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }
    try:
        paper = requests.get(pdf_url, verify=False)
        if paper.status_code != 200:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"PDF download failed: {paper.status_code}",
            }
        with open(file_path, "wb") as f:
            f.write(paper.content)
        if not is_valid_pdf(file_path):
            os.remove(file_path)
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "Broken PDF file",
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
    parser = argparse.ArgumentParser(description="Download a paper PDF via Crossref")
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
