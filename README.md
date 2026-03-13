# DoiHarvest

A tool for batch downloading academic paper PDFs from Sci-Hub, Crossref, and Unpaywall.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
## Project Introduction

DoiHarvest is an automated tool designed to help researchers and scholars batch download academic paper PDF files. It supports obtaining papers from Sci-Hub,Crossref,Unpaywall API, featuring multi-threaded downloading, retry mechanisms, and intelligent domain rotation to improve download efficiency and success rate. Additionally, the tool provides Excel to Markdown conversion functionality for convenient literature information management and sharing.

## Features

- Supports reading literature DOI and title information from Excel, CSV, or text reference files
- Automatically downloads paper PDFs from Sci-Hub
- Supports multi-threaded downloading to improve efficiency
- Supports retry mechanisms and random delays to avoid being blocked
- Automatically updates DOI links in Excel files
- Supports converting Excel files to Markdown format for manual downloading
- Provides download status checking functionality
- Supports downloading open access papers via Crossref API
- Supports downloading open access papers via Unpaywall API

## File Descriptions

- `download.py`: Main download script for downloading papers from Sci-Hub
- `config.py`: Configuration file containing Sci-Hub domain pool and download parameters
- `convertxls.py`: Converts .xls files to .xlsx format
- `create_doi.py`: Generates DOI links for table files
- `convert_md.py`: Converts table files to Markdown format
- `Crossref_download.py`: Downloads open access papers using Crossref API
- `Unpaywall_download.py`: Downloads open access papers using Unpaywall API
- `pyproject.toml`: Project metadata and dependencies for `uv`

## Configuration Instructions

The following parameters can be adjusted in `config.py`:

- `SCI_HUB_DOMAINS`: Sci-Hub domain pool for rotation to avoid blocking
- `MAX_THREADS`: Number of concurrent download threads
- `RETRY_COUNT`: Number of retries for download failures
- `TIMEOUT`: Request timeout duration
- `MIN_DELAY` and `MAX_DELAY`: Random delay range

## Directory Structure

```
.
├── references/           # Store input reference files to be processed
├── data_md/              # Store converted Markdown files
├── logs/                 # Store download.py logs
├── papers/               # Store all downloaded PDF files
├── download.py           # Download papers from Sci-Hub (may require proxy)
├── config.py             # Configuration file
├── convertxls.py         # xls to xlsx tool
├── create_doi.py         # Generate DOI links in table files
├── convert_md.py         # Table to Markdown tool
├── Crossref_download.py  # Crossref download tool (no proxy required)
├── Unpaywall_download.py # Unpaywall download tool (no proxy required)
├── pyproject.toml        # Project metadata and dependency file for uv
└── README.md
```
## Run With UV

This repository uses `uv` and `pyproject.toml` as the dependency source of truth. Do not use `pip` or create a virtual environment manually. Run commands from the repository root with `uv run`, and `uv` will resolve the required dependencies automatically.

```
uv run python download.py --help
```

## Usage

1. Place the Excel file containing literature information in the `references` directory
   - The input file should contain at least `DOI` column
2. Run `download.py` to start downloading literature
   ```
   uv run python download.py
   ```
   To download a single paper directly from the CLI:
   ```
   uv run python download.py --doi 10.1000/example --title "Example Paper"
   ```
3. Downloaded PDF files will be saved in the `papers` directory
4. If your input files are CSV instead of Excel, run the scripts with `--input-format csv`
   ```
   uv run python download.py --input-format csv
   uv run python Crossref_download.py --input-format csv
   ```
   You can also use text reference files (`--input-format txt`) with tab-separated lines:
   ```
   doi:10.1080/03085140903020580	Author 2009 - Title
   url:https://example.com/doc.pdf	Document Name
   isbn:9780674009691	Author 1998 - Book Title
   # Comment lines are ignored
   ```
   Only `doi:` entries are processed; `url:`, `isbn:`, and `#` lines are skipped. Text files are read-only (no status write-back).
5. Download status will be automatically updated in the original input file (it is recommended to delete the rows that have been downloaded to reduce the download volume of `Crossref_download.py` and `Unpaywall_download.py`)
6. Run `Crossref_download.py` or `Unpaywall_download.py` to start downloading literature
   ```
   uv run python Crossref_download.py
   ```
   or
   ```
   uv run python Unpaywall_download.py
   ```
7. If download fails and manual download is required, run `create_doi.py` to generate DOI links and update them to the `DOI Link` column in the input file
   ```
   uv run python create_doi.py
   ```
9. Run `convert_md.py` to convert input files to Markdown format for manual downloading
   ```
   uv run python convert_md.py
   ```

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


## History

This project was originally based on a collection of standalone Python scripts for batch downloading academic papers from Sci-Hub and open access sources. The following major changes and improvements have been made:

- Added support for CSV input and output in addition to Excel, with automatic format detection
- Introduced a unified CLI interface for single-paper downloads and batch processing (via argparse)
- Added a test suite using pytest, with import fixes for script-based repositories
- Migrated dependency management to `pyproject.toml` and the `uv` tool (no pip or manual venv)
- Updated documentation (README, Chinese README) to reflect new features and modern workflow
- Added `.gitignore` and removed generated cache/venv artifacts from version control
- Refactored code for maintainability, including a shared `table_utils.py` for table I/O

If you use or modify this tool, please acknowledge both the original authors and the contributors to these enhancements.
