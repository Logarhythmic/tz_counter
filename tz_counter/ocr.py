from __future__ import annotations

import logging
import queue
import threading
import time
from io import BytesIO
from typing import Any, Dict

from mss import mss
from PIL import Image, ImageEnhance, ImageStat

from .models import AppConfig, OcrResult

_LOG = logging.getLogger(__name__)


class OcrEngine:
    def __init__(self) -> None:
        self._engine_name = "none"
        self._easy_reader = None
        self._pytesseract = None

        try:
            import easyocr  # type: ignore

            self._easy_reader = easyocr.Reader(["en"], gpu=False)
            self._engine_name = "easyocr"
            return
        except Exception as ex:
            _LOG.info("EasyOCR unavailable: %s", ex)

        try:
            import pytesseract  # type: ignore

            self._pytesseract = pytesseract
            self._engine_name = "pytesseract"
        except Exception as ex:
            _LOG.info("Pytesseract unavailable: %s", ex)

    @property
    def engine_name(self) -> str:
        return self._engine_name

    def read(self, image: Image.Image) -> OcrResult:
        if self._engine_name == "easyocr" and self._easy_reader:
            items = self._easy_reader.readtext(image, detail=1)
            if not items:
                return OcrResult(text="", confidence=0.0, details="easyocr: no items", area_hint="")
            text = " ".join(str(item[1]) for item in items)
            confidence = max(float(item[2]) for item in items)
            detail_lines = [f"{float(item[2]):.3f}: {str(item[1])}" for item in items]
            ordered_lines = _easyocr_lines(items)
            area_hint = _area_before_difficulty(ordered_lines)
            return OcrResult(
                text=text,
                confidence=confidence,
                details=(
                    "easyocr items:\n"
                    + "\n".join(detail_lines)
                    + "\n"
                    + "easyocr lines:\n"
                    + "\n".join(ordered_lines)
                ),
                area_hint=area_hint,
            )

        if self._engine_name == "pytesseract" and self._pytesseract:
            data = self._pytesseract.image_to_data(image, output_type=self._pytesseract.Output.DICT)
            line_text = self._pytesseract.image_to_string(image, config="--psm 6")
            lines = [ln.strip() for ln in line_text.splitlines() if ln.strip()]
            raw_texts = data.get("text", [])
            raw_confs = data.get("conf", [])
            tokens: list[tuple[str, float]] = []
            for t, c in zip(raw_texts, raw_confs):
                if not t or not str(t).strip():
                    continue
                try:
                    conf_val = float(c)
                except (TypeError, ValueError):
                    continue
                if conf_val < 0:
                    continue
                tokens.append((str(t).strip(), conf_val))

            texts = [token[0] for token in tokens]
            confs = [token[1] for token in tokens]
            if not texts:
                return OcrResult(text="", confidence=0.0, details="pytesseract: no tokens", area_hint="")
            confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
            detail_lines = [f"{conf/100.0:.3f}: {txt}" for txt, conf in tokens]
            area_hint = _area_before_difficulty(lines)
            return OcrResult(
                text=" ".join(texts),
                confidence=confidence,
                details=(
                    "pytesseract tokens:\n"
                    + "\n".join(detail_lines)
                    + "\n"
                    + "pytesseract lines:\n"
                    + "\n".join(lines)
                ),
                area_hint=area_hint,
            )

        return OcrResult(text="", confidence=0.0, details="ocr engine unavailable", area_hint="")


