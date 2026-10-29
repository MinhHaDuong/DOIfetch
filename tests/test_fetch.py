from types import SimpleNamespace

import pytest

from doifetch import cli


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
        ],
    )

    args = cli.parse_args()

    assert args.doi == "10.1000/example"
    assert args.title == "Example Paper"
    assert args.source == "crossref"


def test_load_download_tasks_reads_txt_and_skips_invalid_doi(tmp_path):
    file_path = tmp_path / "papers.txt"
    file_path.write_text(
        "doi:10.1000/valid\tValid Paper\ndoi:bad-doi\tInvalid Paper\n# comment\n\n",
        encoding="utf-8",
    )

    tasks, skipped_count = cli.load_download_tasks([str(file_path)])

    assert tasks == [("10.1000/valid", "Valid Paper")]
    assert skipped_count == 1


def test_handle_single_download_rejects_invalid_doi():
    args = SimpleNamespace(
        doi="bad-doi", title="Example", source="all", output_dir="papers"
    )

    with pytest.raises(ValueError):
        cli.handle_single_download(args)


def test_parse_args_supports_isbn(monkeypatch):
    monkeypatch.setattr("sys.argv", ["fetch.py", "--isbn", "9780262033848"])

    args = cli.parse_args()

    assert args.isbn == "9780262033848"


def test_handle_single_download_routes_isbn_to_libgen(monkeypatch, tmp_path):
    captured = {}

    def fake_libgen(doi, title, output_dir):
        captured["doi"] = doi
        return {"status": "success", "doi": doi, "title": title, "file_name": "b.pdf"}

    monkeypatch.setattr(cli.libgen, "fetch_pdf", fake_libgen)

    args = SimpleNamespace(
        doi=None,
        isbn="9780262033848",
        title="Some Book",
        source="libgen",
        output_dir=str(tmp_path),
        no_check_zotero=True,
    )

    rc = cli.handle_single_download(args)

    assert rc == 0
    assert captured["doi"] == "isbn:9780262033848"


def test_shared_title_failed_row_stays_on_retry_list(tmp_path):
    refs = tmp_path / "refs.txt"
    refs.write_text(
        "doi:10.1000/ok\tSame Title\ndoi:10.1000/failed\tSame Title\n",
        encoding="utf-8",
    )

    cli.update_source_files([str(refs)], [("Same Title", "https://doi.org/10.1000/ok")])

    assert refs.read_text(encoding="utf-8") == "doi:10.1000/failed\tSame Title\n"


def test_txt_round_trip_keeps_prefixes_and_titles(tmp_path):
    refs = tmp_path / "refs.txt"
    refs.write_text(
        "# No DOI or ISBN:\n"
        "#\tAyres & Kneese 1969\n"
        "doi:10.1000/done\tDone\n"
        "doi:10.1000/left\tLeft\n"
        "url:https://example.com/doc.pdf\tDoc\n"
        "isbn:9780674009691\tBook\n",
        encoding="utf-8",
    )

    cli.update_source_files(
        [str(refs)],
        [
            ("Done", "https://doi.org/10.1000/done"),
            ("Book", "https://doi.org/isbn:9780674009691"),
        ],
    )

    # Fetched rows are dropped; the rest keep their prefixes and titles.
    # Comment lines (including '#<TAB>label') are not rows: the rewrite drops them.
    assert refs.read_text(encoding="utf-8") == (
        "doi:10.1000/left\tLeft\nurl:https://example.com/doc.pdf\tDoc\n"
    )


def test_hyphenated_isbn_row_is_dropped_after_success(tmp_path):
    refs = tmp_path / "refs.txt"
    refs.write_text(
        "isbn:978-0-306-40615-7\tHyphenated\n"
        "isbn:9780674009691\tPlain\n"
        "doi:10.1000/left\tLeft\n",
        encoding="utf-8",
    )

    # The queued task carries the normalized ISBN, so the success link does too.
    cli.update_source_files(
        [str(refs)],
        [
            ("Hyphenated", "https://doi.org/isbn:9780306406157"),
            ("Plain", "https://doi.org/isbn:9780674009691"),
        ],
    )

    assert refs.read_text(encoding="utf-8") == "doi:10.1000/left\tLeft\n"
