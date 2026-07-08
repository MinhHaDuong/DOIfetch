import os

# Sci-Hub domain pool (auto-rotated to avoid bans). Sci-Hub paused new uploads,
# so this pool serves only the frozen pre-~2021 corpus, but its pages expose the
# PDF in a freely scrapable iframe — kept as the reliable path for older papers.
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

# SciDB (the Sci-Hub database frontend hosted by Anna's Archive) serves the full
# Sci-Hub corpus PLUS papers added after Sci-Hub froze uploads, reached at
# {domain}scidb/{doi}. Anna's Archive is anti-bot/membership-gated, so automated
# retrieval is best-effort; tried after the classic Sci-Hub pool.
SCIDB_DOMAINS = [
    "https://annas-archive.se/",
    "https://annas-archive.org/",
    "https://annas-archive.gd/",
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
