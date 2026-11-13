"""Minimal HTML scraping on the standard library, for the shadow sources.

``parse`` collects what Sci-Hub and Libgen pages are read for: every anchor
(its ``href`` and its text) and the first ``iframe`` / ``embed`` ``src``. It
reproduces what the former BeautifulSoup calls returned on the same pages.
"""

from dataclasses import dataclass, field
from html.parser import HTMLParser

# Elements that never take an end tag: no anchor text can wait on them.
_VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr "
    "basefont bgsound command frame keygen menuitem".split()
)
# Text of these elements is not page text (BeautifulSoup keeps it apart).
_NOT_TEXT = frozenset({"script", "style", "template"})


@dataclass
class Anchor:
    href: str
    text: str = ""


@dataclass
class Page:
    anchors: list[Anchor] = field(default_factory=list)
    # ``src`` of the first iframe, or of the first embed when there is no iframe;
    # None when that element has no ``src`` (an iframe without one still wins).
    frame_src: str | None = None


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.page = Page()
        self._open: list[tuple[str, list[str] | None]] = []  # (tag, text pieces)
        self._anchor_of: dict[int, Anchor] = {}
        self._text = ""  # text since the last tag, comment or declaration
        self._frame: dict[str, str | None] = {}

    # Text is cut at every tag, comment and declaration, and each cut piece is
    # stripped on its own before the pieces of an anchor are joined with no
    # separator: "<a> G <b>E</b> T </a>" reads "GET", as get_text(strip=True) did.
    def _flush(self):
        text, self._text = self._text.strip(), ""
        if not text or any(tag in _NOT_TEXT for tag, _ in self._open):
            return
        for _, pieces in self._open:
            if pieces is not None:
                pieces.append(text)

    def handle_data(self, data):
        self._text += data

    def handle_comment(self, data):
        self._flush()

    handle_decl = handle_pi = unknown_decl = handle_comment

    def handle_starttag(self, tag, attrs):
        self._flush()
        values = dict(attrs)  # a repeated attribute keeps its last value
        if tag in ("iframe", "embed") and tag not in self._frame:
            self._frame[tag] = values.get("src") or None
        if tag in _VOID:
            return
        pieces = None
        if tag == "a" and "href" in values:
            anchor = Anchor(values["href"] or "")
            self.page.anchors.append(anchor)
            pieces = []
            self._anchor_of[len(self._open)] = anchor
        self._open.append((tag, pieces))

    def handle_startendtag(self, tag, attrs):
        # "<a href=x />" opens and closes at once, as it did for BeautifulSoup.
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        self._flush()
        names = [name for name, _ in self._open]
        if tag not in names:
            return  # a stray end tag closes nothing
        depth = len(names) - 1 - names[::-1].index(tag)
        for level in range(len(self._open) - 1, depth - 1, -1):
            anchor = self._anchor_of.pop(level, None)
            if anchor is not None:
                anchor.text = "".join(self._open[level][1] or [])
        del self._open[depth:]

    def finish(self):
        self.close()
        self._flush()
        for level, anchor in self._anchor_of.items():  # anchors never closed
            anchor.text = "".join(self._open[level][1] or [])
        for tag in ("iframe", "embed"):
            if tag in self._frame:
                self.page.frame_src = self._frame[tag]
                break
        return self.page


def parse(html):
    """Scrape ``html`` (``str`` or ``bytes``) into a ``Page``.

    Bytes are decoded as UTF-8 with replacement, a leading byte-order mark
    dropped: the rule ``_http.Response.text`` applies when the server names no
    charset. Only URLs and short labels are read from the page, and they are
    ASCII in practice.
    """
    if isinstance(html, bytes):
        html = html.decode("utf-8-sig", errors="replace")
    collector = _Collector()
    collector.feed(html)
    return collector.finish()
