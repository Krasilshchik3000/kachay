from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..config import MB
from ..media import make_thumbnail, probe

PHOTO_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
VIDEO_EXTS = frozenset({".mp4", ".mov", ".m4v", ".webm", ".mkv"})
AUDIO_EXTS = frozenset({".m4a", ".mp3", ".opus", ".ogg", ".webm"})

MediaKind = Literal["photo", "video", "audio"]


@dataclass
class MediaItem:
    path: Path
    kind: MediaKind
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    thumbnail: Path | None = None
    title: str | None = None
    performer: str | None = None

    @property
    def size(self) -> int:
        return self.path.stat().st_size


@dataclass
class DownloadResult:
    items: list[MediaItem]
    source_url: str
    title: str | None = None
    text: str | None = None  # подпись поста (Instagram)
    author: str | None = None
    extra: dict = field(default_factory=dict)


class DownloadError(Exception):
    """Текст исключения показывается пользователю как есть."""


class TooLargeError(DownloadError):
    pass


class LoginRequiredError(DownloadError):
    pass


def format_mb(size: int) -> str:
    return f"{size / MB:.1f} МБ"


def check_size(path: Path, limit: int, what: str = "Файл") -> None:
    size = path.stat().st_size
    if size > limit:
        raise TooLargeError(
            f"{what} весит {format_mb(size)}, а лимит отправки — {format_mb(limit)}. "
            "Подними локальный Bot API сервер (см. README) или попроси «аудио»."
        )


async def video_item(path: Path, *, title: str | None = None) -> MediaItem:
    """Собирает MediaItem для видео: размеры/длительность через ffprobe + превью."""
    info = await probe(path)
    thumb = await make_thumbnail(path, path.with_name(path.stem + ".thumb.jpg"), is_video=True)
    return MediaItem(
        path=path,
        kind="video",
        width=info.width,
        height=info.height,
        duration=info.duration,
        thumbnail=thumb,
        title=title,
    )


async def photo_item(path: Path) -> MediaItem:
    info = await probe(path)
    return MediaItem(path=path, kind="photo", width=info.width, height=info.height)
