# Plan: Remove unused table processor scripts

## Context
The 4 table processor scripts (`create_doi.py`, `sort.py`, `convert_md.py`, `convertxls.py`) are vestigial — their functions are either redundant with the downloaders or trivial enough to do manually. Remove them.

## Changes

### Delete files
- `create_doi.py`
- `sort.py`
- `convert_md.py`
- `convertxls.py`

### config.py
- Remove `MARKDOWN_DIR` (only consumer was convert_md.py)
- Keep `DOI_URL_BASE`, `COL_DOI_LINK` (used by download.py)

### README.md + readmeCH.md
- Remove file descriptions for the 4 deleted scripts
- Remove directory tree entries (`data_md/`, the 4 scripts)
- Remove usage steps 7 and 9 (create_doi, convert_md)
- Remove `sort.py` and `convertxls.py` mentions

### .github/copilot-instructions.md
- Remove the line listing table-processing utilities

### .gitignore
- Remove `data_md/` if present (no longer generated)

## Verification
- `uv run --group dev pytest` — all tests pass
- `grep -rn 'create_doi\|sort\.py\|convert_md\|convertxls\|MARKDOWN_DIR\|data_md' *.py .github/ README.md readmeCH.md` — no stale references
