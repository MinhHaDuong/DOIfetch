"""Offline tests for the stdlib HTTP helper, against a local fake server."""

import gzip
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from doifetch.sources import _http


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status=200, body=b"", headers=()):
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        p = self.path
        if p == "/ok":
            self._send(body=b"hello", headers=[("Content-Type", "text/plain")])
        elif p == "/slow":
            time.sleep(1.5)
            self._send(body=b"late")
        elif p == "/redir":
            self._send(302, headers=[("Location", "/ok")])
        elif p == "/loop":
            self._send(302, headers=[("Location", "/loop")])
        elif p == "/setcookie":
            self._send(headers=[("Set-Cookie", "sid=abc; Path=/")])
        elif p == "/echo-cookie":
            self._send(body=(self.headers.get("Cookie") or "").encode())
        elif p == "/echo-ua":
            self._send(body=(self.headers.get("User-Agent") or "").encode())
        elif p.startswith("/echo-path"):
            self._send(body=p.encode())
        elif p == "/latin1":
            self._send(
                body="café".encode("latin-1"),
                headers=[("Content-Type", "text/html; charset=ISO-8859-1")],
            )
        elif p == "/gzip":
            self._send(
                body=gzip.compress(b"zipped"), headers=[("Content-Encoding", "gzip")]
            )
        elif p == "/echo-auth":
            self._send(body=(self.headers.get("Authorization") or "").encode())
        elif p == "/xhost":
            port = self.server.server_address[1]
            self._send(
                302, headers=[("Location", f"http://localhost:{port}/echo-auth")]
            )
        elif p == "/samehost":
            self._send(302, headers=[("Location", "/echo-auth")])
        elif p == "/to-file":
            self._send(302, headers=[("Location", "file:///etc/hostname")])
        elif p == "/big":
            self._send(body=b"x" * 5000)
        elif p == "/bomb":
            self._send(
                body=gzip.compress(b"\0" * 100000),
                headers=[("Content-Encoding", "gzip")],
            )
        elif p == "/404":
            self._send(404, body=b"nope")
        else:
            self._send(404)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        self._send(body=self.rfile.read(n))


@pytest.fixture(scope="module")
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_get_ok(base):
    r = _http.Session().get(base + "/ok")
    assert r.ok and r.status == 200 and r.content == b"hello" and r.text == "hello"


def test_error_status_does_not_raise(base):
    r = _http.Session().get(base + "/404")
    assert r.status == 404 and not r.ok and r.content == b"nope"


def test_timeout_raises_http_error(base):
    with pytest.raises(_http.HttpError):
        _http.Session(timeout=0.2).get(base + "/slow")


def test_per_call_timeout_overrides(base):
    with pytest.raises(_http.HttpError):
        _http.Session(timeout=10).get(base + "/slow", timeout=0.2)


def test_redirect_followed(base):
    r = _http.Session().get(base + "/redir")
    assert r.status == 200 and r.url.endswith("/ok") and r.text == "hello"


def test_redirect_loop_raises(base):
    with pytest.raises(_http.HttpError):
        _http.Session().get(base + "/loop")


def test_cookies_persist_in_session(base):
    s = _http.Session()
    s.get(base + "/setcookie")
    assert s.get(base + "/echo-cookie").text == "sid=abc"
    assert _http.Session().get(base + "/echo-cookie").text == ""


def test_charset_decoding(base):
    r = _http.Session().get(base + "/latin1")
    assert r.encoding.lower() == "iso-8859-1" and r.text == "café"


def test_gzip_decoding(base):
    assert _http.Session().get(base + "/gzip").content == b"zipped"


def test_text_falls_back_on_unknown_charset():
    r = _http.Response(200, "u", {"content-type": "text/x; charset=bogus"}, b"abc")
    assert r.text == "abc"


def test_user_agent_default_and_override(base):
    assert _http.Session().get(base + "/echo-ua").text == _http.DEFAULT_USER_AGENT
    s = _http.Session(headers={"User-Agent": "X/1"})
    assert s.get(base + "/echo-ua").text == "X/1"


