import requests

from coursera_scraper import downloader


class FakeResp:
    def __init__(self, status_code, body=b"", headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_get(monkeypatch, resp, capture):
    def fake_get(url, **kwargs):
        capture.append(kwargs.get("headers"))
        return resp

    monkeypatch.setattr("coursera_scraper.downloader.requests.get", fake_get)


def test_skip_existing(tmp_path, monkeypatch):
    dest = tmp_path / "f.bin"
    dest.write_bytes(b"done")
    called = []
    _patch_get(monkeypatch, FakeResp(200, b"x"), called)
    assert downloader._download_file("text", "http://u", dest, None) == "skip"
    assert called == []


def test_resume_partial(tmp_path, monkeypatch):
    dest = tmp_path / "f.bin"
    (tmp_path / "f.bin.part").write_bytes(b"AAAA")
    calls = []
    _patch_get(monkeypatch, FakeResp(206, b"BBBB"), calls)
    assert downloader._download_file("text", "http://u", dest, None) == "ok"
    assert dest.read_bytes() == b"AAAABBBB"
    assert calls[0] == {"Range": "bytes=4-"}


def test_resume_server_ignores_range(tmp_path, monkeypatch):
    dest = tmp_path / "f.bin"
    (tmp_path / "f.bin.part").write_bytes(b"AAAA")
    _patch_get(monkeypatch, FakeResp(200, b"FULL"), [])
    assert downloader._download_file("text", "http://u", dest, None) == "ok"
    assert dest.read_bytes() == b"FULL"


def test_resume_416_completes(tmp_path, monkeypatch):
    dest = tmp_path / "f.bin"
    (tmp_path / "f.bin.part").write_bytes(b"COMPLETE")
    _patch_get(monkeypatch, FakeResp(416), [])
    assert downloader._download_file("text", "http://u", dest, None) == "ok"
    assert dest.read_bytes() == b"COMPLETE"


def test_failure_keeps_part(tmp_path, monkeypatch):
    dest = tmp_path / "f.bin"
    (tmp_path / "f.bin.part").write_bytes(b"partial")

    def boom(url, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr("coursera_scraper.downloader.requests.get", boom)
    monkeypatch.setattr("coursera_scraper.downloader.time.sleep", lambda *_: None)
    try:
        downloader._download_file("text", "http://u", dest, None, retries=2)
    except downloader.CourseraError:
        pass
    else:
        raise AssertionError("expected CourseraError")
    assert (tmp_path / "f.bin.part").exists()  # kept for the next resume
