# DOIfetch

A tool for batch downloading academic paper PDFs and books from multiple open-access sources.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
## Project Introduction

DOIfetch is an automated tool designed to help researchers and scholars batch download academic paper and book PDF files. It supports obtaining papers from Crossref, Unpaywall, HAL, and Sci-Hub by DOI; books from Library Genesis by ISBN; and arbitrary documents by URL. It features multi-threaded downloading, retry mechanisms, and intelligent domain rotation.

## Features

- Supports reading literature DOI, ISBN, and URL information from `.txt` reference lists
- Automatically downloads paper PDFs from multiple sources (Crossref, Unpaywall, HAL, ISTEX, Sci-Hub) by DOI
- Downloads books from Library Genesis by ISBN
- Downloads documents directly from URLs
- Supports multi-threaded downloading to improve efficiency
- Supports retry mechanisms and random delays to avoid being blocked
- Automatically updates download status in the original input files
- Skips papers already in your local Zotero library (auto-enabled when a Zotero database is found)
- Unified fetcher interface: each source exposes the same `fetch_pdf()` convention

## File Descriptions

- `fetch.py`: Orchestrator — batch-fetches papers with table I/O, parallelism, retries, and source selection
- `fetch_crossref.py`: Crossref open-access fetcher (no proxy required)
- `fetch_unpaywall.py`: Unpaywall open-access fetcher (no proxy required)
- `fetch_hal.py`: HAL open-archive fetcher — searches by author surname and title
- `fetch_istex.py`: ISTEX fetcher — licensed national archive, resolves a DOI to fulltext (requires an access token)
- `fetch_ezproxy.py`: EZproxy fetcher — institutional-subscription access (e.g. BibCNRS). Rewrites the publisher host into your institution's EZproxy form and downloads with your session cookies. The scriptable equivalent of a "Click & Read" button. Requires `EZPROXY_BASE` + `EZPROXY_COOKIES` (a cookies.txt exported after logging into the proxy); federated SSO cannot be scripted blind, so a live session is needed.
- `fetch_libgen.py`: Library Genesis fetcher — downloads books by ISBN
- `fetch_scihub.py`: Sci-Hub / SciDB fetcher — tries the frozen Sci-Hub corpus, then SciDB via Anna's Archive (may require proxy or VPN)
- `fetch_url.py`: Direct URL fetcher
- `config.py`: Configuration file containing domain pools, download parameters, and shared constants
- `utils.py`: Shared `.txt` list I/O (read/write/list) and DOI validation
- `zotero.py`: Local Zotero-library lookup — locates the database and reports whether a paper is already held
- `pyproject.toml`: Project metadata and dependencies for `uv`

## Configuration Instructions

The following parameters can be adjusted in `config.py`:

- `SCI_HUB_DOMAINS`: Sci-Hub domain pool for rotation to avoid blocking
- `SCIDB_DOMAINS`: Anna's Archive SciDB mirrors (tried after Sci-Hub)
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

### Zotero library dedup

Before downloading, DOIfetch checks your local Zotero library and skips any
paper already held, so you never refetch what you own. The check runs
automatically whenever a Zotero database is found; matching is by DOI first
(case-insensitive), falling back to a near-exact title match when the DOI is
absent.

The database is located in this order: `$ZOTERO_DB_PATH`, then
`$ZOTERO_DATA_DIR/zotero.sqlite`, then the standard Zotero data directories,
then any `dataDir` declared in a `profiles.ini`. Point `ZOTERO_DB_PATH` at your
`zotero.sqlite` if it lives elsewhere:

```
export ZOTERO_DB_PATH=/path/to/zotero.sqlite
```

Reads are read-only (`immutable=1`), so the check is safe while Zotero is
running. When no database is found the check is silently skipped. Pass
`--no-check-zotero` to turn it off.

## Directory Structure

```
.
├── references/           # Store input reference files to be processed
├── logs/                 # Store fetch.py logs
├── papers/               # Store all downloaded PDF files
├── fetch.py              # Orchestrator: batch fetch with source selection
├── fetch_crossref.py     # Crossref fetcher
├── fetch_unpaywall.py    # Unpaywall fetcher
├── fetch_hal.py          # HAL open-archive fetcher
├── fetch_istex.py        # ISTEX licensed-archive fetcher
├── fetch_libgen.py       # Library Genesis fetcher
├── fetch_scihub.py       # Sci-Hub / SciDB fetcher
├── fetch_url.py          # Direct URL fetcher
├── config.py             # Configuration file and shared constants
├── utils.py              # Shared table I/O dispatch and DOI validation
├── pyproject.toml        # Project metadata and dependency file for uv
└── README.md
```
## Install

