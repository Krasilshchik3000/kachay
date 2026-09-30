"""Оркестрация: запрос → загрузчик → результат. Временная папка на каждый запрос."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from .config import Settings
from .downloaders import DownloadResult, InstagramDownloader, YtDlpDownloader
from .links import Kind, LinkRequest

log = logging.getLogger(__name__)


class DownloadService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ytdlp = YtDlpDownloader(settings)
        self.instagram = InstagramDownloader(settings, self.ytdlp)
        self.semaphore = asyncio.Semaphore(settings.concurrency)
        settings.download_dir.mkdir(parents=True, exist_ok=True)

    @contextlib.asynccontextmanager
    async def workdir(self) -> AsyncIterator[Path]:
        path = Path(tempfile.mkdtemp(prefix="job-", dir=self.settings.download_dir)).resolve()
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def _cookies_copy(self, workdir: Path) -> Path | None:
        """yt-dlp и gallery-dl пишут cookies обратно в файл. Даём им копию: оригинал не трогаем,
        параллельные запросы не мешают друг другу, read-only монтирование не ломает загрузку."""
        src = self.settings.cookies_file
        if not src or not src.is_file():
            return None
        dst = workdir / "cookies.txt"
        shutil.copyfile(src, dst)
        return dst

    async def download(self, req: LinkRequest, workdir: Path) -> DownloadResult:
        limit = self.settings.max_upload_bytes
        cookies = self._cookies_copy(workdir)
        if req.audio:
            return await self.ytdlp.download_audio(req.url, workdir, limit, cookies=cookies)
        if req.kind is Kind.INSTAGRAM:
            return await self.instagram.download(req.url, workdir, limit, cookies=cookies)
        return await self.ytdlp.download_video(
            req.url, workdir, limit, youtube=req.kind is Kind.YOUTUBE, cookies=cookies
        )
