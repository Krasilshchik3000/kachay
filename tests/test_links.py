from kachay.links import Kind, extract_url, parse_message, youtube_id_from_url


def test_youtube_watch_with_junk_params():
    req = parse_message("смотри https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLx&t=42s")
    assert req is not None
    assert req.kind is Kind.YOUTUBE
    assert req.youtube_id == "dQw4w9WgXcQ"
    assert req.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert not req.audio and not req.as_file


def test_youtu_be_and_shorts_and_music():
    assert youtube_id_from_url("https://youtu.be/dQw4w9WgXcQ?si=abc") == "dQw4w9WgXcQ"
    assert youtube_id_from_url("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_id_from_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_id_from_url("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share") == "dQw4w9WgXcQ"
    req = parse_message("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
    assert req is not None and req.kind is Kind.YOUTUBE and req.audio


def test_youtube_channel_url_is_not_a_video():
    assert youtube_id_from_url("https://www.youtube.com/@someone") is None
    req = parse_message("https://www.youtube.com/@someone")
    assert req is not None and req.kind is Kind.OTHER


def test_instagram_variants_are_cleaned():
    cases = {
        "https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=MTIzNDU2": "https://www.instagram.com/reel/C1a2B3c4D5e/",
        "https://instagram.com/p/C1a2B3c4D5e": "https://www.instagram.com/p/C1a2B3c4D5e/",
        "https://www.instagram.com/someuser/reel/C1a2B3c4D5e/": "https://www.instagram.com/someuser/reel/C1a2B3c4D5e/",
        "https://www.instagram.com/share/reel/BAxyz123": "https://www.instagram.com/share/reel/BAxyz123/",
        "https://www.instagram.com/stories/someuser/3141592653589/?utm_source=ig": "https://www.instagram.com/stories/someuser/3141592653589/",
    }
    for raw, cleaned in cases.items():
        req = parse_message(raw)
        assert req is not None, raw
        assert req.kind is Kind.INSTAGRAM, raw
        assert req.url == cleaned, raw


def test_instagram_profile_is_not_a_post():
    req = parse_message("https://www.instagram.com/someuser/")
    assert req is not None and req.kind is Kind.OTHER


def test_keywords_ru_and_en():
    assert parse_message("аудио https://youtu.be/dQw4w9WgXcQ").audio
    assert parse_message("https://youtu.be/dQw4w9WgXcQ mp3").audio
    assert parse_message("файл https://www.instagram.com/p/C1a2B3c4D5e/").as_file
    assert parse_message("https://www.instagram.com/p/C1a2B3c4D5e/ file").as_file
    # слова внутри самой ссылки не считаются
    assert not parse_message("https://example.com/audio/file.mp4").audio
    assert not parse_message("https://example.com/audio/file.mp4").as_file


def test_trailing_punctuation_and_no_url():
    assert extract_url("вот (https://youtu.be/dQw4w9WgXcQ).") == "https://youtu.be/dQw4w9WgXcQ"
    assert parse_message("просто текст без ссылки") is None
    assert extract_url("") is None
