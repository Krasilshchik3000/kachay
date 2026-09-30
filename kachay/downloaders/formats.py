"""Выбор форматов yt-dlp под лимит размера. Чистые функции — без сети."""

from __future__ import annotations

from typing import Any

from .base import TooLargeError, format_mb

Format = dict[str, Any]


def format_size(f: Format) -> int | None:
    size = f.get("filesize") or f.get("filesize_approx")
    return int(size) if size else None


def _has_video(f: Format) -> bool:
    return f.get("vcodec") not in (None, "none") and f.get("ext") != "mhtml"


def _has_audio(f: Format) -> bool:
    return f.get("acodec") not in (None, "none")


def _is_h264_mp4(f: Format) -> bool:
    vcodec = (f.get("vcodec") or "").lower()
    return f.get("ext") == "mp4" and vcodec.startswith(("avc1", "h264"))


def _video_key(f: Format) -> tuple:
    # Выше — лучше. H.264 в mp4 играет везде (в т.ч. в Telegram на iOS), поэтому он в приоритете.
    return (f.get("height") or 0, _is_h264_mp4(f), f.get("tbr") or f.get("vbr") or 0)


def _audio_key(f: Format) -> tuple:
    fid = str(f.get("format_id") or "")
    return (f.get("ext") == "m4a", not fid.endswith("-drc"), f.get("abr") or f.get("tbr") or 0)


def _prefer(candidates: list[Format], pred) -> list[Format]:
    preferred = [f for f in candidates if pred(f)]
    return preferred or candidates


def pick_video_spec(formats: list[Format], limit: int, max_height: int = 1080) -> str | None:
    """Возвращает format spec для yt-dlp ("137+140" или "18").

    None — если у форматов нет данных о размере (тогда вызывающий код берёт запасной spec).
    TooLargeError — если даже самый маленький вариант не влезает в лимит.
    """
    video_only = [
        f for f in formats
        if _has_video(f) and not _has_audio(f) and f.get("height") and f["height"] <= max_height
    ]
    audio_only = [f for f in formats if _has_audio(f) and not _has_video(f)]
    progressive = [
        f for f in formats
        if _has_video(f) and _has_audio(f) and (not f.get("height") or f["height"] <= max_height)
    ]

    video_only = _prefer(video_only, _is_h264_mp4)
    audio_only = _prefer(audio_only, lambda f: f.get("ext") == "m4a")

    videos = sorted(video_only, key=_video_key, reverse=True)
    audios = sorted(audio_only, key=_audio_key, reverse=True)
    progressives = sorted(progressive, key=_video_key, reverse=True)

    sizes_known = False
    smallest: int | None = None

    for v in videos:
        vs = format_size(v)
        if vs is None:
            continue
        for a in audios:
            as_ = format_size(a)
            if as_ is None:
                continue
            sizes_known = True
            total = vs + as_
            smallest = total if smallest is None else min(smallest, total)
            if total <= limit:
                return f"{v['format_id']}+{a['format_id']}"

    for p in progressives:
        ps = format_size(p)
        if ps is None:
            continue
        sizes_known = True
        smallest = ps if smallest is None else min(smallest, ps)
        if ps <= limit:
            return str(p["format_id"])

    if not sizes_known:
        return None
    raise TooLargeError(
        f"Даже самый маленький вариант видео весит {format_mb(smallest or 0)}, "
        f"а лимит — {format_mb(limit)}. Подними локальный Bot API сервер (см. README) "
        "или попроси «аудио»."
    )


def pick_audio_spec(formats: list[Format], limit: int) -> str | None:
    audio_only = _prefer(
        [f for f in formats if _has_audio(f) and not _has_video(f)],
        lambda f: f.get("ext") == "m4a",
    )
    audios = sorted(audio_only, key=_audio_key, reverse=True)
    smallest: int | None = None
    for a in audios:
        size = format_size(a)
        if size is None:
            continue
        smallest = size if smallest is None else min(smallest, size)
        if size <= limit:
            return str(a["format_id"])
    if smallest is None:
        return None
    raise TooLargeError(
        f"Аудио весит минимум {format_mb(smallest)}, а лимит — {format_mb(limit)}. "
        "Подними локальный Bot API сервер (см. README)."
    )
