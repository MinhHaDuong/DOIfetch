import os

# Sci-Hub domain pool (auto-rotated to avoid bans)
SCI_HUB_DOMAINS = [
    "https://sci-hub.fr/",
    "https://sci-hub.hkvisa.net/",
    "https://sci-hub.ru/",
    "https://sci-hub.st/",
    "https://sci-hub.se/",
    "https://sci-hub.ren/",
    "https://sci-hub.tw/",
    "https://sci-hub.ee/",
    "https://sci-hub.shop/",
    "https://sci-hub.la/",
]

# Download parameters
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
MAX_THREADS = 15  # concurrency
RETRY_COUNT = 5  # retry count
TIMEOUT = 30  # timeout in seconds
MIN_DELAY = 2  # minimum delay
MAX_DELAY = 8  # maximum delay

# Directories
REFERENCES_DIR = "references"
PAPERS_DIR = "papers"
LOGS_DIR = "logs"

# Zotero (optional local-library dedup; auto-enabled when a DB is found)
# Explicit DB path override; when unset, zotero.find_zotero_db() auto-detects.
ZOTERO_DB_PATH = os.environ.get("ZOTERO_DB_PATH")

# API
DOI_URL_BASE = "https://doi.org/"
UNPAYWALL_EMAIL = "doifetch@users.noreply.github.com"

# Column names
COL_DOI = "DOI"
COL_TITLE = "Article Title"
COL_DOI_LINK = "DOI Link"
COL_DOWNLOAD_STATUS = "Download Status"

# Status values
STATUS_SUCCESS = "success"
