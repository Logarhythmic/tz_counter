from __future__ import annotations

import re
import unicodedata


_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")
_HOLE_LEVEL_RE = re.compile(r"^h[oae]le\s+lev(?:el|et)\s*(.*)$")


def normalize_area_name(text: str) -> str:
    cleaned = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.lower().replace("lvl", "level")
    # Common OCR substitutions in Diablo II text.
    cleaned = cleaned.replace("@", "o")
    cleaned = cleaned.replace("'", "")
    # Preserve common OCR for level suffixes (|, ||, Il) before stripping punctuation.
    cleaned = cleaned.replace("||", " 2 ").replace("|", " 1 ")
    cleaned = _NON_ALNUM.sub(" ", cleaned)
    cleaned = _SPACES.sub(" ", cleaned).strip()
    cleaned = _normalize_hole_level_ocr(cleaned)
    return cleaned


def _normalize_hole_level_ocr(cleaned: str) -> str:
    match = _HOLE_LEVEL_RE.match(cleaned)
    if not match:
        return cleaned

    suffix = match.group(1).strip().replace(" ", "")
    if suffix in {"", "1", "i", "l"}:
        return "hole level 1"
    if suffix in {"2", "ii", "ll", "il", "li"}:
        return "hole level 2"
    return cleaned
