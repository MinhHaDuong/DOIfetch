"""Fetch open-access paper PDFs via the Crossref API."""

import logging
import os

import requests
import urllib3

from doifetch.config import PAPERS_DIR, TIMEOUT, UNPAYWALL_EMAIL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class DoiNotFoundError(Exception):
    """Raised when Crossref returns 404 for a DOI."""


def get_metadata(doi):
    """Return the Crossref `message` dict for a DOI.

    Raises DoiNotFoundError if the DOI is not registered in Crossref (404).
    Returns None on any other failure (network error, non-200 status, bad JSON).
    TLS is verified and the request carries a timeout and a contact address
    (Crossref polite pool).
    """
    try:
        response = requests.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": f"DOIfetch/1.0 (mailto:{UNPAYWALL_EMAIL})"},
            timeout=TIMEOUT,
        )
        if response.status_code == 404:
            raise DoiNotFoundError(f"DOI not found in Crossref (404): {doi}")
        if response.status_code != 200:
            logger.warning("Crossref API error %s for %s", response.status_code, doi)
            return None
        body = response.json()
        if not isinstance(body, dict):
            logger.warning("Crossref returned a non-object body for %s", doi)
            return None
        return body.get("message", {})
    except DoiNotFoundError:
        raise
    except (requests.RequestException, ValueError) as e:
        logger.warning("Crossref metadata request failed for %s: %s", doi, e)
        return None


def get_pdf_url(doi):
    """Use the Crossref API to get a PDF download link.

    Raises DoiNotFoundError if the DOI is not registered in Crossref.
    Returns None if registered but no open-access PDF link is available.
    """
    message = get_metadata(doi)
    if not message:
        return None
    pdf_links = [
        link["URL"]
        for link in message.get("link", [])
        if link.get("content-type") == "application/pdf"
        and link.get("content-version") == "vor"
    ]
    return pdf_links[0] if pdf_links else None


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF via Crossref.

    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
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
        paper = requests.get(pdf_url, timeout=60)
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
    except Exception as e:  # noqa: BLE001 - a fetcher reports failure, never raises into the fetch loop
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }
