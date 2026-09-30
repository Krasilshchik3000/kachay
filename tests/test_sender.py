import html
import re
from pathlib import Path

from kachay.downloaders import DownloadResult
from kachay.sender import build_caption, chunked, source_label

TAG_RE = re.compile(r"<[^>]+>")


def visible(caption: str) -> str:
    return html.unescape(TAG_RE.sub("", caption))


def test_chunked():
    assert list(chunked(range(23), 10)) == [list(range(10)), list(range(10, 20)), [20, 21, 22]]
    assert list(chunked([], 10)) == []


def test_source_label():
    assert source_label("https://www.instagram.com/p/abc/") == "Instagram"
    assert source_label("https://youtu.be/abc") == "YouTube"
    assert source_label("https://www.youtube.com/watch?v=abc") == "YouTube"
    assert source_label("https://vimeo.com/123") == "vimeo.com"


def test_caption_youtube_has_bold_title_author_and_link():
    r = DownloadResult(
        items=[], source_url="https://www.youtube.com/watch?v=abc", title="Title <b>", author="Chan & Co"
    )
    cap = build_caption(r)
    assert cap.startswith("<b>Title &lt;b&gt;</b>\nChan &amp; Co")
    assert cap.endswith('<a href="https://www.youtube.com/watch?v=abc">YouTube</a>')


def test_caption_instagram_is_trimmed_to_telegram_limit():
    long_text = "слово " * 500
    r = DownloadResult(items=[], source_url="https://www.instagram.com/p/abc/", text=long_text, author="@someone")
    cap = build_caption(r)
    assert len(visible(cap)) <= 1024
    assert "…" in cap
    assert cap.endswith('<a href="https://www.instagram.com/p/abc/">Instagram</a>')


def test_caption_without_text_is_just_link():
    r = DownloadResult(items=[], source_url="https://www.instagram.com/p/abc/")
    assert build_caption(r) == '<a href="https://www.instagram.com/p/abc/">Instagram</a>'


def test_path_import_smoke():
    assert Path is not None
