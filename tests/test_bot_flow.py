"""Оффлайн-прогон хэндлеров через Dispatcher с подменённой сессией Telegram."""

from __future__ import annotations

import asyncio
import shutil
import typing
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageText,
    SendAudio,
    SendMediaGroup,
    SendMessage,
    SendVideo,
)
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from kachay.bot import build_public_router, build_router
from kachay.config import MB, Settings
from kachay.downloaders import DownloadError, DownloadResult, MediaItem
from kachay.sender import TelegramSender
from kachay.service import DownloadService

ALLOWED = 42
STRANGER = 7


class MockedSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        returning = method.__returning__
        if returning is Message:
            return _msg(100 + len(self.requests)).as_(bot)
        if typing.get_origin(returning) is list:
            return [_msg(100 + len(self.requests)).as_(bot)]
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""


def _msg(message_id: int, text: str | None = None, user_id: int = ALLOWED) -> Message:
    return Message(
        message_id=message_id,
        date=datetime(2026, 1, 1),
        chat=Chat(id=user_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="u"),
        text=text,
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_token="x",
        allowed_user_ids=frozenset({ALLOWED}),
        cookies_file=None,
        download_dir=tmp_path / "data",
        max_upload_bytes=50 * MB,
        telegram_api_base=None,
        js_runtime="deno",
        pot_provider_url=None,
        proxy=None,
        max_video_height=1080,
        concurrency=1,
        log_level="INFO",
        auto_restart_hours=0,
    )


def _setup(tmp_path: Path, fake_download):
    settings = _settings(tmp_path)
    session = MockedSession()
    bot = Bot("123456:ABCDEFghijklmnopqrstuvwxyz", session=session, default=DefaultBotProperties(parse_mode="HTML"))
    service = DownloadService(settings)
    service.download = fake_download  # type: ignore[method-assign]
    dp = Dispatcher()
    dp.include_router(build_router(settings, service, TelegramSender(bot)))
    dp.include_router(build_public_router(settings))
    return dp, bot, session


def _text_update(text: str, user_id: int = ALLOWED) -> Update:
    return Update(update_id=1, message=_msg(10, text, user_id))


