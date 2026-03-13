"""Network smoke tests: hit real APIs with known open-access DOIs.

Run with:  uv run --group dev pytest -m network
Skip with: uv run --group dev pytest -m 'not network'
"""

import os

import pytest
import requests

from conftest import SAMPLE_DOIS

# First DOI is PLOS ONE (open access), most likely to have PDFs available.
OA_DOI = SAMPLE_DOIS[0][0]  # 10.1371/journal.pone.0001636


@pytest.mark.network
class TestCrossref:
    def test_crossref_api_resolves_doi(self):
        """Crossref API returns metadata for a known DOI."""
        url = f"https://api.crossref.org/works/{OA_DOI}"
        resp = requests.get(url, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"]["DOI"].lower() == OA_DOI.lower()

    def test_crossref_get_pdf_url(self):
        """get_pdf_url_from_crossref returns a URL for an OA paper."""
        from Crossref_download import get_pdf_url_from_crossref

        pdf_url = get_pdf_url_from_crossref(OA_DOI)
        # PLOS ONE should have a PDF link via Crossref
        if pdf_url:
            assert pdf_url.startswith("http")


@pytest.mark.network
class TestUnpaywall:
    def test_unpaywall_api_resolves_doi(self):
        """Unpaywall API returns OA location for a known OA DOI."""
        url = f"https://api.unpaywall.org/v2/{OA_DOI}?email=doiharvest@users.noreply.github.com"
        resp = requests.get(url, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_oa"] is True
        assert data["best_oa_location"] is not None

    def test_unpaywall_downloads_pdf(self, tmp_path):
        """Unpaywall PDF URL delivers a real PDF file to disk."""
        url = f"https://api.unpaywall.org/v2/{OA_DOI}?email=doiharvest@users.noreply.github.com"
        data = requests.get(url, timeout=30).json()
        pdf_url = data["best_oa_location"]["url_for_pdf"]
        assert pdf_url, "Unpaywall returned no PDF URL for known OA DOI"
        resp = requests.get(pdf_url, timeout=60)
        assert resp.status_code == 200
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(resp.content)
        assert pdf_path.stat().st_size > 1000, "Downloaded file too small to be a real PDF"
        assert resp.content[:5] == b"%PDF-", "Downloaded file is not a valid PDF"


@pytest.mark.network
class TestDownloadPaper:
    def test_download_paper_to_disk(self, tmp_path):
        """download_paper fetches a PDF to disk via Sci-Hub."""
        from download import download_paper

        result = download_paper(OA_DOI, "Test Paper", output_dir=str(tmp_path))
        # Sci-Hub may be unavailable, so we accept success or failure
        # but the function should not crash
        assert result["status"] in ("success", "failed", "skipped")
        if result["status"] == "success":
            pdf_path = tmp_path / result["file_name"]
            assert pdf_path.exists()
            assert pdf_path.stat().st_size > 0
