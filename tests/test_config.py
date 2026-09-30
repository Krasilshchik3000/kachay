import base64

import pytest

from kachay.config import MB, ConfigError, Settings

BASE = {"BOT_TOKEN": "123:abc", "ALLOWED_USER_IDS": "1, 2"}
COOKIES = "# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tXYZ\n"


def test_requires_token_and_whitelist(tmp_path):
    with pytest.raises(ConfigError):
        Settings.from_env({"ALLOWED_USER_IDS": "1", "DOWNLOAD_DIR": str(tmp_path)})
    with pytest.raises(ConfigError):
        Settings.from_env({"BOT_TOKEN": "x", "DOWNLOAD_DIR": str(tmp_path)})
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE, "ALLOWED_USER_IDS": "abc", "DOWNLOAD_DIR": str(tmp_path)})


def test_defaults_and_local_api_limit(tmp_path):
    s = Settings.from_env({**BASE, "DOWNLOAD_DIR": str(tmp_path)})
    assert s.allowed_user_ids == frozenset({1, 2})
    assert s.max_upload_bytes == 50 * MB
    assert s.cookies_file is None
    s = Settings.from_env({**BASE, "DOWNLOAD_DIR": str(tmp_path), "TELEGRAM_API_BASE": "http://api:8081"})
    assert s.max_upload_bytes == 2000 * MB


def test_cookies_file_wins_when_present(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text(COOKIES)
    s = Settings.from_env({**BASE, "DOWNLOAD_DIR": str(tmp_path), "COOKIES_FILE": str(f), "COOKIES_B64": "eA=="})
    assert s.cookies_file == f


def test_cookies_from_base64_env(tmp_path):
    b64 = base64.b64encode(COOKIES.encode()).decode()
    env = {**BASE, "DOWNLOAD_DIR": str(tmp_path / "data"), "COOKIES_FILE": "/nonexistent/c.txt", "COOKIES_B64": b64}
    s = Settings.from_env(env)
    assert s.cookies_file == tmp_path / "data" / "cookies.txt"
    assert s.cookies_file.read_text() == COOKIES


def test_cookies_from_plain_env_normalizes_newlines(tmp_path):
    env = {**BASE, "DOWNLOAD_DIR": str(tmp_path), "COOKIES_TXT": COOKIES.replace("\n", "\r\n")}
    s = Settings.from_env(env)
    assert s.cookies_file is not None and s.cookies_file.read_text() == COOKIES


def test_bad_base64_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE, "DOWNLOAD_DIR": str(tmp_path), "COOKIES_B64": "not base64!!"})
