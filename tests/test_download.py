from types import SimpleNamespace

import pytest

import download


def test_parse_args_supports_single_download_and_csv(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "download.py",
            "--doi",
            "10.1000/example",
            "--title",
            "Example Paper",
            "--input-format",
            "csv",
        ],
    )

    args = download.parse_args()

    assert args.doi == "10.1000/example"
    assert args.title == "Example Paper"
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

    tasks, skipped_count = download.load_download_tasks([str(file_path)])

    assert tasks == [("10.1000/valid", "Valid Paper"), ("", "Title Only")]
    assert skipped_count == 1


def test_handle_single_download_rejects_invalid_doi():
    args = SimpleNamespace(doi="bad-doi", title="Example")

    with pytest.raises(ValueError):
        download.handle_single_download(args)