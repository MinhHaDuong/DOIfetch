"""Fetch open-access paper PDFs via the Unpaywall API."""

import argparse
import os
import warnings

import urllib3

from config import PAPERS_DIR

warnings.filterwarnings("ignore", category=FutureWarning, module="pandas")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF via Unpaywall.

    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    safe_doi = doi.replace("/", "_").replace(":", "_")
    file_name = f"{safe_doi}.pdf"
    file_path = os.path.join(output_dir, file_name)

    import requests
    from pdf_utils import is_valid_pdf

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
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "Broken PDF file",
            }

    try:
        url = f"https://api.unpaywall.org/v2/{doi}?email=your@email.com"
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"Unpaywall API error: {response.status_code}",
            }
        data = response.json()
        oa = data.get("best_oa_location")
        if not oa or not oa.get("url_for_pdf"):
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "No open access PDF found",
            }
        pdf_url = oa["url_for_pdf"]
        pdf_resp = requests.get(pdf_url, timeout=60)
        if pdf_resp.status_code != 200:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"PDF download failed: {pdf_resp.status_code}",
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
