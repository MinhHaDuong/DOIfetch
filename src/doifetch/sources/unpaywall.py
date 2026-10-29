"""Fetch open-access paper PDFs via the Unpaywall API."""

import os

import urllib3

from doifetch.config import PAPERS_DIR, UNPAYWALL_EMAIL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF via Unpaywall.

    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    import requests

    from doifetch.pdf_utils import clean_filename, is_valid_pdf

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
        url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
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
    except Exception as e:  # noqa: BLE001 - a fetcher reports failure, never raises into the fetch loop
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }
