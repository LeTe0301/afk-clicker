# Spec: Per-game hotkeys (G#57)

## Summary
Turn the single toggle hotkey (`self.hotkey`/`store.data["hotkey"]`, armed by one `HotkeyWatcher` regardless of which game is selected) into a per-game, optional value — stored on each game's own settings block, re-armed on every game switch, with no cross-game fallback — reusing the macros feature's own "rebuild watchers on `_select()`" lifecycle, but with one deliberate deviation: a same-game rebuild must not tear down and recreate the live listener, because an existing test (`HotkeyListenerSurvivesRebuild.test_listener_object_identity_is_unchanged_across_a_rebuild`, `tests/test_ui.py:5851`) already asserts object identity survives a theme/scale rebuild.

## Goals
- Each game gets its own optional toggle hotkey, stored on its own settings entry, independent of every other game's.
- Only the currently-selected game's hotkey is ever armed — switching games disarms the old one and arms the new one, mirroring `_arm_macro_hotkeys()`'s existing per-game rebuild-on-switch lifecycle (`afk_clicker.py:5184-5213`).
- Existing users with a configured hotkey keep it working, unchanged, for every game they already have configured — handled by a new settings migration, not a runtime fallback.
- The existing Hotkey tab (Record/Apply card, `afk_clicker.py:3612-3632`) stays exactly where it is and keeps its two-step Record-then-Apply interaction; only its data scope changes (per-game instead of global), plus its subtitle text.

## Non-goals
- No "global default hotkey that a per-game value can override" concept. Rejected in favor of mirroring macros' own precedent exactly (optional, per-game, no fallback layer) — see "Why not a global-default fallback" below. A fresh game starts with no hotkey, the same way a fresh game starts with no macros today.
- No collision detection/rejection between two games' hotkeys, or between a game's toggle hotkey and its own macros' hotkeys. See "Collision policy" below — this is a deliberate decision, not an oversight.
- No change to the Record/Apply two-step interaction itself, `HotkeyRecorder`, `Hotkey`, or `HotkeyWatcher` (`afk_clicker.py:462-686`) — all of these are already game-agnostic and need no change.
- No fix for the pre-existing, unrelated cosmetic gap where `self.hotkey_label` resets to its hardcoded "Not set" default text after a theme/scale rebuild and is never repainted from `self.registered_hotkey` (today's `_build_ui()` tail resyncs the status pill from `registered_hotkey` but never `hotkey_label` — confirmed by grep, there is no `_show_hotkey()` call anywhere in `_build_ui()`'s tail). Out of scope: pre-existing, not a regression this ticket introduces, not something the ticket asks for.
- No change to `_arm_macro_hotkeys()`/macro hotkeys themselves, beyond them continuing to coexist unchanged.

## Background / current state
Today, `store.data["hotkey"]` is one top-level JSON blob. `AfkAutoclicker.__init__` restores it once at startup (`afk_clicker.py:3007-3023`, after the first `_build_ui()` call) and arms a single `HotkeyWatcher` as `self.hk_listener`, calling `self.toggle` on match. The Hotkey tab's Record/Apply card (`afk_clicker.py:3612-3632`) is one of three per-game-page tabs (alongside Clicking and Macros) but is **not** actually scoped to the selected game: `apply_hotkey()` (`afk_clicker.py:5150-5180`) writes straight to `store.data["hotkey"]`, and nothing in `_select()` (`afk_clicker.py:4191-4263`) ever touches `hotkey_label`/`hk_listener`/`registered_hotkey` — the toggle fires identically no matter which game is selected.

Macros (`afk_clicker.py:5182-5341`) already solved the adjacent "per-game, optional chord" problem: each macro's hotkey lives in that game's own `"macros"` list entry, and `_arm_macro_hotkeys()`/`_disarm_macro_hotkeys()` (`afk_clicker.py:5184-5213`) rebuild the live set of `HotkeyWatcher`s for only the currently-selected game's macros, called from `_select()` (every real switch) and from `_build_content()`'s own bootstrap replay of `_select(self.current, persist=False)` (`afk_clicker.py:3395`, and the `_show_settings()`-adjacent call at `afk_clicker.py:4420`).

