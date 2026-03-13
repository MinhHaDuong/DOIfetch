import pandas as pd

from table_utils import list_table_files, read_table, write_table


def test_list_table_files_filters_by_format(tmp_path):
    (tmp_path / "papers.csv").write_text("DOI,Article Title\n", encoding="utf-8")
    (tmp_path / "papers.xlsx").write_text("placeholder", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    auto_files = list_table_files(str(tmp_path), "auto")
    csv_files = list_table_files(str(tmp_path), "csv")
    excel_files = list_table_files(str(tmp_path), "excel")

    assert auto_files == [str(tmp_path / "papers.csv"), str(tmp_path / "papers.xlsx")]
    assert csv_files == [str(tmp_path / "papers.csv")]
    assert excel_files == [str(tmp_path / "papers.xlsx")]


def test_csv_round_trip(tmp_path):
    file_path = tmp_path / "input.csv"
    expected = pd.DataFrame(
        [
            {"DOI": "10.1000/test", "Article Title": "Example Title", "Download Status": "pending"},
        ]
    )

    write_table(expected, str(file_path))
    actual = read_table(str(file_path))

    pd.testing.assert_frame_equal(actual, expected)