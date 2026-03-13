"""Smoke tests: verify that the same 2 DOIs load correctly from all input formats."""

import download
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
    from table_utils import list_table_files

    all_files = list_table_files(str(sample_data_dir), "auto")
    tasks, skipped = download.load_download_tasks(all_files)
    assert len(tasks) == len(SAMPLE_DOIS) * 3
    assert {doi for doi, _ in tasks} == EXPECTED_DOIS
    assert skipped == 0
