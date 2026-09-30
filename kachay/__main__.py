from __future__ import annotations

import logging
import shutil
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode

from . import __version__
from .bot import build_router
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


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        sys.exit(2)

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
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
    dp.run_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
