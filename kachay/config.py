from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MB = 1024 * 1024
BOT_API_LIMIT_MB = 50  # обычный api.telegram.org
LOCAL_API_LIMIT_MB = 2000  # локальный telegram-bot-api сервер


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_user_ids: frozenset[int]
    cookies_file: Path | None
    download_dir: Path
    max_upload_bytes: int
    telegram_api_base: str | None
    js_runtime: str
    pot_provider_url: str | None
    proxy: str | None
    max_video_height: int
    concurrency: int
    log_level: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        token = env.get("BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError("BOT_TOKEN не задан")

        allowed = _parse_ids(env.get("ALLOWED_USER_IDS", ""))
        if not allowed:
            raise ConfigError(
                "ALLOWED_USER_IDS не задан. Бот без белого списка не запускается: "
                "иначе им сможет пользоваться кто угодно."
            )

        cookies_file: Path | None = None
        raw_cookies = env.get("COOKIES_FILE", "").strip()
        if raw_cookies:
            cookies_file = Path(raw_cookies)
            if not cookies_file.is_file():
                log.warning(
                    "COOKIES_FILE=%s не найден. Instagram без cookies почти всегда не работает.",
                    cookies_file,
                )
                cookies_file = None

        api_base = env.get("TELEGRAM_API_BASE", "").strip() or None
        default_limit = LOCAL_API_LIMIT_MB if api_base else BOT_API_LIMIT_MB
        max_mb = _parse_int(env.get("MAX_UPLOAD_MB"), default_limit, "MAX_UPLOAD_MB")
        if max_mb <= 0:
            raise ConfigError("MAX_UPLOAD_MB должен быть больше нуля")

        download_dir = Path(env.get("DOWNLOAD_DIR", "").strip() or "./data")

        return cls(
            bot_token=token,
            allowed_user_ids=allowed,
            cookies_file=cookies_file,
            download_dir=download_dir,
            max_upload_bytes=max_mb * MB,
            telegram_api_base=api_base,
            js_runtime=env.get("YTDLP_JS_RUNTIME", "").strip() or "deno",
            pot_provider_url=env.get("YTDLP_POT_PROVIDER_URL", "").strip() or None,
            proxy=env.get("DOWNLOAD_PROXY", "").strip() or None,
            max_video_height=_parse_int(env.get("MAX_VIDEO_HEIGHT"), 1080, "MAX_VIDEO_HEIGHT"),
            concurrency=max(1, _parse_int(env.get("CONCURRENCY"), 2, "CONCURRENCY")),
            log_level=env.get("LOG_LEVEL", "").strip().upper() or "INFO",
        )


def _parse_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError as exc:
            raise ConfigError(f"ALLOWED_USER_IDS: «{part}» — не число") from exc
    return frozenset(ids)


def _parse_int(raw: str | None, default: int, name: str) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name}: «{raw}» — не число") from exc
