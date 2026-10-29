"""Small HTTP helper on the standard library (no third-party dependency).

Built on ``urllib.request`` and ``http.cookiejar``. Behaviour:

- every request has a timeout and a User-Agent;
- redirects are followed (at most ``MAX_REDIRECTS``), cookies persist on a
  ``Session``;
- TLS uses the system certificate store (``ssl.create_default_context``);
- an HTTP error status does not raise: the ``Response`` carries it, so callers
  test ``response.ok`` or ``response.status``;
- transport failures (DNS, refused connection, timeout, redirect loop) raise
  ``HttpError``;
- only ``http`` and ``https`` URLs are accepted, initially and on redirects;
  an https -> http redirect is refused, and ``Authorization``/``Cookie``
  headers are dropped when a redirect changes origin;
- raw and decompressed bodies are capped at ``MAX_BODY_BYTES`` (``HttpError``);
- ``gzip`` and ``deflate`` bodies are decoded, and ``Response.text`` decodes
  with the declared charset, falling back to UTF-8 with replacement.
"""

from __future__ import annotations

import http.cookiejar
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 30.0
MAX_REDIRECTS = 10
MAX_BODY_BYTES = 200 * 1024 * 1024
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; DOIfetch)"


class HttpError(OSError):
    """Transport-level failure: no usable HTTP response was obtained."""


@dataclass(frozen=True)
class Response:
    """Final response after redirects."""

    status: int
    url: str
    headers: Mapping[str, str]
    content: bytes = field(repr=False)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def encoding(self) -> str | None:
        match = re.search(
            r"charset\s*=\s*[\"']?([\w.:-]+)", self.headers.get("content-type", "")
        )
        return match.group(1) if match else None

    @property
    def text(self) -> str:
        for enc in (self.encoding, "utf-8"):
            if not enc:
                continue
            try:
                return self.content.decode(enc, errors="replace")
            except LookupError:
                continue
        return self.content.decode("utf-8", errors="replace")


_ALLOWED_SCHEMES = ("http", "https")
_SENSITIVE_HEADERS = ("authorization", "cookie")
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _check_scheme(url: str) -> None:
    if urllib.parse.urlsplit(url).scheme.lower() not in _ALLOWED_SCHEMES:
        raise urllib.error.URLError(f"refusing non-HTTP(S) URL: {url}")


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    return scheme, parts.hostname, parts.port or _DEFAULT_PORTS.get(scheme)


class _LimitedRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS
    max_repeats = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_scheme(newurl)
        old = urllib.parse.urlsplit(req.full_url).scheme.lower()
        if old == "https" and urllib.parse.urlsplit(newurl).scheme.lower() != "https":
            raise urllib.error.URLError(f"refusing https -> http redirect: {newurl}")
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        cross_origin = _origin(req.full_url) != _origin(newurl)
        for name in list(new_req.headers):
            lowered = name.lower()
            if lowered == "proxy-authorization" or (
                cross_origin and lowered in _SENSITIVE_HEADERS
            ):
                del new_req.headers[name]
        if fp is not None:
            # The inherited handler drains the redirect body with an unbounded
            # read() before following; the body is unused, so skip the drain.
            fp.read = lambda *args: b""
        return new_req


def _read_capped(resp) -> bytes:
    raw = resp.read(MAX_BODY_BYTES + 1)
    if len(raw) > MAX_BODY_BYTES:
        raise HttpError(f"response body exceeds {MAX_BODY_BYTES} bytes")
    return raw


def _inflate(body: bytes, wbits: int, *, multi_member: bool = False) -> bytes:
    """Decompress under one cumulative size budget.

    ``multi_member`` decodes concatenated gzip members like ``gzip.decompress``
    (trailing NUL padding tolerated); every member must be complete.
    """
    out = bytearray()
    data = body
    while True:
        d = zlib.decompressobj(wbits)
        chunk = d.decompress(data, MAX_BODY_BYTES + 1 - len(out))
        out += chunk
        if len(out) > MAX_BODY_BYTES or d.unconsumed_tail:
            raise HttpError(f"decompressed body exceeds {MAX_BODY_BYTES} bytes")
        if not d.eof:
            raise HttpError("truncated compressed body")
        data = d.unused_data
        if not multi_member or not data.strip(b"\0"):
            return bytes(out)


def _decode_body(body: bytes, encoding: str) -> bytes:
    encoding = encoding.strip().lower()
    if encoding in ("gzip", "x-gzip"):
        return _inflate(body, 16 + zlib.MAX_WBITS, multi_member=True)
    if encoding == "deflate":
        try:
            return _inflate(body, zlib.MAX_WBITS)
        except zlib.error:
            return _inflate(body, -zlib.MAX_WBITS)
    return body


class Session:
    """A cookie-keeping HTTP client."""

    def __init__(
        self,
        headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self.headers: dict[str, str] = {"User-Agent": DEFAULT_USER_AGENT}
        if headers:
            self.headers.update(headers)
        self.timeout = timeout
        self.cookies = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            _LimitedRedirects,
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(
                context=context or ssl.create_default_context()
            ),
        )

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        return self.request("GET", url, params=params, headers=headers, timeout=timeout)

    def post(
        self,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        body = urllib.parse.urlencode(data or {}).encode("ascii")
        merged = {
            "Content-Type": "application/x-www-form-urlencoded",
            **(headers or {}),
        }
        return self.request("POST", url, body=body, headers=merged, timeout=timeout)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        if params:
            sep = "&" if urllib.parse.urlsplit(url).query else "?"
            url = url + sep + urllib.parse.urlencode(params)
        merged = {"Accept-Encoding": "gzip, deflate", **self.headers, **(headers or {})}
        try:
            _check_scheme(url)
        except urllib.error.URLError as err:
            raise HttpError(f"{method} {url}: {err}") from err
        req = urllib.request.Request(url, data=body, headers=merged, method=method)
        try:
            try:
                resp = self._opener.open(
                    req, timeout=self.timeout if timeout is None else timeout
                )
            except urllib.error.HTTPError as err:
                if 300 <= err.code < 400:  # urllib gave up following redirects
                    raise
                resp = err  # an HTTPError is itself a readable response
            with resp:
                raw = _read_capped(resp)
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                status = resp.status if hasattr(resp, "status") else resp.code
                final_url = resp.geturl()
            content = _decode_body(raw, hdrs.get("content-encoding", ""))
        except (OSError, EOFError, zlib.error) as err:  # URLError, timeout, TLS, loop
            raise HttpError(f"{method} {url}: {err}") from err
        return Response(status=status, url=final_url, headers=hdrs, content=content)


def get(url: str, **kwargs) -> Response:
    """One-shot GET with a throwaway session."""
    session_kwargs = {k: kwargs.pop(k) for k in ("headers", "timeout") if k in kwargs}
    return Session(**session_kwargs).get(url, **kwargs)
