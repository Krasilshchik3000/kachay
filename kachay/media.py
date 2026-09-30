"""Обёртки над ffmpeg/ffprobe."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

THUMB_MAX_SIDE = 320  # требование Telegram к thumbnail


@dataclass(frozen=True)
class ProbeInfo:
    width: int | None
    height: int | None
    duration: int | None


async def run(cmd: list[str], timeout: float) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


async def probe(path: Path) -> ProbeInfo:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,side_data_list:format=duration",
        "-of", "json",
        str(path),
    ]
    try:
        rc, out, err = await run(cmd, timeout=60)
    except (TimeoutError, OSError) as exc:
        log.warning("ffprobe не запустился: %s", exc)
        return ProbeInfo(None, None, None)
    if rc != 0:
        log.warning("ffprobe rc=%s: %s", rc, err.strip()[:300])
        return ProbeInfo(None, None, None)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return ProbeInfo(None, None, None)

    streams = data.get("streams") or [{}]
    stream = streams[0]
    width = stream.get("width")
    height = stream.get("height")
    # Повёрнутое видео (телефонные записи): меняем стороны местами.
    for sd in stream.get("side_data_list") or []:
        rotation = sd.get("rotation")
        if isinstance(rotation, (int, float)) and abs(rotation) % 180 == 90:
            width, height = height, width
    duration_raw = (data.get("format") or {}).get("duration")
    duration: int | None = None
    if duration_raw:
        try:
            duration = max(1, math.ceil(float(duration_raw)))
        except ValueError:
            pass
    return ProbeInfo(width, height, duration)


async def make_thumbnail(src: Path, dst: Path, *, is_video: bool) -> Path | None:
    """JPEG ≤320px по большей стороне. Для видео берём кадр на 1-й секунде, если есть."""
    scale = (
        f"scale='min({THUMB_MAX_SIDE},iw)':'min({THUMB_MAX_SIDE},ih)':force_original_aspect_ratio=decrease"
    )
    attempts = [["-ss", "1"], []] if is_video else [[]]
    for seek in attempts:
        cmd = [
            "ffmpeg", "-y", "-v", "error", *seek, "-i", str(src),
            "-frames:v", "1", "-vf", scale, "-q:v", "4", str(dst),
        ]
        try:
            rc, _, err = await run(cmd, timeout=60)
        except (TimeoutError, OSError) as exc:
            log.warning("ffmpeg thumbnail: %s", exc)
            return None
        if rc == 0 and dst.is_file() and dst.stat().st_size > 0:
            return dst
        log.debug("ffmpeg thumbnail rc=%s: %s", rc, err.strip()[:200])
    return None


async def shrink_video(src: Path, dst: Path, limit_bytes: int, duration: int | None) -> Path | None:
    """Перекодирует видео так, чтобы влезть в лимит. Возвращает None, если это бессмысленно."""
    if not duration:
        return None
    audio_kbps = 96
    total_kbps = (limit_bytes * 8 * 0.92) / duration / 1000
    video_kbps = int(total_kbps - audio_kbps)
    if video_kbps < 250:
        return None
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", f"{video_kbps}k", "-maxrate", f"{video_kbps}k", "-bufsize", f"{video_kbps * 2}k",
        "-vf", "scale=-2:'min(720,ih)'",
        "-c:a", "aac", "-b:a", f"{audio_kbps}k",
        "-movflags", "+faststart",
        str(dst),
    ]
    try:
        rc, _, err = await run(cmd, timeout=1800)
    except (TimeoutError, OSError) as exc:
        log.warning("ffmpeg shrink: %s", exc)
        return None
    if rc != 0:
        log.warning("ffmpeg shrink rc=%s: %s", rc, err.strip()[:300])
        return None
    return dst if dst.is_file() else None
