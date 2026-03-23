# TZ Counter

Desktop tracker for Diablo II area progress using **on-screen OCR only**.

This counter doesn't not directly interact with the game at all. It takes a screenshot and reads the map info from that. If your map is not open, **it will not work**. If the portion of your screen where it expects to find map info is different than whats in the config, **it will not work**. Use the print debug artifacts button to see what the counter sees and adjust your config file accordingly.

## What this app does

- Polls a configurable top-right screen region for area text.
- Resolves the area name to a bundled Act 1-5 Hell dataset (Champion/Unique min-max only).
- Lets you increment/decrement counts with global hotkeys.
- Highlights the current area row.
- Marks rows green when counts are inside each row's min-max range.
- Saves run progress locally.

## Install

```bash
c:/python314/python.exe -m pip install -r requirements.txt
```

## Run

```bash
c:/python314/python.exe -m tz_counter
```

## Controls

Default hotkeys in `config.json`:

- increment: `ctrl+num 5`
- decrement: `ctrl+num 4`
- reset current area: `ctrl+num 8`

You can change these in `config.json`.

## Config

`config.json` is auto-created on first run.

### `config.json` options

- `ocr_interval_ms`
OCR polling interval in milliseconds.

- `stale_grace_ms`
How long to keep last valid area when map text temporarily disappears.

- `confidence_threshold`
Minimum OCR confidence (0.0-1.0) required before resolving area text.

- `terminal_print_interval_seconds`
Interval for terminal area line output.

- `print_area_to_console`
When `true`, prints periodic area lines to terminal (`Current Area: ...` or `unknown: ...`).

- `debug_print_interval_seconds`
Legacy key still accepted and synced to `terminal_print_interval_seconds` for backward compatibility.

- `save_debug_artifacts`
When `true`, writes periodic debug PNG/TXT artifacts to the `debug/` folder.

- `auto_follow_current_area`
When `true`, table scrolls/focuses the currently detected area row.

- `capture_mode`
`monitor-relative` or `absolute`.
`monitor-relative` applies `capture_left/top` relative to `monitor_index` bounds.
`absolute` uses virtual desktop coordinates directly.

- `monitor_index`
1-based monitor index used by `monitor-relative` mode.

- `capture_left`, `capture_top`, `capture_width`, `capture_height`
Capture rectangle for OCR.

- `table_row_height`
Row height for the area table.

- `hotkey_inc`, `hotkey_dec`, `hotkey_reset_current`
Global hotkey mappings.

- `hotkey_debounce_ms`
Minimum gap between repeated triggers for the same hotkey action.

### Example

```json
{
	"ocr_interval_ms": 900,
	"stale_grace_ms": 3500,
	"confidence_threshold": 0.55,
	"terminal_print_interval_seconds": 10,
	"print_area_to_console": true,
	"debug_print_interval_seconds": 10,
	"save_debug_artifacts": true,
	"auto_follow_current_area": true,
	"capture_mode": "monitor-relative",
	"monitor_index": 2,
	"capture_left": 3318,
	"capture_top": 35,
	"capture_width": 507,
	"capture_height": 447,
	"table_row_height": 64,
	"hotkey_inc": "ctrl+num 5",
	"hotkey_dec": "ctrl+num 4",
	"hotkey_reset_current": "ctrl+num 8",
	"hotkey_debounce_ms": 250
}
```

### OCR backend requirements

- `pytesseract` is included in `requirements.txt`.
- You must also have the native Tesseract executable installed and available on `PATH` (or configured explicitly).
- If no OCR backend is available, the app will show `engine=none` in status/debug.

## Data

- `data/hell_targets.json`: tracked rows (areas with Hell champion/unique min-max values).
- `data/hell_areas.json`: full area catalog (including areas without elite counts) used for area identification.

The table UI stays filtered to tracked rows, but OCR resolution can still identify untracked areas.

To regenerate from the wiki pages:

```bash
c:/python314/python.exe scripts/generate_hell_targets.py
```

## Notes

- Global hotkeys may conflict with other apps.
- Keep game in borderless/windowed mode for easier region calibration.
- OCR accuracy depends heavily on the selected capture region.
