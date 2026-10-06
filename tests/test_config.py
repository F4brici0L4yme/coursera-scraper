from coursera_scraper import config


def test_resolve_flag_wins():
    assert config.resolve({"resolution": "720p"}, "resolution", "1080p") == "1080p"


def test_resolve_config_over_default():
    assert config.resolve({"resolution": "720p"}, "resolution", None) == "720p"


def test_resolve_default():
    assert config.resolve({}, "resolution", None) == "best"


def test_load_config_ignores_unknown_keys(monkeypatch, tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"resolution": "720p", "bogus": 1}')
    monkeypatch.setattr(config, "CONFIG_FILE", p)
    assert config.load_config() == {"resolution": "720p"}


def test_save_config_merges(monkeypatch, tmp_path):
    p = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", p)
    config.save_config({"resolution": "720p"})
    config.save_config({"lang": "es"})
    assert config.load_config() == {"resolution": "720p", "lang": "es"}


def test_load_config_bad_json(monkeypatch, tmp_path):
    p = tmp_path / "config.json"
    p.write_text("not json")
    monkeypatch.setattr(config, "CONFIG_FILE", p)
    assert config.load_config() == {}
