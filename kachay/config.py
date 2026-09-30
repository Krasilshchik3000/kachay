from __future__ import annotations

import base64
import binascii
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
    auto_restart_hours: float

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

        api_base = env.get("TELEGRAM_API_BASE", "").strip() or None
        default_limit = LOCAL_API_LIMIT_MB if api_base else BOT_API_LIMIT_MB
        max_mb = _parse_int(env.get("MAX_UPLOAD_MB"), default_limit, "MAX_UPLOAD_MB")
        if max_mb <= 0:
            raise ConfigError("MAX_UPLOAD_MB должен быть больше нуля")

        download_dir = Path(env.get("DOWNLOAD_DIR", "").strip() or "./data")
        cookies_file = _resolve_cookies(env, download_dir)

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
            auto_restart_hours=_parse_float(env.get("AUTO_RESTART_HOURS"), 24.0, "AUTO_RESTART_HOURS"),
        )


def _resolve_cookies(env: Mapping[str, str], download_dir: Path) -> Path | None:
    """COOKIES_FILE (путь) → COOKIES_B64 (base64 содержимого) → COOKIES_TXT (содержимое как есть).

    Варианты с содержимым нужны для хостингов без файловой системы под рукой (Railway и т.п.):
    файл пишется в DOWNLOAD_DIR при старте."""
    raw_path = env.get("COOKIES_FILE", "").strip()
    if raw_path:
        path = Path(raw_path)
        if path.is_file():
            return path
        log.warning("COOKIES_FILE=%s не найден, смотрю COOKIES_B64 / COOKIES_TXT.", path)

    content: str | None = None
    b64 = env.get("COOKIES_B64", "").strip()
    if b64:
        try:
            content = base64.b64decode("".join(b64.split()), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ConfigError(f"COOKIES_B64: не удалось раскодировать base64 ({exc})") from exc
    elif env.get("COOKIES_TXT", "").strip():
        content = env["COOKIES_TXT"]

    if content is None:
        log.warning("Cookies не заданы. Instagram без cookies почти всегда не работает.")
        return None

    download_dir.mkdir(parents=True, exist_ok=True)
    path = download_dir / "cookies.txt"
    path.write_text(content.replace("\r\n", "\n").rstrip("\n") + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    log.info("Cookies записаны в %s из переменной окружения", path)
    return path


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


def _parse_float(raw: str | None, default: float, name: str) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name}: «{raw}» — не число") from exc
    if value < 0:
        raise ConfigError(f"{name} не может быть отрицательным")
    return value


def _parse_int(raw: str | None, default: int, name: str) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name}: «{raw}» — не число") from exc
