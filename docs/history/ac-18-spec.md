# Spec: Button click-away test (G#18 / GH#22)

Written by the orchestrator, not product-manager: this is the fourth test in an
existing, proven pattern (`NumBoxFocus` in `tests/test_ui.py`), with no product,
design or architecture decision to make.

## Summary
G#18/GH#22 collected two should-fix items from PR #21's review. The first, a
comment saying `root.bind_all("<Button-1>", ...)` is interpreter-wide, already
landed with PR #30 (`afk_clicker.py:2243-2249`). The ticket's own 2026-09 comment
confirms that and marks the ticket half done. The second is still open: no
automated test clicks a `Button` canvas while a number field is focused.
`NumBoxFocus` covers a plain label (`test_click_elsewhere_drops_focus`), a
`Segmented` (`test_a_segmented_control_still_changes_its_variable`) and a `GameItem`
(`test_a_game_item_still_selects`), but not `Button`.

The behaviour is correct today. The risk is a silent regression. Tk runs bindtags
in order: widget, class, toplevel, `all`. `Button` binds `<Button-1>` on the
widget itself (`afk_clicker.py:1596`, `self.bind("<Button-1>", self._click)`), so a
future `return "break"` from `Button._click`, or an earlier bindtag that breaks,
would stop `_maybe_drop_focus` on the `all` tag (`afk_clicker.py:3952-3959`) from
ever running. The field would stay focused and nothing would fail.

## Goals
- One new test in `NumBoxFocus` (`tests/test_ui.py:790`) that focuses a number
  field, clicks an app `Button` canvas, and asserts **both** that the field lost
  focus **and** that the button's own command ran.

## Non-goals
- No production code change. The comment half is already done.
- No change to `_maybe_drop_focus`, `Button`, or the existing `NumBoxFocus` tests
  and helpers.
- Nothing from other queued tickets (G#21 updater residue, G#40 macOS sidebar flake).
- ux-designer is skipped: nothing visible changes.

## Proposed approach
Mirror `test_a_segmented_control_still_changes_its_variable` and
`test_a_game_item_still_selects` exactly:
`self.focus_and_settle(self.ui.click_ms)`, then `event_generate("<Button-1>", x=.., y=..)`
on the button, `self.root.update()`, `assertNotEqual(self.root.focus_get(),
self.ui.click_ms.entry)`, and an assertion that the command ran.

Which button to click:
- `event_generate` is a no-op on an unmapped widget (see `focus_and_settle`'s
  comment), and `focus_and_settle` switches to the Clicking pane. So the button must
  be viewable while the Clicking pane is shown.
- **Preferred:** a real `app.Button` the app already places where it is viewable
  at that point. Swap its `command` for a recording stub (`button.command = ...`,
  since `_click` calls `self.command()`) so the test does not start clicking,
  register a hotkey or hit the network.
- **Fallback, if no app `Button` is viewable alongside the Clicking pane:**
  construct a real `app.Button` with a recording command, packed into the Clicking
  pane, and destroy it at the end of the test. It is still the real class and its
  real widget-level binding, which is what the regression would break.
- Name the choice and the reason in `docs/implementation.md`.

## Acceptance criteria
- [ ] A new `NumBoxFocus` test clicks an `app.Button` canvas while
      `self.ui.click_ms.entry` holds focus. It asserts focus left the entry and the
      button's command ran exactly once.
- [ ] Sabotage-verify: temporarily make `Button._click` return `"break"` after
      calling the command. The new test must fail on the focus assertion, and the
      command assertion must still pass, which shows the test separates the two.
      Restore it, then confirm `git diff afk_clicker.py` is empty.
- [ ] The full suite passes: 375 tests OK (skipped=10), one more than the 374
      baseline on `main` `2c89b3a`.
- [ ] Only `tests/test_ui.py` changes, plus `docs/implementation.md`.
