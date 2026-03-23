from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .models import AreaCatalogEntry, AreaTarget
from .normalization import normalize_area_name


class DataValidationError(RuntimeError):
    pass


def load_targets(data_path: Path) -> List[AreaTarget]:
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    targets: List[AreaTarget] = []
    for row in payload:
        targets.append(
            AreaTarget(
                act=int(row["act"]),
                area_name=str(row["area_name"]),
                min_count=int(row["min_count"]),
                max_count=int(row["max_count"]),
            )
        )
    _validate(targets)
    return targets


def load_area_catalog(data_path: Path) -> List[AreaCatalogEntry]:
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    catalog: List[AreaCatalogEntry] = []
    for row in payload:
        min_raw = row.get("min_count")
        max_raw = row.get("max_count")
        catalog.append(
            AreaCatalogEntry(
                act=int(row["act"]),
                area_name=str(row["area_name"]),
                min_count=int(min_raw) if min_raw is not None else None,
                max_count=int(max_raw) if max_raw is not None else None,
            )
        )
    return catalog


def build_target_index(targets: List[AreaTarget]) -> Dict[str, AreaTarget]:
    index: Dict[str, AreaTarget] = {}
    for target in targets:
        index.setdefault(normalize_area_name(target.area_name), target)
    return index


def build_area_name_index(catalog: List[AreaCatalogEntry]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for row in catalog:
        index.setdefault(normalize_area_name(row.area_name), row.area_name)
    return index


def _validate(targets: List[AreaTarget]) -> None:
    for target in targets:
        if target.min_count > target.max_count:
            raise DataValidationError(
                f"Invalid target range for {target.area_name}: {target.min_count} > {target.max_count}"
            )
