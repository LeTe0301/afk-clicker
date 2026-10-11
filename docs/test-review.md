# Test & Review: Themes test-order pollution (G#67/GH#118)

## Scope
Test-infrastructure-only change: `tests/test_ui.py` only (plus a `backlog.md` status-line
update). No production code touched. Covers the spec's 4 acceptance criteria in
`docs/spec.md`: (1) full suite green in normal order, (2) the specific repro order no longer
reproduces, (3) a regression mechanism exists, (4) full suite still green overall.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1: full suite green in normal discovery order | automated | pass | `DISPLAY=:99 .../python -m unittest discover -s tests -t .` → `Ran 605 tests in 130.390s / OK (skipped=10)`, run myself this session |
| 2 | AC2: `AppIcon` → `Themes` repro order no longer fails post-fix | automated | pass | `python -m unittest tests.test_ui.AppIcon tests.test_ui.Themes -v` on the actual (unmodified) working tree → `Ran 8 tests in 0.376s / OK`, run myself |
| 2b | Pre-fix repro genuinely fails (sanity-check the claim, not just the fix) | automated | pass | `git stash` (reverting the whole diff) then same command → `FAILED (failures=11)` with the exact `test_module_globals_still_ship_dark_only` AssertionError pattern claimed; `git stash pop` restored cleanly, confirmed via `git diff` byte-identical to pre-stash |
| 3 | AC3: new `ThemeDoesNotLeakBetweenTestClasses` test is a real tripwire, not tautological | automated | pass | Surgically removed only the `AppIcon.tearDown()` block (kept the new test), ran `python -m unittest tests.test_ui.ThemeDoesNotLeakBetweenTestClasses -v` directly → `FAILED (failures=1)` with 11 sub-failures matching the same AssertionError shape. Restored the exact original 2-hunk diff by hand (verified `git diff tests/test_ui.py` is byte-identical to the diff captured before this check), then reran the same command → `OK`. This is a genuine revert-and-watch-it-fail check I performed myself, not a restatement of the developer's claim. |
| 4 | AC4: full suite still green / no regressions | automated | pass | Same run as #1; matches developer's claimed count exactly (605 tests, 10 skipped, 0 failures) |
| 5 | Root-cause claim: 28 of 29 original `set_active_theme` call sites already have an unconditional `tearDown` reset, `AppIcon` is the one exception | automated (AST script) | pass | Wrote a one-off Python AST script (not committed — scratch check only) walking every class containing a `set_active_theme` call in the pre-fix file and checking for a top-level unconditional `set_active_theme("dark")` call in `tearDown`. Output: all 23 theme-touching classes in the current (fixed) file pass except `SetActiveThemeUnknownName`, which has no `tearDown` by design — confirmed separately that `set_active_theme()` (`afk_clicker.py:99-118`) raises `ValueError` *before* mutating any global, so that call site never actually leaks. `AppIcon` is listed as `tearDown=yes` only because the fix is now in place. |
| 6 | Causal chain: does `_apply_appearance("light")` (what `AppIcon`'s test calls) actually go through `set_active_theme`? | code read | pass | `afk_clicker.py:4301-4309` — `_apply_appearance()` calls `set_active_theme(resolved)` directly. Confirms the root-cause narrative is a real call chain, not an assumption. |

## Regression check
Full existing suite run (CI's exact invocation): `DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .` — result: **pass**, `Ran 605 tests in 130.390s`, `OK (skipped=10)`. Only output noise was pre-existing `ResourceWarning`s from `tests/test_updater.py` (unrelated file, unrelated to this diff).

## Defects found
None. Testing pass is clean — proceeding to review.

---

## Spec coverage
All 4 acceptance criteria implemented and independently verified as above:
1. ✅ full suite green (normal order) — verified.
2. ✅ repro order fixed — verified both directions (fails pre-fix, passes post-fix).
3. ✅ regression mechanism exists and is a real tripwire (verified via my own revert, not trust in the developer's claim).
4. ✅ full suite still green — verified, same run as #1.

No production code was touched, matching the spec's non-goal. The other 28 already-correct
call sites were left untouched (spot-checked structurally via AST, not just a few manual
samples) — matches the spec's explicit non-goal against touching them.

## Findings (most severe first)

### 1. Spec's own call-site count is off by one — nit
- File: `docs/spec.md:19` ("There are 30 call sites of `app.set_active_theme(...)`")
- Issue: actual count on unmodified `main` (`git show HEAD:tests/test_ui.py | grep -c set_active_theme`) is 29, not 30. The developer's implementation.md correctly uses 29. This is an orchestrator spec-authoring slip, not a developer defect, and it didn't affect the actual debugging (which was done against the real 29, not the stated 30).
- Failure scenario: none — purely a documentation discrepancy, doesn't affect correctness of the fix or tests.

No should-fix or must-fix findings. The diff is minimal (one `tearDown()` override matching an established in-file convention, one new regression test, no production code), the regression test genuinely catches the specific leak shape it targets (verified by revert), and the documented scope limitation (this tripwire only covers the `AppIcon`↔`Themes` adjacency, not every possible future leak) is an honest, spec-compliant tradeoff explicitly reasoned through in `docs/implementation.md`, consistent with the spec's own preference for a root-cause fix over a blanket safety net.

## Follow-ups (non-blocking)
- Correct `docs/spec.md`'s "30 call sites" to 29 if/when this spec doc is revisited (cosmetic only).

## Overall verdict
**Approve.**
