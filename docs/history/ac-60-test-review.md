# Test & Review: Import/export of a game profile (G#60)

## Scope
Covers every acceptance criterion in `docs/spec.md` for export/import of a
single game's full stored settings (clicking fields, macros, hotkey) via
`tkinter.filedialog`, the `_sanitize_game_entry()` extraction, and the
sidebar-footer UI surface specified in `docs/design.md`. Diff reviewed:
`afk_clicker.py` (233 lines changed) and `tests/test_ui.py` (299 lines
changed), both uncommitted on `feature/ac-60/import-export-game-profile`.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Export writes envelope (`kind`, `profile_version`, `app_version`, `name`, `game` minus `_profile`, macros/hotkey as-is) | Automated | pass | `ExportedGames.test_export_writes_the_envelope_for_the_selected_game`, `test_export_strips_profile_bookkeeping_for_a_custom_game` — ran: `DISPLAY=:99 .../python3 -m unittest tests.test_ui.ExportedGames -v` → OK |
| 2 | Export save dialog cancelled → no file, no status | Automated | pass | `test_cancelled_export_writes_no_file_and_shows_no_status`, `test_cancelling_a_second_export_clears_a_previous_status` → ok |
| 3 | Well-formed import → new custom game, selected, fields/macros/hotkey match | Automated | pass | `ImportedGames.test_import_creates_a_new_selected_custom_game_matching_the_file`, `test_a_well_formed_hotkey_round_trips` (ran for real, not skipped — Linux) → ok |
| 4 | Name collision → disambiguated, existing game untouched | Automated | pass | `test_import_disambiguates_a_colliding_display_name` → ok |
| 5 | Malformed macro/hotkey dropped, rest imports, no exception | Automated | pass | `test_a_malformed_macro_is_dropped_the_rest_still_imports`, `test_a_malformed_hotkey_is_dropped_the_rest_still_imports` → ok |
| 6 | Not-JSON / wrong `kind`/`profile_version` → refused, no game, failure shown | Automated | pass | `test_not_valid_json_is_rejected`, `test_wrong_kind_is_rejected`, `test_wrong_profile_version_is_rejected` → ok |
| 7 | Import dialog cancelled → nothing changes | Automated | pass | `test_cancelled_import_changes_nothing` → ok |
| 8 | Minecraft import never shows Eating panel, keys still present in storage | Automated | pass (see Finding/judgment-call note below) | `test_imported_from_minecraft_does_not_show_the_eating_panel` → ok |
| 9 | Export write failure → no partial file, failure shown | Automated | pass, **and verified the test actually detects a regression** | `test_export_write_failure_leaves_no_partial_file_and_shows_failure`; I reverted the atomic-write/cleanup logic in a scratch copy of `afk_clicker.py`, re-ran this one test, and it failed (`AssertionError: True is not false` on the tmp-file-removed assertion), then restored the real file and reran the full 21 to confirm no damage |
| 10 | `_sanitize_game_entry()` extraction is behavior-preserving | Automated + manual diff read | pass | `StoreMacroFiltering` (4 tests) and `SettingsSchemaVersion`'s hotkey tests (4 tests) pass unmodified; `git diff` shows the two inline blocks replaced by one `_sanitize_game_entry(game)` call per game with identical logic, no semantic change (per-game order doesn't matter since each game's processing is independent) |
| 11 | No `tkinter.filedialog` precedent elsewhere in the codebase | Manual (grep) | pass | `grep -rn filedialog afk_clicker.py tests/` shows only the one new import + two new call sites |
| 12 | Untrusted import data cannot write outside intended locations or crash | Manual code trace | pass | Game id/macros/hotkey go through `_sanitize_game_entry()`/`_validate_macro()`/`Hotkey.from_json()` (bounded step count, bounded chord length, reject-not-coerce); no untrusted value is ever used as a filesystem path; scalar fields that bypass validation at load time are coerced safely at display/persist time by pre-existing `fmt_num()` (catches `TypeError`/`ValueError`, never raises), `_num()` (same), and `Segmented._paint()` (`except ValueError: idx = 0`) — traced each, none can raise on garbage input |
| 13 | Vertical-budget risk (two new buttons + 2-line status at 130%, many games) doesn't clip `settings_item` | Manual, reproduced independently | pass | Wrote a throwaway script (not committed) constructing the app at `ui_scale=130` with 11 games (2 built-in + 9 added via `_add_game`) and a failure status set: got `s=1.355`, window height 1002, side height 932, `settings_item` bottom=857 — **matches the developer's reported numbers exactly** |
| 14 | Collapsed-rail glyphs (`+`/`↑`/`↓`) and status glyph (`OK`/`!`, not colour alone) | Manual, reproduced independently | pass | Reproduced the rail collapse via a real resize below `RAIL_COLLAPSE_THRESHOLD` (not a manual attribute poke, which `_rebuild_ui()` silently overrides from live geometry) — got `['+', '↑', '↓']` and status text `'!'` with `fg=#f06262` (BAD) |
| 15 | WCAG contrast ratios claimed in `docs/design.md` | Manual, recomputed from literal hex | pass | Recomputed relative-luminance contrast from the literal `THEMES` hex values independently (own script, linearised sRGB, `L`, ratio formula) — every pairing reproduces design.md's numbers almost exactly (13.32 vs 13.33, 5.22, 8.15, 17.43, 5.11, 5.05, 4.28, 4.22, 5.67) and all claimed AA passes are real passes |
| 16 | Two pre-existing tests modified for the new sidebar widgets are legitimate, not papered over | Manual diff read + run | pass | `RailCollapse.test_add_current_game_button_survives_collapse` now asserts the full ordered glyph list `["+", "↑", "↓"]` instead of a bare count of 1 — strictly more specific, still fails if ordering or glyphs regress. `SettingsNavigation.test_sidebar_no_longer_holds_the_update_widgets` now expects `self.ui.profile_io_label` alongside `count_label` in the sidebar's Label list — correct, since the new status label is a real, always-built sidebar Label, and the test's actual purpose (no stray update-widget leaks into the sidebar) is unchanged |