def _sample(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x00" * 2048)
    return p


def test_stranger_is_ignored(tmp_path):
    async def fake(req, workdir):
        raise AssertionError("не должно вызываться")

    dp, bot, session = _setup(tmp_path, fake)
    result = asyncio.run(dp.feed_update(bot, _text_update("https://youtu.be/dQw4w9WgXcQ", STRANGER)))
    assert result is UNHANDLED
    assert session.requests == []


def test_stranger_gets_only_their_id_on_start(tmp_path):
    async def fake(req, workdir):
        raise AssertionError("не должно вызываться")

    dp, bot, session = _setup(tmp_path, fake)
    asyncio.run(dp.feed_update(bot, _text_update("/start", STRANGER)))
    assert len(session.requests) == 1 and isinstance(session.requests[0], SendMessage)
    assert f"<code>{STRANGER}</code>" in session.requests[0].text
    assert "Кинь ссылку" not in session.requests[0].text


def test_allowed_user_start_shows_help_and_id(tmp_path):
    async def fake(req, workdir):
        raise AssertionError("не должно вызываться")

    dp, bot, session = _setup(tmp_path, fake)
    asyncio.run(dp.feed_update(bot, _text_update("/start", ALLOWED)))
    assert len(session.requests) == 1
    assert "Кинь ссылку" in session.requests[0].text and f"<code>{ALLOWED}</code>" in session.requests[0].text


def test_youtube_video_flow_sends_video_with_audio_button(tmp_path):
    seen = {}

    async def fake(req, workdir):
        seen["req"] = req
        seen["workdir"] = workdir
        assert workdir.is_dir()
        video = _sample(workdir, "v.mp4")
        item = MediaItem(path=video, kind="video", width=640, height=360, duration=4)
        return DownloadResult(items=[item], source_url=req.url, title="Заголовок", author="Канал")

    dp, bot, session = _setup(tmp_path, fake)
    asyncio.run(dp.feed_update(bot, _text_update("глянь https://youtu.be/dQw4w9WgXcQ?si=x")))

    assert seen["req"].url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert not seen["workdir"].exists(), "временная папка должна удаляться"

    kinds = [type(r) for r in session.requests]
    assert kinds[0] is SendMessage  # «⏳ Качаю…»
    assert kinds[-1] is DeleteMessage
    send_video = next(r for r in session.requests if isinstance(r, SendVideo))
    assert send_video.width == 640 and send_video.height == 360 and send_video.duration == 4
    assert send_video.supports_streaming is True
    assert send_video.reply_to_message_id == 10
    assert "<b>Заголовок</b>" in send_video.caption and "YouTube</a>" in send_video.caption
    assert send_video.reply_markup.inline_keyboard[0][0].callback_data == "audio:dQw4w9WgXcQ"
    assert any(isinstance(r, EditMessageText) and "Отправляю" in r.text for r in session.requests)


def test_instagram_carousel_goes_in_albums_of_ten(tmp_path):
    async def fake(req, workdir):
        items = [MediaItem(path=_sample(workdir, f"{i:03}.jpg"), kind="photo") for i in range(12)]
        items.append(MediaItem(path=_sample(workdir, "013.mp4"), kind="video", width=1, height=1, duration=1))
        return DownloadResult(items=items, source_url=req.url, text="подпись", author="@user")

    dp, bot, session = _setup(tmp_path, fake)
    asyncio.run(dp.feed_update(bot, _text_update("https://www.instagram.com/p/C1a2B3c4D5e/?igsh=1")))

    groups = [r for r in session.requests if isinstance(r, SendMediaGroup)]
    assert [len(g.media) for g in groups] == [10, 3]
    assert groups[0].media[0].caption and "подпись" in groups[0].media[0].caption
    assert all(not m.caption for m in groups[0].media[1:]) and all(not m.caption for m in groups[1].media)
    assert groups[1].media[-1].supports_streaming is True


def test_audio_button_callback(tmp_path):
    async def fake(req, workdir):
        assert req.audio and req.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        item = MediaItem(path=_sample(workdir, "a.m4a"), kind="audio", duration=3, title="Трек", performer="Кто-то")
        return DownloadResult(items=[item], source_url=req.url, title="Трек")

    dp, bot, session = _setup(tmp_path, fake)
    cb = CallbackQuery(
        id="1",
        from_user=User(id=ALLOWED, is_bot=False, first_name="u"),
        chat_instance="ci",
        data="audio:dQw4w9WgXcQ",
        message=_msg(55),
    )
    asyncio.run(dp.feed_update(bot, Update(update_id=2, callback_query=cb)))

    assert isinstance(session.requests[0], AnswerCallbackQuery)
    audio = next(r for r in session.requests if isinstance(r, SendAudio))
    assert audio.title == "Трек" and audio.performer == "Кто-то" and audio.duration == 3
    assert audio.audio.filename == "Трек.m4a"


def test_download_error_is_shown_to_user(tmp_path):
    async def fake(req, workdir):
        raise DownloadError("нет такого видео <x> & y")

    dp, bot, session = _setup(tmp_path, fake)
    asyncio.run(dp.feed_update(bot, _text_update("https://youtu.be/dQw4w9WgXcQ")))
    edits = [r for r in session.requests if isinstance(r, EditMessageText)]
    assert edits and edits[-1].text == "❌ нет такого видео &lt;x&gt; &amp; y"
    assert not any(isinstance(r, (SendVideo, DeleteMessage)) for r in session.requests)


def test_no_link_gets_hint(tmp_path):
    async def fake(req, workdir):
        raise AssertionError("не должно вызываться")

    dp, bot, session = _setup(tmp_path, fake)
    asyncio.run(dp.feed_update(bot, _text_update("привет")))
    assert len(session.requests) == 1 and isinstance(session.requests[0], SendMessage)
    assert "ссылки" in session.requests[0].text
    shutil.rmtree(tmp_path / "data", ignore_errors=True)
