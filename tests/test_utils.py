import pandas as pd

from table_utils import list_table_files, read_table, write_table


def test_list_table_files_filters_by_format(tmp_path):
    (tmp_path / "papers.csv").write_text("DOI,Article Title\n", encoding="utf-8")
    (tmp_path / "papers.xlsx").write_text("placeholder", encoding="utf-8")
    (tmp_path / "refs.txt").write_text("doi:10.1000/test\tTest\n", encoding="utf-8")

    auto_files = list_table_files(str(tmp_path), "auto")
    csv_files = list_table_files(str(tmp_path), "csv")
    excel_files = list_table_files(str(tmp_path), "excel")
    txt_files = list_table_files(str(tmp_path), "txt")

    assert auto_files == [
        str(tmp_path / "papers.csv"),
        str(tmp_path / "papers.xlsx"),
        str(tmp_path / "refs.txt"),
    ]
    assert csv_files == [str(tmp_path / "papers.csv")]
    assert excel_files == [str(tmp_path / "papers.xlsx")]
    assert txt_files == [str(tmp_path / "refs.txt")]


def test_csv_round_trip(tmp_path):
    file_path = tmp_path / "input.csv"
    expected = pd.DataFrame(
        [
            {
                "DOI": "10.1000/test",
                "Article Title": "Example Title",
                "Download Status": "pending",
            },
        ]
    )

    write_table(expected, str(file_path))
    actual = read_table(str(file_path))

    pd.testing.assert_frame_equal(actual, expected)


def test_read_txt(tmp_path):
    txt_file = tmp_path / "refs.txt"
    txt_file.write_text(
        "doi:10.1080/03085140903020580\tÇalışkan & Callon 2009 - Economization\n"
        "doi:10.1016/j.shpsc.2010.08.002\tDahan 2010 - Numerical Box\n"
        "url:https://example.com/doc.pdf\tSome Document\n"
        "isbn:9780674009691\tDesrosières 1998\n"
        "# No DOI or ISBN:\n"
        "#\tAyres & Kneese 1969\n"
        "\n",
        encoding="utf-8",
    )

    df = read_table(str(txt_file))

    assert list(df.columns) == ["DOI", "Article Title"]
    assert len(df) == 2
    assert df.iloc[0]["DOI"] == "10.1080/03085140903020580"
    assert df.iloc[0]["Article Title"] == "Çalışkan & Callon 2009 - Economization"
    assert df.iloc[1]["DOI"] == "10.1016/j.shpsc.2010.08.002"


def test_write_table_noop_for_txt(tmp_path):
    txt_file = tmp_path / "refs.txt"
    txt_file.write_text("doi:10.1000/test\tTest\n", encoding="utf-8")
    original = txt_file.read_text()

    df = pd.DataFrame([{"DOI": "10.9999/new", "Article Title": "New"}])
    write_table(df, str(txt_file))

    assert txt_file.read_text() == original
