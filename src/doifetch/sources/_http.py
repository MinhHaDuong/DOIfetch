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
- ``gzip`` and ``deflate`` bodies are decoded, and ``Response.text`` decodes
  with the declared charset, falling back to UTF-8 with replacement.
"""

from __future__ import annotations

import gzip
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


class _LimitedRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS
    max_repeats = MAX_REDIRECTS


def _decode_body(body: bytes, encoding: str) -> bytes:
    encoding = encoding.strip().lower()
    if encoding in ("gzip", "x-gzip"):
        return gzip.decompress(body)
    if encoding == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
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
                raw = resp.read()
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
