# Test & Review: Confirm before deleting a custom game profile or macro (G#63/GH#111)

## Scope
Covers all 8 acceptance criteria in `docs/spec.md` plus the design-added edge cases (single
open slot, rebuild teardown, stale-target re-check, long/empty name) and the developer-flagged
`GameItem` click-dispatch deviation.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1: glyph click opens themed modal naming profile; not yet deleted | automated | pass | `tests/test_ui.py::DeletedGames::test_clicking_the_delete_glyph_opens_a_confirm_dialog_without_selecting_first`, `DeleteConfirmDialogs::test_game_dialog_names_the_profile_and_does_not_delete_yet` |
| 2 | AC2: Delete removes profile exactly as `_delete_game` did | automated | pass | `DeleteConfirmDialogs::test_game_dialog_confirm_deletes_exactly_like_delete_game` |
| 3 | AC3: Cancel/Escape/close box leave profile intact | automated | pass | `test_game_dialog_cancel_leaves_the_profile_untouched`, `..._escape_...`, `..._close_box_...` |
| 4 | AC4: macro Delete opens modal naming macro; not yet deleted | automated | pass | `test_macro_dialog_names_the_macro_and_does_not_delete_yet` |
| 5 | AC5: Delete removes macro exactly as `_delete_macro` did | automated | pass | `test_macro_dialog_confirm_deletes_exactly_like_delete_macro` |
| 6 | AC6: Cancel/Escape leave macro intact (close-box path shares the identical `_cancel`/`WM_DELETE_WINDOW` code already proven on the game dialog, see Findings #3) | automated | pass | `test_macro_dialog_cancel_leaves_the_macro_untouched`, `..._escape_...` |
| 7 | AC7: uses theme tokens/`Button`, not `tkinter.messagebox` | automated + static | pass | `grep -n messagebox afk_clicker.py` → no matches; code reads `BG/INK/MUTED/BAD/ACCENT_INK`, `Button(...)` throughout `_open_confirm_dialog` |
| 8 | AC8: built-in profiles still show no delete glyph | automated | pass | `DeletedGames::test_only_custom_profiles_get_a_delete_glyph`, `test_built_in_profiles_cannot_be_deleted` |
| 9 | Edge: rapid double-click can't stack two dialogs | automated | pass | `DeleteConfirmDialogs::test_only_one_game_dialog_is_ever_open`, `test_a_double_click_on_the_delete_glyph_cannot_stack_two_dialogs` |
| 10 | Edge: `_rebuild_ui()` closes an open confirm dialog | automated | pass | `test_rebuild_ui_closes_an_open_confirm_dialog` |
| 11 | Edge: macro confirm is a no-op if current game changed while dialog open | automated | pass | `test_macro_dialog_confirm_is_a_no_op_if_the_current_game_changed` |
| 12 | Edge: confirm while deleted game is currently selected → falls back to `global` | automated | pass | `test_game_dialog_confirm_deletes_exactly_like_delete_game` (adds+selects, then confirms, asserts fallback) |
| 13 | Design "Copy rules": long name (>40 chars) truncated to 39+`…` | automated, added this pass | pass | `test_game_dialog_truncates_a_long_profile_name` (new) |
| 14 | Design "Copy rules": empty name → generic fallback heading | automated, added this pass | pass | `test_game_dialog_falls_back_to_generic_heading_for_an_empty_name`, `test_macro_dialog_falls_back_to_generic_heading_for_an_empty_name` (new) |
| 15 | Deviation: `GameItem._on_click` fix is load-bearing, not speculative | manual revert-and-watch-it-fail | pass | reverted the fix locally, re-ran test #1 → failed exactly as implementation.md predicted (`current == 'custom:some other game'`, expected `'global'`); restored the fix, re-ran → passed again (see Findings #0 note) |
| 16 | Button `danger` kwarg doesn't collide with existing positional callers | static | pass | `grep -nE "Button\([^)]*,\s*(True|False)\s*[,)]" afk_clicker.py` → no hits; every existing call site passes `width=`/`primary=` by keyword |
| 17 | WCAG contrast claims in `docs/design.md` | recomputed independently | pass | see Findings #0; all text pairings ≥4.5:1, non-text gap pre-existing and correctly flagged, not introduced by this change |

## Regression check
Full existing suite: `DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python3 -m unittest discover -s tests -t .`
Result: **573 passed, 10 skipped (pre-existing, platform-gated), 0 failures** — 570 from the
developer's own set plus 3 new tests I added this pass (long-name truncation, two empty-name
fallbacks). Re-ran the targeted classes (`DeletedGames`, `DeleteConfirmDialogs`, `MacrosTab`,
`MacroIntervals`) individually with `-v` as well; all green. `python3 -m py_compile afk_clicker.py
tests/test_ui.py` compiles clean.

## Defects found
None. Testing pass is clean.

---

## Spec coverage
All 8 acceptance criteria and every edge case in `docs/spec.md` are implemented and covered by an
automated test (see table above). Two design-level requirements (`docs/design.md` "Copy rules":
long-name truncation, empty-name fallback) were implemented correctly but had no test before this
pass — I added three tests to close that gap (rows 13–14); all pass against the existing,
unmodified implementation.

## Findings (most severe first)

### 0. (Verification note, not a defect) Developer's flagged deviation independently confirmed
I did not take the `GameItem._on_click` root-cause claim on faith. I temporarily reverted it to
the pre-change `self.bind("<Button-1>", lambda e: self.on_click(self.profile["id"]))`, re-ran the
affected test, and it failed exactly as predicted (`self.ui.current` became
`'custom:some other game'` instead of staying `'global'` — the row reselected itself on the same
click that was supposed to only open a confirm dialog). Restored the fix, re-ran, green again. The
fix is real, necessary, correctly scoped to `GameItem` only, and well-commented. Also recomputed
every WCAG relative-luminance/contrast figure in `docs/design.md` from the literal hex values
(independently, via the standard formula) — all ratios matched within rounding (e.g. INK on BG
14.47:1 vs. documented 14.52:1), and every AA pass/fail conclusion holds. No issues.

### 1. Nit — macro dialog's close-box (`WM_DELETE_WINDOW`) path has no macro-specific test
- File: `tests/test_ui.py`, `DeleteConfirmDialogs`
- Issue: the game dialog gets a dedicated close-box test
  (`test_game_dialog_close_box_leaves_the_profile_untouched`); the macro dialog doesn't. Both route
  through the identical shared `_cancel`/`WM_DELETE_WINDOW` wiring in `_open_confirm_dialog`
  (`afk_clicker.py` ~`:5237-5241`), so this isn't a code-path gap — the mechanism is proven once
  and reused — just a documentation/completeness nit against AC6's literal wording ("Cancel is
  clicked, Escape is pressed, or the window is closed").
- Failure scenario: none realistic — would only matter if a future change diverged the two
  dialogs' close-box wiring, which the shared-helper design makes unlikely.

### 2. Nit — `backlog.md` diff is a pre-emptive entry, not this cycle's concern
- File: `backlog.md`
- Issue: adds a "G#63 / GH#111 ... (Leo, approved 2026-10-10)" line under "In progress" items
  while the item is still being built/reviewed. Harmless, orchestrator's job to reconcile at
  close-out, not a code defect.

No must-fix or should-fix findings.

## Follow-ups (non-blocking)
- Optionally add a macro-specific close-box test for completeness (Finding #1) — low value given
  the shared code path, skip unless touching this area again anyway.

## Overall verdict
**Approve.**
