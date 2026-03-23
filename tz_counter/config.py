from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import AppConfig


def load_or_create_config(path: Path) -> AppConfig:
    if not path.exists():
        config = AppConfig()
        path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
        return config

    payload = json.loads(path.read_text(encoding="utf-8"))

    # Migrate legacy interval key if terminal-specific key is missing.
    if "terminal_print_interval_seconds" not in payload and "debug_print_interval_seconds" in payload:
        payload["terminal_print_interval_seconds"] = payload["debug_print_interval_seconds"]

    merged = asdict(AppConfig())
    merged.update(payload)

    # Keep both keys in sync for backward compatibility with older configs/code.
    merged["debug_print_interval_seconds"] = int(merged.get("terminal_print_interval_seconds", 10))

    # keyboard library uses "num" aliases; normalize legacy values like "numpad 8".
    for key in ("hotkey_inc", "hotkey_dec", "hotkey_reset_current"):
        value = merged.get(key)
        if isinstance(value, str):
            merged[key] = value.replace("numpad ", "num ").replace("numpad", "num")

    mode = merged.get("capture_mode")
    if mode not in {"absolute", "monitor-relative"}:
        merged["capture_mode"] = "monitor-relative"

    merged["hotkey_debounce_ms"] = max(0, int(merged.get("hotkey_debounce_ms", 250)))

    config = AppConfig(**merged)

    # Keep config.json as the single editable source with all active keys visible.
    normalized = asdict(config)
    if normalized != payload:
        path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

    return config
