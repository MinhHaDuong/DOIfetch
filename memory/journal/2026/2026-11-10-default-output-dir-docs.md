# Ticket 0029: default output directory docs instead of papers (2026-11-10)

Context: ticket 0029 was filed from a harness session on 2026-11-10 as a ticket-only request
(PR #50), on an author decision of the same day. It was accepted and implemented in one
interface session the same morning (PR #51, merged at 844d8bb, merge commit abb9b89).

Events:
- PR #50 read as bookkeeping tier (two paths under `tickets/`) and landed on the gate record
  alone, merged at 5f92745.
- The change: `PAPERS_DIR = "papers"` became `OUTPUT_DIR = "docs"` in `src/doifetch/config.py`;
  the `--output-dir` help and README step 3 say the old default was `papers` up to v0.2.0;
  `.gitignore` gained `docs/*.pdf` because this repository tracks `docs/pr-archive/`. No fallback
  to an existing `papers/` directory, no version bump.
- `src/doifetch/cli.py` (541 lines) and `src/doifetch/config.py` (70 lines) carry CRLF line
  endings on main; `README.md`, `.gitignore` and the tests are LF. A Python script that edited
  `cli.py` with `Path.read_text` / `write_text` rewrote every line ending to LF: `git diff --stat`
  showed 1083 changed lines for a 7-line edit. `ruff format --check` passed on both forms. The
  endings were restored with `sed -i 's/$/\r/'` before the commit; the committed diff is 10
  insertions and 8 deletions outside the new test file.
- The new test `tests/test_output_dir.py::test_fetch_without_output_dir_writes_under_docs` failed
  before the change with `papers/Doc.pdf` where `docs/Doc.pdf` was expected, and gaze saw the
  same failure when it ran the file against origin/main.
- gaze REVIEWED on 7638fc2 (one Haiku seat, the regression script and the lead's own read);
  verify-gate APPROVED round 1 on 844d8bb, whose only delta from the reviewed head is the ticket
  close.

Outcome: merged; ticket 0029 closed. Not addressed: the README directory tree labels `docs/` as
the download folder while this repository also tracks `docs/pr-archive/` there (gaze `consider`,
left as is); the mixed CRLF and LF line endings in `src/doifetch/`.