One command, with [uv](https://docs.astral.sh/uv/):

```
uv tool install git+https://github.com/MinhHaDuong/DOIfetch
doifetch --help
```

The core depends on `requests` only and reads `.txt` reference lists. The
`shadow` extra adds the opt-in Sci-Hub and Libgen sources (beautifulsoup4):

```
uv tool install 'doifetch[shadow] @ git+https://github.com/MinhHaDuong/DOIfetch'
```

Without the extra, the missing feature fails with a message naming it.
`uv run` in this repository installs the extra.

### Default sources

With no `--source`, `doifetch` tries the open and institutional sources in
order until one succeeds: Crossref, Unpaywall, HAL, ISTEX, EZproxy (EZproxy
needs `EZPROXY_BASE` and `EZPROXY_COOKIES`; otherwise it is skipped).

### Other sources

Sci-Hub and Libgen are never tried by default. They need the `shadow` extra;
name them to use them:

```
doifetch --source scihub --doi 10.1000/example
doifetch --source libgen --isbn 9780000000000
```

### ISTEX login

If ISTEX answers that authentication is needed (token missing or expired):

- In an interactive session (terminal and graphical display), `doifetch` opens
  Firefox on <https://api.istex.fr/token/>. Log in, save the new token
  (`ISTEX_ACCESSTOKEN`, or `~/.config/keys/istex.env`), press Enter, and the
  download is retried once.
- Otherwise it prints one line, `ISTEX login needed: <url>`, and carries on
  with the other sources.

## Run With UV

This repository uses `uv` and `pyproject.toml` as the dependency source of truth. Do not use `pip` or create a virtual environment manually. Run commands from the repository root with `uv run`, and `uv` will resolve the required dependencies automatically.

```
uv run python fetch.py --help
```

## Usage

1. Place the reference file in the `references` directory.
2. Run `fetch.py` to start downloading (tries Crossref → Unpaywall → HAL → ISTEX → EZproxy in order):
   ```
   uv run fetch.py
   ```
   To use a specific source only:
   ```
   uv run fetch.py --source crossref
   uv run fetch.py --source unpaywall
   uv run fetch.py --source hal
   uv run fetch.py --source istex
   uv run fetch.py --source libgen
   uv run fetch.py --source scihub
   ```
   To download a single paper directly from the CLI:
   ```
   uv run fetch.py --doi 10.1000/example --title "Example Paper"
   ```
   Files are named `<FirstAuthor> <Year> - <Title>` from the DOI's Crossref
   metadata. Without `--title` that name is used as is. A supplied title that
   matches Crossref's is kept unchanged; a clear mismatch logs a warning and the
   file is named from Crossref. Pass `--keep-title` to force your own name. If
   Crossref is unreachable, your title is used.
   To download a single book by ISBN (routed to Libgen):
   ```
   uv run fetch.py --isbn 9780674009691 --title "Author 1998 - Book Title"
   ```
   Individual fetchers also work standalone:
   ```
   uv run fetch_crossref.py --doi 10.1000/example
   uv run fetch_unpaywall.py --doi 10.1000/example
   uv run fetch_hal.py --title "Author et al. 2015 - The Title"
   uv run fetch_istex.py --doi 10.1000/example
   uv run fetch_libgen.py --isbn 9780674009691 --title "Author 1998 - Book Title"
   uv run fetch_scihub.py --doi 10.1000/example --title "Example Paper"
   ```
3. Downloaded files will be saved in the `papers` directory as `.pdf` or `.epub` depending on what Libgen provides.
4. Batch input is a `.txt` list in the data directory, one entry per line: an identifier, a TAB, then the title. Blank lines and lines starting with `#` are ignored:
   ```
   doi:10.1080/03085140903020580	Author 2009 - Title
   url:https://example.com/doc.pdf	Document Name
   isbn:9780674009691	Author 1998 - Book Title
   # Comment lines are ignored
   ```
   All three entry types are processed: `doi:` goes through the source cascade,
   `url:` is fetched directly, and `isbn:` is fetched from Library Genesis.
5. After a run the input file is rewritten to the works still missing, so it is the retry list. Comment lines are not kept.

## Sci-Hub and SciDB access

Sci-Hub paused new uploads, so its corpus is frozen at papers registered up to
roughly 2021. SciDB, the Sci-Hub database frontend hosted by Anna's Archive,
serves that full collection plus papers added since, reached at
`{domain}scidb/{doi}`. The `scihub` source therefore tries the classic Sci-Hub
domains first — their pages expose the PDF in a freely scrapable iframe — and
falls back to SciDB for papers outside the frozen corpus.

Anna's Archive is anti-bot and membership-gated, so automated SciDB retrieval is
best-effort: some papers resolve only through slow downloads or a browser. When
SciDB does not serve the PDF directly, the fetch fails gracefully and the paper
stays in the failed-DOI list for manual retrieval. Sci-Hub/SciDB remains the
last source in the cascade, after Crossref, Unpaywall, HAL, and ISTEX.

## Library Genesis access

Library Genesis is a shadow library. According to [Wikipedia](https://en.wikipedia.org/wiki/Library_Genesis),
access may be blocked at the ISP level in several countries (UK, France, Germany, Italy, Belgium, and others).
If connections time out, use a VPN or try a different network. The fetcher tries these mirrors in order:
`libgen.rs`, `libgen.is`, `libgen.gs`. Downloads are resolved via `libgen.li`.

## Testing

Run the test suite from the repository root:

```
uv run --group dev pytest
```


## Notes

- Use `uv run` from the repository root so dependencies come from `pyproject.toml`
- Please comply with relevant laws and regulations and academic ethics, for personal learning and research only
- Network issues or access restrictions may be encountered for Sci-Hub and Library Genesis
- Adjust the number of concurrent threads and delay time as needed to avoid being blocked


## Acknowledgements

This project is a fork of [DoiHarvest](https://github.com/hanhan6688/DoiHarvest) by HMC, licensed under the [MIT License](LICENSE).

Major changes from the original:

- Restructured CLI into `fetch_*.py` source-specific fetchers with a unified interface and `fetch.py` orchestrator
- Centralized shared constants into `config.py`
- Added CSV and TXT input support with automatic format detection
- Added HAL open archive fetcher (search by author + title)
- Added ISTEX licensed-archive fetcher (resolve DOI to fulltext)
- Added Library Genesis fetcher (search by ISBN)
- Added direct URL fetcher
- Added a test suite using pytest
- Migrated to `uv` and `pyproject.toml` for dependency management
- Refactored for maintainability (shared `utils.py`, English-only docs)
