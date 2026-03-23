from __future__ import annotations

import logging
import queue
import threading
import time
from typing import List

import keyboard

from .models import AppConfig

_LOG = logging.getLogger(__name__)


class HotkeyManager:
    def __init__(self, config: AppConfig, out_queue: queue.Queue) -> None:
        self._config = config
        self._queue = out_queue
        self._handles: List[int] = []
        self._started = False
        self._lock = threading.Lock()
        self._debounce_lock = threading.Lock()
        self._last_action_ts: dict[str, float] = {}

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._register(self._config.hotkey_inc, "inc")
            self._register(self._config.hotkey_dec, "dec")
            self._register(self._config.hotkey_reset_current, "reset_current")
            self._started = True

    def stop(self) -> None:
        with self._lock:
            for handle in self._handles:
                keyboard.remove_hotkey(handle)
            self._handles.clear()
            self._started = False

    def _register(self, combo: str, action: str) -> None:
        attempts = self._build_combo_attempts(combo)
        for candidate in attempts:
            try:
                handle = keyboard.add_hotkey(
                    candidate,
                    lambda action=action: self._on_action(action),
                )
                self._handles.append(handle)
                _LOG.info("Registered hotkey %s => %s", candidate, action)
                return
            except Exception as ex:
                _LOG.debug("Failed to register hotkey candidate %s: %s", candidate, ex)

        _LOG.warning("Failed to register hotkey %s with all known aliases", combo)

    def _on_action(self, action: str) -> None:
        now = time.monotonic()
        debounce_ms = max(0, int(self._config.hotkey_debounce_ms))

        with self._debounce_lock:
            prev = self._last_action_ts.get(action)
            if prev is not None and (now - prev) * 1000.0 < debounce_ms:
                _LOG.debug("Ignored hotkey repeat: %s", action)
                return
            self._last_action_ts[action] = now

        self._queue.put({"type": "hotkey", "action": action})

    @staticmethod
    def _build_combo_attempts(combo: str) -> List[str]:
        attempts: List[str] = [combo]
        attempts.append(combo.replace("numpad ", "num ").replace("numpad", "num"))
        attempts.append(combo.replace("num ", "numpad ").replace("num", "numpad"))

        deduped: List[str] = []
        seen = set()
        for item in attempts:
            if item not in seen:
                deduped.append(item)
                seen.add(item)
        return deduped