def test_params_encoded(base):
    r = _http.Session().get(base + "/echo-path", params={"q": "a b"})
    assert r.text == "/echo-path?q=a+b"


def test_post_form(base):
    r = _http.Session().post(base + "/x", data={"a": "1"})
    assert r.text == "a=1"


def test_connection_refused_raises():
    with pytest.raises(_http.HttpError):
        _http.Session(timeout=1).get("http://127.0.0.1:1/")


def test_one_shot_get(base):
    assert _http.get(base + "/ok", timeout=5).text == "hello"


def test_authorization_dropped_on_cross_host_redirect(base):
    s = _http.Session(headers={"Authorization": "Bearer SECRET"})
    assert s.get(base + "/xhost").text == ""


def test_authorization_kept_on_same_host_redirect(base):
    s = _http.Session(headers={"Authorization": "Bearer SECRET"})
    assert s.get(base + "/samehost").text == "Bearer SECRET"


@pytest.mark.parametrize("url", ["file:///etc/hostname", "ftp://example.org/x"])
def test_non_http_scheme_refused(url):
    with pytest.raises(_http.HttpError):
        _http.Session().get(url)


def test_redirect_to_file_refused(base):
    with pytest.raises(_http.HttpError):
        _http.Session().get(base + "/to-file")


def test_https_to_http_redirect_refused():
    handler = _http._LimitedRedirects()
    req = urllib.request.Request("https://a.example/x")
    with pytest.raises(urllib.error.URLError):
        handler.redirect_request(req, None, 302, "", {}, "http://a.example/y")


def test_oversized_body_fails(base, monkeypatch):
    monkeypatch.setattr(_http, "MAX_BODY_BYTES", 1000)
    with pytest.raises(_http.HttpError):
        _http.Session().get(base + "/big")


def test_decompression_bomb_fails(base, monkeypatch):
    monkeypatch.setattr(_http, "MAX_BODY_BYTES", 1000)
    with pytest.raises(_http.HttpError):
        _http.Session().get(base + "/bomb")


def test_body_within_cap_ok(base, monkeypatch):
    monkeypatch.setattr(_http, "MAX_BODY_BYTES", 6000)
    assert len(_http.Session().get(base + "/big").content) == 5000


def test_truncated_gzip_body_fails():
    body = gzip.compress(b"hello world" * 100)[:-20]
    with pytest.raises(_http.HttpError):
        _http._decode_body(body, "gzip")


def _redirected(url, newurl, headers):
    handler = _http._LimitedRedirects()
    req = urllib.request.Request(url, headers=headers)
    return handler.redirect_request(req, None, 302, "", {}, newurl)


@pytest.mark.parametrize("newurl", ["https://a.example/y", "https://b.example/y"])
def test_proxy_authorization_dropped_on_every_redirect(newurl):
    new_req = _redirected(
        "https://a.example/x", newurl, {"Proxy-Authorization": "Basic c2VjcmV0"}
    )
    assert "proxy-authorization" not in {k.lower() for k in new_req.headers}


def test_redirect_response_body_not_drained():
    class Fp:
        def read(self, *args):
            raise AssertionError("redirect body read without a bound")

        def close(self):
            pass

    fp = Fp()
    handler = _http._LimitedRedirects()
    req = urllib.request.Request("https://a.example/x")
    handler.redirect_request(req, fp, 302, "", {}, "https://a.example/y")
    assert fp.read() == b""


def test_multi_member_gzip_fully_decoded():
    body = gzip.compress(b"first,") + gzip.compress(b"second")
    assert _http._decode_body(body, "gzip") == b"first,second"


def test_multi_member_gzip_shares_one_budget(monkeypatch):
    monkeypatch.setattr(_http, "MAX_BODY_BYTES", 1000)
    body = gzip.compress(b"\0" * 600) + gzip.compress(b"\0" * 600)
    with pytest.raises(_http.HttpError):
        _http._decode_body(body, "gzip")


def test_truncated_last_gzip_member_fails():
    body = gzip.compress(b"first") + gzip.compress(b"second" * 100)[:-20]
    with pytest.raises(_http.HttpError):
        _http._decode_body(body, "gzip")
