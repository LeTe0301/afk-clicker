# Implementation: Import/export of a game profile (G#60)

## Summary
Added "Export" and "Import" buttons to the sidebar footer, directly below
"Add current game", that write/read a single game's full stored settings
(clicking fields, macros, hotkey) as a standalone JSON file via
`tkinter.filedialog`. Export acts on `self.current`; import always creates a
brand-new custom game (never overwrites), disambiguating a colliding display
name. Feedback is a sticky status strip in the sidebar footer, per
`docs/design.md`'s override of the spec's original `game_state`-flash
proposal. `Store.__init__`'s inline macros/hotkey filtering was extracted
into a shared `_sanitize_game_entry()` helper, reused by `import_game()`.

## Root cause
N/A — this is a new feature, not a bugfix.

## Changes by file

### `afk_clicker.py`
- **`from tkinter import filedialog`** (`:40`) — new stdlib import, next to
  the existing `from tkinter import font as tkfont`. Confirmed before adding
  it that no `tkinter.filedialog` call existed anywhere in this codebase
  (per `docs/spec.md`'s own background note).
- **`PROFILE_EXPORT_KIND` / `PROFILE_FORMAT_VERSION`** (`:1695-1696`) — the
  export envelope's own `"kind"`/`"profile_version"` constants, placed right
  after `_run_settings_migrations()` and before the new sanitize helper,
  versioned independently of `SETTINGS_VERSION`.
- **`_sanitize_game_entry(game)`** (`:1699-1716`), new module-level function
  — extracted verbatim (behavior-preserving) from `Store.__init__`'s two
  inline macros/hotkey filtering blocks. Mutates and returns `game`.
- **`Store.__init__`** (around `:1755-1763`) — the two inline `for game in
  self.data["games"].values(): ...` blocks (macros filter, hotkey filter)
  collapsed into one loop calling `_sanitize_game_entry(game)`. Pure
  refactor; `StoreMacroFiltering` and `SettingsSchemaVersion`'s own hotkey
  tests (`tests/test_ui.py`) pass unchanged, proving no behavior moved.
- **`AfkAutoclicker.__init__`** — added `self._profile_io_status = None`
  (near `self._save_failed`) — a plain `(message, ok)` tuple or `None`,
  survives `_rebuild_ui()` since it isn't a Tk object.
- **`_build_ui()` sidebar block** (right after the existing "Add current
  game" `Button`, before the footer divider) — new widgets:
  - Collapsed rail: two stacked `Button`s, `"↑"` (export) / `"↓"` (import),
    width 36, direct children of `side`, mirroring how "Add current game"
    already collapses to `"+"`.
  - Expanded: a `tk.Frame` row holding "Export"/"Import" `Button`s side by
    side, each `width=(rail_w-28-6)//2` (87px at 100%), `padx=(int(6*s), 0)`
    between them — **using `int(6*s)` at every scale step**, per the
    orchestrator's correction to design.md's own flagged arithmetic error
    (design.md's table literally wrote 7px/8px for the 115%/130% steps;
    the gap is `int(6*s)` uniformly, same as every other `*s`-scaled gap in
    this file).
  - `self.profile_io_label`, a `tk.Label` with `bg=CARD` (not `BG` — see
    "Key decisions" below), built every `_build_ui()` call and immediately
    repainted via `self._paint_profile_io_status()`.
- **`export_current_game()`** (`:4551-4591`), new `AfkAutoclicker` method —
  `asksaveasfilename` (defaultextension `.json`, `initialdir` from
  `os.path.dirname(config_path())`, `initialfile` from a one-line slug of
  the game's display name); empty result → `_note_profile_io(None)`
  (cancel clears any earlier status) and return. Builds the envelope from
  `dict(self.store.game(self.current))` minus `"_profile"`, with `"macros"`/
  `"hotkey"` defaulted to `[]`/`None` via `setdefault` (a game that never had
  either saved has neither key in storage at all — written plainly anyway,
  per the spec's own edge case). Writes atomically (`path + ".tmp"` then
  `os.replace()`, mirroring `Store.save()`, not calling it). Success →
  `Exported "<name>"` (OK); write failure → `Export failed: couldn't write
  the file` (BAD), tmp file removed.
- **`import_game()`** (`:4593-4639`), new `AfkAutoclicker` method —
  `askopenfilename`; empty result → `_note_profile_io(None)`, return.
  `json.load()` wrapped in `try/except (OSError, ValueError)`. Envelope
  validated exactly as specified (dict, `kind`, `profile_version == 1`
  exactly, non-empty `name` string, `game` dict) — any failure → `Import
  failed: not a valid game profile file` (BAD), no game created. On success:
  disambiguates the display name against every existing `by_id` key (`" (2)"`,
  `" (3)"`, ...), builds the new custom profile via `make_profile()`, pre-seeds
  the store entry through `_sanitize_game_entry(dict(blob["game"]))` *before*
  `_select()` so the existing defaults-merge + widget-fill + `_persist()` tail
  coerces every scalar field (same mechanism "Add current game" already
  relies on — no new scalar validation written), then `_rebuild_list()` +
  `_select(game_id)` + success status `Imported as "<name>"` (set *after*
  `_select()`, so the selection's own repaint doesn't clobber it).
- **`_note_profile_io(message, ok=None)`** (`:4641-4649`) — records
  `self._profile_io_status` and repaints immediately. `message=None` clears
  (cancel).
- **`_paint_profile_io_status()`** (`:4651-4666`) — shows/hides
  `self.profile_io_label` from `self._profile_io_status`; collapsed rail
  shows `"OK"`/`"!"` (glyph + colour, not colour alone), expanded shows the
  full message. No `self._rebuilding` guard needed (unlike
  `_paint_save_notice()`): `profile_io_label` lives in the sidebar, which is
  always built, not gated on Settings being open.

### `tests/test_ui.py`
- **`SanitizeGameEntry`** (new `unittest.TestCase`, after `StoreMacroFiltering`)
  — 5 direct unit tests on `app._sanitize_game_entry()` (well-formed survives,
  malformed macro dropped, non-list macros dropped not coerced, corrupt
  hotkey dropped, missing hotkey left absent). No Tk needed.
- **`ExportedGames`** (new `UITestCase`, after `DeletedGames`) — 6 tests:
  envelope shape/content for a built-in game, `_profile` stripped for a
  custom game, success status text/colour, cancelled export writes no file
  and shows no status, a cancelled *second* export clears a previous status,
  write failure (via the same `app.os.replace`-raises monkeypatch technique
  `SaveFailureNotice` already uses) leaves no partial file and shows the
  failure status. `filedialog.asksaveasfilename` is patched directly
  (saved/restored in `setUp`/`tearDown`), per this repo's no-`unittest.mock`
  convention.
- **`ImportedGames`** (new `UITestCase`, after `ExportedGames`) — 11 tests
  covering every acceptance criterion: new selected custom game matching
  the file, name-collision disambiguation (existing game untouched),
  malformed macro dropped / rest imports, malformed hotkey dropped / rest
  imports, a well-formed hotkey round-trips (`@needs_input_permission` —
  see below), not-valid-JSON / wrong `kind` / wrong `profile_version` all
  rejected with no game created, a cancelled import changes nothing, and an
  imported "Minecraft" profile never shows the Eating panel (while
  `eat_every`/`eat_hold` still survive in storage — `eat_mode` itself does
  **not** survive as `"pause"`; see "Key decisions" below).
- **`RailCollapse.test_add_current_game_button_survives_collapse`** — updated:
  the collapsed rail now has 3 direct `Button` children (`"+"`, `"↑"`,
  `"↓"`), not 1; asserts the full ordered glyph list instead of a bare count.
- **`SettingsNavigation.test_sidebar_no_longer_holds_the_update_widgets`** —
  updated: Export/Import live inside their own row `Frame` (so the direct
  sidebar `Button` count is still 1), and the expected label list now
  includes `self.ui.profile_io_label` alongside `self.ui.count_label`.

## Key decisions / tradeoffs
- **Status mechanism**: built to `docs/design.md`'s sidebar status strip,
  not the spec's original `self.game_state` flash — both documents already
  flag this as a verified, pre-approved technical correction (`_mark_running()`
  rewrites `game_state` every 5s; it isn't a live widget while Settings is
  open), not a product decision re-litigated here.
- **Export/Import row gap**: `int(6*s)` at every scale step, per the explicit
  correction to design.md's own flagged table error (7px/8px at 115%/130%
  would have been a one-off special case inconsistent with every other
  `*s`-scaled gap in this file).
- **`eat_mode` does not survive import from Minecraft as `"pause"`** — verified
  directly against the running app (not assumed from reading): `_select()`'s
  own fill forces the widget to `"off"` for any non-eating profile
  (`self.eat_mode.set(values["eat_mode"] if profile["eating"] else "off")`),
  and its tail `_persist()` call then writes that `"off"` back to storage.
  Only `eat_every`/`eat_hold` (ordinary widget-backed numeric fields) survive
  the import with their original values. The spec's acceptance criterion
  ("even though `eat_mode`/`eat_every`/`eat_hold` are still present in its
  stored data") is satisfied literally — all three keys are present — but
  `eat_mode`'s *value* changes to `"off"` as an unavoidable consequence of
  the spec's own mandated mechanism (pre-seed the store, then let `_select()`'s
  existing merge/coerce/persist tail run unmodified). This is not a new
  design choice; it is what the spec's own step 9 ("No new scalar validation
  is written") produces when run against this file.
- **Export always writes `"macros": []` / `"hotkey": null`** even when the
  source game never had either key in storage (via `.setdefault()`) — matches
  the spec's literal envelope example and its "Export of a game with no
  macros and no hotkey" edge case; without this, a never-customized game's
  export would silently omit both keys instead of writing them plainly.
- **No `_rebuilding` guard on `_paint_profile_io_status()`**: unlike
  `_paint_save_notice()` (gated on the Appearance pane existing, which is
  torn down when Settings is closed), `profile_io_label` lives in the
  sidebar, which `_build_ui()` always constructs — there is no window where
  export/import's own button-click handler could run while the sidebar is
  mid-teardown.

## Deviations from spec
Both deviations below were pre-approved by the orchestrator before this
cycle started (per the task brief), not independent judgment calls made
during implementation:
1. **Feedback mechanism** — built to `docs/design.md`'s sidebar status strip
   instead of the spec's `self.game_state` flash proposal (see "Key
   decisions" above and `docs/design.md`'s own "Summary" section for the
   full verified reasoning).
2. **Row gap arithmetic** — `int(6*s)` at every scale step, not the literal
   7px/8px design.md's own table wrote for 115%/130% (design.md's own report
   flagged this as its own error).

