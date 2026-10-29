"""Network smoke tests: hit real APIs with known open-access DOIs.

Run with:  uv run --group dev pytest -m network
Skip with: uv run --group dev pytest -m 'not network'
"""

import json

import pytest
from conftest import SAMPLE_DOIS

from doifetch.config import UNPAYWALL_EMAIL
from doifetch.sources import _http
from doifetch.sources.contract import Request

# First DOI is PLOS ONE (open access), most likely to have PDFs available.
OA_DOI = SAMPLE_DOIS[0][0]  # 10.1371/journal.pone.0001636


@pytest.mark.network
class TestCrossref:
    def test_crossref_api_resolves_doi(self):
        """Crossref API returns metadata for a known DOI."""
        url = f"https://api.crossref.org/works/{OA_DOI}"
        resp = _http.get(url, timeout=30)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["message"]["DOI"].lower() == OA_DOI.lower()

    def test_crossref_get_pdf_url(self):
        """get_pdf_url runs without error and returns URL or None."""
        from doifetch.sources.crossref import get_pdf_url

        pdf_url = get_pdf_url(OA_DOI)
        # Not all OA papers have direct PDF links in Crossref
        if pdf_url:
            assert pdf_url.startswith("http")

    def test_crossref_404_for_unknown_doi(self, tmp_path):
        """fetch_pdf reports a clear error for a DOI that does not exist in Crossref."""
        from doifetch.sources.crossref import fetch

        req = Request("doi", "10.9999/nonexistent.doi.000", str(tmp_path / "t.pdf"))
        result = fetch(req)
        assert result.status == "failed"
        error = (result.error or "").lower()
        assert "404" in error or "not found" in error

    def test_crossref_downloads_pdf(self, tmp_path):
        """If Crossref provides a PDF URL, it delivers a real PDF."""
        from doifetch.sources.crossref import get_pdf_url

        pdf_url = get_pdf_url(OA_DOI)
        if not pdf_url:
            pytest.skip("Crossref has no PDF link for this DOI")
        resp = _http.get(pdf_url, timeout=60)
        assert resp.status == 200
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(resp.content)
        assert pdf_path.stat().st_size > 1000, (
            "Downloaded file too small to be a real PDF"
        )
        assert resp.content[:5] == b"%PDF-", "Downloaded file is not a valid PDF"


@pytest.mark.network
class TestUnpaywall:
    def test_unpaywall_api_resolves_doi(self):
        """Unpaywall API returns OA location for a known OA DOI."""
        url = f"https://api.unpaywall.org/v2/{OA_DOI}?email={UNPAYWALL_EMAIL}"
        resp = _http.get(url, timeout=30)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["is_oa"] is True
        assert data["best_oa_location"] is not None

    def test_unpaywall_downloads_pdf(self, tmp_path):
        """Unpaywall PDF URL delivers a real PDF file to disk."""
        url = f"https://api.unpaywall.org/v2/{OA_DOI}?email={UNPAYWALL_EMAIL}"
        data = json.loads(_http.get(url, timeout=30).text)
        pdf_url = data["best_oa_location"]["url_for_pdf"]
        assert pdf_url, "Unpaywall returned no PDF URL for known OA DOI"
        resp = _http.get(pdf_url, timeout=60)
        assert resp.status == 200
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(resp.content)
        assert pdf_path.stat().st_size > 1000, (
            "Downloaded file too small to be a real PDF"
        )
        assert resp.content[:5] == b"%PDF-", "Downloaded file is not a valid PDF"


@pytest.mark.network
class TestSciHub:
    def test_fetch_pdf_to_disk(self, tmp_path):
        """fetch_pdf fetches a PDF to disk via Sci-Hub."""
        from doifetch.sources.contract import Request
        from doifetch.sources.scihub import fetch

        path = tmp_path / "Test Paper.pdf"
        result = fetch(Request("doi", OA_DOI, str(path)))
        # Sci-Hub may be unavailable, so we accept success or failure
        # but the function should not crash
        assert result.status in ("success", "failed", "skipped")
        if result.status == "success":
            assert path.exists()
            assert path.stat().st_size > 1000
            with open(path, "rb") as f:
                assert f.read(5) == b"%PDF-"
