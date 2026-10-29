# Raid f9e483: release v0.2.0 and the interface-session merges

Date: 2026-10-29. Project: DOIfetch. Raid: f9e483 ("all open"), run from the interface session with
two successive Opus team leads for waves 2–10.

## Context

The raid started with 8 open tickets (0006–0013). 0008 was split into eight children (0015–0022).
The release audits for v0.2.0 (security, UX dry-run, docs coherence) produced 0024 and 0025. The
author added 0023 (title kind, option a), 0026 (CORE), 0027 (CLI discoverability). 0012 was
reshaped by author ruling after the DOAB/OAPEN REST APIs answered 403 on padme.

## Events

- PR #33 (0024, HTTP helper hardening, carries the ISTEX bearer token and EZproxy cookies):
  - A gaze cross-family seat (gpt-6-luna) was recorded as `ran` after about 10 s with no reasoning.
  - A direct `codex exec -m gpt-6.1-sol` read of the same diff found four issues: Proxy-Authorization
    kept on redirect, redirect bodies read uncapped, multi-member gzip truncated, default-port origin
    mismatch. All four were fixed with red-first tests.
  - The next gaze found a regression from the cap fix (Content-Length no longer enforced); fixed.
  - A later gaze record listed a seat labelled OpenAI that ran as a Claude subagent; verify-gate
    `--require-cross-family` refused it. A gaze run from the interface session with
    `gaze_seat.py --runtime codex` recorded a codex seat, and the gate approved round 1.
- `raid_land.py` refused #30, #33 (twice) and #39 for a missing review-head ref; each reviewed commit
  still existed and `review_notes.py keep-head` re-pinned it.
- Release: version bump PR #41, README wording PR #42 (runtime is standard library only).
  `git tag -s` failed twice: no tty for pinentry from the `!` shell, then a wrong YubiKey OpenPGP
  user PIN (one try spent, two left). The author ruled to tag unsigned; v0.2.0 is an annotated tag
  (c66a2e5) on fc85d31, pushed by Claude. Harness ticket 1344's criterion was changed to the unsigned
  tag after the author confirmed it in the harness session.
- Harness defects reported to the harness session during the run: gaze close refusing egg-info
  (fixed as 1345), and later 1355–1358 plus the seat and review-head items above.

## Outcome

Every PR of this raid, #14 to #43, is merged; #14, #18, #20, #29, #31, #35, #38 and #40 were
tickets or memory only. Main is at c870f74 after CORE (#43), gate green. `erg ready` is empty at
close.

## References

PRs #30, #33, #34, #39, #41, #42, #43; tag v0.2.0; harness tickets 1344, 1345, 1355–1358;
attribution records under memory/evidence/attribution/.
