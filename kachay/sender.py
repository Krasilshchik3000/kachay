"""Отправка результата в Telegram: альбомы по 10, видео с превью, аудио, документы."""

from __future__ import annotations

import html
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

from .config import MB
from .downloaders import DownloadResult, MediaItem

log = logging.getLogger(__name__)

ALBUM_MAX = 10
CAPTION_MAX = 1024
PHOTO_MAX_BYTES = 10 * MB
TITLE_MAX = 200
REQUEST_TIMEOUT = 900  # секунд на один upload

T = TypeVar("T")


def chunked(items: Iterable[T], size: int) -> Iterator[list[T]]:
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def source_label(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    if "instagram.com" in host:
        return "Instagram"
    if "youtube.com" in host or host == "youtu.be":
        return "YouTube"
    return host or "Источник"


def build_caption(result: DownloadResult) -> str:
    """HTML-подпись ≤ 1024 видимых символов: заголовок, автор, текст поста, ссылка."""
    label = source_label(result.source_url)
    link = f'<a href="{html.escape(result.source_url, quote=True)}">{html.escape(label)}</a>'

    title = (result.title or "").strip()[:TITLE_MAX]
    author = (result.author or "").strip()[:100]
    body = (result.text or "").strip()

    head_visible = title + ("\n" + author if author else "")
    budget = CAPTION_MAX - len(label) - 2  # "\n\n" перед ссылкой
    remaining = budget - len(head_visible) - (2 if head_visible and body else 0)
    if len(body) > remaining:
        body = body[: max(0, remaining - 1)].rstrip() + "…" if remaining > 1 else ""

    head_html = ""
    if title:
        head_html = f"<b>{html.escape(title)}</b>"
    if author:
        head_html += ("\n" if head_html else "") + html.escape(author)

    parts = [p for p in (head_html, html.escape(body)) if p]
    parts.append(link)
    return "\n\n".join(parts)


def _thumb(item: MediaItem) -> FSInputFile | None:
    return FSInputFile(item.thumbnail) if item.thumbnail else None


class TelegramSender:
    def __init__(self, bot: Bot, request_timeout: int = REQUEST_TIMEOUT) -> None:
        self.bot = bot
        self.timeout = request_timeout

    async def send(
        self,
        chat_id: int,
        result: DownloadResult,
        *,
        as_file: bool = False,
        reply_to: int | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        caption = build_caption(result)
        common = {"chat_id": chat_id, "reply_to_message_id": reply_to, "request_timeout": self.timeout}

        if as_file:
            await self._send_documents(result.items, caption, common)
            return

        audio = [i for i in result.items if i.kind == "audio"]
        visual = [i for i in result.items if i.kind in ("photo", "video")]
        # Фото тяжелее 10 МБ Telegram как фото не примет — уйдут документами.
        album = [i for i in visual if not (i.kind == "photo" and i.size > PHOTO_MAX_BYTES)]
        heavy = [i for i in visual if i not in album]

        for item in audio:
            await self.bot.send_audio(
                audio=FSInputFile(item.path, filename=_audio_filename(item)),
                caption=caption,
                title=item.title,
                performer=item.performer,
                duration=item.duration,
                thumbnail=_thumb(item),
                reply_markup=reply_markup,
                **common,
            )
            caption = ""

        if len(album) == 1:
            item = album[0]
            if item.kind == "video":
                await self.bot.send_video(
                    video=FSInputFile(item.path),
                    caption=caption,
                    width=item.width,
                    height=item.height,
                    duration=item.duration,
                    thumbnail=_thumb(item),
                    supports_streaming=True,
                    reply_markup=reply_markup,
                    **common,
                )
            else:
                await self.bot.send_photo(
                    photo=FSInputFile(item.path),
                    caption=caption,
                    reply_markup=reply_markup,
                    **common,
                )
            caption = ""
        elif album:
            for chunk in chunked(album, ALBUM_MAX):
                media = []
                for item in chunk:
                    if item.kind == "video":
                        media.append(
                            InputMediaVideo(
                                media=FSInputFile(item.path),
                                caption=caption,
                                width=item.width,
                                height=item.height,
                                duration=item.duration,
                                thumbnail=_thumb(item),
                                supports_streaming=True,
                            )
                        )
                    else:
                        media.append(InputMediaPhoto(media=FSInputFile(item.path), caption=caption))
                    caption = ""
                await self.bot.send_media_group(media=media, **common)

        if heavy:
            await self._send_documents(heavy, caption, common)

    async def _send_documents(self, items: list[MediaItem], caption: str, common: dict) -> None:
        if len(items) == 1:
            item = items[0]
            await self.bot.send_document(
                document=FSInputFile(item.path),
                caption=caption,
                thumbnail=_thumb(item),
                **common,
            )
            return
        for chunk in chunked(items, ALBUM_MAX):
            media = []
            for item in chunk:
                media.append(
                    InputMediaDocument(media=FSInputFile(item.path), caption=caption, thumbnail=_thumb(item))
                )
                caption = ""
            await self.bot.send_media_group(media=media, **common)


def _audio_filename(item: MediaItem) -> str:
    base = (item.title or item.path.stem).strip() or "audio"
    safe = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in base)[:80]
    return f"{safe}{item.path.suffix or '.m4a'}"


__all__ = ["TelegramSender", "build_caption", "chunked", "source_label", "Path"]
