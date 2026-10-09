# Spec: Import/export of a game profile (G#60)

## Summary
Add "Export" and "Import" actions that write/read a single game's full settings
(clicking fields, macros, hotkey) as a standalone JSON file, so a known-good
configuration can be shared or restored, for any built-in or custom game,
always landing as a new custom game on import.

## Goals
- Export the currently-selected game's complete stored settings (clicking
  fields + macros + hotkey) to a JSON file the user picks via a native file
  dialog.
- Import that file back, creating a brand-new custom game profile pre-filled
  with the exported values -- never overwriting an existing game.
- Reuse this app's existing validation, atomic-write, and custom-game-creation
  machinery rather than inventing parallel versions of any of it.

## Non-goals
- No cloud/online sharing -- local file only.
- No "overwrite an existing game" import mode -- import is always additive
  (a new custom game), never a target picker.
- No multi-profile/export-all bundle -- one game per file, matching the
  ticket's "a game profile" (singular).
- No preview/diff UI before import beyond the resulting sidebar entry itself.
- No profile-format migration framework -- only `profile_version == 1` is
  accepted; a migration path is added if/when a version 2 is ever needed
  (YAGNI).
- Does not touch `appearance`, `ui_scale`, or any other top-level (non-per-game)
  `Store` field.
- Does not change what "custom" means, or add any new delete/edit affordance
  for built-in profiles.

## Background / current state
- `Store` (`afk_clicker.py:1691-1818`) is the existing JSON settings store
  (`config_path()`, `:1561`), already schema-versioned via `SETTINGS_VERSION`
  (`:1571`) with a migration chain (`_run_settings_migrations`, `:1670`).
  `Store.__init__` (`:1694-1772`) loads `games` and then runs two defensive
  per-game sanitize passes inline: macros through `_validate_macro()`
  (`:1731-1735`, validator itself at `:760-798`) and the per-game `hotkey`
  blob through `Hotkey.from_json()`/`.to_json()` (`:1744-1751`, validator at
  `:511-574`). Both follow the same contract: reject-and-drop a malformed
  entry, never coerce it into something plausible-but-wrong.
- A per-game stored dict's known scalar fields are `click_ms`, `jitter_ms`,
  `autostop_min`, `click_mode`, `left_enabled`, `right_enabled`,
  `right_click_ms`, `right_jitter_ms`, `eat_mode`, `eat_every`, `eat_hold`
  (built in `_persist()`, `:4422-4435`) plus `macros` (list) and `hotkey`
  (dict), and, only for a custom game, `_profile` (`:4437-4439`, that game's
  own `{id, name, title}` bookkeeping -- irrelevant to any other game).
  `Store.put_game()` (`:1799-1814`) merges rather than replaces, specifically
  so `macros`/`hotkey` survive a plain clicking-field save untouched.
- Scalar fields are **never range/type-validated at load time** -- `_select()`
  (`:4253-4331`) merges `profile["defaults"]` with whatever is stored
  (`:4266-4268`) and feeds it through `_num()`/`fmt_num()` when filling the
  widgets, which already coerces any garbage value to something safe, then
  `_persist()`'s own tail call (`:4331`) immediately writes the coerced value
  back. This is the exact same safety net "Add current game" already relies
  on for a freshly-defaulted profile -- no new scalar validation is needed for
  import either.
- `PROFILES`/`make_profile()` (`:1829-1865`) distinguish built-in from custom:
  only the two hardcoded `PROFILES` entries (`minecraft`, `global`) exist up
  front; every other game is created via `make_profile()`, which always sets
  `"custom": True` and `"eating": False`. `profile.get("custom")` (not the
  `"custom:"` id prefix) is the actual flag every caller checks
  (`GameItem.__init__`, `:2547`; `_delete_game`, `:2470`).
- `add_current_game()`/`_add_game()` (`:4442-4461`) is the existing "create a
  new custom game" flow: scan the foreground window title, trim to 28 chars,
  build `game_id = "custom:" + name.lower()`, skip creation and just select if
  that id already exists, otherwise `make_profile()` + append to
  `self.profiles`/`self.by_id` + `_rebuild_list()` + `_select()`.
- The sidebar footer already has one global action button under the game
  list: `Button(side, add_label, self.add_current_game, s, width=rail_w - 28)`
  (`:3387-3388`), right above a divider and the Settings entry. `Button`
  itself is `afk_clicker.py:2067-2112` (canvas-based, `width`/`primary` kwargs).
- `Store.save()` (`:1774-1794`) already writes atomically: `path + ".tmp"`,
  then `os.replace()`, with the tmp file cleaned up on a failed write. This is
  the pattern to mirror for the export file write, not a new one.
