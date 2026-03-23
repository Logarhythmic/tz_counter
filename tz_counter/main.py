from __future__ import annotations

import logging
import queue
import tkinter as tk
from pathlib import Path

from .config import load_or_create_config
from .data_store import build_area_name_index, build_target_index, load_area_catalog, load_targets
from .hotkeys import HotkeyManager
from .ocr import OcrWorker
from .resolver import AreaResolver
from .state import StateStore
from .ui import TrackerUi


def run() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    config_path = root_dir / "config.json"
    data_path = root_dir / "data" / "hell_targets.json"
    areas_path = root_dir / "data" / "hell_areas.json"
    state_path = root_dir / "run_state.json"
    debug_dir = root_dir / "debug"

    config = load_or_create_config(config_path)
    targets = load_targets(data_path)
    catalog = load_area_catalog(areas_path) if areas_path.exists() else []
    area_name_index = build_area_name_index(catalog) if catalog else None
    resolver = AreaResolver(build_target_index(targets), area_name_index=area_name_index)
    state_store = StateStore(state_path=state_path, stale_grace_ms=config.stale_grace_ms)
    state_store.load()

    event_queue: queue.Queue = queue.Queue()

    ocr = OcrWorker(config=config, out_queue=event_queue)
    ocr.start()

    hotkeys = HotkeyManager(config=config, out_queue=event_queue)
    hotkeys.start()

    def stop_workers() -> None:
        ocr.stop()
        hotkeys.stop()

    logging.info("OCR engine: %s", ocr.engine_name)
    if ocr.engine_name == "none":
        logging.warning(
            "No OCR backend loaded. Install pytesseract (and ensure Tesseract executable is on PATH) or EasyOCR."
        )

    root = tk.Tk()
    TrackerUi(
        root=root,
        targets=targets,
        resolver=resolver,
        state=state_store,
        config=config,
        event_queue=event_queue,
        on_close=stop_workers,
        debug_dir=debug_dir,
    )
    root.mainloop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
