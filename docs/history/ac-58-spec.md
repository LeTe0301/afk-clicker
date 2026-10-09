# Spec: Macros-specific regression test for the `put_game()` merge fix (G#58)

Written by the orchestrator, not product-manager — this is a mechanical repeat of a
technique already proven in the same session (G#57's cycle), not a new product or
design decision. No ux-designer pass needed either: pure test addition, no UI surface.

## Background

G#57 (per-game hotkeys, `feature/ac-57/per-game-hotkeys`, cycle review: APPROVE WITH
FOLLOW-UPS) found and fixed a real bug in `Store.put_game()` (`afk_clicker.py:1759`):
it used to wholesale-replace a game's settings dict on every persist
(`self.data["games"][game_id] = values`) instead of merging, silently wiping that
game's `"macros"` list (and, before the fix, the new per-game `"hotkey"` key) on the
very next `_persist()` call. Fixed by merging instead
(`self.data["games"].setdefault(game_id, {}).update(values)`).

The fix is covered by an existing test via the hotkey path
(`HotkeyPersistence.test_restored_and_armed_after_restart`, reverting the fix makes it
fail) but has **zero direct regression coverage via the macros path** — this was G#57's
cycle review Finding #1 (should-fix, non-blocking), filed as this ticket.

## The gap, precisely

`_save_macro()` (`afk_clicker.py:5312`) does not go through `put_game()` at all — it
mutates `self.store.game(game_id)["macros"]` directly (an in-place reference into
`self.data["games"][game_id]`) and calls `self.store.save()` directly. So saving a
macro alone never exercises the bug.

The bug only bites on the *next* call that goes through `put_game()` — that's
`_persist()` (`afk_clicker.py:4351`), which runs whenever a Clicking-pane field changes
(or, per the existing `NumBox`/`Segmented` wiring, on various field-edit traces) and
calls `self.store.put_game(self.current, values)` with a `values` dict that has no
`"macros"` key. Before the fix: this wholesale-replaced the per-game dict, discarding
`"macros"` entirely. After the fix: `_persist()`'s `values` are merged in, and
`"macros"` (not part of `values`) survives untouched.

## Test to add

One new test, same file/class-adjacency convention as the hotkey precedent
(`HotkeyPersistence`) — add to `StoreMacroFiltering` or `MacrosTab` (whichever existing
class already has a `self.ui`/`self.store` fixture selecting `"minecraft"`; follow
whichever of the two is the closer sibling by reading both class bodies first), named
something like `test_a_macro_survives_an_unrelated_persist_call`:

1. `self.ui._select("minecraft")`.
2. Save one macro via `self.ui._save_macro("minecraft", None, "Test macro", hotkey, steps)`
   — same call shape as `test_save_macro_persists_and_arms_its_hotkey`
   (`tests/test_ui.py:7559`). Assert it returns `True`.
3. Trigger an unrelated `_persist()` — call `self.ui._persist()` directly (simplest,
   most direct route to the exact code path that wiped macros; no need to drive it
   through a real field edit/trace when the method itself is the thing under test).
4. Assert the macro is still there, both in memory
   (`self.ui.store.game("minecraft")["macros"]`, length 1, same name) and reloaded from
   disk (`app.Store(self.config)`, same assertion) — mirroring
   `test_save_macro_persists_and_arms_its_hotkey`'s own on-disk check.

## Sabotage verification

Confirm this test actually exercises the fix: temporarily revert `put_game()` to its
old wholesale-replace body, run the new test alone, confirm it fails with a clear
assertion (macro list empty or missing), then restore the fix and confirm green. This
is the same verification the reviewer already did by hand for the hotkey-path test;
this ticket turns that into a committed, automated test for the macros path.

## Acceptance criteria

- [ ] New test added, passing against the current (fixed) `put_game()`.
- [ ] Sabotage-verified: fails against a reverted (wholesale-replace) `put_game()`.
- [ ] Full suite still green (`python -m unittest discover -s tests -t .`), no other
      test's count or behavior changed.

## Non-goals

- No change to `put_game()`, `_persist()`, or `_save_macro()` themselves — the fix
  already shipped in G#57. This ticket is test-coverage only.
- No change to the hotkey-path test already covering this fix.
