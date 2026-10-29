# Project Guidelines

## Architecture
- This repository is a Python package (`src/doifetch`) with a `doifetch` console command.
- `doifetch/cli.py` is the batch orchestrator: it manages table I/O, parallelism, and source selection.
- `doifetch --help` is the user-facing reference (examples, batch line format, environment variables, exit codes); keep it, the README Usage section and the `cli.py` docstring consistent.
- `doifetch/sources/*.py` (scihub, crossref, unpaywall, ...) are source-specific fetchers, each exposing `NAME`, `ACCEPTS` and `fetch(req: Request) -> Result` (the contract in `sources/contract.py`).
- `doifetch/config.py` holds shared constants (directories, column names, Sci-Hub domains, download parameters).
- `doifetch/utils.py` provides shared I/O dispatch for reading/writing `.txt` reference lists, plus DOI validation.

## Build And Run
- Use `uv run` from the repo root instead of `pip` or manual virtualenv setup.
- Keep dependencies in `pyproject.toml` and run the CLI with `uv run doifetch`.
- Run tests with `uv run --group dev pytest` from the repo root.
- For network-dependent changes, keep validation focused: use `pytest` for non-network behavior and targeted script runs for real download flows.

## Conventions
- Preserve the current style: top-level functions, minimal abstractions, and shared constants in `config.py`.
- All fetchers follow the same interface convention: `fetch(req: Request) -> Result` returning a `Result` with `status` (`success`, `failed` or `skipped`), `source`, and `path` or `error`; a fetcher never raises.
- Keep dependency changes in `pyproject.toml`, and add test-only tooling to the `dev` dependency group.
- Preserve the internal column names `DOI`, `Article Title`, and `Download Status`.
- All code, comments, and documentation must be in English.

## Operational Constraints
- Assume network access can fail. Download code should keep timeout handling and non-destructive failure paths.
- Be careful with file mutations: `doifetch` overwrites input files and writes PDFs/logs into `papers/` and `logs/`.
- `sources/scihub.py` depends on fragile HTML parsing against Sci-Hub pages. Keep scraper changes minimal and isolate parsing logic when modifying it.
- Avoid broad refactors unless requested. Small targeted edits are safer in this repo than architectural rewrites.