That bootstrap replay matters here specifically: a theme/scale change runs `_rebuild_ui()` → `_build_content()` → `_select(self.current, persist=False)` **with the same `game_id`**, not a real switch. Macros have no test asserting watcher object identity across this replay (and in fact get torn down and recreated every time, untested either way). The toggle hotkey does — `HotkeyListenerSurvivesRebuild.test_listener_object_identity_is_unchanged_across_a_rebuild` (`tests/test_ui.py:5851-5862`) asserts `self.ui.hk_listener` is the *same object* after `_apply_appearance("light")` triggers a rebuild. That test currently passes only because `_select()` never touches `hk_listener` at all today. Wiring per-game arming into `_select()` the same unconditional way macros do would start tearing the listener down and recreating it on every rebuild replay — breaking that test. See "Proposed approach" §3 for the guard that avoids this.

`SETTINGS_VERSION = 2` (`afk_clicker.py:1571`), with `_SETTINGS_MIGRATIONS = {0: ..., 1: ...}` (`afk_clicker.py:1641`) keyed by the version a file is coming *from*. Each per-game entry already carries an independently-filtered `"macros"` list (`Store.__init__`, `afk_clicker.py:1698-1711`) — "garbage type → drop it, not coerce" is the established contract for a malformed per-game sub-field.

