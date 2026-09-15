# Implementation: Button click-away test (G#18 / GH#22)

## Summary
`NumBoxFocus` (`tests/test_ui.py:790`) already covered a plain label, a
`Segmented`, and a `GameItem` clicking a number field away from focus, but
nothing exercised a `Button` canvas doing the same. `Button` binds `<Button-1>`
on the widget itself (`afk_clicker.py:1596`), ahead of the `all` bindtag that
carries `_maybe_drop_focus` (`afk_clicker.py:3952-3959`, bound at `2243`); a
future `return "break"` from `Button._click`, or an earlier bindtag breaking,
would silently stop the drop-focus behaviour from ever running for a real
button click, with nothing failing. One new test,
`test_a_button_still_runs_its_command`, closes that gap.

## Changes by file
- `tests/test_ui.py` (`NumBoxFocus`, inserted between
  `test_a_game_item_still_selects` and
  `test_starting_from_a_background_thread_drops_focus`, ~lines 917-937): added
  `test_a_button_still_runs_its_command`. No other test, helper, or class in
  this file changed.

## Key decisions / tradeoffs

### Which button to click
**Correction (Round 2): this section was wrong in round 1.** The round-1
investigation checked Record/Apply (`afk_clicker.py:2874-2875`, in
`self.hotkey_pane`) and `self.update_button` (`afk_clicker.py:3058`, in
Settings' Updates pane) — both correctly hidden while the Clicking pane is
shown — but missed a third app-placed `Button`: "Add current game"
(`afk_clicker.py:2607-2609`), packed into `self.side` (the sidebar). `self.side`
and `self.content` (which houses the `hotkey_pane`/`clicking_pane` toggle) are
packed as siblings inside `shell`, not as parent/child — the sidebar sits
outside the tab toggle entirely and stays viewable regardless of which content
tab is active. Confirmed live (see Round 2 below): `winfo_viewable() == 1` for
the "Add current game" button immediately after `_set_content_tab("clicking")`,
vs. `0` for Record and Apply. Since the spec's fallback is conditional on "no
app `Button` is viewable alongside the Clicking pane," and that precondition is
false, the preferred approach applies: swap the real button's `.command` for a
recording stub. See "Round 2" below for what changed as a result.

### Structure
Mirrors `test_a_segmented_control_still_changes_its_variable` and
`test_a_game_item_still_selects`: `self.focus_and_settle(self.ui.click_ms)`,
then `event_generate("<Button-1>", ...)` on the target widget,
`self.root.update()`, `assertNotEqual(self.root.focus_get(),
self.ui.click_ms.entry)`. Added one difference required by the fallback: since
the button is newly packed rather than pre-existing, the test waits with
`self.pump_until(lambda: button.winfo_viewable(), timeout=1.0)` before
clicking — `event_generate` is a no-op on an unmapped widget
(`focus_and_settle`'s own comment, `tests/test_ui.py:793-813`), and a freshly
packed sibling of an already-mapped pane still needs at least one pumped
`update()` before Tk actually maps it.

The final assertion, `assertEqual(clicked, [1])`, is what distinguishes this
test from the other `NumBoxFocus` click-away tests: it confirms the button's
own command actually ran, not just that focus moved for some other reason.

## Deviations from spec
None. The spec's Non-goals (no production change, no change to
`_maybe_drop_focus`/`Button`/other `NumBoxFocus` tests) were followed exactly;
the fallback button-placement path was used because the preferred path (an
app-placed `Button` viewable alongside Clicking) does not exist today, exactly
as the spec anticipated as a possibility.

## Known limitations
None beyond what the spec already named: this test proves the *current*
binding order keeps working, not that it can never regress by a different
mechanism (e.g., a change to bindtag order itself rather than a `"break"`
return) — the same limitation the other three `NumBoxFocus` click-away tests
already carry.

## How to verify locally
Environment (this repo's convention: venv + Xvfb `:99`, confirm nothing else
is running first):
```
pgrep -a Xvfb            # :99 should already be up
pgrep -af "[u]nittest"   # nothing else running
cd /home/dev/projects/afk-clicker
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```

### New test in isolation (this session)
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.NumBoxFocus.test_a_button_still_runs_its_command -v
```
Ran 5 times back to back: `ok` all 5 times, ~0.14s each — no focus-flakiness
observed under this Xvfb.

### Whole `NumBoxFocus` class (this session)
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.NumBoxFocus -v
```
```
Ran 10 tests in 1.233s

OK
```
All 10 tests pass together, including the new one alongside the existing 9.

### Full suite result (this session, final state)
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```
```
Ran 375 tests in 66.714s

OK (skipped=10)
```
One more than the documented 374 baseline on `main` `2c89b3a`, same skip
count — matches the spec's acceptance criterion exactly. The `ResourceWarning`s
printed during the run are all in `tests/test_updater.py` (lines 686/704/740/
753/768) — pre-existing and out of this cycle's scope, same observation
`docs/history/ac-10-implementation.md` already made for the same file.

### Sabotage-verify performed this session
Temporarily changed `Button._click` (`afk_clicker.py:1611-1613`) to:
```python
    def _click(self, _event):
        if self._enabled:
            self.command()
        return "break"
```
and reran the new test in isolation:
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.NumBoxFocus.test_a_button_still_runs_its_command -v
```
Result: `FAIL`, on `self.assertNotEqual(self.root.focus_get(),
self.ui.click_ms.entry)` — the field stayed focused, exactly the regression
this test exists to catch.

To confirm the command assertion independently still passes under the same
sabotage (rather than merely never being reached because the prior assertion
raised first), temporarily swapped the two assertions' order in the test
(command check first, focus check second) and reran the same command: result
was still `FAIL`, but now only on the (now second) focus assertion — the
command assertion ahead of it raised nothing, confirming
`assertEqual(clicked, [1])` passes on its own under the sabotage. Both the
assertion-order swap and the `Button._click` sabotage were reverted
immediately after.

Confirmed clean afterward:
```
git diff afk_clicker.py
```
produced no output (empty diff) — the sabotage left no trace in production
code. Reran the new test once more post-revert: `ok`.

## Verification of scope
```
git status --short
git diff --stat
```
```
 M tests/test_ui.py
?? docs/spec.md

 tests/test_ui.py | 23 +++++++++++++++++++++++
 1 file changed, 23 insertions(+)
```
Only `tests/test_ui.py` changed (23 insertions, matching the spec's "Only
`tests/test_ui.py` changes" acceptance criterion); `docs/spec.md` was already
untracked before this session began. No scratch files were left in the repo
tree — a throwaway script used mid-session to explore an alternate
verification path lived only under the session's scratchpad directory and was
deleted before this doc was written.

## Round 2

`docs/test-review.md`'s must-fix: round 1's "Which button to click"
investigation missed a real, already-placed, already-viewable `app.Button` —
"Add current game" (`afk_clicker.py:2607-2609`), packed into `self.side` (the
sidebar), which the reviewer confirmed live stays viewable alongside the
Clicking pane (`self.side` and `self.content` are packed as siblings inside
`shell`, not parent/child — the sidebar sits outside the Hotkey/Clicking tab
toggle). The spec's fallback (construct-and-destroy) is conditional on no
such button existing; since one does, the preferred approach applies.

### What changed
`tests/test_ui.py`'s `NumBoxFocus` class:
- Added `_find_add_game_button` (mirrors `_find_segmented_for`,
  `tests/test_ui.py:841-852`): walks the widget tree from `self.ui.side`,
  matching `isinstance(w, app.Button) and w.command == self.ui.add_current_game`.
  Matches on the bound command rather than the label, because the label reads
  "+" instead of "Add current game" while the rail is collapsed (bound-method
  equality holds across the two separate attribute accesses —
  `widget.command` and `self.ui.add_current_game` compare equal even though
  each access produces a distinct bound-method object). Asserts the button was
  found with a clear failure message, same pattern as `_find_segmented_for`.
- Reworked `test_a_button_still_runs_its_command` to use that real button
  instead of constructing and packing a throwaway one: saves
  `button.command`, replaces it with a recording stub (`lambda:
  clicked.append(1)`), and restores the original command in `finally` — no
  `pack()`/`destroy()` needed, since the button is already part of the app's
  own widget tree.
- Kept the viewability wait (`self.pump_until(lambda: button.winfo_viewable(),
  timeout=1.0)`), since the button's viewability while the Clicking pane is
  shown was only confirmed *after* `_set_content_tab("clicking")` runs, not
  before `setUp` — but made the failure loud: `pump_until` returns `None` on
  both the success and the timeout path (bare `return` vs. falling off the end
  of the loop; `tests/test_ui.py:142-160`), so wrapping it in `assertTrue`
  directly would fail even on success. Instead, kept the existing idiom this
  same class already uses right below it (`focus_and_settle`'s own
  `focus_force` retry loop, `tests/test_ui.py:832-839`): pump, then assert the
  predicate explicitly afterward — `self.assertTrue(button.winfo_viewable(),
  "the button never became viewable")`.
- Comment above the test names symbols (`self.add_current_game`, `self.side`,
  `self.content`) rather than `afk_clicker.py:N` line numbers, per the
  reviewer's finding (d) that line-number comments are this repo's accepted
  convention but the task asked for symbol names here; kept short.

No production code changed.

### New test code
```python
    def _find_add_game_button(self):
        def walk(widget):
            if isinstance(widget, app.Button) and widget.command == self.ui.add_current_game:
                return widget
            for child in widget.winfo_children():
                found = walk(child)
                if found is not None:
                    return found
            return None
        found = walk(self.ui.side)
        self.assertIsNotNone(found, "no matching Button found for add_current_game")
        return found

    def test_a_button_still_runs_its_command(self):
        # "Add current game" is packed into the sidebar (self.side), a
        # sibling of the Hotkey/Clicking tab toggle rather than a child of
        # it, so it stays viewable while the Clicking pane is shown. Found
        # by its bound command rather than its label -- the label reads "+"
        # instead while the rail is collapsed.
        button = self._find_add_game_button()
        original_command = button.command
        clicked = []
        button.command = lambda: clicked.append(1)
        try:
            self.focus_and_settle(self.ui.click_ms)
            self.pump_until(lambda: button.winfo_viewable(), timeout=1.0)
            self.assertTrue(button.winfo_viewable(), "the button never became viewable")
            button.event_generate("<Button-1>", x=2, y=2)
            self.root.update()
            self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)
            self.assertEqual(clicked, [1])
        finally:
            button.command = original_command
```

### Verification this session
Venv: pynput 1.7.7 at
`/tmp/claude-1000/-home-dev-projects-afk-clicker/31f5a905-5b3f-4e0f-95d5-176a1d0748c4/scratchpad/pv`,
Xvfb `:99` already running, confirmed no other `unittest` process active first.

New test in isolation, 5 runs back to back:
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.NumBoxFocus.test_a_button_still_runs_its_command -v
```
`ok` all 5 times, ~0.14s each — no flakiness.

Whole `NumBoxFocus` class:
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.NumBoxFocus -v
```
```
Ran 10 tests in 1.220s

OK
```
All 10 pass, including the reworked test.

Full suite:
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```
```
Ran 375 tests in 66.613s

OK (skipped=10)
```
375 OK / skipped=10, matching the spec's AC3. Same pre-existing
`ResourceWarning`s in `tests/test_updater.py` (lines 686/704/740/753/768) as
round 1 and `docs/history/ac-10-test-review.md` already noted.

Sabotage-verify, redone per the review's own methodology (a monkeypatch of
`afk_clicker.Button._click` inside a one-off script run from the scratchpad
against the already-imported `afk_clicker` module, not an on-disk edit):
patched `_click` to call the command then `return "break"`, then ran the
reworked test via `unittest.TestLoader.loadTestsFromName` against the live,
patched module. Result: `FAIL` at `self.assertNotEqual(self.root.focus_get(),
self.ui.click_ms.entry)` — `AssertionError: <Entry ...> == <Entry ...>` —
same failure point the spec's AC2 names. Reordered the two assertions
(command check first, focus check second) under the same sabotage and reran:
`assertEqual(clicked, [1])` raised nothing; the run failed only on the (now
second) focus assertion, with the same message — confirming the command
assertion holds independently under sabotage, not merely unreached. Both
probe scripts lived only under the scratchpad directory and were deleted
after use.

`git diff --stat afk_clicker.py` and `git status --short afk_clicker.py` were
both empty throughout and after — the sabotage never touched disk.

### Scope check
```
git status --short
git diff --stat
```
```
 M tests/test_ui.py
?? docs/implementation.md
?? docs/spec.md
?? docs/test-review.md

 tests/test_ui.py | 34 ++++++++++++++++++++++++++++++++++
 1 file changed, 34 insertions(+)
```
Only `tests/test_ui.py` changed (net +11 lines over round 1's +23, now +34
total — the helper method plus the reworked test body). No scratch files left
in the repo tree.
