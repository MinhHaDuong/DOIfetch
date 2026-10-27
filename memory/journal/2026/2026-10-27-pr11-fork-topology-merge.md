# PR #11 merge on a fork-trunk repository

Date: 2026-10-27 · Project: DOIfetch · PR: MinhHaDuong/DOIfetch#11 (merged 3e07479, head bc557ef)

Context: DOIfetch's `origin` is the read-only upstream hanhan6688/DoiHarvest; the
trunk is the `fork` remote (MinhHaDuong/DOIfetch). `gh` has no default repo set,
so every forge call needed `-R MinhHaDuong/DOIfetch` (or `GH_REPO`).

Events:
- `gh pr view 11` without `-R` answered "Could not resolve to a PullRequest".
- Gaze round 1 (head 8e82003, self + sonnet seat) returned FINDINGS: a missing
  firefox raised FileNotFoundError out of `fetch_istex._refresh_login` on the
  no-token path (fetch_istex.py:65-67 at 8e82003). Reproduced with PATH=/nonexistent.
- Fix bc557ef caught OSError/EOFError in `_refresh_login`; new test
  `test_missing_browser_degrades_to_one_line` failed on 8e82003 with
  FileNotFoundError and passed on bc557ef.
- verify-gate refused round 1 (comment 6444746373): latest gaze covered 8e82003,
  delta to bc557ef was tier full.
- Gaze round 2 (delta only) posted REVIEWED with `seats: panel`, though no
  separate seat ran; the caller disclosed this to verify-gate, which APPROVED
  bc557ef (comment 6444869129) and named the single-family review as main risk.
- Both gaze runs bypassed gaze_setup.py/gaze_close.py because they fetch `origin`
  and remove the review worktree.
- `sync-local-main.sh` hardcodes `origin`; it was not run, local main left
  behind fork/main (ancestor, fast-forwardable).
- `attribution_record.py --seats-pr 11` exited 1: "the review result lists no seat".

Outcome: merged with --merge --match-head-commit; gaze minors 2-5 (browser opens
with no token, 403 treated as login, stale token resent, nits) left unaddressed.
fetch_ezproxy.py and tests/test_fetch_ezproxy.py fail `ruff format --check` on main
(predates PR #11).
