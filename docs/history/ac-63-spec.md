# Spec: Confirm before deleting a custom game profile or macro

Ticket: G#63 (Gitea `admin/afk-clicker#63`) / GH#111 (`LeTe0301/afk-clicker#111`)

## Summary
Add a confirmation step before `_delete_game` (`afk_clicker.py:4619`) or `_delete_macro`
(`afk_clicker.py:5733`) actually deletes anything, since both are currently a single click with no
way back.

## Goals
- Clicking the sidebar delete glyph on a custom game, or "Delete" on a macro row, opens a themed
  confirmation modal naming the specific item before anything is removed.
- Confirming proceeds with exactly today's existing delete behavior, unchanged.
- Cancelling (or dismissing the modal any other way) leaves the profile/macro and all app state
  exactly as it was — no partial deletion.

## Non-goals
- No undo/trash/restore for deleted profiles or macros — a confirm step, not a safety net after
  the fact.
- No change to *what* gets deleted or how (`_delete_game`'s fallback-selection logic,
  `_delete_macro`'s hotkey/interval re-arming) — only *when* it runs.
- No hotkey-collision checking, poll-interval changes, or macro reordering — unrelated, already
  settled elsewhere.
- No settings-schema change — this is presentation-layer only.
- No "don't ask me again" checkbox or per-user preference to skip the confirmation — not asked
  for; keep this minimal.

## Background / current state
- `_delete_game(self, game_id)` (`afk_clicker.py:4619-4644`) is the sole handler wired to
  `GameItem`'s delete glyph (`on_delete=self._delete_game`, `afk_clicker.py:4404`). It guards that
  the profile exists and is custom, then immediately mutates `self.profiles`/`self.by_id`, calls
  `self.store.delete_game(game_id)`, rebuilds the list, and reselects. There is no confirmation
  today — one click wipes the profile's settings, macros, and hotkey.
- `_delete_macro(self, macro)` (`afk_clicker.py:5733-5741`) is wired to each macro row's "Delete"
  button (`afk_clicker.py:5718-5719`, inside `_refresh_macros_pane`). It immediately filters the
  macro out of the game's `"macros"` list, saves, refreshes the pane, and re-arms hotkeys/
  intervals. Also no confirmation today.
- The app never uses `tkinter.messagebox` (confirmed: no `messagebox`/`askyesno` call anywhere in
  `afk_clicker.py`) — it always paints its own flat-themed `tk.Toplevel` for anything that needs a
  dialog, e.g. the update-log-failure dialog (`_show_update_log_dialog`, roughly
  `afk_clicker.py:4982-5133`, using `BG`/`CARD`/`INK`/`MUTED`/`ACCENT`, the shared `Button` helper,
  `top.transient(self.root)`, `<Escape>` bound to dismiss) and the macro editor dialog
  (`_open_macro_editor`, `afk_clicker.py:5786+`, same `tk.Toplevel(self.root)` /
  `dialog.transient(self.root)` shape). Neither of those is itself a yes/no confirm — there is no
  existing confirm-specific modal to reuse verbatim, but both establish the exact look-and-feel
  (colors, `Button` helper, `transient`, `<Escape>`) a new one should match.

## Proposed approach
Add one small, shared helper — e.g. `_confirm(self, title, message, on_confirm)` — that builds a
minimal themed `tk.Toplevel` (title bar, a message `Label` naming the specific item being deleted,
a "Delete" button styled as destructive, and a "Cancel" button as the default/safe action),
`transient(self.root)`, bound `<Escape>` to cancel/close, and calls `on_confirm()` only if the
Delete button is clicked. No `wait_window()`/blocking modal loop is required — matches this app's
existing non-blocking Toplevel precedent (`_show_update_log_dialog`'s own docstring: "Transient,
not modal -- no wait_window()").

Wire it in at the two call sites, not inside the delete functions themselves (keeps
`_delete_game`/`_delete_macro` exactly as-is, just no longer called directly from the button):
- `GameItem`'s delete glyph's `on_delete` callback (currently `self._delete_game` directly,
  `afk_clicker.py:4404`) becomes a small wrapper that opens the confirm dialog naming that game's
  profile name, and only calls the real `self._delete_game(game_id)` on confirm.
- The macro row's "Delete" `Button` (`afk_clicker.py:5718`, currently
  `lambda m=macro: self._delete_macro(m)`) becomes a lambda that opens the confirm dialog naming
  that macro's name, and only calls `self._delete_macro(m)` on confirm.

Message text names the specific item ("Delete '<profile name>'? This removes its settings,
macros, and hotkey." / "Delete macro '<macro name>'? This removes all its steps.") rather than a
generic "Are you sure?", since both deletions destroy more than just the row (settings/hotkey for
a profile; the whole step list for a macro) and the user should see that scope before confirming.

## Affected areas
- `afk_clicker.py` only: one new shared confirm-dialog helper, plus the two call sites above
  (`GameItem`'s `on_delete` wiring near `afk_clicker.py:4404`, and the macro row's Delete button
  near `afk_clicker.py:5718`). `_delete_game`/`_delete_macro` themselves are unchanged.
- No schema/settings-version change, no new Store keys, no new files.
- `tests/test_ui.py` already has a `GH#96` test covering `_delete_game`'s own behavior
  (`tests/test_ui.py:340`) — that test calls `_delete_game` directly today and should keep doing
  so unchanged (it's testing the deletion logic, not the new gate); new tests for this feature
  should instead exercise the confirm/cancel path through whatever the glyph/button now calls.

## Edge cases
- **Cancel / dismiss** (Cancel button, `<Escape>`, or the window's close box) must all leave the
  profile/macro and every other piece of state untouched — same contract as `_open_macro_editor`'s
  own "Cancel... discards it all" behavior.
- **Confirm while the deleted game is currently selected**: unchanged — `_delete_game`'s existing
  fallback-to-`"global"` logic already handles this; the new wrapper doesn't touch it.
- **Rapid double-click on Delete**: the confirm dialog opening on the first click means a second
  click lands on the dialog (or is blocked by it being on top), not on a second delete — no new
  double-delete risk is introduced since the destructive action no longer fires on the first
  click at all.
- **Confirming on a macro that's actively armed** (has a live hotkey/interval): unchanged —
  `_delete_macro` already calls `_arm_macro_hotkeys()`/`_arm_macro_intervals()` after removal.
- Deleting a built-in (non-custom) game profile is not reachable — `GameItem` never draws the
  delete glyph for one (existing precondition, unchanged, still double-checked defensively inside
  `_delete_game`).

## Acceptance criteria
- [ ] Given a custom game profile exists, when its sidebar delete glyph is clicked, then a themed
      confirm modal appears naming that profile and the profile is NOT yet deleted.
- [ ] Given that modal is open, when "Delete" is clicked, then the profile is removed exactly as
      `_delete_game` does today (removed from sidebar, settings/macros/hotkey gone, fallback
      selection to `"global"` if it was selected).
- [ ] Given that modal is open, when "Cancel" is clicked, `<Escape>` is pressed, or the window is
      closed, then the profile remains, fully intact, with no state change.
- [ ] Given a macro exists on the current game, when its "Delete" button is clicked, then a themed
      confirm modal appears naming that macro and the macro is NOT yet deleted.
- [ ] Given that modal is open, when "Delete" is clicked, then the macro is removed exactly as
      `_delete_macro` does today (removed from the list, hotkeys/intervals re-armed, pane
      refreshed).
- [ ] Given that modal is open, when "Cancel" is clicked, `<Escape>` is pressed, or the window is
      closed, then the macro remains, fully intact, with no state change.
- [ ] The confirm modal uses the app's existing theme constants/`Button` helper, not
      `tkinter.messagebox`.
- [ ] Built-in (non-custom) game profiles still show no delete glyph at all (unchanged).

## Open questions
- None blocking. Assumption: a single shared `_confirm()` helper serves both call sites (profile
  delete and macro delete) rather than two bespoke dialogs, since the only difference is the
  message text and the callback — flag to ux-designer/developer if a reason emerges to diverge.

## Risk / rollback notes
Low risk — additive UI gate in front of two already-well-tested existing functions, no data model
change. Rollback is reverting the two call-site wrappers back to calling `_delete_game`/
`_delete_macro` directly and dropping the new helper.
