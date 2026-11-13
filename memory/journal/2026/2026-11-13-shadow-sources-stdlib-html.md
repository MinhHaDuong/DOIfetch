# Ticket 0034: shadow sources parse HTML with the standard library (2026-11-13)

Context: ticket 0034 was filed the same day (PR #61) on the author's request, after a harness
acquisition run failed on "bs4 is not installed" when the wrapper took the plain `uvx` spec for
`--source scihub`. It was worked as a one-ticket raid (id 63c8b1): a blind-spot seat, one
executor through hunt, gaze, one verify-gate round, landing as PR #63 (head cc2b658, merge
commit fb3c0cf).

Events:
- The blind-spot seat reported that `pyproject.toml`'s dev group listed `doifetch[shadow]` and
  that `uv.lock` pinned beautifulsoup4, soupsieve and typing_extensions, so the "suite passes
  without bs4" criterion would have passed with bs4 installed. The points went on the ticket log
  as guidance; the exit criteria were not edited.
- PR #63 added `src/doifetch/sources/_html.py` (an `HTMLParser` collector), removed `require()`
  and `EXTRA_INSTALL` from `utils.py`, and removed bs4 from the dev group and the lock.
- Parity against `BeautifulSoup(html, "html.parser")`, measured before the removal: 34 hand
  cases and 30,000 random fragments by the executor, 20,000 by gaze, the 14 inputs of the
  existing tests as bytes and str on Python 3.10 and 3.14 by the gate. Frozen expected values
  are in `tests/test_html.py`.
- Three differences from bs4 are known and were accepted as non-blocking: an unknown entity
  keeps its `;`; bytes decode as UTF-8 with replacement (no BOM or meta-charset sniffing); CDATA
  text inside an anchor is dropped (`<a href="x">G<![CDATA[E]]>T</a>` gives `GT`, bs4 gave
  `GET`). The PR body lists the first two only.
- Not measured: parity on pages served by the live mirrors. A plain-install `--source scihub`
  run reached the mirrors and returned "PDF link not found".

Decisions already made:
- The `shadow` extra is kept, empty, for one release so that `doifetch[shadow]` pins (the
  harness wrapper, at v0.3.0) still resolve; `pyproject.toml` says to remove it at the next one.
- The harness side (bump the pin, drop the second `uvx` spec) starts when a release carries this
  change; no ticket exists for it yet.

Capture note: `attribution_record.py --capture-unit pr:63` answered `not derivable: reviewers`
and wrote no record; the gaze answer on notes names a plan (`parity (script)`, `criteria (self)`)
and no reviewer line. The record for PR 63 was completed by hand from that answer.
