from __future__ import annotations

from datetime import datetime
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List

from .models import AppConfig, AreaTarget, OcrResult
from .resolver import AreaResolver
from .state import StateStore


class TrackerUi:
    def __init__(
        self,
        root: tk.Tk,
        targets: List[AreaTarget],
        resolver: AreaResolver,
        state: StateStore,
        config: AppConfig,
        event_queue: queue.Queue,
        on_close: Callable[[], None],
        debug_dir: Path,
    ) -> None:
        self.root = root
        # Keep encounter order from the source data (website/game progression).
        self.targets = list(targets)
        self.resolver = resolver
        self.state = state
        self.config = config
        self.event_queue = event_queue
        self.debug_dir = debug_dir
        self.on_close = on_close

        self._last_detected_raw = ""
        self._last_detected_score = 0.0
        self._last_area_hint = ""
        self._last_resolved_area_name = ""
        self._last_ocr_details = ""
        self._last_save = time.time()
        self._last_debug_print = 0.0
        self._ocr_source = "OCR source: initializing"
        self._last_ocr_image: bytes | None = None
        self._last_ocr_raw_image: bytes | None = None
        self._last_capture_region: dict | None = None
        self._last_capture_diag: dict | None = None
        self._last_followed_area_key: str | None = None

        self._item_ids: Dict[str, str] = {}
        self._target_names_by_key: Dict[str, str] = {}

        self.root.title("D2 Hell Champ/Unique Tracker")
        self.root.geometry("980x760")

        self.status_var = tk.StringVar(value="OCR: waiting")
        self.current_var = tk.StringVar(value="Current area: -")

        self._build_layout()
        self._load_rows()

        self.root.protocol("WM_DELETE_WINDOW", self._shutdown)
        self.root.after(200, self._pump)

    def _build_layout(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use(style.theme_use())
        style.configure("Counter.Treeview", rowheight=self.config.table_row_height, font=("Segoe UI", 10))
        style.configure("Counter.Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=(6, 8))
        # Some Windows ttk themes ignore python-side rowheight unless set through ttk::style.
        self.root.tk.call("ttk::style", "configure", "Counter.Treeview", "-rowheight", self.config.table_row_height)

        top = ttk.Frame(self.root, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, textvariable=self.current_var).pack(side=tk.LEFT)

        ttk.Button(top, text="Dump Debug Now", command=self._dump_debug_now).pack(side=tk.RIGHT)
        ttk.Button(top, text="Reset Counts", command=self._reset_counts).pack(side=tk.RIGHT)
        ttk.Button(top, text="New Run", command=self._new_run).pack(side=tk.RIGHT)
        ttk.Button(top, text="Save Now", command=self.state.save).pack(side=tk.RIGHT, padx=6)

        cols = ("act", "area", "min", "max", "current", "status")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings", height=32, style="Counter.Treeview")

        self.tree.heading("act", text="Act")
        self.tree.heading("area", text="Area")
        self.tree.heading("min", text="Min")
        self.tree.heading("max", text="Max")
        self.tree.heading("current", text="Current")
        self.tree.heading("status", text="Status")

        self.tree.column("act", width=70, anchor=tk.CENTER)
        self.tree.column("area", width=430)
        self.tree.column("min", width=100, anchor=tk.CENTER)
        self.tree.column("max", width=100, anchor=tk.CENTER)
        self.tree.column("current", width=110, anchor=tk.CENTER)
        self.tree.column("status", width=140, anchor=tk.CENTER)

        self.tree.tag_configure("in_range", background="#c8f7c5")
        self.tree.tag_configure("over_range", background="#ffd0d0")
        self.tree.tag_configure("current", background="#d9ecff")
        self.tree.tag_configure("current_in_range", background="#92e6a7")
        self.tree.tag_configure("current_over_range", background="#ffb3b3")

        yscroll = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=(0, 10))
        yscroll.pack(side=tk.LEFT, fill=tk.Y, pady=(0, 10))

    def _load_rows(self) -> None:
        for target in self.targets:
            item_id = self.tree.insert(
                "",
                tk.END,
                values=(target.act, target.area_name, target.min_count, target.max_count, 0, "pending"),
            )
            self._item_ids[target.key] = item_id
            self._target_names_by_key[target.key] = target.area_name

    def _new_run(self) -> None:
        self.state.reset_all()
        self.state.save()

    def _reset_counts(self) -> None:
        self.state.reset_all()
        self.state.save()

    def _dump_debug_now(self) -> None:
        snapshot = self.state.snapshot()
        area_name = self._target_names_by_key.get(snapshot.current_area_key or "", "unknown")
        self._write_debug_artifacts(area_name)
        messagebox.showinfo("Debug Saved", f"Saved debug artifact for: {area_name}")

    def _pump(self) -> None:
        self._process_events()
        self._render_state()

        now = time.time()
        if now - self._last_debug_print >= float(self.config.terminal_print_interval_seconds):
            snapshot = self.state.snapshot()
            area_name = self._target_names_by_key.get(snapshot.current_area_key or "", self._last_resolved_area_name or "unknown")
            if self.config.print_area_to_console:
                if area_name == "unknown":
                    hint = self._last_area_hint or "-"
                    print(f"unknown: {hint}, confidence: {self._last_detected_score:.4f}", flush=True)
                else:
                    print(f"Current Area: `{area_name}`", flush=True)
            if self.config.save_debug_artifacts:
                self._write_debug_artifacts(area_name)
            self._last_debug_print = now

        if now - self._last_save > 5.0:
            self.state.save()
            self._last_save = now

        self.root.after(200, self._pump)

    def _process_events(self) -> None:
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                return

            if event["type"] == "ocr":
                self._last_ocr_image = event.get("capture_png")
                self._last_ocr_raw_image = event.get("capture_raw_png")
                self._ocr_source = event.get("monitor_label", self._ocr_source)
                self._last_capture_region = event.get("capture_region")
                self._last_capture_diag = event.get("capture_diagnostics")
                self._handle_ocr(event["result"])
            elif event["type"] == "hotkey":
                self._handle_hotkey(event["action"])
            elif event["type"] == "ocr_info":
                self._ocr_source = event["message"]

    def _handle_ocr(self, result: OcrResult) -> None:
        self._last_detected_raw = result.text
        self._last_detected_score = result.confidence
        self._last_area_hint = result.area_hint
        self._last_ocr_details = result.details

        if result.confidence < self.config.confidence_threshold:
            self._last_resolved_area_name = ""
            self.state.set_current_area(None)
            return

        candidate = result.area_hint or result.text
        resolved = self.resolver.resolve(candidate)
        self._last_resolved_area_name = resolved.area_name
        if not resolved.area_name:
            self.state.set_current_area(None)
            return

        if not resolved.target:
            # We recognized a valid area that is not tracked for counts.
            self.state.set_current_area(None, allow_stale=False)
            return

        self.state.set_current_area(resolved.target.key)

    def _handle_hotkey(self, action: str) -> None:
        if action == "inc":
            self.state.increment_current(1)
        elif action == "dec":
            self.state.increment_current(-1)
        elif action == "reset_current":
            self.state.reset_current()

    def _render_state(self) -> None:
        snapshot = self.state.snapshot()
        current_name = self._target_names_by_key.get(snapshot.current_area_key or "", self._last_resolved_area_name or "-")
        self.current_var.set(f"Current area: {current_name}")

        diag = self._last_capture_diag or {}
        region = self._last_capture_region or {}
        diag_text = (
            f"raw={diag.get('raw_mean', 0.0):.1f} "
            f"white={diag.get('processed_white_ratio', 0.0):.2f} "
            f"black={diag.get('processed_black_ratio', 0.0):.2f} "
            f"region=({region.get('left', '-')},{region.get('top', '-')} {region.get('width', '-')}x{region.get('height', '-')})"
        )
        self.status_var.set(
            f"{self._ocr_source} | {diag_text} | hint: {self._last_area_hint or '-'} | OCR text: {self._last_detected_raw or '-'} | conf: {self._last_detected_score:.2f}"
        )

        for target in self.targets:
            current = int(snapshot.counts.get(target.key, 0))
            item_id = self._item_ids[target.key]

            status = "pending"
            tag = ""
            if current > target.max_count:
                status = "over"
                tag = "over_range"
            elif current >= target.min_count:
                status = "in range"
                tag = "in_range"

            if snapshot.current_area_key == target.key:
                if tag == "in_range":
                    tag = "current_in_range"
                elif tag == "over_range":
                    tag = "current_over_range"
                else:
                    tag = "current"
                self.tree.see(item_id)

            self.tree.item(
                item_id,
                values=(target.act, target.area_name, target.min_count, target.max_count, current, status),
                tags=(tag,) if tag else (),
            )

        if self.config.auto_follow_current_area and snapshot.current_area_key:
            self._follow_current_area(snapshot.current_area_key)

    def _follow_current_area(self, area_key: str) -> None:
        if area_key == self._last_followed_area_key:
            return
        item_id = self._item_ids.get(area_key)
        if not item_id:
            return

        children = self.tree.get_children("")
        total = len(children)
        if total <= 0:
            return

        idx = children.index(item_id)
        visible = max(1, int(self.tree.cget("height")))
        top_idx = max(0, min(total - visible, idx - visible // 2))
        fraction = 0.0 if total <= visible else top_idx / float(total - visible)

        self.tree.yview_moveto(fraction)
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self._last_followed_area_key = area_key

    def _shutdown(self) -> None:
        self.state.save()
        self.on_close()
        self.root.destroy()

    def _write_debug_artifacts(self, area_name: str) -> None:
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.debug_dir / f"ocr_{stamp}"

        if self._last_ocr_image:
            (base.with_name(base.name + "_processed").with_suffix(".png")).write_bytes(self._last_ocr_image)

        if self._last_ocr_raw_image:
            (base.with_name(base.name + "_raw").with_suffix(".png")).write_bytes(self._last_ocr_raw_image)

        text_lines = [
            f"timestamp: {stamp}",
            f"current_area: {area_name}",
            f"ocr_text: {self._last_detected_raw or '-'}",
            f"ocr_area_hint: {self._last_area_hint or '-'}",
            f"ocr_confidence: {self._last_detected_score:.4f}",
            f"ocr_source: {self._ocr_source}",
            f"capture_region: {self._last_capture_region}",
            f"capture_diagnostics: {self._last_capture_diag}",
            "ocr_details:",
            self._last_ocr_details or "-",
        ]
        (base.with_suffix(".txt")).write_text("\n".join(text_lines) + "\n", encoding="utf-8")
