import subprocess
import sys
from pathlib import Path

import pytest

from doifetch.utils import list_table_files, read_table, require, write_table


def test_list_table_files_lists_txt_only(tmp_path):
    (tmp_path / "papers.csv").write_text("DOI,Article Title\n", encoding="utf-8")
    (tmp_path / "papers.xlsx").write_text("placeholder", encoding="utf-8")
    (tmp_path / "refs.txt").write_text("doi:10.1000/test\tTest\n", encoding="utf-8")

    assert list_table_files(str(tmp_path)) == [str(tmp_path / "refs.txt")]


@pytest.mark.parametrize("name", ["refs.csv", "refs.xlsx", "refs.xls"])
def test_non_txt_tables_are_refused(tmp_path, name):
    with pytest.raises(ValueError, match="only .txt"):
        read_table(str(tmp_path / name))
    with pytest.raises(ValueError, match="only .txt"):
        write_table([{"DOI": "10.1000/test"}], str(tmp_path / name))


def test_txt_round_trip_from_missing_references_producer(tmp_path):
    """Shape written by qa_missing_references.py: '#<TAB>label' lines for
    references without an identifier. They are comments, so reading skips them
    and the rewrite does not carry them over."""
    file_path = tmp_path / "missing_references.txt"
    file_path.write_text(
        "doi:10.1000/a\tA\n#\tAyres & Kneese 1969\nisbn:9780674009691\tBook\n",
        encoding="utf-8",
    )

    rows = read_table(str(file_path))
    write_table(rows, str(file_path))

    assert [r["DOI"] for r in rows] == ["10.1000/a", "isbn:9780674009691"]
    assert file_path.read_text(encoding="utf-8") == (
        "doi:10.1000/a\tA\nisbn:9780674009691\tBook\n"
    )


def test_missing_extra_names_it():
    with pytest.raises(ImportError, match=r"'shadow' extra.*doifetch\[shadow\]"):
        require("no_such_module_doifetch", "shadow")


ROOT = Path(__file__).resolve().parent.parent

# Run in a child interpreter whose import system refuses the optional
# dependencies, so the core is proven to work without them installed.
_BLOCK_EXTRAS = """
import sys
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"pandas", "numpy", "bs4", "tqdm"}:
            raise ImportError("blocked: " + name)
sys.meta_path.insert(0, Block())
sys.argv = ["doifetch"] + sys.argv[1:]
"""


def _run_core(code, *args, cwd):
    return subprocess.run(
        [sys.executable, "-c", _BLOCK_EXTRAS + code, *args],
        cwd=cwd,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_core_runs_without_extras(tmp_path):
    done = _run_core("from doifetch import cli; cli.main()", "--help", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "--doi" in done.stdout


def test_doi_mode_needs_no_extras(tmp_path):
    """--doi runs the default cascade to the end with the optional libraries blocked."""
    code = (
        "from doifetch.sources import _http\n"
        "def offline(*a, **k):\n"
        "    raise _http.HttpError('offline')\n"
        "_http.Session.request = offline\n"
        "from doifetch import cli\n"
        "raise SystemExit(cli.main())\n"
    )
    done = _run_core(
        code, "--doi", "10.1000/a", "--title", "T", "--no-check-zotero", cwd=tmp_path
    )
    assert done.returncode == 1, done.stderr
    assert "Traceback" not in done.stderr
    assert "Download failed" in done.stdout


def test_txt_batch_needs_no_extras(tmp_path):
    (tmp_path / "refs.txt").write_text(
        "doi:10.1000/a\tA\ndoi:10.1000/b\tB\n", encoding="utf-8"
    )
    code = (
        "from doifetch import cli, utils\n"
        "files = utils.list_table_files('.')\n"
        "tasks, skipped = cli.load_download_tasks(files)\n"
        "print(sorted(tasks), skipped)\n"
        "cli.update_source_files(files, [('B', 'https://doi.org/10.1000/b')])\n"
    )
    done = _run_core(code, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "[('10.1000/a', 'A'), ('10.1000/b', 'B')] 0" in done.stdout
    assert (tmp_path / "refs.txt").read_text(encoding="utf-8") == "doi:10.1000/a\tA\n"


@pytest.mark.parametrize(
    "source, kind, identifier",
    [("scihub", "doi", "10.1000/a"), ("libgen", "isbn", "9780000000000")],
)
def test_shadow_source_without_extra_fails_clearly(tmp_path, source, kind, identifier):
    """No network call: the missing extra is reported before any request."""
    code = (
        "from doifetch.sources import _http\n"
        "def no_network(*a, **k):\n"
        "    raise AssertionError('network call')\n"
        "_http.get = _http.Session.request = no_network\n"
        f"from doifetch.sources import {source}\n"
        "from doifetch.sources.contract import Request\n"
        f"result = {source}.fetch(Request({kind!r}, {identifier!r}, 'T.pdf'))\n"
        "print(result.status, result.error)\n"
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
