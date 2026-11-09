# Ticket 0028: HAL deposits missed, HAL download blocked by Anubis (2026-11-09)

Context: ticket 0028 was filed from climate-finance-het on 2026-11-04 (PR #45) and fixed in a
team-lead sprint on 2026-11-09 (PR #47, merged at e167eab).

Events:
- PR #45 predated required ID claims (PR #46, merged the same morning). The per-clone claim hook
  checks the whole index, so a standalone claim commit on the pre-claims base failed for all 27
  tickets main had already claimed. The claim for 0028 went into the merge commit that synced main
  into the branch (80b234f). Merging rather than rebasing avoided a force-push.
- Reproduction with real requests: the `hal` source never queried by DOI. It searched
  `authLastName_t` plus `title_t` built from the output file name, which the CLI cuts at 120
  characters, so the Briera 2024 title query (10.1016/j.enpol.2024.114104) returned 0 hits, while
  `doiId_s:"<doi>"` returns hal-04824002. Unpaywall and OpenAlex list the HAL page with no PDF URL.
- HAL file hosts (hal.science and portal hosts such as univ-catholille.hal.science) run Anubis:
  any User-Agent containing `Mozilla` gets a 200 text/html "Making sure you're not a bot!" page;
  curl, the Python default and `DOIfetch/...` get the PDF. DOIfetch sent the config's Chrome UA.
- Fix: DOI lookup first, title search as fallback; the HAL file request sends
  `DOIfetch (+https://github.com/MinhHaDuong/DOIfetch)`. Other sources keep the browser UA.
- gaze REVIEWED (one Sonnet seat plus targeted tests); verify-gate APPROVED round 1 on 350f4d8.
- After merge, on main: offline suite 458 passed; `pytest -m network -k hal` 4 passed; direct
  `hal.fetch` saved Briera 11718641 bytes and Earsom 2024 (10.1111/1758-5899.13324) 312576 bytes,
  both starting `%PDF-`.

Outcome: merged; ticket 0028 closed. Not addressed: a transport error on the DOI lookup skips the
title fallback (unchanged from before); other sources that receive a hal.science PDF URL from
OpenAlex or Unpaywall would still send a Mozilla UA (not reproduced for these DOIs).