No other deviation from `docs/spec.md` or `docs/design.md`.

## Known limitations
- `Button` (canvas-based, pre-existing) takes no keyboard focus — Export and
  Import inherit this pre-existing gap, explicitly called out as out of
  scope in `docs/design.md`'s Accessibility section.
- No visual confirmation of the rendered strip/rail glyphs on a real Windows
  or macOS display — verified structurally (text/colour/pack state) under
  Xvfb only, per `docs/design.md`'s own "Web vs. native differences" note
  that no visual test is possible there.
- The vertical-budget risk `docs/design.md` flagged was checked directly
  (see "How to verify locally" below) and does not clip at 130% with 11
  games and a two-line failure status showing; `WINDOW_MIN_H` was left
  unchanged (740) since no clipping was observed.

## How to verify locally
Environment (this repo's convention — a venv with `pynput` + Xvfb, started
directly, not via `xvfb-run`):
```
Xvfb :99 -screen 0 1280x1024x24 &   # already running in this session
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python3 -m unittest discover -s tests -t .
```

### This ticket's own tests
```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python3 -m unittest \
    tests.test_ui.SanitizeGameEntry tests.test_ui.ExportedGames tests.test_ui.ImportedGames -v
# Ran 21 tests, OK
```

### Full suite result (this session, matching CI's own invocation exactly)
```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python3 -m unittest discover -s tests -t .
Ran 548 tests in 114.422s
OK (skipped=10)
```
548 = the pre-existing 527-test baseline + 21 new tests this cycle. The 10
skips are the pre-existing macOS-only `needs_input_permission` guards,
unchanged by this cycle.

