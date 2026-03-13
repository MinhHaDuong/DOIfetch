# Project Guidelines

## Architecture
- This repository is a small collection of standalone Python scripts, not a package.
- `download.py` is the Sci-Hub workflow and shares runtime settings from `config.py` via `from config import *`.
- `Crossref_download.py` and `Unpaywall_download.py` are separate open-access download paths and write PDFs into `papers/`.
- `table_utils.py` provides shared I/O dispatch for reading/writing Excel, CSV, and TXT files.

## Build And Run
- Use `uv run` from the repo root instead of `pip` or manual virtualenv setup.
- Keep dependencies in `pyproject.toml` and run scripts with commands like `uv run python download.py` or `uv run python Crossref_download.py`.
- Run tests with `uv run --group dev pytest` from the repo root.
- For network-dependent changes, keep validation focused: use `pytest` for non-network behavior and targeted script runs for real download flows.

## Conventions
- Preserve the current script-oriented style: top-level functions, minimal abstractions, and shared constants in `config.py`.
- Keep dependency changes in `pyproject.toml`, and add test-only tooling to the `dev` dependency group.
- Use `pandas` for Excel reads and writes, and preserve existing column names such as `DOI`, `Article Title`, `DOI Link`, and `Download Status`.
- All code, comments, and documentation must be in English.

## Operational Constraints
- Assume network access can fail. Download code should keep retries, timeout handling, and non-destructive failure paths.
- Be careful with file mutations: several scripts overwrite input files or write PDFs/logs directly into `papers/` and `logs/`.
- `download.py` depends on fragile HTML parsing against Sci-Hub pages. Keep scraper changes minimal and isolate parsing logic when modifying it.
- Avoid broad refactors unless requested. Small targeted edits are safer in this repo than architectural rewrites.
