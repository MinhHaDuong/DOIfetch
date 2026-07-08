"""Fetch paper fulltext PDFs from the ISTEX national licensed archive by DOI.

ISTEX (https://www.istex.fr) hosts the full text of publisher back-catalogues
licensed nationally for French higher education and research. Fulltext download
requires a personal access token: generate one at https://api.istex.fr/token/
(you are redirected to your institution's identity federation, e.g. Janus for
CNRS) and expose it in the ISTEX_ACCESSTOKEN environment variable.

Resolution is by DOI: the search API maps the DOI to an ISTEX document id, then
the fulltext endpoint returns the PDF under a Bearer-token Authorization header.
"""

import argparse
import os

import requests

from config import PAPERS_DIR, TIMEOUT

TOKEN_ENV = "ISTEX_ACCESSTOKEN"
ISTEX_SEARCH_URL = "https://api.istex.fr/document/"
ISTEX_FULLTEXT_URL = "https://api.istex.fr/document/{id}/fulltext/pdf"


def _get_token():
    """Read the personal ISTEX access token from the environment."""
    return os.environ.get(TOKEN_ENV, "").strip()


def _resolve_istex_id(doi):
    """Return the ISTEX document id for a DOI, or None if absent from the archive."""
    params = {"q": f'doi:"{doi}"', "size": 1, "output": "id"}
    response = requests.get(ISTEX_SEARCH_URL, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        return None
    hits = response.json().get("hits", [])
    return hits[0]["id"] if hits else None


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF from ISTEX by DOI.

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

    token = _get_token()
    if not token:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": f"{TOKEN_ENV} not set (generate at https://api.istex.fr/token/)",
        }

    if not doi:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": "ISTEX resolution requires a DOI",
        }

    try:
        istex_id = _resolve_istex_id(doi)
        if not istex_id:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "DOI not found in ISTEX",
            }
        response = requests.get(
            ISTEX_FULLTEXT_URL.format(id=istex_id),
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"ISTEX fulltext download failed: {response.status_code}",
            }
        with open(file_path, "wb") as f:
            f.write(response.content)
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
    parser = argparse.ArgumentParser(
        description="Download a paper fulltext PDF from ISTEX by DOI"
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
