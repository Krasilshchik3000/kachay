from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from . import __version__
from .bot import build_public_router, build_router
from .config import ConfigError, Settings
from .sender import TelegramSender
from .service import DownloadService

log = logging.getLogger("kachay")


def _check_tools(settings: Settings) -> None:
    import gallery_dl.version
    import yt_dlp.version

    log.info(
        "kachay %s, yt-dlp %s, gallery-dl %s",
        __version__, yt_dlp.version.__version__, gallery_dl.version.__version__,
    )
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            log.error("%s не найден в PATH — видео и превью работать не будут", tool)
    if not shutil.which(settings.js_runtime):
        log.warning(
            "JS-рантайм «%s» не найден в PATH — YouTube работать не будет (см. README).",
            settings.js_runtime,
        )
    if settings.cookies_file is None:
        log.warning("COOKIES_FILE не задан: Instagram, скорее всего, будет требовать логин.")
    log.info(
        "Лимит отправки %d МБ, API: %s, разрешённые user id: %s",
        settings.max_upload_bytes // (1024 * 1024),
        settings.telegram_api_base or "api.telegram.org",
        sorted(settings.allowed_user_ids),
    )


async def auto_restart(dp: Dispatcher, service: DownloadService, after_seconds: float, poll: float = 30.0) -> None:
    """Через after_seconds дожидается, пока не останется активных загрузок, и останавливает polling.

    Процесс завершается с кодом 0; Docker (restart: unless-stopped) и Railway (restartPolicy ALWAYS)
    поднимают его заново, а entrypoint при старте обновляет yt-dlp и gallery-dl."""
    await asyncio.sleep(after_seconds)
    while service.active_jobs > 0:
        await asyncio.sleep(poll)
    log.info("Плановый перезапуск: останавливаюсь, чтобы обновить yt-dlp при старте")
    try:
        await dp.stop_polling()
    except RuntimeError as exc:  # polling уже не идёт — останавливать нечего
        log.warning("stop_polling: %s", exc)


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        sys.exit(2)

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,  # иначе хостинги (Railway) показывают каждую строку как error
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    _check_tools(settings)

    session = None
    if settings.telegram_api_base:
        session = AiohttpSession(api=TelegramAPIServer.from_base(settings.telegram_api_base, is_local=True))

    bot = Bot(settings.bot_token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    service = DownloadService(settings)
    sender = TelegramSender(bot)

    dp = Dispatcher()
    dp.include_router(build_router(settings, service, sender))
    dp.include_router(build_public_router(settings))

    if settings.auto_restart_hours > 0:
        restart_task: list[asyncio.Task] = []

        @dp.startup()
        async def schedule_restart() -> None:
            restart_task.append(asyncio.create_task(auto_restart(dp, service, settings.auto_restart_hours * 3600)))
            log.info("Плановый перезапуск через %.1f ч (AUTO_RESTART_HOURS)", settings.auto_restart_hours)

        @dp.shutdown()
        async def cancel_restart() -> None:
            for task in restart_task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    dp.run_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
