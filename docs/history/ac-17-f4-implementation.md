# Implementation: UI scale (story #17, Feature 4 — final feature)

## Summary
Added a fourth Settings control, "UI scale" (90% / 100% / 115% / 130%),
below Theme in the existing Appearance card. `self.s` is now the DPI factor
(`self._dpi_s`, still read once from `tk scaling` at startup) multiplied by
the chosen step, so every widget size/font/radius in the file — which
already multiplies by `self.s` — picks the new effective value up for free
on the same in-place rebuild Feature 3 built for Appearance. Persisted as
`settings.json["ui_scale"]`, sanitized in `Store.__init__` exactly like
`"appearance"`. This session built on top of already-completed, uncommitted
WIP (module-level `UI_SCALE_FACTORS`/`UI_SCALE_DEFAULT`, the `Store` default
+ sanitizer, the `self.s`/`self._dpi_s` split, `_apply_minsize`,
`_request_rebuild`, and `_apply_ui_scale` — all present, verified against
`docs/spec.md`, before this session's own changes started); this session
wired the control into the Settings page UI, added the full test suite, and
updated the README.

## Changes by file
- `afk_clicker.py`
  - `_build_settings(s)` (`afk_clicker.py:1890-1910`): added a second `Row`
    ("UI scale") inside the existing Appearance `card()`, directly below
    the Theme `Row` and before the "System is currently…" hint label,
    holding a 4-option `Segmented` (`90%`/`100%`/`115%`/`130%`, `width=220`)
    bound to a new `self.ui_scale_var`. `self.ui_scale_var.trace_add
    ("write", ...)` is registered *after* the `Segmented(...)` constructor
    call — same ordering as `appearance_var`'s own trace, and for the same
    reason (Tcl fires write traces most-recently-registered-first;
    registering the trace before the `Segmented` would fire `_apply_ui_
    scale` *after* the `Segmented`'s own repaint trace, and destroying the
    `Segmented` mid-repaint via the deferred rebuild raises `TclError`).
  - No other production-code changes this session — `UI_SCALE_FACTORS`,
    `UI_SCALE_DEFAULT`, the `Store` default/sanitizer, `self._dpi_s`/
    `self.s`, `_apply_minsize`, `_request_rebuild`, and `_apply_ui_scale`
    were already present as uncommitted WIP before this session's edits
    began (confirmed via `git diff afk_clicker.py` read in full before
    touching anything, per the task's own "already done" list) and their
    numeric behavior was independently verified against every acceptance
    criterion via a throwaway interactive script (see "Key decisions"),
    not just trusted.
- `tests/test_ui.py` — 15 new tests, one per acceptance-criterion bullet
  (plus Store-level round-trip/garbage coverage mirroring `AppearanceStore`'s
  own shape):
  - `UIScaleStore` (new class, `tests/test_ui.py:1559`, right after
    `AppearanceStore`): `Store.__init__`'s `"ui_scale"` sanitization —
    `test_a_fresh_store_defaults_to_100`, `test_known_values_round_trip`,
    `test_garbage_values_fall_back_to_100`, `test_a_missing_ui_scale_key_
    defaults_to_100`, and `test_a_garbage_on_disk_value_resolves_to_100_
    end_to_end` (writes garbage directly into the running test's own
    `settings.json`, matching `test_a_missing_appearance_key_defaults_to_
    system`'s technique, then `self.restart()`s into a fresh
    `AfkAutoclicker` and asserts `self.ui.store.data["ui_scale"] == "100"`
    and `self.ui.s == self.ui._dpi_s` — the spec's exact wording).
  - `UIScale` (new class, `tests/test_ui.py:1605`, after `UIScaleStore`,
    before `SettingsNavigation`): `test_each_step_multiplies_the_dpi_
    factor` (all 4 steps, `self.ui.s == self.ui._dpi_s * UI_SCALE_FACTORS
    [value]`), `test_a_sampled_widget_and_font_scale_with_it` (`self.ui.
    status`'s Canvas `width` and the Theme `Segmented`'s text-item `font`),
    `test_minsize_updates_on_every_scale_change`, `test_a_bigger_step_
    grows_the_window_to_the_new_minimum`, `test_a_manually_enlarged_
    window_is_never_shrunk_by_a_scale_change`, `test_a_scale_choice_
    survives_a_restart_with_no_settings_visit`, `test_ui_scale_is_
    persisted_to_disk`.
  - `RunningClickerSurvivesRebuild.test_worker_running_and_clicks_
    continue_across_a_scale_change` (new test method on the *existing*
    class, `tests/test_ui.py:2100`, mirroring its own Appearance-triggered
    sibling test exactly, just with `_apply_ui_scale("130")` in place of
    `_apply_appearance("light")`) — the running-clicker-survives-a-
    scale-triggered-rebuild criterion.
  - `OverlappingScaleAndAppearanceChanges` (new class, after
    `OverlappingAppearanceChanges`): `test_scale_then_appearance_coalesce_
    into_one_rebuild` and `test_appearance_then_scale_coalesce_into_one_
    rebuild` — the counting-wrapper technique from `test_five_rapid_
    appearance_changes_coalesce_into_exactly_one_rebuild`, generalized to
    interleave the two kinds of change in both orders, asserting both the
    final rendered theme and the final `self.ui.s`.
  - The zero-uncaught-callback-exceptions criterion needs no separate
    test: it's `UITestCase.tearDown`'s existing, unconditional assertion,
    which every test above already runs through.
- `README.md` (`### Aussehen` section, one sentence added after the
  existing Theme/System paragraph): names the four percentages and "sofort
  wirksam, ohne Neustart", mirroring the phrasing of the Theme sentence
  immediately above it.

## Key decisions / tradeoffs
- **Font-size assertion format.** The spec's acceptance criterion asks for
  a sampled widget's "font scale" without specifying how a canvas text
  item's font is read back, and there's no existing precedent in the test
  file for reading a `Segmented`/`StatusPill` text item's font. Checked the
  actual runtime value with a throwaway interactive script (not committed
  anywhere — run via `python -c ...` against the real `Segmented`
  instance) and confirmed `itemcget(item, "font")` returns a plain string
  like `"{Segoe UI} 12"` for an integer point size; the test asserts
  against that exact string shape (`f"{{Segoe UI}} {int(9 * self.ui.s)}"`).
- **"No Settings visit needed" (restart criterion), read against existing
  precedent.** The spec's literal wording says both `self.ui.s` *and*
  `self.ui.ui_scale_var.get()` should reflect the persisted choice after
  `restart()` "with no Settings visit needed." `self.ui.s` genuinely needs
  no visit (computed straight from `self.store.data` in `__init__`), but
  `ui_scale_var` — exactly like `appearance_var` before it — is only
  constructed inside `_build_settings()`, i.e. only after `_show_settings()`
  has run at least once; every existing test that reads `appearance_var`
  already opens Settings first (e.g. `test_settings_page_stays_open_
  across_a_theme_switch_with_the_new_segment_selected`). Followed that
  established, already-working precedent for the `ui_scale_var` half of the
  assertion instead of the literal "no visit" wording: the test checks
  `self.ui.s` immediately after `restart()` with no Settings visit, then
  opens Settings once to confirm `ui_scale_var.get()` too. This is a minor
  wording tension in the spec, not a behavior gap — `appearance_var` has the
  identical constraint today and it isn't treated as a bug there.
- **`test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change`
  derives its "enlarged" geometry from `self.ui._dpi_s`, not a hardcoded
  literal.** An initial version used a fixed `"1000x900"` (matching
  `WindowResize`'s own convention) and failed under this environment's real
  DPI (`self.ui._dpi_s ≈ 1.04`, from `tk scaling` under this Xvfb): 900px
  was larger than 100%'s minsize but *smaller* than 130%'s (`int(690 *
  1.04 * 1.3) ≈ 934`), so growing to 130% correctly grew the window per
  spec — the test's fixed expectation was wrong, not the code. Fixed by
  computing the "enlarged" size from `self.ui._dpi_s * UI_SCALE_FACTORS
  ["130"]` plus a fixed margin, so the test holds on any DPI the suite
  runs under, not just this one.

## Deviations from spec
None in production code — the Settings-page wiring matches `docs/spec.md`
§5's snippet exactly, including the trace-registration ordering §2
requires. The one deviation is in test wording only (see "Key decisions"
above, the `ui_scale_var`/"no Settings visit" point): the test suite
matches the already-established, already-passing `appearance_var`
precedent rather than a literal reading of the acceptance criterion that
would require restructuring when `ui_scale_var` is built — out of scope for
this feature, and `appearance_var` already has the identical shape today.

## Known limitations
- A real `<Button-1>` click on the new `Segmented` control is now exercised
  end-to-end by `UIScale.test_two_real_ui_scale_segmented_clicks_with_no_
  pump_between_them` (`tests/test_ui.py:1703`, added in the fix pass below)
  — this closes the gap an earlier revision of this document described as
  "indirect coverage via `CapturesCallbackExceptions`". That description
  was inaccurate (see "Fix pass: reviewer findings" below for the
  correction and for what was actually verified about the trace-ordering
  hazard itself, empirically, not just asserted).
- This session did not modify `Store.__init__`, `UI_SCALE_FACTORS`,
  `_apply_minsize`, `_request_rebuild`, or `_apply_ui_scale` — all were
  already correct, uncommitted WIP before this session's changes began.
  Their behavior was independently verified against every numeric
  relationship in the spec's acceptance criteria (each step's factor, the
  minsize formula, grow-only vs. never-shrink, garbage-value sanitization,
  coalescing, persistence) via a throwaway interactive script run against
  the live app before writing the corresponding test, then confirmed again
  by the final test suite run below.

## Fix pass: reviewer findings (`docs/test-review.md` Findings 1 and 2)

No production code changed in this pass — both findings were in the
test/docs layer, as scoped.

### Finding 1 — real-click regression test on the new Segmented
- `tests/test_ui.py:156` — `_appearance_segment(self, var=None)` gained an
  optional `var` parameter (default `self.ui.appearance_var`, preserving
  every existing call site — `tests/test_ui.py:1643`, `1798`, `2339`, and
  its own docstring example — unchanged). Chose "add an optional parameter
  to the existing helper" over "extract a `_segment_for(var)` + thin
  `_appearance_segment()` wrapper" because the helper's whole body is the
  five-line recursive `walk()`; a second method whose only job is to
  supply a default argument would be pure indirection for no reuse benefit
  — the simpler option reads more naturally alongside the file's existing
  style (small, direct helpers, e.g. `pump_until`, `restart`, right above
  it in the same class).
- `tests/test_ui.py:1703` — new test
  `UIScale.test_two_real_ui_scale_segmented_clicks_with_no_pump_between_them`,
  mirroring `OverlappingAppearanceChanges.
  test_two_real_segmented_clicks_with_no_pump_between_them` (`tests/
  test_ui.py:2309`): opens Settings, locates the UI-scale Segmented via
  `self._appearance_segment(self.ui.ui_scale_var)`, fires two real
  `<Button-1>` events back to back with no `root.update()` between them
  (`seg_w = seg.w / 4`, since this control has 4 options, not Theme's 3),
  then one `root.update()`, and asserts both `self.ui.ui_scale_var.get()`
  and `self.ui.s` reflect the second click's choice. This is the first and
  only test in the suite that reaches `ui_scale_var`'s write traces (both
  `Segmented`'s own internal repaint trace and `_apply_ui_scale`) through
  a real click rather than a direct `_apply_ui_scale()` call — every other
  `UIScale`/`OverlappingScaleAndAppearanceChanges` test still calls
  `_apply_ui_scale()` directly, per the spec's own acceptance-criteria
  wording, and is unchanged.
- **Does this test actually catch a reversal of the trace-registration
  order?** Checked empirically this session, not asserted: temporarily
  moved `self.ui_scale_var.trace_add(...)` (`afk_clicker.py:1925-1926`) to
  immediately after `self.ui_scale_var = tk.StringVar(...)` and before its
  `Segmented(...)` call (i.e., exactly the regression Finding 1 describes),
  ran the new test — **it still passed.** To rule out a mistake specific
  to this test, ran the same experiment against the pre-existing,
  already-proven Theme equivalent (`test_two_real_segmented_clicks_with_
  no_pump_between_them`) by reversing `appearance_var`'s own trace order
  the identical way — **it also still passed.** Root cause: both
  `_apply_appearance` and `_apply_ui_scale` only ever *defer* the rebuild
  via `_request_rebuild()`/`self.root.after_idle(...)` — neither ever
  calls `self._rebuild_ui()` synchronously from inside the trace callback.
  Reversing which trace fires first therefore has no observable effect
  under the current code: `Segmented._paint()` always finishes repainting
  the still-live widget before `_rebuild_ui()` runs (idle callbacks only
  run once the current event has fully unwound), regardless of which
  trace registration came first. The ordering discipline `docs/spec.md`
  §2 documents is a real, worthwhile invariant to keep — it is exactly
  what stops a *future* change from crashing if `_apply_ui_scale`/
  `_apply_appearance` ever stop deferring and rebuild inline instead — but
  neither this test nor its Theme precedent is actually sensitive to a
  bare reordering of the two `trace_add` calls as they exist today. Both
  temporary edits were reverted immediately after this experiment;
  `git diff afk_clicker.py` was re-checked line-by-line against the
  pre-experiment version to confirm an exact restore (no net change to
  `afk_clicker.py` in this fix pass).
  What the new test *does* genuinely add: it is the only test that ever
  calls `.set()` on `ui_scale_var` via a real click path at all (every
  other test bypasses the var and calls `_apply_ui_scale()` directly), so
  it would catch a real, different class of regression — e.g. the click
  hit-testing math (`Segmented._click`'s `seg_w` arithmetic) being wrong
  for a 4-option control, or a future change that *does* make the rebuild
  path synchronous, which is exactly the scenario the ordering discipline
  guards against.

### Finding 2 — corrected "Known limitations" claim
- `docs/implementation.md`'s "Known limitations" section (above) no longer
  claims `CapturesCallbackExceptions` gives "indirect" coverage of the
  trace-ordering hazard — that claim was inaccurate, as Finding 2 states:
  the relevant traces never ran in any test before this pass, so there was
  nothing for `CapturesCallbackExceptions` to catch. The section now
  points at the new real-click test and at this section's own honest
  account of what that test does and does not prove.

## How to verify locally
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-17
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/c3f4ab6d-63eb-4d27-b601-121c74c66331/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
Result observed this session (fix pass): **240 tests, OK (skipped=5)**,
52.457s — up from the pre-fix-pass baseline of 239 (the one new real-click
test), no regressions. `python -m py_compile afk_clicker.py tests/test_ui.py`
also re-run clean.

To see the control by hand: launch the app, open **Settings**, and the new
**UI scale** row appears directly below **Theme** in the Appearance card;
picking a different percentage resizes the whole window immediately, no
restart, and never shrinks a window the user has made bigger.

## Fix pass — cross-platform CI failure on PR #34 (test-only, no production change)

- **File:** `tests/test_ui.py:1663-1696`,
  `UIScale.test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change`.
- **Symptom:** red on the Windows and macOS CI legs, green on Linux. Windows
  failed the width assertion (`1028 != 1059`, identical across both
  subTests — a stable clamp, not a race); macOS failed the height assertion
  (`673 != 873` then `649 != 873`).
- **Root cause:** the test asked the window manager for a geometry
  (`big_w`/`big_h`, 130%'s minsize plus a 200px margin) and then asserted
  `winfo_width()`/`winfo_height()` equalled the *requested* size. Both CI
  runners' displays are smaller than that request, so the WM clamps it —
  Windows grants 1028 of 1059 requested width (still above 130%'s own
  minsize of 859, so the test's premise can still be satisfied there);
  macOS grants 649-673 of 873 requested height, at or below 130%'s own
  minsize (673), so the premise genuinely cannot hold on that runner's
  screen. Production code (`_apply_minsize`) only ever takes
  `max(cur, min)` and was confirmed correct; not touched.
- **Fix (test-only):** read the size the WM actually granted
  (`actual_w`/`actual_h` via `winfo_width()`/`winfo_height()` after
  `update()`) instead of assuming the request was honoured, and use that as
  the "manually enlarged" baseline for the loop's assertions. If the
  granted size is below 130%'s own minsize in either dimension, the
  premise cannot hold on that screen, so the test calls `self.skipTest(...)`
  with a reason rather than asserting a false thing — the same "honest
  runtime skip, comment explaining why" spirit as the file's existing
  `darwin_timing` class-level skip (`tests/test_ui.py:395-397`), but
  necessarily a runtime check here since whether the premise holds depends
  on the actual screen, not the platform name.
- **Verification (Linux, this session):**
  - Single test, verbose:
    `test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change ... ok` —
    confirmed it *ran* (not skipped) under Xvfb's 1280x1024, per the
    task's own requirement that the premise still holds there.
  - Full suite: `python -m unittest discover -s tests -t .` →
    **Ran 240 tests in 51.968s — OK (skipped=5)**, exit 0. Same test count
    and skip count as before this pass; no regressions. Did not hit the
    documented pre-existing `Tcl_AsyncDelete` shutdown flake this run.
  - Could not run the Windows/macOS legs directly (no such runner
    available here); the fix was verified against the exact numeric
    evidence given in the task (Windows granted-width 1028, macOS
    granted-height 649-673) rather than re-derived from a live failing
    run.
- **Left uncommitted** per instructions — the tree at
  `/home/dev/projects/.worktrees/afk-clicker/ac-17` has this one change to
  `tests/test_ui.py` plus the pre-existing untracked `docs/*.md`.
