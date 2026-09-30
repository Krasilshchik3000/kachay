from pathlib import Path

from kachay.config import MB, Settings
from kachay.downloaders.ytdlp import YtDlpDownloader


def _settings(tmp_path, **over):
    base = dict(
        bot_token="x", allowed_user_ids=frozenset({1}), cookies_file=None, download_dir=tmp_path,
        max_upload_bytes=50 * MB, telegram_api_base=None, js_runtime="deno", pot_provider_url=None,
        youtube_clients=(), proxy=None, max_video_height=1080, concurrency=1, log_level="INFO",
        auto_restart_hours=0,
    )
    base.update(over)
    return Settings(**base)


def test_extractor_args_built_from_settings(tmp_path):
    d = YtDlpDownloader(_settings(tmp_path, pot_provider_url="http://pot:4416", youtube_clients=("tv", "web")))
    opts = d._base_opts(tmp_path, cookies=Path("/c.txt"))
    assert opts["extractor_args"] == {
        "youtubepot-bgutilhttp": {"base_url": ["http://pot:4416"]},
        "youtube": {"player_client": ["tv", "web"]},
    }
    assert opts["cookiefile"] == "/c.txt"
    assert opts["js_runtimes"] == {"deno": {}}


def test_no_extractor_args_by_default(tmp_path):
    opts = YtDlpDownloader(_settings(tmp_path))._base_opts(tmp_path, cookies=None)
    assert "extractor_args" not in opts and "cookiefile" not in opts