## Why not a global-default fallback
The two live options were: (a) per-game optional, falling back to a kept-around global default when unset, or (b) per-game optional, no fallback, mirroring macros exactly. Going with (b):
- (a) needs a second stored value (the "default"), a second UI surface for editing it (since the existing Hotkey tab is already the per-game page — a "default" can't live there without being confusing about which value is being edited), and precedence logic nothing in this codebase has today.
- (b) is zero new surface: same storage shape macros already use (a field on the per-game dict, present or absent), same UI location (the existing Hotkey tab, now genuinely scoped to the selected game), same arming lifecycle macros already proved out. "Prefer zero new surface... mirror the neighbouring feature exactly" is exactly this situation.
- The real continuity concern — existing users losing a hotkey they already rely on — is handled by the migration (§1 below) carrying the old single value into every already-configured game, not by a live fallback. A brand-new game starting with no hotkey is already today's experience for a brand-new game's macros; this is consistent, not a regression.

## Collision policy
No rejection, at record time or anywhere else, for either kind of collision:
- **Two different games sharing a chord.** Harmless by construction: only the selected game's toggle watcher is ever armed (§3 below), the same way only the selected game's macro watchers are armed today. Two games can never both react to the same press, because only one is armed at a time.
- **A game's own toggle hotkey matching one of its own macros' hotkeys.** Already possible today with zero validation anywhere in the codebase (confirmed by grep — no collision-checking code exists for the global toggle vs. a macro, or between two macros of the same game) — both watchers would simply fire on the same press, today and after this change. Adding a check now would be new, unrequested validation for a pre-existing, accepted gap, not something this ticket is scoped to fix.

## Proposed approach

### 1. Storage: move `"hotkey"` onto each game, migrate the old value forward
- Store the value as `game["hotkey"]` (same key name the top-level field already uses — no new vocabulary), holding the same `Hotkey.to_json()` shape as today.
- Remove `"hotkey": None` from `Store.__init__`'s default top-level dict (`afk_clicker.py:1670-1672`) — it is no longer a top-level setting. A stale top-level `"hotkey"` key surviving in an old on-disk file after migration is simply ignored by `self.data.update({k: v for k, v in loaded.items() if k in self.data})`, the same way any other unrecognized key already is — no explicit `pop` needed.
- Bump `SETTINGS_VERSION` to `3` (`afk_clicker.py:1571`) and add `_migrate_settings_v2_to_v3(data)`, registered as `_SETTINGS_MIGRATIONS[2]` (`afk_clicker.py:1641`):
  ```python
  def _migrate_settings_v2_to_v3(data):
      """G#57: the single top-level "hotkey" becomes a per-game value. The
      old chord toggled the clicker identically no matter which game was
      selected, so the least-disruptive carry-forward is to copy it into
      EVERY already-configured game -- not just the one selected at
      migration time -- so every existing game keeps working exactly as
      it did before, with no re-recording. A duplicate chord across games
      is harmless (see docs/spec.md "Collision policy"): only the
      selected game's watcher is ever armed. No games configured yet ->
      nothing to carry forward; a game created after this migration
      starts with no hotkey, same as a freshly created game's macros
      start empty today. Runs on the raw loaded dict, same reasoning as
      every migration above it -- validation of the copied value happens
      afterward, in the per-game shape filter below, same as any other
      per-game field."""
      old_hotkey = data.get("hotkey")
      games = data.get("games")
      if old_hotkey is not None and isinstance(games, dict):
          for game in games.values():
              if isinstance(game, dict):
                  game["hotkey"] = old_hotkey
      return data
  ```
- In `Store.__init__`'s existing per-game filtering loop (`afk_clicker.py:1705-1711`, right where the `"macros"` list is filtered), add the parallel per-game `"hotkey"` filter, same "drop don't coerce" contract:
  ```python
  hotkey_blob = game.get("hotkey")
  if hotkey_blob is not None:
      validated = Hotkey.from_json(hotkey_blob)
      if validated is not None:
          game["hotkey"] = validated.to_json()
      else:
          del game["hotkey"]   # garbage -- drop it, not coerce to None
  ```

### 2. `AfkAutoclicker.__init__`: delete the now-redundant startup-arm block
- `self.hotkey = None` / `self.registered_hotkey = None` / `self.hk_listener = None` (`afk_clicker.py:2778-2780`) stay — same meaning: `self.hotkey` is the pending recorded-but-not-yet-applied candidate for whichever game is currently showing, `self.registered_hotkey`/`self.hk_listener` are what's actually armed for the currently-selected game.
- Add one new slot next to them: `self._toggle_armed_for = None` — which game id `self.hk_listener` is currently armed for, or `None` if nothing is armed. This is the guard that keeps a same-game rebuild from touching the listener (§3).
- Delete the block at `afk_clicker.py:3007-3023` (`saved = Hotkey.from_json(self.store.data.get("hotkey") or {}); if saved is not None: self.hotkey = saved; self.apply_hotkey()`). It is now dead code: `_build_content()`'s own bootstrap `_select(self.current, persist=False)` call (`afk_clicker.py:3395`) will arm the initially-selected game's hotkey via the new `_arm_toggle_hotkey()` (§3), the same call site that already arms macro hotkeys on first boot — there is no longer a separate "restore once at startup" step to carry, exactly as macros never needed one.

### 3. `_select()`: arm/disarm per game, with the rebuild-identity guard
New methods next to `_arm_macro_hotkeys()`/`_disarm_macro_hotkeys()` (`afk_clicker.py:5184-5213`):
```python
def _arm_toggle_hotkey(self):
    """(Re)arms the toggle HotkeyWatcher for the CURRENTLY SELECTED game's
    own stored hotkey -- same rebuild-on-switch lifecycle as
    _arm_macro_hotkeys(), called from the same places (_select(), and
    _build_content()'s own bootstrap replay). Deliberately NOT
    unconditional like _arm_macro_hotkeys(): a theme/scale rebuild
    replays _select() with the SAME game_id, and
    HotkeyListenerSurvivesRebuild.test_listener_object_identity_is_unchanged_across_a_rebuild
    (tests/test_ui.py:5851) requires self.hk_listener to be the exact
    same object across that replay. Skipping the rest of this method
    when the selected game hasn't actually changed is what preserves
    that -- a real game switch always has a different game_id and
    always rearms."""
    game_id = self.current
    if game_id == self._toggle_armed_for:
        return
    self._disarm_toggle_hotkey()
    self.hotkey = None                     # discard any pending, un-applied
    self.apply_button.set_enabled(False)   # recording -- it belonged to
                                            # whichever game was selected
                                            # before, not this one.
    stored = Hotkey.from_json(self.store.game(game_id).get("hotkey") or {})
    self.registered_hotkey = None
    if stored is not None and macos_input_permitted():
        try:
            self.hk_listener = HotkeyWatcher(stored, self.toggle)
            self.hk_listener.start()
            self.registered_hotkey = stored
        except Exception:
            self.hk_listener = None
    self._toggle_armed_for = game_id
    self._show_hotkey(self.registered_hotkey)

def _disarm_toggle_hotkey(self):
    if self.hk_listener is not None:
        self.hk_listener.stop()
        self.hk_listener = None
```
`_select()` (`afk_clicker.py:4191-4263`) calls `self._arm_toggle_hotkey()` right alongside the existing `self._arm_macro_hotkeys()` call (`afk_clicker.py:5255` region / the macros block at the tail of `_select()`).

`on_close()`'s existing `if self.hk_listener is not None: self.hk_listener.stop()` (`afk_clicker.py:5862-5863`) is unchanged — still correct, since `self.hk_listener` always means "whatever's armed right now" regardless of scope.

### 4. `register_hotkey()`/`capture_hotkey()`: discard a stale capture after a game switch
The Record→Apply flow is the one place a background thread's result lands on `self.hotkey`/`self.hotkey_label` asynchronously (`capture_hotkey()`, `afk_clicker.py:5115-5132`, runs on `self.capture_thread`). If the user clicks Record on game A, switches to game B before releasing the chord, the capture still completes and must not get applied to the now-visible game B.
- `register_hotkey()` (`afk_clicker.py:5107-5113`) records which game the capture is for: `self._hotkey_capture_game = self.current` (new slot, initialized to `None` in `__init__` next to `self.capture_thread = None`).
- `_hotkey_captured()`, `_show_hotkey()`'s call from `capture_hotkey()`'s cancel/fail path, and `_hotkey_error()` (`afk_clicker.py:5134-5148`) each start with `if self._hotkey_capture_game != self.current: return` — discard silently. The already-switched-to game's own label/apply-button state (painted by `_arm_toggle_hotkey()` when the switch happened) is left alone, not overwritten by a capture that was never for it.
- `_arm_toggle_hotkey()`'s existing `self.hotkey = None` reset (§3) already covers the mirror case — switching games discards a candidate that was *already captured* but not yet applied; this guard covers one that's *still being captured* when the switch happens.

### 5. `apply_hotkey()`: persist and arm per-game
```python
def apply_hotkey(self):
    if not self.hotkey:
        return
    self._disarm_toggle_hotkey()
    if not macos_input_permitted():
        self.registered_hotkey = None
        self._hotkey_error("Accessibility permission not granted")
        return
    try:
        self.hk_listener = HotkeyWatcher(self.hotkey, self.toggle)
        self.hk_listener.start()
    except Exception as exc:
        self.hk_listener = None
        self._hotkey_error(exc)
        return
    self.registered_hotkey = self.hotkey
    self._toggle_armed_for = self.current
    self.store.game(self.current)["hotkey"] = self.hotkey.to_json()
    self._note_save(self.store.save())
    self.hotkey_label.config(text=self.hotkey.label(), fg=INK)
    self.apply_button.set_enabled(False)
    self.status.set("OFF", BAD, f"{self.hotkey.label()} toggles")
```
Same shape as today (`afk_clicker.py:5150-5180`) — `self.store.data["hotkey"] = ...` becomes `self.store.game(self.current)["hotkey"] = ...`, and `self._toggle_armed_for = self.current` is set on every successful/no-permission path so a subsequent same-game rebuild doesn't redundantly rearm what Apply just armed.

### 6. UI: no relocation, one subtitle change
The Hotkey tab (`afk_clicker.py:3612-3632`) stays exactly where it is — it is already shown per the selected game's page, same as Clicking and Macros; only its underlying data was global before. The only text change: `section(self.hotkey_pane, "Hotkey  ·  shared by every game", s, top=0)` (`afk_clicker.py:3614`) drops the now-inaccurate "shared by every game" — exact replacement wording (e.g. just "Hotkey", matching Clicking/Macros having no subtitle at all, or "Hotkey · this game") is `docs/design.md`'s call, not decided here; no width/overflow implication either way since it is a plain `section()` label change in place.

## Affected areas
Single file, single architectural layer (desktop app logic + its own persisted settings) — no schema/API split, so this stays one spec/one build cycle.
- `afk_clicker.py`:
  - `SETTINGS_VERSION` (`:1571`), new `_migrate_settings_v2_to_v3` (near `:1632`), `_SETTINGS_MIGRATIONS` (`:1641`).
  - `Store.__init__`'s default dict (`:1670-1672`, drop `"hotkey"`) and per-game filter loop (`:1705-1711`, add the hotkey filter).
  - `AfkAutoclicker.__init__` (`:2778-2780` existing slots, add `self._toggle_armed_for = None` and `self._hotkey_capture_game = None`; delete the startup-arm block `:3007-3023`).
  - `_build_content()` (`:3614`, subtitle text only).
  - `_select()` (`:4191-4263`, add `_arm_toggle_hotkey()` call).
  - New `_arm_toggle_hotkey()`/`_disarm_toggle_hotkey()` near `_arm_macro_hotkeys()`/`_disarm_macro_hotkeys()` (`:5184-5213`).
  - `register_hotkey()`, `capture_hotkey()`'s UI callbacks `_hotkey_captured()`/`_show_hotkey()`/`_hotkey_error()` (`:5107-5148`, add the stale-capture guard).
  - `apply_hotkey()` (`:5150-5180`, rewritten per §5).
- `tests/test_ui.py`:
  - `HotkeyPersistence` (`:3028-3136`) — every sub-test currently reads/writes the top-level `store.data["hotkey"]`; needs rewriting against `store.game(<id>)["hotkey"]`. Specifically: `test_a_corrupt_hotkey_starts_clean` (`:3054`, writes `data["hotkey"] = {...}` directly) and `test_nothing_is_saved_when_no_hotkey_was_applied` (`:3068`, reads `json.load(f).get("hotkey")`) both target the old top-level shape explicitly and must move to the per-game one.
  - `HotkeyListenerSurvivesRebuild.test_listener_object_identity_is_unchanged_across_a_rebuild` (`:5841-5862`) — the regression this spec's §3 guard exists to keep green; verify it still passes unmodified (the test itself needs no rewrite, the guard just has to be real).
  - `test_hotkey_is_the_default_active_tab_on_a_fresh_game_page` (`:2763`) and `test_hotkey_card_is_never_part_of_the_settings_page` (`:5255`) — tab/card identity is unchanged, expected to keep passing unmodified; worth an explicit check since they touch `hotkey_label`.
  - New coverage needed (not exhaustive — developer/reviewer's call on exact shape, following the precedent of `StoreMacroFiltering`, `:796`, and `MacrosTab`, `:7521`): per-game isolation (game A's hotkey does not fire while game B is selected, and vice versa), the v2→v3 migration (one game / several games / zero games), the stale-capture-after-switch guard (§4), and a direct test that two games sharing a chord causes no error at record/apply time.

## Edge cases
- **Zero games configured at migration time**: old top-level hotkey (if any) is dropped; nothing crashes; a game added afterward starts with no hotkey.
- **Several games configured at migration time**: old value copied into every one of them, not just the previously-selected one — every existing game keeps toggling on the same chord it always did.
- **Corrupt per-game `"hotkey"` blob for one game**: dropped for that game only (via the new `Store.__init__` filter), same "corrupt is as untrustworthy as missing" contract as every other per-game field — does not block startup and does not affect any other game's own hotkey.
- **Two games sharing the same chord**: no rejection anywhere; harmless, since only the selected game's watcher is ever armed (see "Collision policy").
- **A game's toggle hotkey matching one of its own macros' hotkeys**: both fire on the same press — pre-existing, unchanged behavior, not newly introduced or newly checked.
- **Switching games while a capture is in flight**: the capture thread runs to completion in the background (nothing cancels it, same as today), but its result is discarded on arrival if the selected game has since changed (§4) — it never gets attributed to the wrong game.
- **Switching games with an already-recorded-but-not-yet-applied candidate**: discarded on switch (`_arm_toggle_hotkey()`'s `self.hotkey = None`), never silently applied to the newly-selected game later.
- **Deleting a game**: `Store.delete_game()` (`afk_clicker.py:1763-1765`) already pops the whole per-game dict, including its `"hotkey"` key — no new deletion logic needed.
- **A theme/scale rebuild while staying on the same game**: `self.hk_listener` object identity is preserved (the `_toggle_armed_for` guard) — the one invariant this change must not break.
- **Platform**: `_arm_toggle_hotkey()` reuses `macos_input_permitted()`/`HotkeyWatcher` exactly as `_arm_macro_hotkeys()` already does on every game switch today — no new macOS-specific risk class. The one genuine change in exposure is frequency: a pynput `Listener` now starts/stops once per *game switch* rather than once per Settings "Apply" click, but that is the identical frequency macro-hotkey watchers already churn at on every switch, with no documented macOS crash traced to that churn itself (G#39/G#53 were about untracked `after`/`after_idle` handles and a `_poll_games` race, not listener start/stop churn) — flagged here per the task's own request, not because archaeology found a live risk.

## Acceptance criteria
- [ ] Given a fresh `Store` with no `settings.json`, when loaded, then `data["version"] == 3` and no top-level `"hotkey"` key is ever written back to disk.
- [ ] Given an on-disk v2 file with `data["hotkey"]` set and exactly one game in `data["games"]`, when loaded, then that game's `"hotkey"` equals the old value and it is still armed/toggling when that game is selected, with no re-recording.
- [ ] Given the same, but with several games in `data["games"]`, when loaded, then every one of them has the old value copied into its own `"hotkey"`.
- [ ] Given the same, but with `data["games"]` empty or absent, when loaded, then nothing raises and no game ends up with a `"hotkey"`.
- [ ] Given a corrupt `"hotkey"` blob on one game only, when loaded, then that game's `"hotkey"` is dropped (not present / resolves to no hotkey) while every other game's own `"hotkey"` and the rest of startup are unaffected.
- [ ] Given game A has a hotkey recorded and applied, when game B (with no hotkey) is selected, then pressing A's chord does not call `toggle()`, and `hotkey_label` shows "Not set" for B.
- [ ] Given game A and game B each have their own, different, applied hotkeys, when switching between them, then only the currently-selected game's chord toggles — the previous game's chord does nothing once switched away from.
- [ ] Given game A and game B are both given the **same** chord, when either is Applied, then neither raises/rejects, and whichever is currently selected is the one that toggles.
- [ ] Given a Record is started on game A (chord not yet released) and the user switches to game B before releasing it, when the capture completes, then it is discarded — `self.hotkey`/`hotkey_label`/`apply_button` reflect game B's own already-applied state, not A's just-recorded candidate.
- [ ] Given a hotkey is applied and armed for the currently-selected game, when `_apply_appearance(...)` triggers a theme rebuild with the same game still selected, then `self.ui.hk_listener` is the exact same object before and after (`HotkeyListenerSurvivesRebuild`'s existing test, unmodified, still green).
- [ ] Given `on_close()` is called while a per-game hotkey is armed, then the listener is stopped cleanly (existing on_close coverage, unaffected by the per-game change).
- [ ] Given `macos_input_permitted()` returns `False`, when Apply is clicked for a game, then no listener starts, `registered_hotkey` is `None` for that game, and the recorded candidate (`self.hotkey`) survives so a later Apply (after permission is granted) works without re-recording — same contract `test_no_listener_is_started_without_permission`/`test_registered_hotkey_cleared_on_second_apply_without_permission` already assert, now exercised per-game.
- [ ] All of the above are exercisable and verified under Xvfb/CI the same way existing `HotkeyPersistence`/`MacrosTab` tests already are — no new platform-only verification gap beyond what macro hotkeys already carry (see "Platform" edge case above).

## Open questions
- **Assumption, not a blocker**: the Hotkey tab's subtitle text (`afk_clicker.py:3614`, currently "Hotkey  ·  shared by every game") needs to change since it's no longer accurate, but the exact replacement wording is left to `docs/design.md` — proceeding under "any short, accurate replacement; no layout/width implication either way."
- **Assumption, not a blocker**: migration copies the old global hotkey into *every* already-configured game rather than only the currently-selected one. This is the decided, least-disruptive choice (see §1/"Why not a global-default fallback") — flagging here only so it's visible as a deliberate call, not re-litigated as an open question downstream.

## Risk / rollback notes
- The storage change is additive-and-moved, not purely additive: an old top-level `"hotkey"` stops being read anywhere once `Store.__init__`'s default dict drops it, which is why the migration (§1) is required, not optional — without it, every existing user's hotkey would silently stop working on upgrade. The acceptance criteria's migration cases are the direct check against that regression.
- If the per-game arming lifecycle (§3) needs to be reverted independently, `_arm_toggle_hotkey()`/`_disarm_toggle_hotkey()` are the only new call sites touching `self.hk_listener`'s lifecycle beyond `apply_hotkey()` itself — removing the `_select()` call site alone reverts to "arm only via Apply, never on switch," at the cost of reintroducing the original bug (chord fires regardless of selected game) but with zero storage-format change needed to roll back (the per-game storage and migration are independently safe to keep either way).
- The `_toggle_armed_for` guard is the one piece of new logic with a named failure mode: if it is ever removed or miscomputed, the first symptom is `HotkeyListenerSurvivesRebuild`'s existing test turning red — that test is the designated tripwire for this specific regression, not just incidental coverage.
