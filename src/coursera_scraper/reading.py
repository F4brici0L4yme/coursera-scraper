"""Turn a rendered supplement (reading) into downloadable artifacts.

Coursera returns readings as already-rendered HTML
(``renderableHtmlWithMetadata.renderableHtml``) with images embedded as
signed CloudFront URLs. We keep that HTML faithful (zero conversion loss),
download its images locally, and also emit a plain-text ``.txt`` extracted
with the stdlib ``html.parser`` (no extra dependencies).
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

_SRC_RE = re.compile(r'(?<![-\w])src\s*=\s*(["\'])(.*?)\1', re.IGNORECASE)

_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def rewrite_image_sources(rendered_html: str, name_fn):
    """Rewrite every ``src`` attribute via ``name_fn(url, index)``.

    Returns ``(new_html, urls)`` where ``urls`` are the original (unescaped)
    image URLs in order.
    """
    urls: list[str] = []

    def _repl(m):
        quote = m.group(1)
        url = html.unescape(m.group(2))
        urls.append(url)
        return f"src={quote}{name_fn(url, len(urls))}{quote}"

    return _SRC_RE.sub(_repl, rendered_html), urls


def mime_to_ext(content_type: str) -> str:
    return _EXT_BY_MIME.get(content_type.split(";")[0].strip().lower(), ".img")


def guess_ext_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix
    return suffix if suffix and len(suffix) <= 6 else ".img"


class _TextExtractor(HTMLParser):
    """Convert rendered HTML into readable plain text."""

    _BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "tr", "ul", "ol", "table", "section", "article", "blockquote", "hr"}
    _SKIP = {"script", "style", "head", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self._pre = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in ("pre", "code"):
            self._pre = True
        if tag in self._BLOCK and not self._skip_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in ("pre", "code"):
            self._pre = False
        if tag in self._BLOCK and not self._skip_depth:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(rendered_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(rendered_html)
    lines = []
    for line in "".join(parser.parts).splitlines():
        line = line.strip()
        if line:
            lines.append(line)
    return "\n".join(lines)
