# Implementation: Confirm before deleting a custom game profile or macro

Ticket: G#63 (`admin/afk-clicker#63`) / GH#111 (`LeTe0301/afk-clicker#111`)
Spec: `docs/spec.md`. Design: `docs/design.md`.

## Summary
Added one shared, non-blocking themed confirm dialog (`_open_confirm_dialog`) in front of
`_delete_game` and `_delete_macro`, wired in at the two existing call sites (the sidebar delete
glyph, the macro row's Delete button) instead of inside the delete functions themselves. Both
delete functions are byte-for-byte unchanged. Along the way, fixed a latent `GameItem` click-
dispatch bug this feature exposed (see "Root cause" below).

## Root cause (incidental fix, not a reported bug)
Not a bugfix task, but implementing it surfaced a real pre-existing defect: `GameItem`'s delete
glyph binds `<Button-1>` via `tag_bind(..., "<Button-1>", lambda e: (on_delete(...), "break")[1])`,
and the row itself separately binds `<Button-1>` via plain `bind()` to select the row
(`afk_clicker.py`, `GameItem.__init__`). The comment at that call site claimed `"break"` stops the
row's own select handler from also firing. Confirmed directly (a 5-line throwaway Tk script,
`c.tag_bind(item, "<Button-1>", lambda e: (..., "break")[1]); c.bind("<Button-1>", ...)`) that this
is false: a canvas item's `tag_bind` and the canvas widget's own `bind()` are two independent Tk
dispatch stages, and `"break"` from the first does not suppress the second. This was invisible
before because `on_delete` was always `_delete_game`, which destroys and replaces the `GameItem`
tree synchronously, before Tk ever reached the second dispatch stage. Now that `on_delete` opens a
non-blocking dialog instead (the row survives the click), the second stage ran too, reselecting the
very row whose deletion was still only pending confirmation -- regressing the existing, already-
tested "deletes without selecting first" contract (GH#96).

Fixed at the root, in `GameItem` itself (not in the new confirm-dialog code): the widget-level
`<Button-1>` handler now checks `self.find_withtag("current")` and skips calling `on_click` when
the click landed on the delete glyph, the same "what's under the pointer" query Tk itself used
to decide whether to fire the glyph's own binding.

## Changes by file

- `afk_clicker.py`
  - `Button.__init__`/`Button._colors` (~`:2151`, `:2167`): added `danger=False` kwarg. When set,
    renders with `BAD` fill/outline and `ACCENT_INK` label, hover `_lighten(BAD, 0.18)` -- mirrors
    the existing `primary` branch exactly; default path is unchanged (verified: every existing
    `Button(...)` call site passes `width`/`primary` by keyword, so inserting `danger` between
    `primary` and `width` is positionally safe).
  - `GameItem.__init__`/new `GameItem._on_click` (~`:2656`): root-cause fix above -- the row's own
    `<Button-1>` binding now ignores a click that landed on the delete glyph.
  - `_truncated_dialog_name` (new, module-level, just above `class Button`): truncates a name to 39
    chars + `…` past 40, per `docs/design.md`'s "Copy rules".
  - `AfkAutoclicker.__init__`: added `self._confirm_dialog = None`.
  - `AfkAutoclicker._open_confirm_dialog`, `._close_confirm_dialog`, `._confirm_delete_game`,
    `._confirm_delete_macro` (new, grouped right after `_on_log_dismiss`, ~`:5176`): the shared
    dialog helper and the two call-site wrappers, built exactly per `docs/design.md`'s "Modal
    layout and copy" / "Triggers" / "Confirm / cancel / Escape / close box behavior" sections --
    single open slot, content-driven size (no `geometry("WxH")`), centered over root, Escape/
    Return/Cancel/close-box all just close the dialog, Delete destroys the dialog first and then
    runs the closure.
  - `_rebuild_list` (~`:4440`): `on_delete=self._delete_game` → `on_delete=self._confirm_delete_game`.
  - `_refresh_macros_pane`'s Delete button (~`:5896`): `lambda m=macro: self._delete_macro(m)` →
    `lambda m=macro: self._confirm_delete_macro(m)`.
  - `_rebuild_ui` (~`:3767`): added `self._close_confirm_dialog()` alongside the existing log-
    dialog close, before the teardown loop -- an open confirm dialog is a genuine child of root and
    would otherwise survive with a closure pointed at a torn-down tree (`docs/design.md` "Rebuild").
  - `_delete_game`/`_delete_macro` themselves: untouched, as the spec requires.

- `tests/test_ui.py`
  - Added `_find_button`/`_dialog_label_containing` module-level helpers (walk a dialog's widget
    tree, same shape as `UITestCase._appearance_segment`).
  - Updated `DeletedGames.test_clicking_the_delete_glyph_deletes_without_selecting_first` →
    `..._opens_a_confirm_dialog_without_selecting_first`: this test drove the actual glyph click, so
    its old assertion (immediate deletion) no longer matches the new, intentional behavior; rewrote
    it to assert the dialog opens without deleting or reselecting, then click the dialog's own
    Delete and assert the same "no premature selection" outcome the original test protected.
  - Added `DeleteConfirmDialogs` (new test class): naming for both game and macro dialogs; Delete
    proceeds exactly like the old direct call; Cancel/Escape/close-box (via the registered
    `WM_DELETE_WINDOW` Tcl command, since there is no WM under Xvfb to click a real close box)
    leave state untouched; a second `_confirm_delete_game`/a double glyph-click can't stack two
    dialogs; `_rebuild_ui()` closes an open dialog; a macro delete confirmed after switching away
    from its game is a no-op (the stale-target re-check `docs/design.md` calls for).

## Key decisions / tradeoffs
- Truncation/fallback-heading text is built in the two wrapper methods, not inside
  `_open_confirm_dialog` itself, so the shared helper stays generic (title/heading/body/callback)
  and the "game" vs "macro" fallback copy ("Delete this game?" / "Delete this macro?") stays local
  to each wrapper.
- `_confirm_delete_game`'s closure has no separate stale-target re-check: `_delete_game` already
  re-validates `game_id` against `self.by_id`/`"custom"` at call time (GH#96), so re-checking in the
  wrapper too would be a duplicate guard. `_delete_macro` has no such guard of its own (it always
  acts on `self.current`), so `_confirm_delete_macro`'s closure does the re-check `docs/design.md`
  specifies instead.

## Deviations from spec / design
- None in the dialog itself -- layout, copy, tokens, single-open-slot, Return=cancel, and the
  stale-target re-checks all match `docs/design.md` as written.
- One addition beyond both documents: the `GameItem._on_click` fix described under "Root cause".
  Neither document anticipated it (the latent bug was invisible before this feature delayed
  deletion past the click), but leaving it unfixed would have broken the pre-existing, still-
  tested "clicking the delete glyph doesn't select the row first" contract -- in scope as a
  necessary root-cause fix for a regression this change would otherwise introduce, not scope creep.

## Known limitations
- Keyboard focus for Escape/Return depends on `top.focus_force()` succeeding, which (per
  `docs/design.md`) cannot be verified under Xvfb's no-window-manager environment the same way a
  real WM's focus grant could be -- covered here by driving `<Escape>` directly after an explicit
  `focus_force()`/`update()` in the test, and by invoking the `WM_DELETE_WINDOW` protocol's
  registered command directly for the close-box case, rather than depending on a real WM to deliver
  either.

## How to verify locally
```
Xvfb :99 -screen 0 1280x1024x24 -maxclients 2048 &
DISPLAY=:99 python3 -m unittest tests.test_ui.DeletedGames tests.test_ui.DeleteConfirmDialogs \
  tests.test_ui.MacrosTab tests.test_ui.MacroIntervals -v
# Full suite:
DISPLAY=:99 python3 -m unittest discover -s tests -t . -v
```
(pynput must be importable -- this box's own venv for that is
`/home/dev/.venvs/afk-clicker-test`.) Both run clean: 37/37 and 570/570 (10 skipped, pre-existing
macOS-only/platform-gated tests), respectively, as of this change.

Manually: run the app, add a custom game, click its sidebar `✕` -- a "Delete game" dialog opens
naming it; Escape/Cancel/the window's close button all leave it in place; Delete removes it as
before. Same for a macro's "Delete" button -- "Delete macro" dialog, "steps and hotkey" copy.
