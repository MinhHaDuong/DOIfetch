# Ticket 0033: a Zotero item without a PDF is not a held work (2026-11-12)

Context: ticket 0033 was filed from a climate-finance-het session on 2026-11-12 as a ticket-only
request (PR #58). DOIfetch v0.3.0 in batch mode counted work 10.1016/j.worlddev.2018.12.011,
whose Zotero item had no attachment, as a success, wrote no file and dropped it from the retry
list. The ticket was landed and implemented in one interface session the same afternoon
(PR #59, merged at 800fc6a, merge commit d7e0f2e).

Events:
- PR #58 read as bookkeeping tier (two paths under `tickets/`) and landed on the gate record
  alone, merged at bdb263b.
- First fix (6fe32a1): `zotero_lookup` returns `has_pdf`, computed by a correlated `EXISTS` over
  `itemAttachments` inside the DOI and title queries; the batch tracks skips in their own list
  and prints `Success / Skipped / Failed`. 11 new tests failed on origin/main and passed.
- On the author's library (read-only, `immutable=1`): 3669 live items carry a DOI, 2750 hold a
  PDF file, 919 do not. The ticket's own DOI answered `has_pdf: True` at fix time; the item had
  gained a PDF since the report, so the reported case was not replayed on real data.
- gaze round 1 on 6fe32a1 returned FINDINGS. Its schema script timed out at 120 s; the cause was
  the fix itself. SQLite planned the `EXISTS` through `itemAttachments_contentType`, so each of
  31366 title rows walked about 9600 PDF attachments. A DOI miss followed by the title fallback
  took 0.45 s on origin/main and did not finish in 150 s on 6fe32a1. The test fixture held six
  items and all tests passed.
- Second fix (e02334e): the PDF question is asked per matched item, as two indexed lookups.
  Measured on the same library: 0.50 s in this session, 0.35 s by gaze. A test with 3000 items
  and the two indexes fails on 6fe32a1 at 1.87 s against a 1.0 s limit. The same commit added a
  title fallback after a file-less DOI match, an existence check for linked files with an
  absolute path, and best-score-decides ranking among title matches.
- A timing loop written in this session called `_match_by_doi` once per distinct DOI of the
  library (about 0.18 s each) and ran past the 300 s command bound; it was stopped and replaced
  by three single lookups under `timeout 100`.
- gaze round 2 on e02334e returned REVIEWED with a `consider`: the new title fallback let another
  work with a near-identical title and its own DOI mark a file-less item as held (2 of 200
  sampled file-less DOI items answered held). Third fix (aff2aec): the fallback looks only at
  items with no DOI field.
- gaze round 3 on aff2aec returned REVIEWED. The same 2 of 200 still answer held; the reason
  field was not printed and the cause is not established.
- verify-gate APPROVED round 1 on 800fc6a, whose only delta from the reviewed head is the
  ticket close.

Outcome: merged; ticket 0033 closed. Not addressed: an item of a type without a DOI field (book,
report, thesis) with a near-identical title and a PDF still answers held for another work, as on
main before the fix; a stored attachment whose file is not on disk (on-demand sync) counts as
held; the 2 of 200 held answers above are unexplained.
