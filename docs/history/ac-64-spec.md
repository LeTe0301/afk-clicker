# Spec: Duplicate a macro

## Summary
Add a "Duplicate" button to each macro row (Macros tab) that clones the macro's name, hotkey, steps, and interval into a new macro in the same game, so a user tweaking a timing variant doesn't have to rebuild the step list by hand.

## Goals
- A macro row gets a third action button, "Duplicate", alongside the existing Run/Edit/Delete.
- Clicking it creates a new macro in the current game with the same hotkey, steps, and interval, named `"{original name} (copy)"`.
- The new macro appears immediately in the Macros list, with its hotkey/interval armed the same way any other macro's is.

## Non-goals
- No macro-recording or real-timing capture (that's the separate G#65-to-be-filed proposal).
- No automatic uniqueness/collision handling beyond the fixed `" (copy)"` suffix — duplicating the same macro twice yields two macros both named `"X (copy)"`. Macro names are not required to be unique today (`_validate_macro` only checks non-empty), so this isn't a new problem.
- No confirmation dialog before duplicating — see "Open questions" below for why.
- No change to `_delete_macro`, `_confirm_delete_macro`, or the macro editor dialog's own save path.
- No dedup/collision check on hotkeys — the app already allows two macros to carry the same hotkey today (`_arm_macro_hotkeys` arms a watcher per macro with no cross-macro check), so a duplicated hotkey is consistent with existing behavior, not a new hazard.

## Background / current state
`afk_clicker.py`'s Macros tab (`_refresh_macros_pane`, around line 5878) rebuilds one row per macro in the current game, each with Run/Edit/Delete buttons (lines 5896-5901):

```python
Button(row, "Delete", lambda m=macro: self._confirm_delete_macro(m), s, width=70).pack(side="right")
Button(row, "Edit", lambda m=macro: self._open_macro_editor(m), s, width=60).pack(side="right", padx=(0, int(6 * s)))
Button(row, "Run", lambda m=macro: self._run_macro(m), s, width=60).pack(side="right", padx=(0, int(6 * s)))
```

Persistence for a macro goes through `_save_macro(self, game_id, macro_id, name, hotkey, steps, interval_ms=None)` (line 5921): pass `macro_id=None` and it appends a new macro, assigning a fresh id via `_validate_macro`'s `uuid.uuid4().hex` fallback (line 772-774) when the blob's `"id"` is missing/invalid. `_save_macro` already handles re-validation, `self.store.save()`, and (when the game is the current one) refreshing the pane and rearming hotkey/interval watchers — this is the correct, already-proven path to reuse, not something to reimplement.

Note `_save_macro`'s `hotkey` parameter is a `Hotkey` object (it calls `hotkey.to_json()` internally), not the raw JSON stored on the macro dict. The existing row-render code already does this conversion for display (line 5895): `Hotkey.from_json(macro["hotkey"]) if macro["hotkey"] else None`.

Checked against the prior triage note: there is **no** existing name/id-collision-suffix pattern at `make_profile()`/`_add_game()` (lines 1874, 4658-4671) — `_add_game` just re-selects the existing game if the id collides, it does not rename. That precedent doesn't exist; this spec defines its own (fixed `" (copy)"` suffix, no incrementing) rather than reusing a pattern that isn't actually there.

## Proposed approach
1. Add `_duplicate_macro(self, macro)` near `_delete_macro`/`_save_macro` (around line 5911-5920):
   ```python
   def _duplicate_macro(self, macro):
       hotkey = Hotkey.from_json(macro["hotkey"]) if macro["hotkey"] else None
       self._save_macro(self.current, None, f'{macro["name"]} (copy)', hotkey,
                         macro["steps"], macro.get("interval_ms"))
   ```
   `self.current` is correct here (not a captured game id) because the row's lambda closures already only exist while that game's pane is rendered — same assumption `_delete_macro` makes today.
2. Wire a new button in `_refresh_macros_pane` (line 5896 area), placed between Edit and Run:
   ```python
   Button(row, "Duplicate", lambda m=macro: self._duplicate_macro(m), s, width=70
         ).pack(side="right", padx=(0, int(6 * s)))
   ```

## Affected areas
- `afk_clicker.py` only: one new method (`_duplicate_macro`) and one new `Button(...)` call in `_refresh_macros_pane`. No schema change, no new persisted field, no new dialog.

## Edge cases
- **Macro has no hotkey** (`macro["hotkey"]` is `None`): `hotkey` stays `None`, duplicate is created with no hotkey too — same as a freshly-created macro with hotkey skipped in the editor.
- **Macro has an interval set**: copied as-is via `macro.get("interval_ms")`; the duplicate's interval timer gets armed by `_save_macro`'s existing `_arm_macro_intervals()` call, same lifecycle as any other macro.
- **Steps list**: `macro["steps"]` is passed through `_validate_macro` again inside `_save_macro`, so a macro that was valid when saved remains valid when duplicated — no separate copy/deep-copy concern since `_validate_macro` rebuilds a fresh list of validated step dicts rather than reusing the original list object.
- **Game switched away before the click lands**: not reachable — the button only exists in a row rendered for the currently-selected game's pane; Tk destroys the whole pane on game switch (`_refresh_macros_pane`'s tear-down), so there's no stale-game-id case analogous to `_confirm_delete_macro`'s guard (that guard exists only because its dialog is non-blocking and stays open across a game switch; duplicate has no dialog, so nothing to guard).
- **Duplicating repeatedly**: each click appends one more `"{name} (copy)"` entry; no incrementing counter, no error. Consistent with Non-goals above.

## Acceptance criteria
- [ ] Given a macro with a hotkey, steps, and an interval, when "Duplicate" is clicked, then a new macro appears in the list named `"{original name} (copy)"` with the same hotkey label, the same `"every N ms"` label, and the same steps (verified by opening its Edit dialog).
- [ ] Given a macro with no hotkey and no interval, when "Duplicate" is clicked, then the new macro shows "No hotkey" and no interval label, matching the original.
- [ ] Given a macro's hotkey is a configured chord, when its duplicate is created, then pressing that same hotkey while the current game is selected triggers both the original and the duplicate (existing no-collision-check behavior, not a regression).
- [ ] Given a macro with an interval set, when it's duplicated, then the duplicate's own auto-repeat timer fires independently (visible via `_arm_macro_intervals` rearming, or by waiting one interval tick).
- [ ] Duplicating does not alter or remove the original macro (same id, same fields, still present in the list).
- [ ] The new macro is actually persisted: it survives a game switch away and back (reads from `self.store`, not just in-memory).

## Open questions
- **Does Duplicate need its own confirm dialog (like G#63's delete confirm)?** Assumption: no. Confirm dialogs in this app gate destructive, irreversible actions (delete). Duplicate is purely additive and reversible by just deleting the new row — there's nothing to lose by clicking it. Proceeding without a confirm step; flag if Leo wants one anyway for parity with the other three row buttons.
- **Does Duplicate copy the hotkey?** Assumption: yes, copy it as-is (see Proposed approach / Non-goals). The app has no existing cross-macro hotkey-collision guard anywhere (editor or `_arm_macro_hotkeys`), so leaving the duplicate's hotkey as a straight copy is the zero-new-behavior choice; the user can reassign or clear it afterward via Edit like any other field.

## Risk / rollback notes
Additive-only change (new method + new button), no persisted schema change, no migration. Rollback is reverting the one commit. Worst case if something's wrong: an extra row appears with wrong steps/hotkey, fixable via the existing Edit/Delete buttons on that row — no data loss risk to the original macro or other games.
