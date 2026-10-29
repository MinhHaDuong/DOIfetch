"""Smoke tests: verify that the same 2 DOIs load correctly from a .txt list."""

from conftest import SAMPLE_DOIS

import fetch
from utils import read_doi_from_table

EXPECTED_DOIS = {doi for doi, _ in SAMPLE_DOIS}


def test_load_tasks_from_txt(sample_data_dir):
    tasks, skipped = fetch.load_download_tasks([str(sample_data_dir / "refs.txt")])
    assert {doi for doi, _ in tasks} == EXPECTED_DOIS
    assert skipped == 0


def test_read_doi_from_txt(sample_data_dir):
    """read_doi_from_table works with TXT."""
    dois, df = read_doi_from_table(str(sample_data_dir / "refs.txt"))
    assert {doi for doi, _ in dois} == EXPECTED_DOIS
    assert len(dois) == 2
