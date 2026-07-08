# DOIfetch

A tool for batch downloading academic paper PDFs from Sci-Hub, Crossref, and Unpaywall.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
## Project Introduction

DOIfetch is an automated tool designed to help researchers and scholars batch download academic paper PDF files. It supports obtaining papers from Sci-Hub, Crossref, and Unpaywall API, featuring multi-threaded downloading, retry mechanisms, and intelligent domain rotation to improve download efficiency and success rate.

## Features

- Supports reading literature DOI and title information from Excel, CSV, or text reference files
- Automatically downloads paper PDFs from multiple sources (Crossref, Unpaywall, HAL, ISTEX, Sci-Hub)
- Supports multi-threaded downloading to improve efficiency
- Supports retry mechanisms and random delays to avoid being blocked
- Automatically updates download status in the original input files
- Unified fetcher interface: each source exposes the same `fetch_pdf()` convention

## File Descriptions

- `fetch.py`: Orchestrator — batch-fetches papers with table I/O, parallelism, retries, and source selection
- `fetch_scihub.py`: Sci-Hub fetcher (may require proxy)
- `fetch_crossref.py`: Crossref open-access fetcher (no proxy required)
- `fetch_unpaywall.py`: Unpaywall open-access fetcher (no proxy required)
- `fetch_hal.py`: HAL open-archive fetcher — searches by author surname and title
- `fetch_istex.py`: ISTEX fetcher — licensed national archive, resolves a DOI to fulltext (requires an access token)
- `config.py`: Configuration file containing Sci-Hub domain pool, download parameters, and shared constants
- `utils.py`: Shared table I/O dispatch (read/write/list for Excel, CSV, TXT) and DOI validation
- `pyproject.toml`: Project metadata and dependencies for `uv`

## Configuration Instructions

The following parameters can be adjusted in `config.py`:

- `SCI_HUB_DOMAINS`: Sci-Hub domain pool for rotation to avoid blocking
- `MAX_THREADS`: Number of concurrent download threads
- `RETRY_COUNT`: Number of retries for download failures
- `TIMEOUT`: Request timeout duration
- `MIN_DELAY` and `MAX_DELAY`: Random delay range

### ISTEX access token

The ISTEX source downloads fulltext from a licensed national archive, so it
needs a personal access token. Generate one at <https://api.istex.fr/token/>
(you are redirected to your institution's identity federation, e.g. Janus for
CNRS) and copy the `_accessToken` value from the JSON response. Expose it in the
environment before running:

```
export ISTEX_ACCESSTOKEN=<your token>
```

Keep the token in a file outside the repository and `export` it (a plain
`source` of a file without `export` sets a shell variable the child process
cannot see). The token is strictly personal — never commit or share it.

## Directory Structure

```
.
├── references/           # Store input reference files to be processed
├── logs/                 # Store fetch.py logs
├── papers/               # Store all downloaded PDF files
├── fetch.py              # Orchestrator: batch fetch with source selection
├── fetch_scihub.py       # Sci-Hub fetcher
├── fetch_crossref.py     # Crossref fetcher
├── fetch_unpaywall.py    # Unpaywall fetcher
├── fetch_hal.py          # HAL open-archive fetcher
├── fetch_istex.py        # ISTEX licensed-archive fetcher
├── config.py             # Configuration file and shared constants
├── utils.py              # Shared table I/O dispatch and DOI validation
├── pyproject.toml        # Project metadata and dependency file for uv
└── README.md
```
## Run With UV

This repository uses `uv` and `pyproject.toml` as the dependency source of truth. Do not use `pip` or create a virtual environment manually. Run commands from the repository root with `uv run`, and `uv` will resolve the required dependencies automatically.

```
uv run python fetch.py --help
```

## Usage

1. Place the Excel file containing literature information in the `references` directory
   - The input file should contain at least `DOI` column
2. Run `fetch.py` to start downloading literature from all sources (tries Crossref, Unpaywall, HAL, ISTEX, then Sci-Hub):
   ```
   uv run python fetch.py
   ```
   To use a specific source only:
   ```
   uv run python fetch.py --source crossref
   uv run python fetch.py --source istex
   uv run python fetch.py --source scihub
   ```
   To download a single paper directly from the CLI:
   ```
   uv run python fetch.py --doi 10.1000/example --title "Example Paper"
   ```
   Individual fetchers also work standalone:
   ```
   uv run python fetch_scihub.py --doi 10.1000/example --title "Example Paper"
   uv run python fetch_crossref.py --doi 10.1000/example
   uv run python fetch_unpaywall.py --doi 10.1000/example
   uv run python fetch_istex.py --doi 10.1000/example
   ```
3. Downloaded PDF files will be saved in the `papers` directory
4. If your input files are CSV instead of Excel, run with `--input-format csv`
   ```
   uv run python fetch.py --input-format csv
   ```
   You can also use text reference files (`--input-format txt`) with tab-separated lines:
   ```
   doi:10.1080/03085140903020580	Author 2009 - Title
   url:https://example.com/doc.pdf	Document Name
   isbn:9780674009691	Author 1998 - Book Title
   # Comment lines are ignored
   ```
   Only `doi:` entries are processed; `url:`, `isbn:`, and `#` lines are skipped. Text files are read-only (no status write-back).
5. Download status will be automatically updated in the original input file

## Testing

Run the test suite from the repository root:

```
uv run --group dev pytest
```


## Notes

- Use `uv run` from the repository root so dependencies come from `pyproject.toml`
- Please comply with relevant laws and regulations and academic ethics, for personal learning and research only
- Network issues or Sci-Hub access restrictions may be encountered during downloading
- It is recommended to appropriately adjust the number of concurrent threads and delay time to avoid being blocked


## Acknowledgements

This project is a fork of [DoiHarvest](https://github.com/hanhan6688/DoiHarvest) by HMC, licensed under the [MIT License](LICENSE).

Major changes from the original:

- Restructured CLI into `fetch_*.py` source-specific fetchers with a unified interface and `fetch.py` orchestrator
- Centralized shared constants into `config.py`
- Added CSV and TXT input support with automatic format detection
- Added a test suite using pytest
- Migrated to `uv` and `pyproject.toml` for dependency management
- Refactored for maintainability (shared `utils.py`, English-only docs)
