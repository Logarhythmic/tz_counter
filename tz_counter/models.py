from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AreaTarget:
    act: int
    area_name: str
    min_count: int
    max_count: int

    @property
    def key(self) -> str:
        return f"A{self.act}:{self.area_name}"


@dataclass(frozen=True)
class AreaCatalogEntry:
    act: int
    area_name: str
    min_count: Optional[int] = None
    max_count: Optional[int] = None

    @property
    def has_elite_counts(self) -> bool:
        return self.min_count is not None and self.max_count is not None


@dataclass
class AppConfig:
    ocr_interval_ms: int = 900
    stale_grace_ms: int = 3500
    confidence_threshold: float = 0.55
    # Backward-compatible legacy key (mirrors terminal_print_interval_seconds).
    debug_print_interval_seconds: int = 10
    terminal_print_interval_seconds: int = 10
    print_area_to_console: bool = True
    save_debug_artifacts: bool = True
    auto_follow_current_area: bool = True
    # absolute: use virtual desktop coordinates; monitor-relative: add monitor offset.
    capture_mode: str = "monitor-relative"
    # 1-based monitor index from MSS (1=primary monitor).
    monitor_index: int = 1
    # Tuned default around top-right minimap text for 4K (3840x2160).
    capture_left: int = 3318
    capture_top: int = 35
    capture_width: int = 507
    capture_height: int = 447
    # Increased default height to avoid row clipping on high DPI displays.
    table_row_height: int = 64
    hotkey_inc: str = "ctrl+num 5"
    hotkey_dec: str = "ctrl+num 4"
    hotkey_reset_current: str = "ctrl+num 8"
    # Ignore repeated hotkey triggers inside this window.
    hotkey_debounce_ms: int = 250


@dataclass
class OcrResult:
    text: str
    confidence: float
    details: str = ""
    area_hint: str = ""