(A `pytest`-driven run of `tests/test_ui.py` alone shows 11 unrelated
pre-existing `Themes.test_module_globals_still_ship_dark_only` sub-failures —
confirmed, by running the identical command against `main` before any change
in this cycle, to be a pre-existing `pytest-subtests`-plugin ordering
artifact against this file's module-level theme globals, not something this
cycle introduced or something `unittest discover` — this project's actual
CI runner — reproduces. Not touched, per minimal-diff discipline; out of
this ticket's scope.)

### Vertical-budget check (docs/design.md's flagged risk)
```python
# ui_scale="130", 11 games (2 built-in + 9 added), failure status showing:
window height: 1002   s: 1.355   rail_collapsed: False
side height: 932
settings_item: y=806 height=51 -> bottom=857   (857 < 932, not clipped)
list_frame: natural child height 561 < frame height 625 (all 11 rows mapped)
```
No clipping observed; `WINDOW_MIN_H` left at 740.

### Collapsed-rail smoke check
```python
rail_collapsed: True
button texts: ['+', '↑', '↓']
profile_io_label text: '!'   mapped: True
```

### Verification of scope
```
git status --short
 M afk_clicker.py
 M tests/test_ui.py
?? docs/design.md
?? docs/implementation.md
?? docs/spec.md
```
No file outside `afk_clicker.py`/`tests/test_ui.py` was touched by the code
change itself; no scratch file was left in the repo tree (ad-hoc verification
scripts were run as inline `python3 - <<'EOF'` heredocs against temp
directories, never written into the working tree).
