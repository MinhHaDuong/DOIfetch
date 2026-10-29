"""Fetch paper fulltext PDFs from the ISTEX national licensed archive by DOI.

ISTEX (https://www.istex.fr) hosts the full text of publisher back-catalogues
licensed nationally for French higher education and research. Fulltext download
requires a personal access token: generate one at https://api.istex.fr/token/
(you are redirected to your institution's identity federation, e.g. Janus for
CNRS). Provide it either in the ISTEX_ACCESSTOKEN environment variable or as an
ISTEX_ACCESSTOKEN=... line in ~/.config/keys/istex.env (no export needed).

Resolution is by DOI: the search API maps the DOI to an ISTEX document id, then
the fulltext endpoint returns the PDF under a Bearer-token Authorization header.
"""

import os
import subprocess
import sys
import threading

import requests

from doifetch.config import PAPERS_DIR, TIMEOUT

TOKEN_ENV = "ISTEX_ACCESSTOKEN"
TOKEN_FILE = os.path.expanduser("~/.config/keys/istex.env")
ISTEX_SEARCH_URL = "https://api.istex.fr/document/"
ISTEX_FULLTEXT_URL = "https://api.istex.fr/document/{id}/fulltext/pdf"
LOGIN_URL = "https://api.istex.fr/token/"
AUTH_STATUSES = (401, 403)

# One login prompt per run: worker threads share a single browser round-trip.
_login_lock = threading.Lock()
_login_attempted = False


def _is_interactive():
    """True when a person can answer: a TTY on both ends and a graphical display."""
    has_tty = sys.stdin.isatty() and sys.stdout.isatty()
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return has_tty and has_display


def _open_login_page(url):
    subprocess.Popen(["firefox", url])


def _refresh_login(stale_token):
    """Return a fresh token after an authentication failure, or '' if none.

    Interactive: open Firefox on the login page, wait for Enter, re-read the
    token. Non-interactive: print one line and give up so other sources run.
    Only the first failure of a run prompts; later ones just re-read.
    """
    global _login_attempted
    with _login_lock:
        token = _get_token()
        if token and token != stale_token:
            return token
        if _login_attempted:
            return ""
        _login_attempted = True
        if not _is_interactive():
            print(f"ISTEX login needed: {LOGIN_URL}")
            return ""
        try:
            _open_login_page(LOGIN_URL)
            input("Log in to ISTEX in Firefox, save the token, then press Enter... ")
        except (OSError, EOFError):
            # No firefox on PATH, or stdin closed mid-prompt: degrade like a
            # non-interactive run so the cascade moves on to the next source.
            print(f"ISTEX login needed: {LOGIN_URL}")
            return ""
        return _get_token()


def _token_from_file(path):
    """Return the ISTEX token from an unexported KEY=VALUE env file, or ''."""
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :]
        key, sep, value = line.partition("=")
        if sep and key.strip() == TOKEN_ENV:
            return value.strip().strip("\"'")
    return ""


def _get_token():
    """Read the ISTEX access token from the environment, else ~/.config/keys."""
    return os.environ.get(TOKEN_ENV, "").strip() or _token_from_file(TOKEN_FILE)


def _resolve_istex_id(doi):
    """Return the ISTEX document id for a DOI, or None if absent from the archive."""
    params = {"q": f'doi:"{doi}"', "size": 1, "output": "id"}
    response = requests.get(ISTEX_SEARCH_URL, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        return None
    hits = response.json().get("hits", [])
    return hits[0]["id"] if hits else None


def _download(istex_id, token):
    return requests.get(
        ISTEX_FULLTEXT_URL.format(id=istex_id),
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )


def fetch_pdf(doi, title, output_dir=PAPERS_DIR):
    """Download a single paper PDF from ISTEX by DOI.

    Returns dict with keys: status, doi, title, file_name, error (if failed).
    """
    from doifetch.pdf_utils import clean_filename, is_valid_pdf

    safe_title = title if title else f"Unknown_{doi}"
    file_name = f"{clean_filename(safe_title)}.pdf"
    file_path = os.path.join(output_dir, file_name)

    if os.path.exists(file_path):
        if is_valid_pdf(file_path):
            return {
                "status": "skipped",
                "doi": doi,
                "title": title,
                "file_name": file_name,
            }
        else:
            os.remove(file_path)

    token = _get_token()
    if not token:
        token = _refresh_login("")
    if not token:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": f"{TOKEN_ENV} not set (generate at https://api.istex.fr/token/)",
        }

    if not doi:
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": "ISTEX resolution requires a DOI",
        }

    try:
        istex_id = _resolve_istex_id(doi)
        if not istex_id:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "DOI not found in ISTEX",
            }
        response = _download(istex_id, token)
        if response.status_code in AUTH_STATUSES:
            fresh = _refresh_login(token)
            if fresh:
                response = _download(istex_id, fresh)
        if response.status_code != 200:
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": f"ISTEX fulltext download failed: {response.status_code}",
            }
        with open(file_path, "wb") as f:
            f.write(response.content)
        if not is_valid_pdf(file_path):
            os.remove(file_path)
            return {
                "status": "failed",
                "doi": doi,
                "title": title,
                "file_name": file_name,
                "error": "Downloaded file is not a valid PDF",
            }
        return {
            "status": "success",
            "doi": doi,
            "title": title,
            "file_name": file_name,
        }
    except Exception as e:  # noqa: BLE001 - a fetcher reports failure, never raises into the fetch loop
        return {
            "status": "failed",
            "doi": doi,
            "title": title,
            "file_name": file_name,
            "error": str(e),
        }
