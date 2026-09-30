"""Хэндлеры aiogram."""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
from collections.abc import AsyncIterator

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import Settings
from .downloaders import DownloadError
from .links import Kind, LinkRequest, canonical_youtube_url, parse_message
from .sender import TelegramSender
from .service import DownloadService

log = logging.getLogger(__name__)

HELP = (
    "Кинь ссылку — пришлю контент.\n\n"
    "• Instagram: пост, карусель, reels, stories\n"
    "• YouTube: видео, shorts\n"
    "• Другие сайты — что сможет yt-dlp\n\n"
    "Допиши к ссылке слово:\n"
    "• <b>аудио</b> — только звук (m4a)\n"
    "• <b>файл</b> — оригиналы документами, без сжатия"
)

AUDIO_CB_PREFIX = "audio:"


def build_public_router(settings: Settings) -> Router:
    """Единственное, что видят посторонние: свой user id по /start. Остальное — тишина."""
    router = Router(name="kachay-public")
    router.message.filter(~F.from_user.id.in_(settings.allowed_user_ids))

    @router.message(CommandStart())
    async def on_start_stranger(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        await message.answer(
            f"Твой user id: <code>{user_id}</code>\n"
            "Этот бот личный. Чтобы им пользоваться, впиши id в ALLOWED_USER_IDS и перезапусти бота."
        )

    return router


def build_router(settings: Settings, service: DownloadService, sender: TelegramSender) -> Router:
    router = Router(name="kachay")
    allowed = settings.allowed_user_ids
    router.message.filter(F.from_user.id.in_(allowed))
    router.callback_query.filter(F.from_user.id.in_(allowed))

    @router.message(CommandStart())
    @router.message(Command("help"))
    async def on_start(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        await message.answer(f"{HELP}\n\nТвой user id: <code>{user_id}</code>")

    @router.message(F.text)
    async def on_text(message: Message, bot: Bot) -> None:
        req = parse_message(message.text or "")
        if req is None:
            await message.reply("Не вижу ссылки. /help")
            return
        await run_job(bot, service, sender, message.chat.id, message.message_id, req)

    @router.callback_query(F.data.startswith(AUDIO_CB_PREFIX))
    async def on_audio_button(query: CallbackQuery, bot: Bot) -> None:
        video_id = (query.data or "")[len(AUDIO_CB_PREFIX):]
        await query.answer("Качаю аудио…")
        msg = query.message
        chat_id = msg.chat.id if msg else query.from_user.id
        reply_to = msg.message_id if isinstance(msg, Message) else None
        req = LinkRequest(url=canonical_youtube_url(video_id), kind=Kind.YOUTUBE, audio=True, youtube_id=video_id)
        await run_job(bot, service, sender, chat_id, reply_to, req)

    return router


def audio_keyboard(req: LinkRequest) -> InlineKeyboardMarkup | None:
    if req.kind is not Kind.YOUTUBE or req.audio or not req.youtube_id:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎧 Аудио", callback_data=f"{AUDIO_CB_PREFIX}{req.youtube_id}")]]
    )


@contextlib.asynccontextmanager
async def chat_action(bot: Bot, chat_id: int, action: str) -> AsyncIterator[None]:
    """Telegram сбрасывает статус через 5 секунд — шлём его по кругу, пока работаем."""

    async def loop() -> None:
        while True:
            with contextlib.suppress(Exception):
                await bot.send_chat_action(chat_id, action)
            await asyncio.sleep(4)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def run_job(
    bot: Bot,
    service: DownloadService,
    sender: TelegramSender,
    chat_id: int,
    reply_to: int | None,
    req: LinkRequest,
) -> None:
    log.info("Запрос: %s (%s, audio=%s, file=%s)", req.url, req.kind.value, req.audio, req.as_file)
    status = await bot.send_message(chat_id, "⏳ Качаю…", reply_to_message_id=reply_to)
    action = "upload_voice" if req.audio else "upload_video"
    try:
        async with service.semaphore, service.workdir() as workdir, chat_action(bot, chat_id, action):
            result = await service.download(req, workdir)
            sizes = ", ".join(f"{i.kind} {i.size / 1024 / 1024:.1f}MB" for i in result.items)
            log.info("Скачано %d шт.: %s", len(result.items), sizes)
            with contextlib.suppress(TelegramBadRequest):
                await status.edit_text("📤 Отправляю…")
            await sender.send(
                chat_id,
                result,
                as_file=req.as_file,
                reply_to=reply_to,
                reply_markup=audio_keyboard(req),
            )
        with contextlib.suppress(TelegramBadRequest):
            await status.delete()
    except DownloadError as exc:
        log.warning("Не скачал %s: %s", req.url, exc)
        await _set_status(status, f"❌ {exc}")
    except TelegramBadRequest as exc:
        log.exception("Telegram отверг отправку для %s", req.url)
        await _set_status(status, f"❌ Telegram не принял файл: {exc.message}")
    except TelegramNetworkError as exc:
        log.exception("Сетевая ошибка Telegram для %s", req.url)
        await _set_status(status, f"❌ Не смог загрузить в Telegram: {exc}")
    except Exception as exc:  # noqa: BLE001 — последний рубеж, чтобы бот не молчал
        log.exception("Неожиданная ошибка для %s", req.url)
        await _set_status(status, f"❌ Ошибка: {type(exc).__name__}: {str(exc)[:300]}")


async def _set_status(status: Message, text: str) -> None:
    """Текст ошибки может содержать < и & — экранируем, чтобы HTML-режим его не отверг."""
    with contextlib.suppress(Exception):
        await status.edit_text(html.escape(text[:4000]), disable_web_page_preview=True)