## Regression check
Full suite, exact CI command, run twice (once before my revert-and-restore
probe, once after, to make sure the probe left nothing behind):
```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python3 -m unittest discover -s tests -t .
Ran 548 tests in 115.105s
OK (skipped=10)
```
Matches the developer's reported 548 (527 pre-existing + 21 new), 10 skips
(pre-existing macOS-only guards). `git diff --stat afk_clicker.py` after my
probe-and-restore matches the original diff exactly (233 lines changed) —
confirmed no corruption from the revert test.

No lint/type-check step exists in this project's CI (`.github/workflows/ci.yml`
runs only `unittest discover`) — nothing additional to run there.

## Spec coverage
Every acceptance criterion in `docs/spec.md` maps to a passing automated test
(see table above, rows 1–9) plus the two refactor-preservation criteria (row
10). The one deliberately-flagged interpretation question — does the
Minecraft-import criterion's "even though `eat_mode`/`eat_every`/`eat_hold` are
still present in its stored data" require the *value* to survive — I checked
against the spec text itself, not just the developer's framing: `docs/spec.md`
lines 196-203 (the "Proposed approach" section, written before any code existed)
already states this exact consequence explicitly and calls it "deliberate, not
a gap," and the acceptance criterion's own wording ("still present," not
"unchanged" or "preserved") was written to match that already-decided
mechanism. This is a pre-approved product decision baked into the spec itself,
not an interpretation the developer invented downstream — I'm treating it as
satisfied, not a gap worth blocking on.

## Findings (most severe first)

No must-fix or should-fix findings. Two nits:

### 1. A few validation branches in `import_game()` have no dedicated test — nit
- File: `afk_clicker.py:4604-4610` (the combined validation `if`)
- The compound rejection check covers six conditions (`not dict`, wrong
  `kind`, wrong `profile_version`, `name` not a non-empty str, `game` not a
  dict) but only three of the six (not-JSON → not-a-dict, wrong `kind`, wrong
  `profile_version`) have their own test. A well-formed JSON file missing
  `name` or `game`, or with `name: ""`, would currently be rejected correctly
  (traced by hand) but isn't independently exercised.
- Not a code bug — just a coverage gap on an already-correct compound
  condition. Worth a follow-up test, doesn't block.

### 2. Disambiguated name can exceed the 28-char display convention — nit
- File: `afk_clicker.py:4625-4629`
- `name = blob["name"].strip()[:28]` truncates first, then the collision loop
  appends `" (2)"`, `" (3)"`, ... afterward, so a name that was exactly 28
  chars and collides becomes up to 32 chars. `_add_game()` (the precedent this
  mirrors) never hits this because it has no disambiguation suffix at all — it
  just selects the existing game on collision instead. Purely cosmetic (sidebar
  row width/wrapping), no crash, no data-safety issue. Not worth blocking;
  flag for ux-designer if it's ever visibly ugly in practice.

## Follow-ups (non-blocking)
- Consider a test for the untested `name`/`game` validation branches noted in
  Finding 1.
- The pre-existing, unrelated `pytest-subtests` ordering artifact the
  developer found in `Themes.test_module_globals_still_ship_dark_only` (only
  under a bare `pytest` run of `test_ui.py` alone, not under this project's
  actual CI invocation) is out of scope here and was not touched — noting it
  only so it isn't mistaken for something this cycle introduced.

## Overall verdict
**Approve.** All spec acceptance criteria are implemented and covered by
passing automated tests I ran myself this session; the full existing suite
(548 tests) passes unmodified; the `_sanitize_game_entry()` refactor is
confirmed behavior-preserving; the import path's untrusted-data handling,
atomic-write safety, vertical-budget risk, collapsed-rail behavior, and
WCAG contrast claims were all independently reproduced rather than taken on
trust. The two nits above don't block.
