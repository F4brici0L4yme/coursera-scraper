"""User configuration for defaults (``~/.coursera-scraper/config.json``).

Flags always win over config; config wins over built-in defaults.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".coursera-scraper" / "config.json"

DEFAULTS = {
    "resolution": "best",
    "lang": "en",
    "out_dir": "downloads",
    "concurrency": 3,
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: v for k, v in data.items() if k in DEFAULTS}


def save_config(values: dict) -> None:
    merged = {**load_config(), **{k: v for k, v in values.items() if v is not None}}
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(merged, indent=2, sort_keys=True))


def resolve(cfg: dict, key: str, flag_value):
    if flag_value is not None:
        return flag_value
    return cfg.get(key, DEFAULTS[key])
