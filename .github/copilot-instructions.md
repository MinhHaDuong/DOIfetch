# Project Guidelines

## Architecture
- This repository is a small collection of standalone Python scripts, not a package.
- `fetch.py` is the batch orchestrator: it manages table I/O, parallelism, retries, and source selection.
- `fetch_scihub.py`, `fetch_crossref.py`, and `fetch_unpaywall.py` are source-specific fetchers, each exposing a `fetch_pdf(doi, title, output_dir)` function with the same return convention.
- `config.py` holds shared constants (directories, column names, Sci-Hub domains, download parameters).
- `utils.py` provides shared I/O dispatch for reading/writing Excel, CSV, and TXT files, plus DOI validation.

## Build And Run
- Use `uv run` from the repo root instead of `pip` or manual virtualenv setup.
- Keep dependencies in `pyproject.toml` and run scripts with commands like `uv run python fetch.py` or `uv run python fetch_scihub.py`.
- Run tests with `uv run --group dev pytest` from the repo root.
- For network-dependent changes, keep validation focused: use `pytest` for non-network behavior and targeted script runs for real download flows.

## Conventions
- Preserve the current script-oriented style: top-level functions, minimal abstractions, and shared constants in `config.py`.
- All fetchers follow the same interface convention: `fetch_pdf(doi, title, output_dir) -> dict` returning `status`, `doi`, `title`, `file_name`, and optionally `error`.
- Keep dependency changes in `pyproject.toml`, and add test-only tooling to the `dev` dependency group.
- Use `pandas` for Excel reads and writes, and preserve existing column names such as `DOI`, `Article Title`, `DOI Link`, and `Download Status`.
- All code, comments, and documentation must be in English.

## Operational Constraints
- Assume network access can fail. Download code should keep retries, timeout handling, and non-destructive failure paths.
- Be careful with file mutations: `fetch.py` overwrites input files and writes PDFs/logs into `papers/` and `logs/`.
- `fetch_scihub.py` depends on fragile HTML parsing against Sci-Hub pages. Keep scraper changes minimal and isolate parsing logic when modifying it.
- Avoid broad refactors unless requested. Small targeted edits are safer in this repo than architectural rewrites.
