# A batch on a missing data directory exits 1, after v0.4.0 (2026-11-13)

Context: the first-use audit before v0.4.0 reported that `doifetch --data-dir <missing>` printed
"No records to process" and exited 0. It was left out of the release. After the tag the author
asked for the fix in the same session.

Events:
- PR #67 (head 020b3bb): the batch path checks the data directory before creating the output and
  logs directories, prints `Error: data directory not found: <dir>` and returns 1. The default
  `references` is covered: a bare `doifetch` where it does not exist exits 1 and creates nothing.
  An existing directory without entries still exits 0. Help text and README state the new code.
- `test_no_input_names_directory_and_format` had pinned exit 0 on a nonexistent directory; its
  directory now exists and is empty.
- gaze REVIEWED and verify-gate APPROVED at round 1 on 020b3bb. gaze noted that `--data-dir`
  naming a regular file reads "data directory not found".
- The harness session bumping the DOIfetch pin was asked by session message. It answered that
  the harness calls the wrapper with `--doi`, `--isbn` and `--version` only, and that it lands
  its pin on v0.4.0.

Decisions already made:
- The author ruled "let ride": no v0.4.1. The change of a documented exit code ships with the
  next release, whose notes should state it.
