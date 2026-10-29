# Raid f9e483: package, contract, sources, ISBN (2026-10-29)

Context: raid over tickets 0006-0013, 0015-0022 (PRs #15-#29, #32, #36, #37), with a parallel
session merging into the same files (#30 title kind, #34 http hardening / named-source refusal).

Events:
- PR #32 (ticket 0009) was rebased twice onto main for code-touching conflicts (#30 in cli.py and
  scihub.py; #34 in api.py, cli.py, test_cascade.py), each rebase needing a new gaze round. The
  second rebase restored a "retries" claim in `.github/copilot-instructions.md:5` that #34 had
  removed; caught by gaze round 3 (adopted), fixed in 76d23e6.
- Gaze runs launched inside coder subagents twice produced `seats: self-only` records (one from an
  invalid `--budget 15m`); gaze launched from the depth-1 team lead produced panel records.
  PR #32's first record was self-only and counted as no record.
- `raid_land` refused #32 once: the review-head ref of an intermediate gaze request was missing
  locally; restored with `review_notes.py keep-head`.
- The final gaze on #32 (76d23e6): the codex seat `fixread` refused NOT-RUN (read-only sandbox
  could not reach the review tree); the deterministic `fixcheck` script settled the one-word fix.
- `api.cascade` is now the single cascade (joins failure reasons, stops on success or skipped);
  ISBNs resolve through the `isbn` source (Crossref book DOI, chapters ignored; PR #37).

Capture gaps:
- PR #21 (ticket 0016): the gaze review was a script check (`seats: panel`, no model seat), so
  `attribution_record.py` refused it ("requires ... named reviewers"); no attribution record
  written. PR #32's record was completed by hand from the notes (the helper rejected the anchor
  `cli.py:_candidates`; resolved to `cli.py:266`).
- PRs #20 and #29 are bookkeeping-only with no review; no record.

Outcome: all merged; main at c95c689.