- No `tkinter.filedialog` call exists anywhere in this codebase yet (checked);
  every existing dialog (`HotkeyRecorder`, the macro editor `:5512`, the
  update-log viewer) is a custom in-app `tk.Toplevel` form, not a file picker.
  `tkinter.filedialog` (stdlib) is the right tool for "pick a file path" --
  none of the existing Toplevel forms are a precedent for that, they solve a
  different problem.
- Hotkey/macro collisions across games are **already a tolerated, by-design
  case**, not something this feature needs to solve: `_migrate_settings_v2_to_v3`'s
  own docstring (`:1638-1658`) states "a duplicate chord across games is
  harmless... only the selected game's watcher is ever armed", and
  `_arm_toggle_hotkey()`/`_arm_macro_hotkeys()`/`_arm_macro_intervals()`
  (`:5280, :5341, :5372`, all called from `_select()`, `:4317-4324`) only ever
  arm the *currently selected* game's chords. So an imported game sharing a
  hotkey or a macro id with some other existing game is a non-event -- no new
  collision-detection/stripping logic is needed, and macros/hotkey are
  therefore included in export by default (see "Proposed approach").
- `docs/ROADMAP.md:88` lists this under "Later"; `backlog.md`'s "In progress"
  section already tracks G#60/GH#106 against this branch.

## Proposed approach

### Export format
A small JSON envelope, versioned independently of `SETTINGS_VERSION` (a
different artifact with its own evolution):
```json
{
  "kind": "afk-clicker-game-profile",
  "profile_version": 1,
  "app_version": "0.9.0",
  "name": "Minecraft",
  "game": { "click_ms": 650, "jitter_ms": 0, "...": "...", "macros": [...], "hotkey": null }
}
```
- `"game"` is `dict(self.store.game(self.current))` with the `"_profile"` key
  stripped (source-game bookkeeping, meaningless to the importer, which mints
  its own). Nothing else is stripped: macros and hotkey are included as-is
  (see "Background" on why collisions are a non-issue).
- `"name"` is `self.by_id[self.current]["name"]` -- the display name, which is
  never itself stored in the per-game dict for a built-in profile (it only
  lives in the hardcoded `PROFILES` entry), so it has to be carried at the
  envelope level, not inside `"game"`.
- `__version__` (`:915`) is informational only, never checked on import.

### Export action
New method `export_current_game()` on `AfkAutoclicker`:
1. `tkinter.filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Clickwork game profile", "*.json")], initialdir=os.path.dirname(config_path()), initialfile=f"{slug(name)}.json")`
   where `slug()` is a one-line `name.lower().replace(" ", "-")` (nothing
   fancier -- it only seeds the save dialog's default filename, the user can
   type anything).
2. Empty result (cancelled) -> return, no-op, no feedback shown.
3. Build the envelope above; write it the same atomic way `Store.save()`
   already does (`path + ".tmp"` then `os.replace()`, `:1774-1794`) -- do not
   call `Store.save()` itself, this is a different file.
4. On success/failure, flash a short status the same way `_add_game()`
   already does on `self.game_state` (`:4450`, `fg=BAD` for failure; use `OK`
   for success) -- exact wording/placement is ux-designer's call, the
   mechanism is this existing label.

