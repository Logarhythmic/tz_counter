from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, Optional


@dataclass
class TrackerState:
    counts: Dict[str, int] = field(default_factory=dict)
    current_area_key: Optional[str] = None
    last_valid_area_key: Optional[str] = None
    last_valid_seen_ms: int = 0


class StateStore:
    def __init__(self, state_path: Path, stale_grace_ms: int) -> None:
        self.state_path = state_path
        self.stale_grace_ms = stale_grace_ms
        self._lock = threading.Lock()
        self._state = TrackerState()

    def load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        with self._lock:
            self._state.counts = {str(k): int(v) for k, v in payload.get("counts", {}).items()}
            self._state.current_area_key = payload.get("current_area_key")
            self._state.last_valid_area_key = payload.get("last_valid_area_key")
            self._state.last_valid_seen_ms = int(payload.get("last_valid_seen_ms", 0))

    def save(self) -> None:
        with self._lock:
            payload = {
                "counts": self._state.counts,
                "current_area_key": self._state.current_area_key,
                "last_valid_area_key": self._state.last_valid_area_key,
                "last_valid_seen_ms": self._state.last_valid_seen_ms,
            }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=self.state_path.parent) as tmp:
            json.dump(payload, tmp, indent=2)
            tmp.flush()
            temp_name = tmp.name
        Path(temp_name).replace(self.state_path)

    def snapshot(self) -> TrackerState:
        with self._lock:
            return TrackerState(
                counts=dict(self._state.counts),
                current_area_key=self._state.current_area_key,
                last_valid_area_key=self._state.last_valid_area_key,
                last_valid_seen_ms=self._state.last_valid_seen_ms,
            )

    def set_current_area(self, area_key: Optional[str], allow_stale: bool = True) -> None:
        now_ms = int(time.time() * 1000)
        with self._lock:
            if area_key:
                self._state.current_area_key = area_key
                self._state.last_valid_area_key = area_key
                self._state.last_valid_seen_ms = now_ms
                return

            if not allow_stale:
                self._state.current_area_key = None
                return

            stale_window = now_ms - self._state.last_valid_seen_ms
            if self._state.last_valid_area_key and stale_window <= self.stale_grace_ms:
                self._state.current_area_key = self._state.last_valid_area_key
            else:
                self._state.current_area_key = None

    def increment_current(self, amount: int) -> None:
        with self._lock:
            if not self._state.current_area_key:
                return
            key = self._state.current_area_key
            self._state.counts[key] = max(0, int(self._state.counts.get(key, 0)) + amount)

    def reset_current(self) -> None:
        with self._lock:
            if not self._state.current_area_key:
                return
            self._state.counts[self._state.current_area_key] = 0

    def reset_all(self) -> None:
        with self._lock:
            self._state.counts.clear()
            self._state.current_area_key = None
            self._state.last_valid_area_key = None
            self._state.last_valid_seen_ms = 0
