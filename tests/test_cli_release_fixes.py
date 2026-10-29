"""CLI behaviour pinned for v0.2.0: error reporting, batch reading, --source."""

import threading

from doifetch import cli
from doifetch.sources.contract import Result


def _stub_all(monkeypatch, outcome):
    for name in cli.SOURCES:
        monkeypatch.setitem(cli.SOURCES, name, outcome(name))


def test_all_failed_reports_every_tried_source(monkeypatch, tmp_path):
    _stub_all(
        monkeypatch,
        lambda name: lambda req: Result("failed", name, error=f"{name} reason"),
    )
    out = cli._fetch_one("10.1000/x", "T", str(tmp_path), "all")
    assert out["status"] == "failed"
    for name in cli.DEFAULT_ORDER:
        assert f"{name}: {name} reason" in out["error"]


def test_bad_isbn_exits_1_without_traceback(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["doifetch", "--isbn", "9780674009692", "--output-dir", str(tmp_path)],
    )
    monkeypatch.chdir(tmp_path)
    assert cli.main() == 1
    assert "Invalid ISBN" in capsys.readouterr().out


def test_bare_doi_line_in_batch_file_is_loaded(tmp_path):
    path = tmp_path / "refs.txt"
    path.write_text("10.1000/xyz123\tTitle A\nisbn:9780000000000\tBook\n")
    tasks, skipped = cli.load_download_tasks([str(path)])
    assert tasks == [("10.1000/xyz123", "Title A")]
    assert skipped == 1  # the bad ISBN


def test_progress_counts_the_item_in_flight(monkeypatch, tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "refs.txt").write_text("doi:10.1000/x\tT\n")
    release = threading.Event()

    def slow_fetch(doi, title, output_dir, source, zotero_db=None, keep_title=False):
        release.wait(5)
        return {"status": "failed", "doi": doi, "title": title, "error": "e"}

    def fake_sleep(_):
        release.set()
        for t in threading.enumerate():
            if t is not threading.current_thread() and t.daemon:
                t.join(5)

    monkeypatch.setattr(cli, "_fetch_one", slow_fetch)
    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    monkeypatch.setattr(cli, "LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "doifetch",
            "--data-dir",
            str(tmp_path / "data"),
            "--output-dir",
            str(tmp_path / "out"),
            "--no-check-zotero",
        ],
    )
    cli.main()
    assert "Remaining: 1 |" in capsys.readouterr().out


def test_named_source_not_accepting_the_kind_fails(monkeypatch, tmp_path):
    called = []
    _stub_all(
        monkeypatch,
        lambda name: lambda req: called.append(name) or Result("success", name),
    )
    out = cli._fetch_one("10.1000/x", "T", str(tmp_path), "libgen")
    assert out["status"] == "failed"
    assert "libgen" in out["error"] and "doi" in out["error"]
    assert called == []
