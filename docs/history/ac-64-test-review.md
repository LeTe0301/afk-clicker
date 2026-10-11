# Test & Review: Duplicate a macro (G#64/GH#113)

## Scope
Covers all 6 acceptance criteria in `docs/spec.md`, the two deliberate deviations
documented in `docs/design.md` (two-line row, `_truncated_row_name`), and the
developer's own flagged limitations.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1: hotkey+steps+interval cloned into `"{name} (copy)"` | automated | pass | `tests/test_ui.py::DuplicateMacro::test_duplicate_copies_name_suffix_hotkey_steps_and_interval` |
| 2 | AC2: no hotkey/no interval duplicate matches original | automated | pass | `DuplicateMacro::test_duplicate_with_no_hotkey_or_interval_matches_the_original` |
| 3 | AC3: shared-hotkey chord would trigger both (no collision guard) | automated | pass | `DuplicateMacro::test_original_and_duplicate_both_arm_the_shared_hotkey_independently` (asserts 2 independently armed watchers, same convention as existing hotkey tests — no real keypress simulated anywhere in this suite) |
| 4 | AC4: duplicate's own interval timer fires independently | automated | pass | `DuplicateMacro::test_duplicates_own_interval_timer_fires_independently` (real `self.root.after()` timer observed firing via `pump_until`) |
| 5 | AC5: original untouched (same id/fields) after duplicating | automated | pass | `DuplicateMacro::test_duplicating_does_not_alter_or_remove_the_original` |
| 6 | AC6: duplicate persists across game switch and a fresh `Store` reload | automated | pass | `DuplicateMacro::test_duplicate_persists_across_a_game_switch_away_and_back` |
| 7 | Design: two-line row layout (name+hotkey / interval+4 buttons, order Run/Duplicate/Edit/Delete) | manual, this pass | pass | screenshot below; widget-tree dump (`row_top`/`row_bottom` frames, 4 `Button`s in `row_bottom`) |
| 8 | Design: `_truncated_row_name` preserves `" (copy)"` suffix on a long name, exactly 40 chars | manual, this pass, recomputed | pass | direct call: 57-char name → `'AAAA...AAA…A (copy)'`, len 40, suffix intact |
| 9 | Pre-existing: empty-macros-list pane unaffected by row-layout change | automated (unchanged) | pass | `MacrosTab::test_a_fresh_game_has_no_macros_and_the_pane_says_so` |
| 10 | No existing test assumed a single-line row structure | static grep | pass | `grep -n "macros_list\b"` in `tests/test_ui.py` → only the one empty-state label check (#9); nothing inspects row/button widget-tree shape pre-existing |

## Regression check
Targeted: `DISPLAY=:99 python -m pytest tests/test_ui.py -k "DuplicateMacro or MacrosTab or MacroIntervals" -q`
→ **23 passed** (6 new + 17 pre-existing, no regressions).

Full suite: `DISPLAY=:99 python -m pytest tests/test_ui.py -q` → **457 passed, 11 failed**
(all 11 are `Themes.test_module_globals_still_ship_dark_only` subtests). Independently
re-verified the pre-existing claim myself (did not just trust the developer's report):
`git stash -u`, re-ran the full suite on unmodified `main` → **451 passed, 11 failed**,
identical subtest names/values (`BG`, `CARD`, `CARD_HI`, `LINE`, `INK`, `MUTED`, `ACCENT`,
`ACCENT_INK`, `ACCENT_HI`, `OK`, `BAD`, same mismatched hex pairs each time). 451 + 6 new
`DuplicateMacro` tests = 457, accounting for the only numeric difference. Confirmed
test-order/theme-global pollution pre-existing, unrelated to this diff. Restored the stash
afterward (`git stash pop`); working tree is clean/unchanged.

`python -m py_compile afk_clicker.py tests/test_ui.py` → clean. No lint step exists in
`.github/workflows/ci.yml` (confirmed: it runs `python -m unittest discover` directly).

## Manual exercise
Drove the real app under Xvfb :99 (not just the test harness): created a macro with a long
name, a hotkey, and an interval, switched to the Macros tab, called `_duplicate_macro`, and
inspected both the live widget tree and a screenshot.

- Widget tree: each row is `row_top` (hotkey label right, name label left-expand) over
  `row_bottom` (interval label left, `Delete`/`Edit`/`Duplicate`/`Run` packed right-to-left
  — same code order as the diff, renders visually left-to-right as
  `[Run][Duplicate][Edit][Delete]`), exactly matching `docs/design.md`'s wireframe.
- Screenshot confirms: original row `"Farm north wood with a really l…ive name"` / `Ctrl + M`
  / `every 200 ms`; duplicate row immediately below it, `"Farm north wood with a really
  l…e (copy)"` / `Ctrl + M` / `every 200 ms` — the `(copy)` suffix is visible, matching the
  design's stated purpose for the middle-ellipsis truncation. No-hotkey/no-interval row
  (`Quick click`) renders correctly with `No hotkey` and no interval label. No clipping or
  overlap at this data size.

## Defects found
None. Testing pass is clean.

---

## Spec coverage
All 6 acceptance criteria in `docs/spec.md` are implemented and covered by an automated test
(rows 1–6). AC1's "verified by opening its Edit dialog" is satisfied functionally rather than
literally: `_open_macro_editor` populates its dialog straight from `macro["hotkey"]`/
`macro["steps"]` with no transformation, so asserting on the stored macro dict (as the test
does) verifies the same data the dialog would show — confirmed by reading
`_open_macro_editor`'s `ctx` construction directly. Not a gap.

Both `docs/design.md` deviations (two-line row, `_truncated_row_name`) are implemented as
specified and independently verified visually (rows 7–8), not just read from code.

## Findings (most severe first)

### 0. (Verification note, not a defect) Re-derived the developer's and design doc's factual claims rather than trusting them
- Re-ran the full suite on unmodified `main` myself (not inferred from the developer's report)
  to confirm the 11 `Themes` failures are pre-existing — identical failure set, count checks
  out exactly (451 vs 457 = the 6 new tests). See Regression check.
- Recomputed every WCAG contrast figure in `docs/design.md` from the literal theme hex values
  (`afk_clicker.py:84`, `THEMES["dark"]`) using the standard relative-luminance formula:
  INK/CARD = 13.32:1 (doc: 13.3:1), INK/CARD_HI = 11.62:1 (doc: 11.6:1), MUTED/CARD = 5.76:1
  (doc: 5.8:1), LINE/CARD (non-text, 3:1 threshold) = 1.58:1 (doc: 1.6:1, fails). All match
  within rounding; all pass/fail conclusions hold. No new color pairing was introduced by this
  diff — the Duplicate button reuses the same `Button`/label tokens as its siblings — so the
  pre-existing `LINE`-outline gap is correctly out of scope here, not a new regression.
- Re-derived the `_truncated_row_name` 40-char/suffix-preservation math directly (row 8) rather
  than accepting the design doc's arithmetic.

No must-fix or should-fix findings. Nothing to flag as a nit either — the diff is minimal
(one new method, one new helper, the row split both are predicated on), matches `docs/design.md`
and `docs/spec.md`'s reconciled scope exactly, and introduces no new abstraction, no new
dependency, no new color/token, and no change to `_save_macro`/`_delete_macro`/the editor dialog.

## Follow-ups (non-blocking)
- Pre-existing, not newly introduced by this diff, already correctly flagged by
  `docs/design.md`/`docs/implementation.md` as out of scope: `Button`'s `LINE`-on-`CARD`
  outline contrast (1.6:1, fails WCAG 1.4.11's 3:1) and mouse-only (non-keyboard-focusable)
  buttons. Both affect every button in the app, not just Duplicate. Worth a dedicated
  accessibility-pass ticket, not blocking here.
- The 11 `Themes.test_module_globals_still_ship_dark_only` subtest failures are pre-existing
  test-order pollution on `main`, confirmed again this cycle (also noted in the prior session's
  handoff commit `65e4baa`). Worth a dedicated fix at some point given it now shows up
  repeatedly, but out of scope for G#64.

## Overall verdict
**Approve.**
