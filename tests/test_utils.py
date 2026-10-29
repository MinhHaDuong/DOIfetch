import subprocess
import sys
from pathlib import Path

import pytest

from utils import list_table_files, read_table, require, write_table


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
    expected = [
        {
            "DOI": "10.1000/test",
            "Article Title": "Example Title",
            "Download Status": "pending",
        },
        {"DOI": "", "Article Title": "No DOI, with a comma", "Download Status": ""},
    ]

    write_table(expected, str(file_path))
    actual = read_table(str(file_path))

    assert actual == expected


def test_csv_bom_short_and_long_rows(tmp_path):
    file_path = tmp_path / "excel-export.csv"
    file_path.write_bytes(
        b"\xef\xbb\xbfDOI,Article Title\n10.1000/a,A,surplus\n10.1000/b\n,\n"
    )

    assert read_table(str(file_path)) == [
        {"DOI": "10.1000/a", "Article Title": "A"},
        {"DOI": "10.1000/b", "Article Title": ""},
    ]


def test_xlsx_round_trip(tmp_path):
    file_path = tmp_path / "input.xlsx"
    expected = [
        {"DOI": "10.1000/test", "Article Title": "Example Title"},
        {"DOI": "", "Article Title": "Title only"},
    ]

    write_table(expected, str(file_path))

    assert read_table(str(file_path)) == expected


def test_write_xls_is_refused(tmp_path):
    with pytest.raises(ValueError, match="only .txt, .csv and .xlsx"):
        write_table([{"DOI": "10.1000/test"}], str(tmp_path / "old.xls"))


def test_missing_extra_names_it():
    with pytest.raises(ImportError, match=r"'excel' extra.*doifetch\[excel\]"):
        require("no_such_module_doifetch", "excel")


ROOT = Path(__file__).resolve().parent.parent

# Run in a child interpreter whose import system refuses the optional
# dependencies, so the core is proven to work without them installed.
_BLOCK_EXTRAS = """
import sys
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"pandas", "numpy", "openpyxl", "xlrd", "bs4", "tqdm"}:
            raise ImportError("blocked: " + name)
sys.meta_path.insert(0, Block())
sys.argv = ["doifetch"] + sys.argv[1:]
"""


def _run_core(code, *args, cwd):
    return subprocess.run(
        [sys.executable, "-c", _BLOCK_EXTRAS + code, *args],
        cwd=cwd,
        env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_core_runs_without_extras(tmp_path):
    done = _run_core("import fetch; fetch.main()", "--help", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "--doi" in done.stdout


def test_txt_and_csv_batch_need_no_extras(tmp_path):
    (tmp_path / "refs.txt").write_text("doi:10.1000/a\tA\n", encoding="utf-8")
    (tmp_path / "refs.csv").write_text(
        "DOI,Article Title\n10.1000/b,B\n", encoding="utf-8"
    )
    code = (
        "import fetch, utils\n"
        "files = utils.list_table_files('.', 'auto')\n"
        "tasks, skipped = fetch.load_download_tasks(files)\n"
        "print(sorted(tasks), skipped)\n"
        "fetch.update_source_files(files, [('B', 'https://doi.org/10.1000/b')])\n"
    )
    done = _run_core(code, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "[('10.1000/a', 'A'), ('10.1000/b', 'B')] 0" in done.stdout
    assert "success" in (tmp_path / "refs.csv").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "source, identifier", [("scihub", "10.1000/a"), ("libgen", "isbn:9780000000000")]
)
def test_shadow_source_without_extra_fails_clearly(tmp_path, source, identifier):
    """No network call: the missing extra is reported before any request."""
    code = (
        "import requests\n"
        "def no_network(*a, **k):\n"
        "    raise AssertionError('network call')\n"
        "requests.get = requests.Session.get = no_network\n"
        f"import fetch_{source}\n"
        f"result = fetch_{source}.fetch_pdf({identifier!r}, 'T', '.')\n"
        "print(result['status'], result['error'])\n"
    )
    done = _run_core(code, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("failed ")
    assert "doifetch[shadow]" in done.stdout


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

    assert all(list(row) == ["DOI", "Article Title"] for row in df)
    assert len(df) == 4
    assert df[0]["DOI"] == "10.1080/03085140903020580"
    assert df[0]["Article Title"] == "Çalışkan & Callon 2009 - Economization"
    assert df[1]["DOI"] == "10.1016/j.shpsc.2010.08.002"
    assert df[2]["DOI"] == "url:https://example.com/doc.pdf"
    assert df[2]["Article Title"] == "Some Document"
    assert df[3]["DOI"] == "isbn:9780674009691"
    assert df[3]["Article Title"] == "Desrosières 1998"


def test_write_table_noop_for_txt(tmp_path):
    txt_file = tmp_path / "refs.txt"
    txt_file.write_text("doi:10.1000/test\tTest\n", encoding="utf-8")

    df = [{"DOI": "10.9999/new", "Article Title": "New"}]
    write_table(df, str(txt_file))

    # The file should now contain the new DOI and title
    assert txt_file.read_text() == "doi:10.9999/new\tNew\n"
