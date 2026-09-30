"""Распознавание ссылок и ключевых слов в сообщении."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlsplit


class Kind(StrEnum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    OTHER = "other"  # всё остальное отдаём yt-dlp как есть


@dataclass(frozen=True)
class LinkRequest:
    url: str
    kind: Kind
    audio: bool = False  # прислать только звук
    as_file: bool = False  # прислать оригиналы документами, без сжатия
    youtube_id: str | None = None


_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_TRAILING_JUNK = ".,;:!?)]}>'\"»"

_YT_ID = r"[A-Za-z0-9_-]{11}"
_YT_ID_RE = re.compile(rf"^{_YT_ID}$")
_YT_HOST_RE = re.compile(r"^(?:www\.|m\.|music\.)?(?:youtube\.com|youtube-nocookie\.com)$", re.I)
_YT_PATH_RE = re.compile(rf"^/(?:shorts|live|embed|v|e)/({_YT_ID})", re.I)

_IG_HOST_RE = re.compile(r"^(?:www\.)?instagram\.com$", re.I)
_IG_PATH_RE = re.compile(r"^/(?:[^/]+/)?(?:p|reels?|tv|share|stories)/", re.I)

AUDIO_WORDS = frozenset({"audio", "аудио", "mp3", "m4a", "звук", "music", "музыка"})
FILE_WORDS = frozenset({"file", "файл", "doc", "док", "original", "оригинал"})

_WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.I)


def youtube_id_from_url(url: str) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "youtu.be":
        m = re.match(rf"^/({_YT_ID})", parts.path)
        return m.group(1) if m else None
    if not _YT_HOST_RE.match(host):
        return None
    if parts.path == "/watch":
        v = parse_qs(parts.query).get("v", [""])[0]
        return v if _YT_ID_RE.match(v) else None
    m = _YT_PATH_RE.match(parts.path)
    return m.group(1) if m else None


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def is_instagram_url(url: str) -> bool:
    parts = urlsplit(url)
    return bool(_IG_HOST_RE.match(parts.hostname or "") and _IG_PATH_RE.match(parts.path))


def clean_instagram_url(url: str) -> str:
    """Убирает трекинг-параметры (?igsh=..., ?utm_...) — они только мешают."""
    path = urlsplit(url).path
    if not path.endswith("/"):
        path += "/"
    return f"https://www.instagram.com{path}"


def extract_url(text: str) -> str | None:
    m = _URL_RE.search(text)
    if not m:
        return None
    return m.group(0).rstrip(_TRAILING_JUNK)


def parse_message(text: str) -> LinkRequest | None:
    """Первая ссылка в сообщении + ключевые слова вокруг неё."""
    url = extract_url(text)
    if not url:
        return None

    words = {w.lower() for w in _WORD_RE.findall(text.replace(url, " "))}
    audio = bool(words & AUDIO_WORDS)
    as_file = bool(words & FILE_WORDS)

    host = (urlsplit(url).hostname or "").lower()
    if host == "music.youtube.com":
        audio = True

    video_id = youtube_id_from_url(url)
    if video_id:
        return LinkRequest(
            url=canonical_youtube_url(video_id),
            kind=Kind.YOUTUBE,
            audio=audio,
            as_file=as_file,
            youtube_id=video_id,
        )
    if is_instagram_url(url):
        return LinkRequest(url=clean_instagram_url(url), kind=Kind.INSTAGRAM, audio=audio, as_file=as_file)
    return LinkRequest(url=url, kind=Kind.OTHER, audio=audio, as_file=as_file)
