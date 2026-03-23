from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.theamazonbasin.com/wiki/index.php/Act_{act}"


@dataclass
class AreaRow:
    act: int
    area_name: str
    min_count: Optional[int]
    max_count: Optional[int]


def table_to_grid(table: Tag) -> List[List[str]]:
    rows = table.find_all("tr")
    grid: List[List[str]] = []
    spans: dict[tuple[int, int], str] = {}

    for r, row in enumerate(rows):
        out_row: List[str] = []
        col = 0
        cells = row.find_all(["th", "td"])
        c_idx = 0

        while c_idx < len(cells) or (r, col) in spans:
            while (r, col) in spans:
                out_row.append(spans[(r, col)])
                col += 1

            if c_idx >= len(cells):
                break

            cell = cells[c_idx]
            c_idx += 1
            text = cell.get_text(" ", strip=True)
            rowspan = _as_int(cell.get("rowspan"), default=1)
            colspan = _as_int(cell.get("colspan"), default=1)

            for _ in range(colspan):
                out_row.append(text)
                for rr in range(1, rowspan):
                    spans[(r + rr, col)] = text
                col += 1

        grid.append(out_row)

    width = max((len(r) for r in grid), default=0)
    return [r + [""] * (width - len(r)) for r in grid]


def _as_int(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, list):
        if not value:
            return default
        value = value[0]
    try:
        return int(str(value))
    except ValueError:
        return default


def parse_act(act: int) -> List[AreaRow]:
    response = requests.get(BASE_URL.format(act=act), timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    target_table: Tag | None = None
    candidates: list[tuple[int, Tag]] = []
    for table in soup.find_all("table"):
        first_tr = table.find("tr")
        if not first_tr:
            continue
        first_th_count = len(first_tr.find_all("th"))
        if first_th_count < 5 or first_th_count > 20:
            continue

        has_monster_level = False
        has_champion_unique = False
        for tr in table.find_all("tr")[:8]:
            th_text = " ".join(cell.get_text(" ", strip=True).lower() for cell in tr.find_all("th"))
            if "monster level" in th_text:
                has_monster_level = True
            if "champion and unique" in th_text:
                has_champion_unique = True
        if has_monster_level and has_champion_unique:
            candidates.append((len(table.find_all("tr")), table))

    if candidates:
        target_table = max(candidates, key=lambda item: item[0])[1]

    if target_table is None:
        raise RuntimeError(f"Could not find area table for act {act}")

    grid = table_to_grid(target_table)
    if len(grid) < 3:
        raise RuntimeError(f"Unexpected table layout for act {act}")

    tr_rows = target_table.find_all("tr")
    header_rows = 0
    for tr in tr_rows:
        if tr.find("td"):
            break
        header_rows += 1

    if header_rows == 0:
        header_rows = min(4, len(grid) - 1)

    headers = grid[:header_rows]
    data_rows = grid[header_rows:]

    col_count = len(headers[0])
    lower_headers = [[headers[r][c].strip().lower() for c in range(col_count)] for r in range(len(headers))]

    name_idx = _find_exact_header_col(lower_headers, {"name", "area"})
    hell_min_idx, hell_max_idx = _find_hell_champ_cols(lower_headers)

    rows: List[AreaRow] = []
    for row in data_rows:
        if name_idx >= len(row):
            continue
        name = row[name_idx].strip()
        if not name:
            continue

        min_raw = row[hell_min_idx].strip()
        max_raw = row[hell_max_idx].strip()
        min_count: Optional[int] = None
        max_count: Optional[int] = None
        if min_raw and max_raw:
            try:
                min_count = int(min_raw)
                max_count = int(max_raw)
            except ValueError:
                min_count = None
                max_count = None

        rows.append(
            AreaRow(
                act=act,
                area_name=name,
                min_count=min_count,
                max_count=max_count,
            )
        )
    return rows


def _find_col(paths: List[str], required_parts: List[str]) -> int:
    for idx, path in enumerate(paths):
        if all(part in path for part in required_parts):
            return idx
    raise RuntimeError(f"Could not find column containing: {required_parts}")


def _find_exact_header_col(headers: List[List[str]], expected: set[str]) -> int:
    if not headers:
        raise RuntimeError("No headers available")

    col_count = len(headers[0])
    for c in range(col_count):
        values = {headers[r][c] for r in range(len(headers)) if headers[r][c]}
        if values & expected:
            return c
    raise RuntimeError(f"Could not find expected header column: {expected}")


def _find_hell_champ_cols(headers: List[List[str]]) -> tuple[int, int]:
    if len(headers) < 3:
        raise RuntimeError("Expected at least 3 header rows for Champion/Unique columns")

    col_count = len(headers[0])
    for c in range(col_count):
        if (
            headers[0][c] == "champion and unique"
            and headers[1][c] == "h"
            and headers[2][c] == "min"
            and c + 1 < col_count
            and headers[0][c + 1] == "champion and unique"
            and headers[1][c + 1] == "h"
            and headers[2][c + 1] == "max"
        ):
            return c, c + 1

    raise RuntimeError("Could not find Champion and Unique Hell Min/Max columns")


def main() -> None:
    all_rows: List[AreaRow] = []
    for act in range(1, 6):
        all_rows.extend(parse_act(act))

    root = Path(__file__).resolve().parent.parent

    all_out = [asdict(row) for row in all_rows]
    all_path = root / "data" / "hell_areas.json"
    all_path.write_text(json.dumps(all_out, indent=2), encoding="utf-8")

    tracked_out = [asdict(row) for row in all_rows if row.min_count is not None and row.max_count is not None]
    tracked_path = root / "data" / "hell_targets.json"
    tracked_path.write_text(json.dumps(tracked_out, indent=2), encoding="utf-8")

    print(f"Wrote {len(all_out)} rows to {all_path}")
    print(f"Wrote {len(tracked_out)} rows to {tracked_path}")


if __name__ == "__main__":
    main()
