from __future__ import annotations

import re
import unicodedata


_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalize_area_name(text: str) -> str:
    cleaned = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.lower().replace("lvl", "level")
    # Common OCR substitutions in Diablo II text.
    cleaned = cleaned.replace("@", "o")
    cleaned = cleaned.replace("'", "")
    cleaned = _NON_ALNUM.sub(" ", cleaned)
    cleaned = _SPACES.sub(" ", cleaned).strip()
    return cleaned
