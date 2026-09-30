"""YouTube и всё, что умеет yt-dlp."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpError

from ..config import Settings
from ..media import make_thumbnail, probe
from .base import (
    AUDIO_EXTS,
    VIDEO_EXTS,
    DownloadError,
    DownloadResult,
    LoginRequiredError,
    MediaItem,
    check_size,
    video_item,
)
from .formats import pick_audio_spec, pick_video_spec

log = logging.getLogger(__name__)

# Запасные spec'и, когда размеры форматов неизвестны (не-YouTube сайты, трансляции).
FALLBACK_VIDEO_SPEC = "bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/bv*+ba/b"
FALLBACK_AUDIO_SPEC = "ba[ext=m4a]/ba/b"


class _YdlLogger:
    """Перенаправляет вывод yt-dlp в logging."""

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            log.debug(msg)
        else:
            log.info(msg)

    def info(self, msg: str) -> None:
        log.info(msg)

    def warning(self, msg: str) -> None:
        log.warning(msg)

    def error(self, msg: str) -> None:
        log.error(msg)


class YtDlpDownloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ---------- публичное API (async) ----------

    async def download_video(
        self, url: str, workdir: Path, limit: int, *, youtube: bool, cookies: Path | None = None
    ) -> DownloadResult:
        info, path = await asyncio.to_thread(self._download_video_sync, url, workdir, limit, youtube, cookies)
        check_size(path, limit, "Видео")
        item = await video_item(path, title=info.get("title"))
        return DownloadResult(
            items=[item],
            source_url=info.get("webpage_url") or url,
            title=info.get("title"),
            author=info.get("channel") or info.get("uploader"),
        )

    async def download_audio(
        self, url: str, workdir: Path, limit: int, *, cookies: Path | None = None
    ) -> DownloadResult:
        info, path = await asyncio.to_thread(self._download_audio_sync, url, workdir, limit, cookies)
        check_size(path, limit, "Аудио")
        thumb: Path | None = None
        raw_thumb = _find_file(workdir, info.get("id"), {".jpg", ".jpeg", ".png", ".webp"})
        if raw_thumb:
            thumb = await make_thumbnail(raw_thumb, workdir / "audio.thumb.jpg", is_video=False)
        duration = info.get("duration")
        if not duration:
            duration = (await probe(path)).duration
        item = MediaItem(
            path=path,
            kind="audio",
            duration=int(duration) if duration else None,
            thumbnail=thumb,
            title=info.get("track") or info.get("title"),
            performer=info.get("artist") or info.get("channel") or info.get("uploader"),
        )
        return DownloadResult(
            items=[item],
            source_url=info.get("webpage_url") or url,
            title=info.get("title"),
            author=info.get("channel") or info.get("uploader"),
        )

    # ---------- внутренности (sync, крутятся в thread pool) ----------

    def _base_opts(self, workdir: Path, cookies: Path | None) -> dict[str, Any]:
        s = self.settings
        opts: dict[str, Any] = {
            "logger": _YdlLogger(),
            "quiet": True,
            "noprogress": True,
            "noplaylist": True,
            "playlist_items": "1",
            "outtmpl": str(workdir / "%(id)s.%(ext)s"),
            "restrictfilenames": True,
            "overwrites": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "js_runtimes": {s.js_runtime: {}},
        }
        if cookies:
            opts["cookiefile"] = str(cookies)
        if s.proxy:
            opts["proxy"] = s.proxy
        if s.pot_provider_url:
            opts["extractor_args"] = {"youtubepot-bgutilhttp": {"base_url": [s.pot_provider_url]}}
        return opts

    def _probe(self, url: str, opts: dict[str, Any]) -> dict[str, Any]:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return _first_entry(info)

    def _download_with_info(self, info: dict[str, Any], url: str, opts: dict[str, Any]) -> dict[str, Any]:
        """Качает по уже полученному info (без повторного захода на сайт), с запасным полным путём."""
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                clean = ydl.sanitize_info(info, remove_private_keys=True)
                result = ydl.process_ie_result(dict(clean), download=True)
                if result and (result.get("requested_downloads") or result.get("filepath")):
                    return _first_entry(result)
            except YtDlpError:
                raise
            except Exception:
                log.exception("process_ie_result не сработал, качаю заново полным циклом")
            return _first_entry(ydl.extract_info(url, download=True))

    def _download_video_sync(
        self, url: str, workdir: Path, limit: int, youtube: bool, cookies: Path | None
    ) -> tuple[dict, Path]:
        opts = self._base_opts(workdir, cookies)
        opts["merge_output_format"] = "mp4"
        try:
            info = self._probe(url, opts)
            spec = pick_video_spec(info.get("formats") or [], limit, self.settings.max_video_height)
            opts["format"] = spec or FALLBACK_VIDEO_SPEC
            log.info("yt-dlp format=%s for %s", opts["format"], url)
            info = self._download_with_info(info, url, opts)
        except YtDlpError as exc:
            raise _translate(exc) from exc
        path = _output_path(info, workdir, VIDEO_EXTS)
        return info, path

    def _download_audio_sync(
        self, url: str, workdir: Path, limit: int, cookies: Path | None
    ) -> tuple[dict, Path]:
        opts = self._base_opts(workdir, cookies)
        opts.update(
            {
                "writethumbnail": True,
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
                    {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
                ],
            }
        )
        try:
            info = self._probe(url, opts)
            spec = pick_audio_spec(info.get("formats") or [], limit)
            opts["format"] = spec or FALLBACK_AUDIO_SPEC
            log.info("yt-dlp audio format=%s for %s", opts["format"], url)
            info = self._download_with_info(info, url, opts)
        except YtDlpError as exc:
            raise _translate(exc) from exc
        path = _output_path(info, workdir, AUDIO_EXTS | {".m4a"})
        return info, path


def _first_entry(info: dict[str, Any] | None) -> dict[str, Any]:
    if not info:
        raise DownloadError("yt-dlp ничего не вернул по этой ссылке")
    if info.get("_type") == "playlist" or "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise DownloadError("По ссылке нашёлся плейлист без доступных видео")
        return entries[0]
    return info


def _find_file(workdir: Path, stem: str | None, exts: set[str] | frozenset[str]) -> Path | None:
    if not stem:
        return None
    for p in sorted(workdir.iterdir()):
        if p.is_file() and p.suffix.lower() in exts and p.stem == stem:
            return p
    return None


def _output_path(info: dict[str, Any], workdir: Path, exts: frozenset[str] | set[str]) -> Path:
    for d in info.get("requested_downloads") or []:
        fp = d.get("filepath")
        if fp and Path(fp).is_file():
            return Path(fp)
    fp = info.get("filepath")
    if fp and Path(fp).is_file():
        return Path(fp)
    found = _find_file(workdir, info.get("id"), exts)
    if found:
        return found
    candidates = [p for p in workdir.iterdir() if p.is_file() and p.suffix.lower() in exts]
    if len(candidates) == 1:
        return candidates[0]
    raise DownloadError("yt-dlp отработал, но файла на диске нет")


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _translate(exc: YtDlpError) -> DownloadError:
    msg = _ANSI_RE.sub("", str(exc))
    msg = re.sub(r"^\s*ERROR:\s*", "", msg).strip()
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return LoginRequiredError(
            "YouTube просит подтвердить, что ты не бот. Нужны cookies от YouTube "
            "в COOKIES_FILE или сервер PO-токенов (см. README)."
        )
    if "login" in low and ("required" in low or "cookies" in low):
        return LoginRequiredError(
            "Сайт требует логин. Положи свежий cookies.txt в COOKIES_FILE (см. README)."
        )
    if "unsupported url" in low:
        return DownloadError("Эту ссылку yt-dlp не понимает.")
    if "private video" in low:
        return DownloadError("Видео приватное.")
    if "requested format is not available" in low:
        return DownloadError("У видео нет подходящего формата (mp4/h264).")
    if "video unavailable" in low or "not available" in low:
        return DownloadError("Видео недоступно (удалено, ограничено по региону или возрасту).")
    if "javascript runtime" in low or "js runtime" in low or "ejs" in low:
        return DownloadError("yt-dlp не нашёл JS-рантайм (deno). Проверь установку (см. README).")
    return DownloadError(f"yt-dlp: {msg[:400]}")
