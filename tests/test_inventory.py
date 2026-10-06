from coursera_scraper.inventory import classify, format_size, scan_downloads


def _make_course(root):
    (root / "demo" / "01-mod-a" / "01-les").mkdir(parents=True, exist_ok=True)
    (root / "demo" / "02-mod-b" / "01-les").mkdir(parents=True, exist_ok=True)
    (root / "demo" / "01-mod-a" / "01-les" / "01-x-transcript.txt").write_text("t")
    (root / "demo" / "01-mod-a" / "01-les" / "02-y-reading.txt").write_text("r")
    (root / "demo" / "01-mod-a" / "01-les" / "assets").mkdir(parents=True, exist_ok=True)
    (root / "demo" / "01-mod-a" / "01-les" / "assets" / "img.png").write_bytes(b"\x89PNG")
    (root / "demo" / "02-mod-b" / "01-les" / "01-z-video.mp4").write_bytes(b"v")


def test_scan_downloads(tmp_path):
    _make_course(tmp_path)
    courses = scan_downloads(tmp_path)
    assert len(courses) == 1
    c = courses[0]
    assert c["slug"] == "demo"
    assert len(c["modules"]) == 2
    assert c["files"]["transcripts"] == 1
    assert c["files"]["readings"] == 1
    assert c["files"]["videos"] == 1
    assert c["files"]["images"] == 1
    assert sum(c["files"].values()) == 4
    assert c["size"] > 0


def test_scan_empty(tmp_path):
    assert scan_downloads(tmp_path) == []


def test_ignores_non_module_dirs(tmp_path):
    (tmp_path / "demo" / "not-a-module").mkdir(parents=True, exist_ok=True)
    (tmp_path / "demo" / "not-a-module" / "x.txt").write_text("x")
    assert scan_downloads(tmp_path) == []


def test_classify_images(tmp_path):
    (tmp_path / "demo" / "01-mod" / "01-les" / "assets").mkdir(parents=True, exist_ok=True)
    img = tmp_path / "demo" / "01-mod" / "01-les" / "assets" / "a.png"
    img.write_bytes(b"\x89PNG")
    assert classify(img, tmp_path / "demo" / "01-mod") == "images"


def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
