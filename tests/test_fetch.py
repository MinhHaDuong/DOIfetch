from types import SimpleNamespace

import pytest

import fetch


def test_parse_args_supports_single_download_and_source(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "fetch.py",
            "--doi",
            "10.1000/example",
            "--title",
            "Example Paper",
            "--source",
            "crossref",
            "--input-format",
            "csv",
        ],
    )

    args = fetch.parse_args()

    assert args.doi == "10.1000/example"
    assert args.title == "Example Paper"
    assert args.source == "crossref"
    assert args.input_format == "csv"


def test_load_download_tasks_reads_csv_and_skips_invalid_doi(tmp_path):
    file_path = tmp_path / "papers.csv"
    file_path.write_text(
        "DOI,Article Title\n"
        "10.1000/valid,Valid Paper\n"
        "bad-doi,Invalid Paper\n"
        ",Title Only\n",
        encoding="utf-8",
    )

    tasks, skipped_count = fetch.load_download_tasks([str(file_path)])

    assert tasks == [("10.1000/valid", "Valid Paper"), ("", "Title Only")]
    assert skipped_count == 1


def test_handle_single_download_rejects_invalid_doi():
    args = SimpleNamespace(
        doi="bad-doi", title="Example", source="all", output_dir="papers"
    )

    with pytest.raises(ValueError):
        fetch.handle_single_download(args)
