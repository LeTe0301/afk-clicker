# Test & Review: Button outline fails WCAG 1.4.11 non-text contrast (G#66/GH#117)

## Scope
Re-test + review pass against `docs/spec.md`'s 5 acceptance criteria, after the previous round's
blocked verdict (Defect 1: `ButtonOutlineContrast` was tautological, never exercised
`Button._colors()`). This round verifies the developer's rewrite actually fixes that.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | `Button` neutral-state outline is `MUTED` not `LINE`, both themes | `test_dark_enabled_clears_3_to_1` / `test_light_enabled_clears_3_to_1` — build a real `app.Button`, read `b.itemcget(b.shape, "outline")` | pass | ran directly; both `ok` |
| 2 | `Button` disabled-state outline is `MUTED` not `LINE`, both themes | `test_dark_disabled_clears_3_to_1` / `test_light_disabled_clears_3_to_1` — same but `b.set_enabled(False)` first | pass | ran directly; both `ok` |
| 3 | Regression test asserts computed WCAG contrast of **Button's actual rendered outline** vs `CARD` ≥ 3:1, both themes, and genuinely catches a regression | Independently reverted the two `LINE`/`MUTED` swaps in `afk_clicker.py` (not trusting the developer's claim), reran `ButtonOutlineContrast`, confirmed fail, restored, confirmed pass again | **pass** | see "Revert-and-rerun check" below — no longer tautological, Defect 1 is resolved |
| 4 | No change to `danger`/`primary`/hover states or other widgets | Diff read: only the two `LINE`→`MUTED` lines touched; full suite includes `PrimaryButtonTheme` and other theme-sensitive tests, all green | pass | diff + suite run |
| 5 | Full suite still green | `DISPLAY=:99 ~/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .` | pass | `Ran 604 tests in 144.452s — OK (skipped=12)` |

### Revert-and-rerun check (independent, not trusted from developer's report)
1. Reverted `afk_clicker.py`'s two lines back to `LINE` (`CARD, LINE, MUTED` / `(CARD_HI if hover
   else CARD), LINE, INK`), kept `tests/test_ui.py` as committed.
2. `DISPLAY=:99 ~/.venvs/afk-clicker-test/bin/python -m unittest tests.test_ui.ButtonOutlineContrast -v`
   → all 4 tests **FAIL**, with the exact expected ratios:
   `1.5806392530876632` (dark, both enabled/disabled) and `1.431640480293426` (light, both
   enabled/disabled) — matching the spec's and the earlier round's independently-recomputed
   1.58:1/1.43:1 exactly.
3. Restored the fix (`git diff afk_clicker.py` back to the exact original two-line diff), reran →
   all 4 **pass** (`OK`, 0.086s).

This confirms the rewritten test genuinely exercises `Button._colors()`'s real output rather than
asserting a fact about the palette dict — Defect 1 from the prior round is resolved.

### tearDown theme-leak check (G#67-adjacent)
`ButtonOutlineContrast.tearDown` resets to `"dark"` unconditionally after `self.root.destroy()`,
not just on the happy path. Verified both directions:
- Normal pass: ran `ButtonOutlineContrast` immediately followed by
  `Themes.test_module_globals_still_ship_dark_only` in one process → both `ok`, no leak.
- Failure path (the exact class of bug G#67 tracks — a test that calls `set_active_theme("light")`
  and doesn't restore `"dark"`): with the bug reintroduced, ran only
  `test_light_enabled_clears_3_to_1` (which switches to `"light"`, builds the Button, *then* fails
  its assertion) immediately followed by `Themes.test_module_globals_still_ship_dark_only` →
  the Themes test still passed (`ok`). unittest runs `tearDown` after a failed test method as long
  as `setUp` succeeded, so the reset fires even when the assertion inside the test raises — this
  test does not contribute to the G#67 leak class.

## Regression check
Full existing suite run as above: 604 tests, 12 skipped (pre-existing, display/platform-gated),
0 failures/errors. No tests outside `ButtonOutlineContrast` were touched by this diff.

## Review pass

Read the actual diff (`git diff afk_clicker.py tests/test_ui.py`) directly, not just the
implementation doc's description.

- **`afk_clicker.py`**: exactly the two lines specified in the spec's `Fix` section, nothing else.
  `danger`/`primary` branches untouched, matching non-goals.
- **`tests/test_ui.py`**: `_contrast()` is a correct, standard WCAG 2.x relative-luminance
  implementation (sRGB linearization, 0.03928 threshold, `(L1+0.05)/(L2+0.05)` with lighter over
  darker) — recomputed by hand against the same hex values and got identical ratios to the test's
  own failure output above. `ButtonOutlineContrast` follows the existing `PrimaryButtonTheme`
  instantiate-and-inspect pattern (same file, lines above it) rather than inventing a new idiom.
  `setUp`/`tearDown` match the shape used elsewhere in the file for tests that touch
  `set_active_theme`.
- **Simplicity**: no new abstractions beyond the one module-level `_contrast()` helper, which was
  already justified last round (no existing contrast helper in the codebase, confirmed by grep)
  and is unchanged this round. Four small test methods, one per theme × enabled state — proportionate
  to the two states the spec's acceptance criteria 1/2 name, no speculative extra coverage (hover
  state correctly excluded — outline color doesn't vary with hover in the neutral branch).
- **Security / correctness**: no external input, no injection surface; nothing to flag.

## Spec coverage

All 5 acceptance criteria traced to a specific test and independently verified this round (see
table above). No gaps.

## Findings
None — no must-fix, should-fix, or nit items from this round's review. The previous round's sole
defect is resolved and independently confirmed.

## Overall verdict
**Approve.** The fix is correct (independently recomputed contrast ratios, unchanged from last
round), the regression test genuinely exercises `Button`'s real rendered outline (independently
reverted and confirmed it fails, then restored and confirmed it passes), the tearDown's theme reset
is unconditional and doesn't leak even on a mid-test failure, and the full suite is green (604
tests, 0 failures). Ready to hand back to product-manager.
