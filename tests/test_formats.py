import pytest

from kachay.downloaders.base import TooLargeError
from kachay.downloaders.formats import pick_audio_spec, pick_video_spec

MB = 1024 * 1024


def f(fid, *, ext, vcodec, acodec, height=None, size=None, abr=None, tbr=None):
    d = {"format_id": fid, "ext": ext, "vcodec": vcodec, "acodec": acodec}
    if height is not None:
        d["height"] = height
    if size is not None:
        d["filesize"] = size
    if abr is not None:
        d["abr"] = abr
    if tbr is not None:
        d["tbr"] = tbr
    return d


YOUTUBE = [
    f("sb0", ext="mhtml", vcodec="none", acodec="none"),  # storyboard
    f("137", ext="mp4", vcodec="avc1.640028", acodec="none", height=1080, size=80 * MB, tbr=4000),
    f("248", ext="webm", vcodec="vp9", acodec="none", height=1080, size=50 * MB, tbr=2500),
    f("136", ext="mp4", vcodec="avc1.4d401f", acodec="none", height=720, size=40 * MB, tbr=2000),
    f("135", ext="mp4", vcodec="avc1.4d401e", acodec="none", height=480, size=20 * MB, tbr=1000),
    f("18", ext="mp4", vcodec="avc1.42001E", acodec="mp4a.40.2", height=360, size=15 * MB, tbr=700),
    f("140", ext="m4a", vcodec="none", acodec="mp4a.40.2", size=8 * MB, abr=128),
    f("140-drc", ext="m4a", vcodec="none", acodec="mp4a.40.2", size=8 * MB, abr=128),
    f("251", ext="webm", vcodec="none", acodec="opus", size=7 * MB, abr=130),
]


def test_prefers_h264_mp4_over_vp9_at_same_height():
    assert pick_video_spec(YOUTUBE, 200 * MB) == "137+140"


def test_steps_down_the_ladder_to_fit_limit():
    assert pick_video_spec(YOUTUBE, 50 * MB) == "136+140"  # 48 МБ
    assert pick_video_spec(YOUTUBE, 30 * MB) == "135+140"  # 28 МБ


def test_falls_back_to_progressive_when_split_does_not_fit():
    assert pick_video_spec(YOUTUBE, 20 * MB) == "18"


def test_raises_when_nothing_fits():
    with pytest.raises(TooLargeError):
        pick_video_spec(YOUTUBE, 10 * MB)


def test_respects_max_height():
    assert pick_video_spec(YOUTUBE, 200 * MB, max_height=720) == "136+140"


def test_unknown_sizes_return_none():
    formats = [
        f("hls-1", ext="mp4", vcodec="avc1", acodec="mp4a", height=720),
        f("hls-2", ext="mp4", vcodec="avc1", acodec="mp4a", height=360),
    ]
    assert pick_video_spec(formats, 50 * MB) is None
    assert pick_audio_spec(formats, 50 * MB) is None


def test_audio_prefers_m4a_non_drc_and_respects_limit():
    assert pick_audio_spec(YOUTUBE, 100 * MB) == "140"
    with pytest.raises(TooLargeError):
        pick_audio_spec(YOUTUBE, 5 * MB)


def test_audio_falls_back_to_other_codecs_when_no_m4a():
    formats = [f("251", ext="webm", vcodec="none", acodec="opus", size=7 * MB, abr=130)]
    assert pick_audio_spec(formats, 100 * MB) == "251"
