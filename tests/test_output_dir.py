"""Default output directory (ticket 0029): docs, overridable by --output-dir."""

import os

from doifetch import cli
from doifetch.sources.contract import Result


def _fetch_url(monkeypatch, tmp_path, *extra):
    """Run a single --url fetch from tmp_path; return the path asked of the source."""
    seen = []

    def fake(req):
        seen.append(req)
        return Result("success", "url", path=req.path)

    monkeypatch.setitem(cli.SOURCES, "url", fake)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "doifetch",
            "--url",
            "https://example.com/doc.pdf",
            "--title",
            "Doc",
            "--no-check-zotero",
            *extra,
        ],
    )
    assert cli.main() == 0
    return seen[0].path


def test_fetch_without_output_dir_writes_under_docs(monkeypatch, tmp_path):
    path = _fetch_url(monkeypatch, tmp_path)
    assert path == os.path.join("docs", "Doc.pdf")
    assert (tmp_path / "docs").is_dir()
    assert not (tmp_path / "papers").exists()


def test_output_dir_overrides_the_default(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere"
    path = _fetch_url(monkeypatch, tmp_path, "--output-dir", str(target))
    assert path == os.path.join(str(target), "Doc.pdf")
    assert target.is_dir()
    assert not (tmp_path / "docs").exists()
