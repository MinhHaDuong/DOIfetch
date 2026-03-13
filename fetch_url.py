"""Fetch paper PDFs directly from a URL."""

import argparse
import os

import requests

from config import HEADERS, PAPERS_DIR, TIMEOUT


def fetch_pdf(url, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF from a direct URL.

    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    from pdf_utils import clean_filename, is_valid_pdf

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
    except Exception as e:
        return {
            "status": "failed",
            "doi": url,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Download a paper PDF from a URL")
    parser.add_argument("--url", required=True, help="Direct URL to the PDF")
    parser.add_argument("--title", default="", help="Title of the paper")
    parser.add_argument("--output-dir", default=PAPERS_DIR, help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    result = fetch_pdf(args.url, args.title, args.output_dir)

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
