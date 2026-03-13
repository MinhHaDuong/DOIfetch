"""Smoke tests: verify that the same 2 DOIs load correctly from all input formats."""

import download
from Crossref_download import read_doi_from_table as crossref_read
from Unpaywall_download import read_doi_from_table as unpaywall_read
from conftest import SAMPLE_DOIS


EXPECTED_DOIS = {doi for doi, _ in SAMPLE_DOIS}


def test_load_tasks_from_csv(sample_data_dir):
    tasks, skipped = download.load_download_tasks(
        [str(sample_data_dir / "refs.csv")]
    )
    assert {doi for doi, _ in tasks} == EXPECTED_DOIS
    assert skipped == 0


def test_load_tasks_from_xlsx(sample_data_dir):
    tasks, skipped = download.load_download_tasks(
        [str(sample_data_dir / "refs.xlsx")]
    )
    assert {doi for doi, _ in tasks} == EXPECTED_DOIS
    assert skipped == 0


def test_load_tasks_from_txt(sample_data_dir):
    tasks, skipped = download.load_download_tasks(
        [str(sample_data_dir / "refs.txt")]
    )
    assert {doi for doi, _ in tasks} == EXPECTED_DOIS
    assert skipped == 0


def test_load_tasks_from_all_formats(sample_data_dir):
    """Auto-detect picks up all 3 files, yielding 2 DOIs x 3 formats = 6 tasks."""
    from utils import list_table_files

    all_files = list_table_files(str(sample_data_dir), "auto")
    tasks, skipped = download.load_download_tasks(all_files)
    assert len(tasks) == len(SAMPLE_DOIS) * 3
    assert {doi for doi, _ in tasks} == EXPECTED_DOIS
    assert skipped == 0


def test_crossref_read_doi_from_csv(sample_data_dir):
    """Crossref read_doi_from_table works with CSV."""
    dois, df = crossref_read(str(sample_data_dir / "refs.csv"))
    assert {doi for doi, _ in dois} == EXPECTED_DOIS
    assert df is not None
    assert len(dois) == 2


def test_crossref_read_doi_from_txt(sample_data_dir):
    """Crossref read_doi_from_table works with TXT."""
    dois, df = crossref_read(str(sample_data_dir / "refs.txt"))
    assert {doi for doi, _ in dois} == EXPECTED_DOIS
    assert len(dois) == 2


def test_unpaywall_read_doi_from_csv(sample_data_dir):
    """Unpaywall read_doi_from_table works with CSV."""
    dois, df = unpaywall_read(str(sample_data_dir / "refs.csv"))
    assert {doi for doi, _ in dois} == EXPECTED_DOIS
    assert df is not None
    assert len(dois) == 2


def test_unpaywall_read_doi_from_txt(sample_data_dir):
    """Unpaywall read_doi_from_table works with TXT."""
    dois, df = unpaywall_read(str(sample_data_dir / "refs.txt"))
    assert {doi for doi, _ in dois} == EXPECTED_DOIS
    assert len(dois) == 2
