"""Offline tests for the stdlib HTTP helper, against a local fake server."""

import gzip
import threading
import time
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
