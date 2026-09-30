import json

from kachay.downloaders.base import LoginRequiredError
from kachay.downloaders.instagram import classify_error, collect_files, read_metadata


def test_collect_files_keeps_carousel_order_and_skips_sidecars(tmp_path):
    for name in ("002_b.mp4", "001_a.jpg", "003_c.jpg", "001_a.jpg.json", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in collect_files(tmp_path)] == ["001_a.jpg", "002_b.mp4", "003_c.jpg"]
    assert collect_files(tmp_path / "missing") == []


def test_read_metadata_uses_first_readable_sidecar(tmp_path):
    a = tmp_path / "001_a.jpg"
    b = tmp_path / "002_b.jpg"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    (tmp_path / "001_a.jpg.json").write_text("{broken", "utf-8")
    (tmp_path / "002_b.jpg.json").write_text(json.dumps({"description": "hi", "username": "u"}), "utf-8")
    assert read_metadata([a, b]) == {"description": "hi", "username": "u"}
    assert read_metadata([a]) == {}


def test_classify_error():
    assert isinstance(classify_error("[instagram][error] 401 Unauthorized: login required"), LoginRequiredError)
    assert "429" in str(classify_error("HTTP 429 Too Many Requests"))
    assert "404" in str(classify_error("[instagram][error] HttpError: '404 Not Found'"))
    assert "без подробностей" in str(classify_error(""))
