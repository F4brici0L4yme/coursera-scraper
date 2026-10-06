from coursera_scraper.downloader import _asset_ext, _pick_localized, pick_video_url, sanitize


def test_sanitize():
    assert sanitize("Hello, World!") == "Hello-World"
    assert sanitize("a/b\\c:d*e?") == "a-b-c-d-e"


def test_pick_video_url_best():
    sources = {
        "byResolution": {
            "720p": {"mp4VideoUrl": "https://x/720.mp4"},
            "1080p": {"mp4VideoUrl": "https://x/1080.mp4"},
            "360p": {"webMVideoUrl": "https://x/360.webm"},
        }
    }
    res, url = pick_video_url(sources, "best")
    assert res == "1080p"
    assert url == "https://x/1080.mp4"


def test_pick_video_url_fallback():
    sources = {"byResolution": {"360p": {"webMVideoUrl": "https://x/360.webm"}}}
    res, url = pick_video_url(sources, "1080p")
    assert res == "360p"  # requested 1080p missing -> fall back to best available
    assert url == "https://x/360.webm"


def test_pick_video_url_none():
    assert pick_video_url({"byResolution": {}}, "best") == (None, None)


def test_pick_localized():
    tracks = {"en": "https://x/en", "es": "https://x/es"}
    assert _pick_localized(tracks, "en") == "https://x/en"
    assert _pick_localized(tracks, "fr") == "https://x/en"  # fallback to first
    assert _pick_localized({}, "en") is None


def test_asset_ext_from_filename():
    assert _asset_ext("slides.pdf", "generic", "https://x") == "pdf"
    assert _asset_ext("nb.ipynb", "generic", "https://x") == "ipynb"


def test_asset_ext_from_type():
    # filename without extension -> use type_name when it is a concrete type
    assert _asset_ext("noext", "pdf", "https://x") == "pdf"


def test_asset_ext_generic_not_leaked(monkeypatch):
    # "generic" type_name must never become ".generic"; sniff fallback decides
    monkeypatch.setattr("coursera_scraper.downloader._sniff_asset_ext", lambda url: ".pdf")
    assert _asset_ext("noext", "generic", "https://x") == "pdf"


def test_asset_ext_sniff_fallback(monkeypatch):
    monkeypatch.setattr("coursera_scraper.downloader._sniff_asset_ext", lambda url: None)
    assert _asset_ext("noext", "generic", "https://x") == "bin"
