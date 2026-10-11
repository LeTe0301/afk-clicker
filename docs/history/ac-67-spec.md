# Spec: Themes test-order pollution (G#67/GH#118)

Minimal spec written by the orchestrator — this is test-infrastructure-only, no production code
change expected, no design decision. Full product-manager/ux-designer pass skipped per the
project's token-efficiency convention.

## Problem

`Themes::test_module_globals_still_ship_dark_only` (`tests/test_ui.py:4286-4291`) asserts the
module-level globals (`app.BG`, `app.CARD`, ... `app.LINE`, etc.) still equal
`app.THEMES["dark"][...]`. It fails intermittently — specifically when it runs *after* some other
test that called `app.set_active_theme("light")` or `app.set_active_theme(app.resolve_appearance(...))`
without restoring `"dark"` afterward.

Confirmed pre-existing (not a regression) independently across three consecutive cycles this
session (G#63, G#64, G#65 reviews) via `git stash` isolation on unmodified `main` — same 11
subtest failures every time, always the same test, always this exact symptom.

There are 30 call sites of `app.set_active_theme(...)` across `tests/test_ui.py`. Most classes
that call it already have their own `tearDown()` unconditionally resetting to `"dark"` (e.g.
`tests/test_ui.py:4416-4418`, `:6325-6327`, `:7906-7907`, and others) — but at least one does not,
or one's reset isn't actually unconditional (e.g. only runs on success, or is itself conditional).

## What to do

This needs real **systematic debugging** (per the `superpowers:systematic-debugging` skill), not
a guess:

1. Find the actual culprit call site — the one that changes the active theme and does NOT
   unconditionally restore it before the test (or test class) is done. A fast way: run the suite
   with `-v` and compare which other test(s) ran immediately before a failing
   `test_module_globals_still_ship_dark_only` run across a few different orderings/seeds, or
   grep every `set_active_theme` call site and check each one's enclosing test method/class for a
   matching unconditional reset (most do have one — find which doesn't, or whose reset can be
   skipped, e.g. only in a `finally`-less path that an exception bypasses).
2. Fix at the root: ensure the real culprit's own test/class properly restores `"dark"`
   unconditionally (via `tearDown()` or `self.addCleanup(...)`, matching this file's own
   established convention — see the examples above).
3. Also consider (your judgment, root-cause permitting): if the real problem is that this
   decentralized "every class resets its own mess" convention is inherently fragile (easy for a
   new test/class to forget), a single centralized safety net (e.g. in the `Themes` test class
   itself, or in `tests/context.py` alongside its existing `gc.disable()` suite-wide pattern) that
   guarantees `app.set_active_theme("dark")` before `test_module_globals_still_ship_dark_only`
   runs would also close the gap — but prefer fixing the actual leak if a single clear culprit
   exists, rather than only papering over it with a defensive reset in the test that
   happens to be the one that notices.

## Non-goals

- No production code change (`afk_clicker.py`) expected — this is purely a test-isolation gap,
  unless systematic debugging finds otherwise.
- Don't touch the 20+ already-correctly-resetting call sites beyond what's needed to fix the
  actual leak.

## Acceptance criteria

1. Running the full suite in its normal order is green (as it already mostly is).
2. Running `Themes` and the actual culprit test/class in reverse order, or any order that
   previously could reproduce the pollution, no longer reproduces it — demonstrate this
   concretely (e.g. `python -m unittest tests.test_ui.<CulpritClass> tests.test_ui.Themes -v`).
3. A regression test or mechanism exists that would catch a *future* reintroduction of this same
   leak (not just a one-off manual verification).
4. Full suite still green, no regressions.
