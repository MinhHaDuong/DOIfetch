"""Fetch open-access paper PDFs via the Unpaywall API."""

import argparse
import os
import warnings

import requests
import urllib3

from config import PAPERS_DIR, UNPAYWALL_EMAIL

warnings.filterwarnings("ignore", category=FutureWarning, module="pandas")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF via Unpaywall.

    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    safe_doi = doi.replace("/", "_").replace(":", "_")
    file_name = f"{safe_doi}.pdf"
    file_path = os.path.join(output_dir, file_name)

    if os.path.exists(file_path):
        return {
            "status": "skipped",
            "doi": doi,
            "title": title,
            "file_name": file_name,
        }

    try:
        url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
        response = requests.get(url).json()

        if "best_oa_location" not in response or not response["best_oa_location"]:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"No open access version for {doi}",
            }

        pdf_url = response["best_oa_location"]["url_for_pdf"]
        if not pdf_url:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"No PDF found for {doi}",
            }

        paper = requests.get(pdf_url, verify=False)
        with open(file_path, "wb") as f:
            f.write(paper.content)
        print(f"Downloaded: {doi}")
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
            "error": f"Error downloading {doi}: {str(e)}",
        }


def main():
    parser = argparse.ArgumentParser(description="Download a paper PDF via Unpaywall")
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