### Import action
New method `import_game()` on `AfkAutoclicker`:
1. `tkinter.filedialog.askopenfilename(filetypes=[("Clickwork game profile", "*.json")], initialdir=os.path.dirname(config_path()))`.
2. Empty result (cancelled) -> return, no-op.
3. Read and `json.load()` the file (wrap in `try/except (OSError, ValueError)` ->
   treat as "invalid file", go to step 6's failure path).
4. Validate the envelope, reject-not-coerce, same contract as every other
   loader in this file:
   - top level must be a `dict`
   - `blob.get("kind") == "afk-clicker-game-profile"`
   - `blob.get("profile_version") == 1` (exactly -- not `<=`, there is no
     older or newer version to tolerate yet)
   - `blob.get("name")` is a non-empty `str`
   - `blob.get("game")` is a `dict`
   Anything else -> failure path (step 6).
5. Sanitize `"game"` through a **new shared helper**, `_sanitize_game_entry(game)`,
   factored out of `Store.__init__`'s existing inline macros/hotkey filtering
   (`:1731-1751`) so both callers (the normal settings load, and this import
   path) run the exact same validation instead of two copies of it:
   ```python
   def _sanitize_game_entry(game):
       macros = game.get("macros")
       if isinstance(macros, list):
           game["macros"] = [m for m in (_validate_macro(raw) for raw in macros) if m is not None]
       elif "macros" in game:
           del game["macros"]
       hotkey_blob = game.get("hotkey")
       if hotkey_blob is not None:
           validated = Hotkey.from_json(hotkey_blob)
           if validated is not None:
               game["hotkey"] = validated.to_json()
           else:
               del game["hotkey"]
       return game
   ```
   `Store.__init__`'s own two blocks (`:1731-1751`) become `for game in
   self.data["games"].values(): _sanitize_game_entry(game)`. No behavior
   change there -- pure extraction.
6. On any validation/read failure: flash a failure status on `self.game_state`
   (same mechanism as export), create nothing, return.
7. On success: derive a unique custom id/name exactly like `_add_game()` does,
   plus disambiguation on collision:
   ```python
   name = blob["name"].strip()[:28]
   candidate, n = name, 1
   while ("custom:" + candidate.lower()) in self.by_id:
       n += 1
       candidate = f"{name} ({n})"
   game_id = "custom:" + candidate.lower()
   ```
   (Pull `game_id = "custom:" + x.lower()` into a one-line helper shared with
   `_add_game()` if that reads cleaner -- not load-bearing either way.)
8. `profile = make_profile(game_id, candidate, candidate)`; append to
   `self.profiles`/`self.by_id` exactly like `_add_game()` (`:4457-4459`).
9. `self.store.game(game_id).update(_sanitize_game_entry(dict(blob["game"])))`
   -- pre-seed the store entry *before* selecting, so `_select()`'s existing
   merge-from-defaults + widget-fill + `_persist()` tail (`:4266-4331`)
   naturally coerces every scalar field and writes it back, exactly as it
   already does for "Add current game". No new scalar validation is written.
10. `self._rebuild_list()`; `self._select(game_id)`; flash a success status.

Because `make_profile()` always sets `"eating": False` (`:1863`), an imported
profile -- even one exported from the built-in Minecraft profile -- never
shows the Eating panel. This is **deliberate**, not a gap: it's the exact same
rule every other custom game already lives under (`_select()`'s
`self.eat_mode.set(values["eat_mode"] if profile["eating"] else "off")`,
`:4279`); the raw `eat_mode`/`eat_every`/`eat_hold` values still ride along in
storage harmlessly, same as they would for any custom game that happens to
have them set.

### UI surface
Two new buttons, "Export" and "Import", in the sidebar footer, directly below
the existing "Add current game" button (`:3386-3388`), using the same `Button`
widget. Rationale: export acts on `self.current` (whichever game is currently
selected) -- the sidebar footer is the only place that selection context is
already naturally in scope at the top level (Settings has no notion of "the
current game"); import is scope-free (always creates a new game), the same
scope "Add current game" already has one row above it. Exact pixel layout
(side-by-side split of the existing button's width vs. stacked, and what the
collapsed rail shows instead of full labels, mirroring `add_label = "+" if
self._rail_collapsed else "Add current game"` at `:3386`) is ux-designer's
call in `docs/design.md`, not decided here.

## Affected areas
- `afk_clicker.py`:
  - `Store.__init__` (`:1724-1751`): extract into new `_sanitize_game_entry()`
    helper (pure refactor, no behavior change), placed near `_validate_macro`/
    `Hotkey` (e.g. just above `Store`, around `:1690`).
  - New constants near `SETTINGS_VERSION` (`:1571`): `PROFILE_EXPORT_KIND =
    "afk-clicker-game-profile"`, `PROFILE_FORMAT_VERSION = 1`.
  - New `AfkAutoclicker` methods: `export_current_game()`, `import_game()`
    (near `add_current_game()`/`_add_game()`, `:4442-4461`).
  - Sidebar footer build (`:3386-3388`): two new `Button` widgets wired to the
    methods above.
  - `import os` already present; add `import tkinter.filedialog` (or
    `from tkinter import filedialog`) at the top with the other imports.
- `tests/test_ui.py`: new tests near the existing `Store`/migration/macro-
  validation tests (`:604-890`) for `_sanitize_game_entry()`, and near the
  existing add/delete-game tests (`:399-430`, and the `_add_game`/`_delete_game`
  call sites) for `export_current_game()`/`import_game()`. Mock
  `tkinter.filedialog.askopenfilename`/`asksaveasfilename` directly (patch the
  module-level function) rather than driving a real file-picker widget under
  Xvfb -- this is the standard, already-idiomatic way the test suite would
  isolate a stdlib dialog call; no existing dialog in this codebase needed
  that technique before since none of them used `tkinter.filedialog`.
- No `docs/ROADMAP.md`/`backlog.md` edits are part of this spec -- that
  bookkeeping happens at merge time per this project's own workflow, not
  inside the build cycle.

## Edge cases
- Export/Import dialog cancelled (empty path returned) -> silent no-op, no
  status flashed, no file touched.
- Export write fails (permission denied, disk full) -> atomic tmp-then-replace
  means no half-written file is left at the destination; failure status shown.
- Import file is not valid JSON, or top-level isn't a dict, or `kind`/
  `profile_version` don't match exactly -> rejected outright, no game created,
  failure status shown.
- Import file's `game.macros` contains one malformed entry -> that entry is
  dropped, the rest of the macro list and all scalar fields still import
  (same partial-survival contract `Store.__init__` already gives a corrupted
  settings.json).
- Import file's `game.hotkey` is malformed -> hotkey dropped (imported game
  starts with "Not set"), scalar fields and macros still import.
- Imported name collides with an existing game's display name (built-in or
  custom) -> suffixed `" (2)"`, `" (3)"`, ... ; the existing game is never
  touched, overwritten, or merged with.
- Export of a game with no macros and no hotkey -> `"macros": []`,
  `"hotkey": null` written plainly; re-importing produces an empty-macros,
  no-hotkey custom game, no crash.
- Export/import of a *built-in* profile (Minecraft, Global) -> allowed for
  export (read-only, no risk); import of either always still lands as a new
  **custom** game (see "Proposed approach" on why the Eating panel then never
  shows).
- Two games (pre-existing and/or freshly imported) sharing the same hotkey
  chord or macro id -> no crash, no special handling needed; only the
  currently-selected game's chords are ever armed (see "Background").
- Platform differences: `initialdir` reuses `config_path()`'s own existing
  per-OS logic (`:1561-1568`) -- no new platform branching.

## Acceptance criteria
- [ ] Given any selected game (built-in or custom) and Export clicked, when a
      destination is chosen, then a JSON file is written there matching the
      envelope shape above, with `"game"` equal to that game's stored settings
      minus `"_profile"`, including its macros and hotkey as-is.
- [ ] Given Export's save dialog is cancelled, then no file is written and no
      status is shown.
- [ ] Given a previously-exported, well-formed file, when Import selects it,
      then a new custom game appears in the sidebar, selected, with its
      Clicking-tab fields, macros, and hotkey matching the exported values.
- [ ] Given an imported file's `name` collides with an existing game's display
      name, then the new game is created with a disambiguated name/id instead
      of overwriting or merging with the existing one.
- [ ] Given an imported file with one malformed macro or a malformed hotkey,
      then that field is dropped (empty list / unset) while the rest of the
      profile still imports successfully, with no exception raised.
- [ ] Given a file that is not valid JSON, or whose `kind`/`profile_version`
      don't match exactly, then Import refuses it, creates no game, and shows
      a failure indication.
- [ ] Given Import's open dialog is cancelled, then nothing changes.
- [ ] Given a profile exported from the built-in Minecraft profile is
      imported, then the resulting custom game does not show the Eating
      panel, even though `eat_mode`/`eat_every`/`eat_hold` are still present
      in its stored data.
- [ ] Given Export's write fails (e.g. unwritable destination), then no
      partial file is left and a failure indication is shown.
- [ ] `Store.__init__`'s existing macros/hotkey sanitize behavior
      (`tests/test_ui.py:856-890`, `:795-833`) is unchanged after extracting
      `_sanitize_game_entry()` -- same tests, same pass/fail outcomes.

## Open questions
None blocking. One non-blocking note: the exact pixel layout of the two new
sidebar buttons (split vs. stacked, collapsed-rail glyphs) is left to
ux-designer's `docs/design.md`, per this spec's "Proposed approach > UI
surface" -- the *location* (sidebar footer, acting on `self.current` for
export, scope-free for import) is the product decision made here and should
not be re-litigated downstream.

## Risk / rollback notes
- Pure additive feature plus one internal refactor (`_sanitize_game_entry`
  extraction) that preserves existing behavior exactly -- low risk to
  existing flows. If the extraction is ever suspect, reverting it back to
  inline code in `Store.__init__` is a mechanical, zero-risk undo.
- Import creates a new custom game, which is already deletable via the
  existing delete-glyph path (`_delete_game`, `:4463-4488`) -- a bad import is
  trivially reversible by the user without any new "undo" feature.
- No existing file, schema version, or migration path is touched -- rollback
  of this whole feature is simply removing the two new methods/buttons and the
  (behavior-preserving) refactor.
