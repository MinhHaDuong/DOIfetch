"""CLI discoverability (ticket 0027): --version, help text, no-input, --url."""

import importlib.metadata

import pytest

from doifetch import cli
from doifetch.sources.contract import Result


def _help(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["doifetch", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.parse_args()
    assert exc.value.code == 0
    return " ".join(capsys.readouterr().out.split())


def test_version_prints_installed_metadata(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["doifetch", "--version"])
    with pytest.raises(SystemExit) as exc:
        cli.parse_args()
    assert exc.value.code == 0
    assert importlib.metadata.version("doifetch") in capsys.readouterr().out


def test_help_teaches_batch_env_exit_codes_and_defaults(monkeypatch, capsys):
    out = _help(monkeypatch, capsys)
    for needle in (
        "Examples",
        "TAB",
        "doi:",
        "isbn:",
        "url:",
        "EZPROXY_BASE",
        "EZPROXY_COOKIES",
        "ISTEX_ACCESSTOKEN",
        "istex.env",
        "OPENALEX_API_KEY",
        "OPENALEX_KEY_FILE",
        "Exit codes",
        "--url",
        "default: references",
        "default: papers",
    ):
        assert needle in out, needle


def test_help_has_no_stale_wording(monkeypatch, capsys):
    out = _help(monkeypatch, capsys)
    assert "via Libgen" not in out
    assert "paper PDFs" not in out


def test_no_input_names_directory_and_format(monkeypatch, tmp_path, capsys):
    data = tmp_path / "nowhere"
    monkeypatch.setattr(
        "sys.argv",
        [
            "doifetch",
            "--data-dir",
            str(data),
            "--output-dir",
            str(tmp_path / "out"),
            "--no-check-zotero",
        ],
    )
    monkeypatch.setattr(cli, "LOGS_DIR", str(tmp_path / "logs"))
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert str(data) in out
    assert ".txt" in out
    assert "TAB" in out


def test_url_flag_downloads_through_url_source(monkeypatch, tmp_path, capsys):
    seen = []

    def fake(req):
        seen.append(req)
        return Result("success", "url", path=req.path)

    monkeypatch.setitem(cli.SOURCES, "url", fake)
    monkeypatch.setattr(
        "sys.argv",
        [
            "doifetch",
            "--url",
            "https://example.com/doc.pdf",
            "--title",
            "Doc",
            "--output-dir",
            str(tmp_path),
            "--no-check-zotero",
        ],
    )
    monkeypatch.setattr(cli, "LOGS_DIR", str(tmp_path / "logs"))
    assert cli.main() == 0
    assert [(r.kind, r.identifier) for r in seen] == [
        ("url", "https://example.com/doc.pdf")
    ]


def test_url_flag_rejects_non_http(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["doifetch", "--url", "ftp://x/y.pdf", "--output-dir", str(tmp_path)],
    )
    monkeypatch.setattr(cli, "LOGS_DIR", str(tmp_path / "logs"))
    assert cli.main() == 1
    assert "Invalid URL" in capsys.readouterr().out
