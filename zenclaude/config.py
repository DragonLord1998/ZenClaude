from __future__ import annotations

import sys
from typing import Any

from zenclaude.paths import CONFIG_FILE

DEFAULTS: dict[str, Any] = {
    "defaults": {
        "memory": "8g",
        "cpus": "4",
        "pids": 256,
        "snapshot": True,
    },
    "notifications": {
        "enabled": True,
        "sound": True,
    },
    "dashboard": {
        "port": 7777,
        "host": "127.0.0.1",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return DEFAULTS.copy()

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib
        except ImportError:
            return DEFAULTS.copy()

    with open(CONFIG_FILE, "rb") as f:
        user_config = tomllib.load(f)

    return _deep_merge(DEFAULTS, user_config)
