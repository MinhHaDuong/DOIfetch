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

import json
import os
import subprocess
import sys
import threading

from doifetch.config import TIMEOUT
from doifetch.sources import _http
from doifetch.sources._pdf import already_there, save_pdf
from doifetch.sources.contract import Kind, Request, Result

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


def _resolve_istex_id(doi: str) -> str | None:
    """Return the ISTEX document id for a DOI, or None if absent from the archive."""
    params = {"q": f'doi:"{doi}"', "size": "1", "output": "id"}
    response = _http.get(ISTEX_SEARCH_URL, params=params, timeout=TIMEOUT)
    if not response.ok:
        return None
    hits = json.loads(response.text).get("hits", [])
    return hits[0]["id"] if hits else None


def _download(istex_id: str, token: str) -> _http.Response:
    return _http.get(
        ISTEX_FULLTEXT_URL.format(id=istex_id),
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )


NAME = "istex"
ACCEPTS: frozenset[Kind] = frozenset({"doi"})


def _fetch(req: Request) -> Result:
    def fail(error: str) -> Result:
        return Result("failed", NAME, error=error)

    if (done := already_there(req, NAME)) is not None:
        return done

    token = _get_token()
    if not token:
        token = _refresh_login("")
    if not token:
        return fail(f"{TOKEN_ENV} not set (generate at https://api.istex.fr/token/)")

    istex_id = _resolve_istex_id(req.identifier)
    if not istex_id:
        return fail("DOI not found in ISTEX")
    response = _download(istex_id, token)
    if response.status in AUTH_STATUSES:
        fresh = _refresh_login(token)
        if fresh:
            response = _download(istex_id, fresh)
    if response.status != 200:
        return fail(f"ISTEX fulltext download failed: {response.status}")
    return save_pdf(req, NAME, response.content, "Downloaded file is not a valid PDF")


def fetch(req: Request) -> Result:
    """Download a single paper PDF from ISTEX by DOI."""
    try:
        return _fetch(req)
    except Exception as e:  # noqa: BLE001 - the contract: never raise into the fetch loop
        return Result("failed", NAME, error=str(e))
