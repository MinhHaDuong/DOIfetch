"""The standard-library page scraper behaves as BeautifulSoup did.

Each expected value below was produced by ``BeautifulSoup(html, "html.parser")``
(``find_all("a", href=True)`` with ``get_text(strip=True)``, and
``find("iframe") or find("embed")``) before that dependency was removed.
"""

import pytest

from doifetch.sources import _html, libgen, scihub


def _anchors(html):
    return [(a.href, a.text) for a in _html.parse(html).anchors]


@pytest.mark.parametrize(
    "html, expected",
    [
        (b'<embed src="E"><iframe src="I"></iframe>', "I"),
        (b'<iframe src="I"></iframe><embed src="E">', "I"),
        (b'<embed src="E">', "E"),
        # An iframe without a src still wins: there is no src to use.
        (b'<iframe></iframe><embed src="E">', None),
        (b'<iframe src="1" src="2"></iframe>', "2"),  # the last duplicate wins
        (b"<html>nothing</html>", None),
    ],
)
def test_frame_src(html, expected):
    assert _html.parse(html).frame_src == expected


@pytest.mark.parametrize(
    "html, expected",
    [
        (b'<a href="x"> G <b>E</b> T </a>', [("x", "GET")]),  # pieces stripped alone
        (b'<a href="x">G<!-- c -->E T</a>', [("x", "GE T")]),
        (b"<a href>GET</a>", [("", "GET")]),  # an empty href is kept
        (b'<a name="n">GET</a>', []),  # no href: skipped
        (b'<a href="1" href="2">x</a>', [("2", "x")]),
        (b'<a href="x">a<a href="y">b</a>c</a>', [("x", "abc"), ("y", "b")]),
        (b'<a href="x"><script>zz</script>GE<style>q</style>T</a>', [("x", "GET")]),
        (b'<a href="x">GET', [("x", "GET")]),  # never closed
        (b'<a href="x"/>GET</a>', [("x", "")]),  # self-closed
        (b'<A HREF="X">get</A>', [("X", "get")]),
        (b'\xef\xbb\xbf<a href="x">GET</a>', [("x", "GET")]),  # byte-order mark
        (b'<p><a href="x">G</p>ET</a>', [("x", "G")]),  # the paragraph ends it
        (b'<a href="x">G&nbsp;E&amp;T</a>', [("x", "G\xa0E&T")]),
        (b'<a href="a&amp;b">x</a>', [("a&b", "x")]),
        ('<a href="x">GET</a>', [("x", "GET")]),  # str as well as bytes
    ],
)
def test_anchors(html, expected):
    assert _anchors(html) == expected


def test_bytes_are_decoded_as_utf8_with_replacement():
    assert _anchors("<a href='x'>café</a>".encode()) == [("x", "café")]
    assert _anchors(b"<a href='x'>a\xffb</a>") == [("x", "a�b")]


def test_extract_pdf_url_prefers_iframe_whatever_the_order():
    both = b'<embed src="https://e/e.pdf"><iframe src="https://i/i.pdf"></iframe>'
    assert scihub.extract_pdf_url(both) == "https://i/i.pdf"


def test_libgen_get_link_found_across_nested_and_split_text():
    page = _html.parse('<a href="get.php?md5=m"> G <b>E</b> T </a>')
    assert [a.text.upper() for a in page.anchors] == ["GET"]
    assert libgen._extract_md5(_html.parse('<a href="/x?md5=' + "B" * 32 + '">')) == (
        "b" * 32
    )