class OcrWorker(threading.Thread):
    def __init__(self, config: AppConfig, out_queue: queue.Queue) -> None:
        super().__init__(daemon=True)
        self._config = config
        self._queue = out_queue
        self._stop = threading.Event()
        self._engine = OcrEngine()

    @property
    def engine_name(self) -> str:
        return self._engine.engine_name

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        with mss() as screen:
            monitor_info = self._resolve_monitor(screen)
            self._queue.put({"type": "ocr_info", "message": monitor_info["label"]})
            while not self._stop.is_set():
                try:
                    capture_region = {
                        "left": monitor_info["left"] + int(self._config.capture_left),
                        "top": monitor_info["top"] + int(self._config.capture_top),
                        "width": self._config.capture_width,
                        "height": self._config.capture_height,
                    }
                    shot = screen.grab(capture_region)
                    raw_image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    processed_image = _preprocess_image(raw_image)
                    result = self._engine.read(processed_image)
                    diagnostics = _compute_diagnostics(raw_image, processed_image)
                    self._queue.put(
                        {
                            "type": "ocr",
                            "result": result,
                            "capture_png": _to_png_bytes(processed_image),
                            "capture_raw_png": _to_png_bytes(raw_image),
                            "monitor_label": monitor_info["label"],
                            "capture_region": capture_region,
                            "capture_diagnostics": diagnostics,
                        }
                    )
                except Exception as ex:
                    self._queue.put({"type": "ocr_info", "message": f"capture error: {ex}"})
                    _LOG.exception("OCR capture failed: %s", ex)
                time.sleep(self._config.ocr_interval_ms / 1000.0)

    def _resolve_monitor(self, screen: mss) -> Dict[str, Any]:
        monitors = screen.monitors
        if self._config.capture_mode == "absolute":
            virtual = monitors[0]
            return {
                "left": 0,
                "top": 0,
                "label": (
                    f"engine={self._engine.engine_name} mode=absolute mon=virtual "
                    f"bounds=({virtual['left']},{virtual['top']} {virtual['width']}x{virtual['height']})"
                ),
            }

        requested = max(1, int(self._config.monitor_index))
        if requested < len(monitors):
            m = monitors[requested]
            return {
                "left": int(m["left"]),
                "top": int(m["top"]),
                "label": (
                    f"engine={self._engine.engine_name} mode=monitor-relative mon={requested} "
                    f"bounds=({m['left']},{m['top']} {m['width']}x{m['height']})"
                ),
            }

        # Fallback to primary monitor if requested index is out of range.
        m = monitors[1]
        return {
            "left": int(m["left"]),
            "top": int(m["top"]),
            "label": (
                f"engine={self._engine.engine_name} mode=monitor-relative mon={requested}->1 "
                f"bounds=({m['left']},{m['top']} {m['width']}x{m['height']})"
            ),
        }


def _preprocess_image(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    contrasted = ImageEnhance.Contrast(gray).enhance(2.2)
    # Thresholding helps stabilize OCR on noisy map text.
    return contrasted.point(lambda p: 255 if p > 138 else 0)


def _to_png_bytes(image: Image.Image) -> bytes:
    with BytesIO() as buf:
        image.save(buf, format="PNG")
        return buf.getvalue()


def _compute_diagnostics(raw_image: Image.Image, processed_image: Image.Image) -> Dict[str, float]:
    raw_gray = raw_image.convert("L")
    proc_gray = processed_image.convert("L")

    raw_mean = float(ImageStat.Stat(raw_gray).mean[0])
    proc_mean = float(ImageStat.Stat(proc_gray).mean[0])
    hist = proc_gray.histogram()
    total = max(1, int(sum(hist)))
    white_ratio = float(hist[255]) / float(total)
    black_ratio = float(hist[0]) / float(total)

    return {
        "raw_mean": raw_mean,
        "processed_mean": proc_mean,
        "processed_white_ratio": white_ratio,
        "processed_black_ratio": black_ratio,
    }


def _area_before_difficulty(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if "difficulty" in line.lower() and idx > 0:
            return lines[idx - 1]
    return ""


def _easyocr_lines(items: list) -> list[str]:
    if not items:
        return []

    rows: list[dict[str, object]] = []
    for item in items:
        box = item[0]
        token = str(item[1]).strip()
        if not token:
            continue

        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        y_mid = (min(ys) + max(ys)) / 2.0
        x_min = min(xs)

        placed = False
        for row in rows:
            if abs(y_mid - float(row["y"])) <= 14:
                row_tokens = row["tokens"]
                assert isinstance(row_tokens, list)
                row_tokens.append((x_min, token))
                row["y"] = (float(row["y"]) + y_mid) / 2.0
                placed = True
                break

        if not placed:
            rows.append({"y": y_mid, "tokens": [(x_min, token)]})

    lines: list[str] = []
    for row in sorted(rows, key=lambda r: float(r["y"])):
        row_tokens = row["tokens"]
        assert isinstance(row_tokens, list)
        tokens = [tok for _, tok in sorted(row_tokens, key=lambda p: p[0])]
        lines.append(" ".join(tokens).strip())

    return [ln for ln in lines if ln]
