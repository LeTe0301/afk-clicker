# Implementation: Themes test-order pollution (G#67/GH#118)

## Summary
`AppIcon` (`tests/test_ui.py:4092`) had no `tearDown()` override at all. Its
`test_icon_reference_survives_a_rebuild` calls `self.ui._apply_appearance("light")`
(line 4109, now 4116) and never restores `"dark"` -- unlike every other theme-touching
class in the file, which has its own unconditional reset. That left the module-level
theme globals pointed at Quartz (light) after `AppIcon` ran, which is exactly the
state `Themes::test_module_globals_still_ship_dark_only` (`tests/test_ui.py:4286-4291`
pre-fix) was failing against whenever it ran afterward. Added `AppIcon.tearDown()` to
match the file's own convention, plus a regression test that runs the `AppIcon` ->
`Themes` pair as a sub-suite so a future class that forgets the same reset fails
loudly here too.

## Root cause
Confirmed by elimination, not guesswork: grepped every one of the 29 `set_active_theme(`
call sites in `tests/test_ui.py` and checked each enclosing class for an unconditional
reset. 28 of them already have one (`tearDown()` calling `app.set_active_theme("dark")`
unconditionally, several via `super().tearDown()` first -- e.g. `TabBarNavigation`
line 3850-3852, `RunningClickerSurvivesRebuild` line 6964-6966). `AppIcon` was the one
exception: it inherits `UITestCase` but never overrode `tearDown()`, so
`test_icon_reference_survives_a_rebuild`'s `_apply_appearance("light")` call (needed to
prove the icon reference survives a rebuild under a real theme change) leaked
unconditionally -- not just on an exception path, every single run.

This didn't show up in the normal full-suite run because `unittest discover`'s default
alphabetical class ordering puts `AppIcon` (position 6) far before `Themes` (position
82), and `TabBarNavigation` (position 81, immediately before `Themes` alphabetically)
*does* reset dark correctly in its own `tearDown()` -- so by the time `Themes` runs,
the leak has already been masked by an unrelated class's own correct reset. It only
surfaces when `AppIcon` (or no later resetting class) runs immediately before `Themes`,
exactly the kind of subset/reordering the spec's acceptance criteria asked to
demonstrate.

Repro (before the fix, confirmed in this session):
```
$ DISPLAY=:99 .../bin/python -m unittest tests.test_ui.AppIcon tests.test_ui.Themes -v
...
FAIL: test_module_globals_still_ship_dark_only ... (name='ACCENT')
AssertionError: '#2b58cc' != '#e08a55'
----------------------------------------------------------------------
Ran 8 tests in 0.373s
FAILED (failures=11)
```
After the fix, the identical command:
```
Ran 8 tests in 0.368s
OK
```

## Changes by file
- `tests/test_ui.py`:
  - `AppIcon` (line 4092) -- added `tearDown()`: `super().tearDown()` then
    `app.set_active_theme("dark")` unconditionally, matching the exact pattern used by
    `TabBarNavigation`/`RunningClickerSurvivesRebuild`/etc. This is the root-cause fix.
  - Added `ThemeDoesNotLeakBetweenTestClasses` (new standalone `unittest.TestCase`,
    placed right after `Themes`) with one test,
    `test_app_icon_then_themes_leaves_dark_restored`, that builds a `unittest.TestSuite`
    of exactly `AppIcon` + `Themes`, runs it into a throwaway `unittest.TestResult`, and
    asserts `result.wasSuccessful()`. This is the permanent regression test for AC3:
    verified it actually catches the leak by reverting the `AppIcon.tearDown()` fix
    (`git stash`) and re-running just this mechanism directly -- it failed with 11
    failures, exactly matching the original repro, then passed again after restoring
    the fix.

No production code (`afk_clicker.py`) was touched -- this was purely a test-isolation
gap, as the spec expected.

## Key decisions / tradeoffs
- **Root-cause fix over a centralized safety net.** The spec allowed either; a single,
  clear, unconditional culprit existed (`AppIcon`), so fixed that directly rather than
  adding a blanket "force dark" `setUp()` to `Themes`. A blanket reset there would have
  made `Themes` pass regardless of which class leaked what, which defeats the point of
  the new regression test (AC3 wants a future reintroduction to be *caught*, not
  silently absorbed) -- the spec itself warns against "only papering over it with a
  defensive reset in the test that happens to be the one that notices."
- **Regression test runs a nested sub-suite rather than asserting on `app._ACTIVE`
  directly.** This exercises the exact two-class interaction the bug lived in (ordering
  between two separate `TestCase` classes), not just a static reset-state check, and
  it's the same mechanism the spec's own acceptance criteria used to demonstrate the
  repro. Verified it is a real tripwire, not a no-op, by deliberately reverting the fix
  and re-running it (see above) -- it failed as expected.
- Did not touch any of the other 28 already-correct call sites, per the spec's
  explicit non-goal.

## Deviations from spec
None. Fixed the actual leak (`AppIcon`) rather than only adding a defensive reset, and
also added the regression mechanism AC3 asked for, in that priority order per the
spec's own guidance.

## Known limitations
The new regression test only covers reintroduction of *this* leak shape (a
theme-touching class with no reset) specifically between `AppIcon` and `Themes`. A
different future class that leaks theme state elsewhere in the alphabet, without ever
running adjacent to `AppIcon`, would not be caught by this test -- it would need the
same kind of pairwise check added for itself, following this one as a template. This
was a deliberate choice (see "Key decisions" above): a fully generic safety net was
available but would have masked rather than caught future leaks.

## How to verify locally
1. Repro proof (pre-fix behaviour, for reference -- do not actually revert the fix to
   run this): `git stash`, then
   `DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest tests.test_ui.AppIcon tests.test_ui.Themes -v`
   shows 11 failures; `git stash pop` restores the fix.
2. Fixed-state proof: the same command now prints `Ran 8 tests ... OK`.
3. New regression test alone:
   `DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest tests.test_ui.ThemeDoesNotLeakBetweenTestClasses -v`
   -> `OK`.
4. Full suite (CI's exact invocation):
   `DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .`
   -> `Ran 605 tests ... OK (skipped=10)`, confirmed in this session.
