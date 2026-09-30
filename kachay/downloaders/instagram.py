"""Instagram: посты, карусели, reels, stories — через gallery-dl, с запасным yt-dlp."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from ..config import MB, Settings
from ..media import probe, run, shrink_video
from .base import (
    PHOTO_EXTS,
    VIDEO_EXTS,
    DownloadError,
    DownloadResult,
    LoginRequiredError,
    MediaItem,
    TooLargeError,
    format_mb,
    photo_item,
    video_item,
)
from .ytdlp import YtDlpDownloader

log = logging.getLogger(__name__)

GALLERY_DL_TIMEOUT = 900
FILENAME_FMT = "{num:>03}_{media_id}.{extension}"


class InstagramDownloader:
    def __init__(self, settings: Settings, ytdlp: YtDlpDownloader) -> None:
        self.settings = settings
        self.ytdlp = ytdlp

    async def download(
        self, url: str, workdir: Path, limit: int, *, cookies: Path | None = None
    ) -> DownloadResult:
        out = workdir / "ig"
        out.mkdir(parents=True, exist_ok=True)
        rc, stdout, stderr = await self._run_gallery_dl(url, out, cookies)
        files = collect_files(out)

        if not files:
            log.warning("gallery-dl rc=%s, файлов нет. stderr: %s", rc, stderr.strip()[-800:])
            primary = classify_error(stderr)
            # Для видео/reels yt-dlp иногда справляется там, где gallery-dl нет.
            try:
                return await self.ytdlp.download_video(url, workdir, limit, youtube=False, cookies=cookies)
            except DownloadError as exc:
                log.warning("yt-dlp fallback тоже не смог: %s", exc)
                raise primary from exc

        meta = read_metadata(files)
        items: list[MediaItem] = []
        for path in files:
            if path.suffix.lower() in VIDEO_EXTS:
                path = await self._fit_video(path, limit)
                items.append(await video_item(path))
            else:
                items.append(await photo_item(path))

        author = meta.get("username")
        return DownloadResult(
            items=items,
            source_url=meta.get("post_url") or url,
            text=meta.get("description") or None,
            author=f"@{author}" if author else None,
        )

    async def _run_gallery_dl(self, url: str, out: Path, cookies: Path | None) -> tuple[int, str, str]:
        cmd = [
            sys.executable, "-m", "gallery_dl",
            "--config-ignore",
            "--no-input",
            "-D", str(out),
            "-f", FILENAME_FMT,
            "--write-metadata",
        ]
        if cookies:
            cmd += ["--cookies", str(cookies)]
        if self.settings.proxy:
            cmd += ["--proxy", self.settings.proxy]
        cmd.append(url)
        log.info("gallery-dl %s", url)
        try:
            return await run(cmd, timeout=GALLERY_DL_TIMEOUT)
        except TimeoutError as exc:
            raise DownloadError("gallery-dl не уложился в 15 минут") from exc
        except OSError as exc:
            raise DownloadError(f"gallery-dl не запустился: {exc}") from exc

    async def _fit_video(self, path: Path, limit: int) -> Path:
        size = path.stat().st_size
        if size <= limit:
            return path
        log.info("Видео %s весит %s > лимита, перекодирую", path.name, format_mb(size))
        info = await probe(path)
        dst = path.with_name(path.stem + ".small.mp4")
        result = await shrink_video(path, dst, limit, info.duration)
        if not result or result.stat().st_size > limit:
            raise TooLargeError(
                f"Видео весит {format_mb(size)}, ужать под лимит {format_mb(limit)} не вышло. "
                "Подними локальный Bot API сервер (см. README)."
            )
        path.unlink(missing_ok=True)
        return result


def collect_files(out: Path) -> list[Path]:
    """Медиафайлы в порядке карусели (имя начинается с номера)."""
    if not out.is_dir():
        return []
    files = [
        p for p in out.iterdir()
        if p.is_file() and p.suffix.lower() in (PHOTO_EXTS | VIDEO_EXTS)
    ]
    return sorted(files, key=lambda p: p.name)


def read_metadata(files: list[Path]) -> dict:
    """gallery-dl --write-metadata кладёт рядом <file>.json; берём первый читаемый."""
    for path in files:
        sidecar = path.with_name(path.name + ".json")
        if not sidecar.is_file():
            continue
        try:
            data = json.loads(sidecar.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def classify_error(stderr: str) -> DownloadError:
    low = stderr.lower()
    if "sessionid" in low or "login" in low or "401" in low or "authentication" in low or "unauthorized" in low:
        return LoginRequiredError(
            "Instagram требует логин. Положи свежий cookies.txt из браузера, "
            "где ты залогинен в Instagram, в COOKIES_FILE (см. README)."
        )
    if "429" in low or "rate limit" in low or "rate-limit" in low:
        return DownloadError("Instagram ограничил запросы (429). Подожди немного и попробуй снова.")
    if "404" in low or "not found" in low:
        return DownloadError("Instagram отвечает 404: пост удалён, приватный или ссылка битая.")
    tail = stderr.strip().splitlines()[-1] if stderr.strip() else "без подробностей"
    return DownloadError(f"gallery-dl не смог скачать: {tail[:300]}")


__all__ = ["InstagramDownloader", "collect_files", "read_metadata", "classify_error", "MB"]
