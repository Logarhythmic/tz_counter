from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set

from rapidfuzz import fuzz, process

from .models import AreaTarget
from .normalization import normalize_area_name


@dataclass
class ResolveResult:
    target: Optional[AreaTarget]
    area_name: str
    score: float


class AreaResolver:
    def __init__(
        self,
        target_index: Dict[str, AreaTarget],
        area_name_index: Optional[Dict[str, str]] = None,
        fuzzy_threshold: float = 82.0,
    ) -> None:
        self.target_index = target_index
        self.area_name_index = area_name_index or {key: target.area_name for key, target in target_index.items()}
        self.keys = list(self.area_name_index.keys())
        self.fuzzy_threshold = fuzzy_threshold

    def resolve(self, text: str) -> ResolveResult:
        normalized = normalize_area_name(text)
        if not normalized:
            return ResolveResult(target=None, area_name="", score=0.0)

        exact_name = self.area_name_index.get(normalized)
        if exact_name:
            return ResolveResult(target=self.target_index.get(normalized), area_name=exact_name, score=100.0)

        match = process.extractOne(
            normalized,
            self.keys,
            scorer=fuzz.ratio,
            score_cutoff=self.fuzzy_threshold,
        )
        if match:
            key, score, _ = match
            return ResolveResult(target=self.target_index.get(key), area_name=self.area_name_index[key], score=float(score))

        # Fallback for custom-font OCR confusion (for example e<->o in Diablo text).
        fallback = self._resolve_with_confusion_variants(normalized)
        if fallback:
            return fallback

        return ResolveResult(target=None, area_name="", score=0.0)

    def _resolve_with_confusion_variants(self, normalized: str) -> Optional[ResolveResult]:
        variants = _font_confusion_variants(normalized)
        if not variants:
            return None

        for variant in variants:
            exact_name = self.area_name_index.get(variant)
            if exact_name:
                return ResolveResult(target=self.target_index.get(variant), area_name=exact_name, score=99.0)

        best_key: Optional[str] = None
        best_score = 0.0
        # Keep fallback fuzzy matching strict to avoid coercing valid-but-unsupported
        # areas (for example "Den of Evil") into an unrelated tracked target.
        fallback_cutoff = self.fuzzy_threshold

        for variant in variants:
            match = process.extractOne(
                variant,
                self.keys,
                scorer=fuzz.ratio,
                score_cutoff=fallback_cutoff,
            )
            if not match:
                continue

            key, score, _ = match
            score_f = float(score)
            if score_f > best_score:
                best_key = key
                best_score = score_f

        if best_key is None:
            return None

        return ResolveResult(target=self.target_index.get(best_key), area_name=self.area_name_index[best_key], score=best_score)


def _font_confusion_variants(text: str, max_variants: int = 24) -> Set[str]:
    transforms = (
        lambda s: s.replace("e", "o"),
        lambda s: s.replace("o", "e"),
        lambda s: s.replace("ee", "oo"),
        lambda s: s.replace("oo", "ee"),
        lambda s: s.replace("p", "d"),
        lambda s: s.replace("d", "p"),
        lambda s: s.replace("i", "l"),
        lambda s: s.replace("l", "i"),
    )

    seen: Set[str] = {text}
    frontier = [text]

    while frontier and len(seen) < max_variants + 1:
        current = frontier.pop(0)
        for transform in transforms:
            candidate = transform(current)
            if candidate == current or candidate in seen:
                continue
            seen.add(candidate)
            frontier.append(candidate)
            if len(seen) >= max_variants + 1:
                break

    seen.discard(text)
    return seen
