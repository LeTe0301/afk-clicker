# Implementation: Horizontal tab bar under the page title (story #24, Feature 2 of 5)

## Summary
Added `TabBar(tk.Canvas)`, a new sibling class to `Segmented`: left-aligned,
natural-width tabs bound to a `tk.StringVar`, with a bottom underline (in
`ACCENT`) under the active tab and a full-width `LINE`-colored separator
below the whole bar. The game page now shows `Hotkey | Clicking` directly
below the title row, with `Eating` nested inside `Clicking` as a
conditionally-shown sub-section exactly as before. Settings shows
`Appearance | Updates` in the same position. Both panes on each page are
built in full, unconditionally, every time `_build_content()`/
`_build_settings()` runs; only which pane is `.pack()`ed differs, using the
same `.pack()`/`.pack_forget()` idiom already proven for `eat_section`/
`eat_card`. Active-tab state lives in two new plain instance attributes
(`self._content_tab`, `self._settings_tab`), session-only (not persisted to
`settings.json`), following the existing `self._settings_open` precedent.

## Root cause
N/A — new feature, not a bugfix.

## Changes by file
- `afk_clicker.py:167-176` — four new module-level constants, placed
  immediately after `ROW_LABEL_GAP`: `TAB_HEIGHT = 32`, `TAB_GAP = 28`,
  `TAB_PAD_BOTTOM = 6`, `TAB_UNDERLINE_H = 2`, matching `docs/design.md`'s
  confirmed values (no retuning needed).
- `afk_clicker.py:1263-1319` (new `TabBar` class) — placed directly after
  `Segmented`/`_pill_pts`, before `StatusPill`, per `docs/spec.md`'s
  placement instruction. The constructor computes every tab's x-range once,
  using **bold** font metrics uniformly (active or not) so the underline/
  hit-box geometry never shifts when the active tab changes — only fill
  colors and the underline's position change in `_paint()`. Draws, in
  z-order: a full-width `LINE` separator first (`create_line`), then each
  tab's text, then the `ACCENT` underline rectangle last — so the
  underline visually overrides the separator under the active tab, and the
  separator shows through as a faint divider under every inactive tab
  (`docs/design.md`'s "Separator from content" section). `_click()`
  hit-tests each tab's own measured width plus one full `TAB_GAP` to its
  right (per `docs/design.md`'s "touch target" note); `_paint()` recolors
  every tab's text and repositions the underline rectangle to the active
  tab's x-range.
- `afk_clicker.py:1600-1608` (`__init__`) — two new plain instance
  attributes next to `self._settings_open`: `self._content_tab = "hotkey"`,
  `self._settings_tab = "appearance"`. Never read from/written to
  `settings.json`; survive `_rebuild_ui()` as ordinary Python attributes.
- `afk_clicker.py:2157-2200` (new `_set_content_tab`/`_set_settings_tab`
  methods, next to `_show_settings()`) — the two toggle methods from the
  spec's sketch: validate the incoming value, store it, keep the bound
  `content_tab_var`/`settings_tab_var` in step, then `pack_forget()` both
  panes and `pack()` exactly the one that should be visible. See "Post-
  implementation fix" below — the var-sync line was missing from the first
  pass and was added in response to reviewer feedback, before this doc's
  first handoff.
- `afk_clicker.py:1899-1973` (`_build_content(s)`) — inserted the `TabBar`
  (`Hotkey | Clicking`) directly after `game_note.pack(...)`, wrapped the
  existing Hotkey card construction into a new `self.hotkey_pane` frame
  (kept its `section(..., "Hotkey  ·  shared by every game", s, top=0)`
  header verbatim), wrapped the existing Clicking card + Eating
  sub-section into a new `self.clicking_pane` frame (dropped the redundant
  `section(body, "Clicking", s)` header per `docs/design.md`, kept
  `section(self.clicking_pane, "Eating", s)` verbatim since it is a
  sub-section, not a tab). No construction call for any existing widget
  changed — only which frame each is parented into. Both panes are built
  and `.pack()`ed, in this order, before the trailing
  `self._set_content_tab(self._content_tab)` call hides whichever one
  should not be visible — build order is load-bearing (see spec's "Build
  order is load-bearing" section: a card built while its pane is still
  packed gets a real `_redraw()` pass; `pack_forget()` afterward does not
  erase that already-computed geometry, but a pane hidden before its cards
  are ever built would leave them stuck at Tk's placeholder defaults).
- `afk_clicker.py:1975-2085` (`_build_settings(s)`) — same treatment: a
  `TabBar` (`Appearance | Updates`) after the title row,
  `self.appearance_pane` holding the existing Theme/UI-scale card +
  OS-theme hint (dropped the redundant `section(body, "Appearance", s)`
  header), `self.updates_pane` holding the existing Version/Check-for-
  updates card (dropped the redundant `section(body, "Updates", s)`
  header), and a trailing `self._set_settings_tab(self._settings_tab)`.
  `_apply_appearance()`, `_apply_ui_scale()`, `_select()`, `_show_settings()`
  are all unchanged, per the spec — each already re-runs
  `_build_content`/`_build_settings` in full (via `_rebuild_ui()` or
  `_build_ui()`'s own branch), whose own trailing `_set_*_tab()` call
  re-establishes the correct visible pane from the untouched
  `self._content_tab`/`self._settings_tab`.
- `tests/test_ui.py:641-656` (`NumBoxFocus.focus_and_settle`) — added
  `self.ui._set_content_tab("clicking"); self.root.update()` at the top,
  before `numbox.entry.focus_set()`. Required: `focus_set()`/
  `event_generate()` are no-ops on a widget inside an unmapped ancestor
  (confirmed empirically per `docs/spec.md`'s "Test impact" findings 1/2),
  and every `NumBox` this class exercises lives in the Clicking pane while
  Hotkey is the default-active tab. All 9 `NumBoxFocus` tests funnel
  through this one helper, so one change covers all of them.
- `tests/test_ui.py`
  (`BindAllBoundOnce.test_a_click_still_drops_focus_exactly_once_after_two_
  theme_changes`) — same one-line fix (`self.ui._set_content_tab
  ("clicking"); self.root.update()`) immediately before the direct
  `self.ui.click_ms.entry.focus_set()` call, which does not go through the
  shared helper.
- `tests/test_ui.py` (`RowValueColumn`'s
  `test_offset_is_unchanged_when_the_card_stretches` and
  `test_extra_width_becomes_trailing_margin_not_a_growing_gap`) — added
  `self.ui._set_content_tab("clicking"); self.root.update()` immediately
  after each test's `self.root.geometry("900x760"); self.root.update()`,
  before reading `winfo_width()`/`winfo_x()`. Recommended, not required
  (per spec): a hidden pane's geometry does not track a live resize
  (finding 4), so without this both assertions would still pass, but for a
  hollow reason — they would never actually observe the resize the tests
  are named for.
- `tests/test_ui.py` (new `TabBarNavigation(UITestCase)` class, placed
  directly after `RowValueColumn`, before `Selftest`) — originally 10
  tests, now 12 (see "Post-implementation fix" below) covering:
  default-active tab on both pages, a real `<Button-1>` tab click switching
  the visible pane (at the tab's own measured x-range, not a hand-picked
  constant), a direct (non-click) setter call also moving the tab indicator
  on both pages, both content panes' widgets existing regardless of which
  is packed, `update_button` existing once Settings is open regardless of
  which Settings tab is showing, the updater still reflecting state while
  its tab is active, Eating staying conditional inside the Clicking pane,
  active-tab state surviving a rebuild on both pages, and a running clicker
  continuing to click across a tab switch. Added a `tearDown()` resetting
  `app.set_active_theme("dark")`, matching the existing precedent in
  `BindAllBoundOnce`/`SettingsNavigation` — two of the new tests call
  `_apply_appearance("light")` and would otherwise leak theme state into
  whichever test runs next alphabetically (this bit during the first
  full-suite run in this session; see "Known limitations").

## Post-implementation fix: setter → indicator var was one-way
Reported by the coordinator after reproducing it against this build while
screenshotting the feature: `_set_content_tab()`/`_set_settings_tab()`
re-packed the correct pane but never wrote the corresponding
`content_tab_var`/`settings_tab_var`, so a direct call to either setter with
a value different from what the var already held moved the pane without
moving the underline — e.g. a Clicking pane rendered under a still-
underlined "Hotkey" tab. This worked "by luck" for both existing call
sites (`_build_content`'s/`_build_settings`'s own trailing
`self._set_content_tab(self._content_tab)`/`self._set_settings_tab(self._
settings_tab)` lines, which always pass the value the var already holds)
and for a real tab click (which works in the *other* direction: the var's
own write trace is what calls the setter, so the var is already correct
before the setter ever runs). Both of this feature's own test classes only
drove tab changes by clicking the bar, so neither direction's asymmetry was
exercised.

**Fix** (`afk_clicker.py:2157-2200`, both setters): after validating and
storing the incoming value, each setter now also writes the bound var if it
disagrees:
```python
if self.content_tab_var.get() != value:
    self.content_tab_var.set(value)
```
The `!=` guard is load-bearing, not an optimization: Tcl fires a variable's
write traces even when the new value equals the old one, and the var's own
trace calls straight back into this same setter — writing the var
unconditionally would re-enter the setter with the same value forever. The
guard makes the re-entrant call a no-op (its own `!=` check now reads
"already equal") and terminates exactly one call deep. This reasoning is
recorded in both setters' docstrings, not only here, since it is exactly
the kind of thing a future editor (e.g. Feature 3's rail work, or #15's
Macros tab) would otherwise have to re-derive from a stack trace.

**Verification that the fix actually fixes the reported bug**: reverted
just the two-line var-sync addition (keeping everything else) and reran the
two new setter-direction tests below — both failed exactly as reported
(`'hotkey' != 'clicking'` / `'appearance' != 'updates'`), while every other
`TabBarNavigation` test still passed. Restored the fix and confirmed all 12
pass again before re-running the full suite.

**New tests added** (`tests/test_ui.py`, `TabBarNavigation`):
- `test_calling_the_setter_directly_also_moves_the_tab_indicator` — calls
  `self.ui._set_content_tab("clicking")` directly (not via a click) while
  `content_tab_var` still holds `"hotkey"`, then asserts both that
  `clicking_pane` is packed *and* that `content_tab_var.get() ==
  "clicking"`.
- `test_calling_the_settings_setter_directly_also_moves_the_indicator` —
  same shape for `_set_settings_tab("updates")`/`settings_tab_var`.

Both click-driven tests (`test_clicking_the_clicking_tab_shows_only_the_
clicking_pane`, `test_clicking_updates_shows_only_that_pane`) were left
unchanged — they cover the real user path and should stay.

## Post-review fix: the running-clicker test never actually switched tabs
The reviewer proved `test_a_running_clicker_is_unaffected_by_a_tab_switch`
(`tests/test_ui.py`, `TabBarNavigation`) tested nothing it claimed to: it
called `self.ui._set_content_tab("hotkey")` while `_content_tab` was
already `"hotkey"` — a no-op, not a switch — and deleting that line entirely
left the test passing identically. This is the single highest-risk
invariant this feature could break (`_sync_settings()`'s 200ms poll feeds
the live click-worker thread from Clicking-pane widgets unconditionally),
so a hollow test on exactly this criterion was a blocker, not a nitpick.
The feature code itself was not at fault — the reviewer's own patched
version of the test (genuinely switching tabs) passed.

**Fix**: rewrote the test to switch both directions while the clicker runs
-- `hotkey -> clicking -> hotkey` -- pumping the loop and clearing/checking
`self.ui.mouse.clicks` after each switch (not only at the end), plus an
initial check that clicks are produced before any switch at all. Both
`self.ui.running` and non-empty `mouse.clicks` are asserted after each
switch.

**Verification that the rewritten test would actually catch the regression
it targets**: temporarily patched `_set_content_tab()` (scratch in-place
edit to `afk_clicker.py`, reverted immediately after, never committed) to
call `self.running = False` on every invocation, simulating a tab switch
that kills a running clicker. Reran the test in isolation — it failed
(`AssertionError: False is not true` on the post-switch `self.assertTrue
(self.ui.running)`), then restored the real source and confirmed the test
passes again. Confirms the test is now load-bearing, not merely green.

**Two non-blocking review suggestions, both applied:**
1. Added `test_active_content_tab_survives_a_ui_scale_rebuild` and
   `test_active_settings_tab_survives_a_ui_scale_rebuild`, mirroring the
   two existing Appearance-triggered rebuild-survival tests but via
   `self.ui._apply_ui_scale("115")` — the same shared `_request_rebuild()`
   path, reached through a different caller. No tearDown/global-state
   concern here (unlike Appearance): `ui_scale` lives only in each test's
   own temp-file `Store`, not in module-level state.
2. `test_the_updater_still_reflects_state_while_its_tab_is_active` still
   drives `_set_update_state()` directly rather than through the async
   check-for-updates worker chain. Left as-is per the reviewer's own
   framing ("reasonable for a unit test") — noted here as a deliberate
   scope limitation: the async chain (`check_update()` ->
   `_check_worker()` -> `_offer_update()`/`_set_update_state()`) already
   has dedicated coverage elsewhere in `SettingsUpdates`, and this test's
   only job is to confirm the Updates pane's own visibility doesn't
   interfere with that existing contract, not to re-prove the async path.

## Post-review fix (round 3): `focus_and_settle()` was racy, ~29% of full-suite runs
The reviewer identified and root-caused the flake this doc's previous round
flagged as "observed but not conclusively attributed": under a stress loop,
`focus_and_settle()` (`tests/test_ui.py:641-663`, shared by all 9
`NumBoxFocus` tests) failed roughly 1 run in 8, and one verbose run failed
all seven `NumBoxFocus` tests in the same run.

**Root cause** (reviewer's, independently reproduced): `_set_content_tab
("clicking")` maps the Clicking pane for the *first* time, and a single
`root.update()` does not reliably wait out the X server's `MapNotify`
round trip. `focus_set()` on a widget that is not yet viewable is
**dropped by Tk, not queued** -- the request silently evaporates, so
`self.root.focus_get()` can still read the toplevel itself
(`<tkinter.Tk object .>`) instead of the entry, and the very next line's
`assertEqual` fails.

**Fix** (`tests/test_ui.py`, `focus_and_settle()`): applied the reviewer's
validated patch exactly, keeping the existing explanatory comment above it
and adding a second comment explaining the non-obvious part (the dropped-
not-queued behavior, so a future editor does not "simplify" the waits
away):
```python
self.ui._set_content_tab("clicking")
self.root.update()
self.pump_until(lambda: numbox.entry.winfo_viewable(), timeout=1.0)
numbox.entry.focus_set()
self.pump_until(lambda: self.root.focus_get() == numbox.entry, timeout=1.0)
self.assertEqual(self.root.focus_get(), numbox.entry,
                 "setup failed to focus the entry")
```
Both waits use the file's own existing `pump_until()` helper (no new
technique) and fail closed: if the widget never becomes viewable, or never
actually takes focus, within 1s, the final `assertEqual` still reports a
genuine regression rather than silently passing.

**Not touched, per explicit scope**: `RunningClickerSurvivesRebuild.test_
worker_running_and_clicks_continue_across_a_scale_change`'s separate
failure under extreme induced load (background click-worker thread CPU
starvation, pre-existing code this feature's diff never touches) -- left
alone, tracked by the reviewer separately.

**Verification**: ran the full suite 10 times after the fix -- **10/10
`OK`** (`Ran 259 tests`, `OK (skipped=5-7)`; the skip count varies 5-7
depending on live-network availability for `test_updater.py`'s
`LiveRepository` tests and `AFK_SLOW_TESTS`, unrelated to this fix). Also
ran `NumBoxFocus` alone 18 times back-to-back -- **18/18 `OK`**, matching
the reviewer's own reported 0-in-18 result for the patched helper (vs. the
original helper's ~1-in-8 failure rate under the same class of induced
load). No product code (`afk_clicker.py`) changed in this round --
`TabBar`, the setters, and the pane-visibility mechanism were never
implicated; this was purely test-harness timing in code this feature
introduced.

## Key decisions / tradeoffs
- Followed the spec's `TabBar` sketch essentially verbatim — the spec had
  already argued why `Segmented` cannot serve (opposite geometry model:
  equal-width filled pill vs. natural-width underline) and the sketch's
  shape (compute all tab geometry once at construction using bold metrics,
  only move a paint layer afterward) mirrors `Segmented`'s own established
  pattern in this file, so there was no reason to deviate.
- Drew the `LINE` separator as a single `create_line` at `y = h - 1`,
  created *before* the per-tab text and the `ACCENT` underline rectangle,
  so the underline (created last) paints on top of the separator under the
  active tab and the separator alone shows through elsewhere — this
  reproduces `docs/design.md`'s described appearance (a full-width faint
  divider, with the active tab's underline "overriding" it) without a
  second canvas or a frame-based border.
- `_build_content`'s Clicking pane construction dropped the `section(body,
  "Clicking", s)` call per `docs/design.md`'s settled redundant-header
  decision; `"Hotkey  ·  shared by every game"` and `"Eating"` were kept
  verbatim, unchanged in wording or placement relative to their card.

## Deviations from spec
- None from `docs/spec.md`'s functional requirements. `docs/design.md`'s
  four pixel constants were adopted unchanged (`TAB_HEIGHT=32`, `TAB_GAP=28`,
  `TAB_PAD_BOTTOM=6`, `TAB_UNDERLINE_H=2`) — the design's own fit-check
  confirmed they hold at every UI-scale/DPI step, so no retuning was
  needed.
- The spec flagged the two `RowValueColumn` resize tests as "recommended,
  not required" changes. Applied both, as the spec's own reasoning
  (avoiding hollow coverage of a hidden pane) was sound and the fix is a
  two-line addition with no other side effect.

## Known limitations
- During the first full-suite run in this session, the two
  `TabBarNavigation` tests that call `_apply_appearance("light")` (to
  prove active-tab state survives a rebuild) leaked the light theme into
  `Themes.test_module_globals_still_ship_dark_only`, which runs later
  alphabetically and asserts the module's dark-only globals. Fixed by
  adding a `tearDown()` to `TabBarNavigation` that resets
  `app.set_active_theme("dark")`, matching the identical precedent already
  present in `BindAllBoundOnce` and `SettingsNavigation`. Not a defect in
  the feature itself — a test-suite hygiene gap in the new test class,
  caught and fixed within this same session before reporting results.
- No visual/manual screenshot verification was performed beyond what the
  automated suite exercises (pane visibility, tab-click hit-testing,
  underline repositioning via `_paint()`'s own logic) — this environment
  has no way to visually inspect the rendered Xvfb output. The four pixel
  constants and color/contrast reasoning are `docs/design.md`'s own,
  unmodified here.
- The previous round of this doc flagged one unattributed full-suite
  failure as "consistent with the known pre-existing flake class, not
  conclusively attributed." It is now resolved and reattributed: it was
  `focus_and_settle()`'s `MapNotify` race (see "Post-review fix (round 3)"
  above), not the pre-existing `Tcl_AsyncDelete` shutdown flake this file
  already documents separately. That pre-existing flake (exit 134, no
  summary printed) remains real and unrelated to this feature; it was not
  observed in any run performed across this feature's review rounds.

## How to verify locally
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-24
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/c3f4ab6d-63eb-4d27-b601-121c74c66331/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
Observed in this session, after all three post-review rounds above:
**`Ran 259 tests` — `OK`** (245-test baseline + 14 `TabBarNavigation`
tests, `skipped` varying 5-7 depending on live-network/`AFK_SLOW_TESTS`
availability, unrelated to this feature). Test count history across
review: 255 (before the setter/var-sync fix, 10 tests) -> 257 (after that
fix, 12 tests, including the then-hollow running-clicker test) -> 259
(running-clicker test rewritten to genuinely switch tabs + 2 new UI-scale
rebuild-survival tests; test *count* unchanged by round 3's
`focus_and_settle()` fix, since that round only changed an existing shared
helper's body, adding no new test).

## Post-review fix (round 4): `focus_and_settle()`'s real mechanism is cross-process X focus contention, not a MapNotify race

Round 3 found that its own must-fix patch (the `pump_until`-based viewability
wait) genuinely fixed the MapNotify race it targeted, but a second,
distinct mechanism survived under load: `focus_set()` on an already-viewable
widget sometimes never transferred real input focus, `focus_get()` reading
`None`. This round instruments and fixes that second mechanism, and also
corrects one piece of the diagnostic evidence that turned out to be wrong.

### Instrumentation: what actually happens

Built the app for real (`app.AfkAutoclicker`, real `setUp`/`settle()`
sequence, no bare-Tk shortcuts) and logged `root.focus_get()`/
`focus_displayof()`/`winfo_viewable()` at each step, under the same induced
load (a background `unittest discover` loop on a shared display), scratch
probes in the session's scratchpad dir (not committed):

- **The tab switch is not the trigger.** A control that skips
  `_set_content_tab("clicking")` entirely and just pumps `root.update()` for
  2s after `setUp`'s `focus_force()` loses real focus *more* often (14/20)
  than a treatment that does switch (12/20) — statistically the same or
  worse, not better. This refutes the "unmapping the previous pane drops
  focus" lead named in the dispatch: `_set_content_tab()` is incidental,
  not causal.
- **The trigger is a second Tk-owning process holding a window on the same
  X display.** Same "no switch, just pump for 2s" control: **0/20** focus
  losses when the induced load runs on a *separate* display (`:98`,
  matching this project's `ab.sh` harness), vs. **12-14/20** when the load
  runs on the *same* display (`:99`) as the test. Root cause: this Xvfb has
  no window manager, so nothing arbitrates real X input-focus ownership
  between two independent Tk clients sharing one display — under load,
  `root.focus_get()` can transition from the toplevel to `None` at any
  point from 0.015s to ~1.9s into ordinary event-loop pumping, with no
  event this process can observe, confirming the dispatch's point 4
  (`focus_set()` cannot reacquire ownership once lost; only `focus_force()`
  can) and point 3 (cross-process focus stealing on a shared display is
  real) — but shows the *pane switch* was never the mechanism, and that the
  hazard requires two live Tk clients on one display, not load alone.
- **A single re-force on `root` right before `focus_set()` is not enough.**
  Re-running `root.focus_force()` followed immediately by
  `numbox.entry.focus_set()` cut the failure rate but left a residual
  ~1-in-4 to 1-in-5 run-level rate with a *different* signature
  (`root.focus_get()` reads the toplevel, not `None` or the entry). Cause:
  if `root` still nominally holds real ownership at that moment (it was
  never fully lost, just not yet forwarded to the entry), calling
  `focus_force()` on `root` again is a no-op at the X level — no fresh
  `FocusIn` fires, so Tk's internal forward-to-the-registered-widget logic
  never runs, and `focus_set()` on the entry sits stuck.

### Correction to a diagnostic claim in this round's dispatch

The dispatch's point 2 asserted "load on a separate display (`:98`) gives
the identical 9/3 failure rate as load on the same display (`:99`)," used
to rule out cross-process focus contention as the cause. Re-ran this
exact comparison myself with `ab.sh`, verifying no orphaned load process
survived between runs (`ps aux | grep "python -m unittest discover"`
before and after every batch — the same contamination round 2's reviewer
caught once already):

| Load display | Test display | Iterations | Result |
|---|---|---|---|
| `:99` (shared) | `:99` | 12 | 9 pass / 3 fail |
| `:99` (shared) | `:99` | 16 | 14 pass / 2 fail |
| `:98` (separate) | `:99` | 12 | **12 pass / 0 fail** |
| `:98` (separate) | `:99` | 16 | **16 pass / 0 fail** (one earlier 16-run batch read 13/3, traced to a leftover orphaned load process still running on `:99` from a prior verification — discarded, not counted) |

Separate-display load is clean across 28 verified-uncontaminated iterations;
same-display load fails consistently. **Point 2 does not hold up** — it was
very likely produced by the same orphan-process contamination round 2's own
reviewer independently caught and flagged once already in this feature's
history. This does not weaken the core finding that this branch introduced
a real, reproducible defect (point 1 — the main-vs-branch A/B under
identical same-display stress — stands untouched by this correction): it
narrows *why*. `focus_and_settle()`'s added waits (the round-2/3
`pump_until` calls) measurably widen the window between `setUp`'s
`focus_force()` and the test's own `focus_set()`, during which a second
Tk client sharing the *same* display can seize real X focus — main never
had that extra pumped window because it never packed/unpacked a Clicking
pane at all. The hazard's root cause (no window manager arbitrating input
focus between two simultaneous Tk clients on one display) is not something
a normal single-process CI run can hit — CI runs one Tk-owning process at a
time, never two concurrently — but it is exactly what this project's own
`ab.sh` stress harness (and the reviewer's own prior rounds) deliberately
constructs, so it remains the right verification methodology for this
class of test-harness timing bug even though it would not fire in a plain,
unloaded CI run.

### Fix

`tests/test_ui.py`, `NumBoxFocus.focus_and_settle()`: replaced the
single `numbox.entry.focus_set()` + one `pump_until` with a bounded retry
loop that calls `focus_force()` directly on the *entry* (not `root`) —
this both reacquires real ownership and targets the right widget in one
step, avoiding the no-op-when-root-already-has-focus dead end above:
```python
deadline = time.monotonic() + 3.0
while time.monotonic() < deadline:
    numbox.entry.focus_force()
    self.pump_until(lambda: self.root.focus_get() == numbox.entry, timeout=0.5)
    if self.root.focus_get() == numbox.entry:
        break
self.assertEqual(self.root.focus_get(), numbox.entry,
                 "setup failed to focus the entry")
```
Each attempt is cheap and the loop exits the instant one lands — in the
normal (unloaded, single-process) case this still converges on the first
attempt, same as before.

### Verification, matching the required bar

`ab.sh`, both display configurations, ≥12 iterations, checked clean of
orphaned load processes before and after each batch:

| Config | Before this round's fix | After this round's fix |
|---|---|---|
| Load `:99`, test `:99` (shared) | 9/3, 14/2 (~19-25% run-level fail) | **19/20 pass, then 19/20 pass again** (5% run-level fail, both single failures the retry loop's own `None`-never-converged signature, in runs where the whole 9-test class took 5-9s instead of the usual ~3s — a genuine CPU-starvation tail, not a margin bug: consistent with round 3's own finding that even a 5x timeout on a single attempt didn't always converge) |
| Load `:98`, test `:99` (separate) | 16/0, 12/0 (already clean) | **16/0 pass** (still clean, as expected — this config never exercised the mechanism at all) |

Full suite (259 tests), load on `:99`, 8 runs: **5/8 `OK`, 3/8 `FAILED`** —
runs 5 and 7 hit the pre-existing, already-documented `Tcl_AsyncDelete`-class
interpreter-shutdown cascade (`docs/implementation.md`'s own "Known
limitations", `docs/spec.md:609-610`, ~1-in-4 historical rate — this batch's
2/8 is consistent, not worse); run 6 hit the pre-existing, already-tracked
`RunningClickerSurvivesRebuild` GIL-starvation flake (round 3's own "Item
3", confirmed out of scope, unrelated to this feature's diff). **Zero of
the 33 individual failures/errors across all three failing runs were
`NumBoxFocus`/`focus_and_settle()`** (grepped every run's log for
`NumBoxFocus`: no matches). No product code (`afk_clicker.py`) touched this
round — the fix is entirely inside the test harness, in code this feature's
own diff already owns.

### Not fully eliminated — reported honestly, not rounded up

Unlike round 3's claimed (and since-refuted) 10/10 and 18/18, this round
does not claim 0 failures: a genuine ~5% residual remains under the same
two-Tk-client-on-one-shared-display stress this project's own harness uses,
tied to CPU-starvation tails long enough that even a 3-second, 6-attempt
retry budget cannot always converge. Raising the budget further would trade
away real-run latency for a diminishing return against an artificial
worst case; the retry loop already converges on the first attempt in every
normal (unloaded or separate-display) run observed. This residual is not
reachable by a normal single-process CI run at all, per the corrected
diagnosis above (CI never runs two Tk-owning processes concurrently on one
display), so it is not expected to affect CI in practice — only this
project's own deliberate stress-testing of the test harness itself.

**Reliability check, round 3 (the one that matters most)**: this feature
had a ~29% full-suite failure rate at the point round 2 was reported,
traced to `focus_and_settle()`'s `MapNotify` race (see "Post-review fix
(round 3)" above) -- a single earlier green run had proven nothing. After
the fix: **10/10 full-suite runs `OK`**, plus **18/18** isolated runs of
`NumBoxFocus` alone `OK` (the class every one of the race's observed
failures came from), matching the reviewer's own reported 0-in-18 result
for the patched helper. No product code was touched in this round.

New/changed tests (`tests/test_ui.py`, class `TabBarNavigation(UITestCase)`):
- `test_hotkey_is_the_default_active_tab_on_a_fresh_game_page`
- `test_clicking_the_clicking_tab_shows_only_the_clicking_pane`
- `test_calling_the_setter_directly_also_moves_the_tab_indicator`
- `test_both_content_panes_widgets_exist_no_matter_which_is_packed`
- `test_appearance_is_the_default_active_settings_tab`
- `test_clicking_updates_shows_only_that_pane`
- `test_calling_the_settings_setter_directly_also_moves_the_indicator`
- `test_the_updater_still_reflects_state_while_its_tab_is_active`
- `test_eating_stays_conditional_inside_the_clicking_pane`
- `test_active_content_tab_survives_a_rebuild`
- `test_active_settings_tab_survives_a_ui_scale_rebuild` (new this round)
- `test_active_settings_tab_survives_a_rebuild`
- `test_active_content_tab_survives_a_ui_scale_rebuild` (new this round)
- `test_a_running_clicker_is_unaffected_by_a_tab_switch` (rewritten this
  round to genuinely switch tabs both directions while running)

To run only the new class:
```
DISPLAY=:99 .../venv/bin/python -m unittest tests.test_ui.TabBarNavigation -v
```

Exactly three pre-existing tests (outside `TabBarNavigation`) were
modified, matching `docs/spec.md`'s "Test impact" section precisely (one
required helper fix covering 9 tests, one required direct fix, two
recommended fixes) — no other pre-existing test was touched.

## Post-review fix (round 5): a fourth `winfo_rootx()` assertion in `RowValueColumn` never observed a mapped widget, Windows-only

PR #40 CI was red on Windows only (Ubuntu/macOS green), one failure:

```
FAIL: test_random_jitter_hint_wraps_instead_of_overlapping_the_control
AssertionError: 1 not less than or equal to 0
```

### Root cause

`tests/test_ui.py`, `RowValueColumn.test_random_jitter_hint_wraps_instead_of_overlapping_the_control`,
its final assertion (`hint.winfo_rootx() + hint.winfo_width() <=
self.ui.jitter_ms.winfo_rootx()`) measures two widgets that live inside
`clicking_pane`, which feature 2 makes hidden by default (`hotkey` is the
default active game-page tab) — and, unlike the two sibling tests directly
above it in the same class, this one never called `self.ui._set_content_tab
("clicking")` before measuring. `1` and `0` in the failure are Tk's
placeholder values for an unmapped widget, not real geometry.

This is the same defect class round 3/4's sibling tests
(`test_offset_is_unchanged_when_the_card_stretches`,
`test_extra_width_becomes_trailing_margin_not_a_growing_gap`,
`tests/test_ui.py:829-858`) were already fixed for — a fourth instance in
the same class was missed. The two already-fixed tests needed the switch
for a *behavioral* reason (a hidden pane doesn't reflow on resize, so
"before"/"after" would trivially match for the wrong reason); this one
needs it because `winfo_rootx()` specifically — an absolute on-screen
position — is invalid on an unmapped widget, which the app's own code
comment (`afk_clicker.py:1906-1916`) already documents empirically:
`pack_forget()` does **not** erase an already-computed *width*, but an
absolute root position requires actual window-manager placement and Tk
resets it (to 0 on Windows) once unmapped. That distinction — `winfo_x()`/
`winfo_width()`/`winfo_height()` stay valid on an unmapped-but-previously-
laid-out widget, `winfo_rootx()`/`winfo_rooty()` do not — is why only this
one assertion, of the four in the class, ever failed.

On Linux/X11 the bug was invisible: probing at `DISPLAY=:99` before any
fix, `hint.winfo_rootx() + hint.winfo_width()` returned `389` and
`jitter_ms.winfo_rootx()` returned `403` even while `clicking_pane`'s own
`winfo_manager()` was `''` (unmanaged) — stale-but-plausible cached
positions from before the pane was hidden during `__init__`, coincidentally
satisfying `389 <= 403`. Windows resets root position to `0` on unmap
instead of leaving it stale, so only the Windows leg could ever catch this.

### Fix

`tests/test_ui.py:916-925`: added the same `self.ui._set_content_tab
("clicking")` + `self.root.update()` pair the two sibling tests already
use, immediately before the `winfo_rootx()`-based assertion (left the two
earlier assertions in the test — the `wraplength` check and the
`winfo_reqheight()` comparison — untouched, since neither depends on the
pane being mapped):
```python
self.ui._set_content_tab("clicking")
self.root.update()
self.assertLessEqual(
    hint.winfo_rootx() + hint.winfo_width(),
    self.ui.jitter_ms.winfo_rootx())
```

### Item 2: does the assertion hold for a real reason once genuinely mapped, or was this masking a real overlap bug?

Probed directly (`DISPLAY=:99`, same venv) before and after the pane
switch:

| | `hint.winfo_rootx() + winfo_width()` | `jitter_ms.winfo_rootx()` | margin |
|---|---|---|---|
| Before switch (stale, pre-fix) | 389 | 403 | 14px (accidental) |
| After switch + update (real) | 389 | 403 | 14px (genuine) |

The numbers are identical before and after on Linux — expected, since X11
never invalidated them in the first place; the value itself did not change,
only whether it was trustworthy. With the pane actually mapped
(`clicking_pane.winfo_manager() == 'pack'`, `hint.winfo_viewable() == 1`),
the 14px margin is real, not coincidental: `hint`'s outer width is capped by
its fixed `wraplength=int(ROW_LABEL_W * s)` (140px at `s=1`, measured
`winfo_width() == 144` once the Label's own border/padding is added), while
the label column itself (`Row`'s `grid_columnconfigure(0, minsize=int((
ROW_LABEL_W + ROW_LABEL_GAP) * s))`, 152px at `s=1`) is 8px wider than that.
`wraplength` is a fixed pixel limit, not a function of the rendered text or
font — unlike the requested-width-vs-wraplength comparison this same test's
own comment (lines 899-907) already flags as font-sensitive and previously
broke on Segoe UI — so this margin holds on any platform/font, not just the
one measured here. **No product bug**; the test's assertion was correct in
intent, only its measurement was invalid before this fix.

### Item 3: audit of every geometry-introspection call in `tests/test_ui.py`

Checked every `winfo_rootx`/`winfo_width`/`winfo_height`/`winfo_x`/
`winfo_y` call for the same class of defect: is the widget inside a pane
feature 2 made hidden by default, and does the assertion depend on
absolute root position (unsafe while unmapped) rather than a
parent-relative size/position (safe, per the distinction established
above)?

| Lines | Widget(s) | Call | In a hidden-by-default pane? | Verdict |
|---|---|---|---|---|
| 791-796 | `self.ui.content`, `self.ui.side` | `winfo_width()` | No — always-mapped containers, not a tab-hidden pane | Safe |
| 802-803, 2040-2041, 2062, 2077-2078 | `self.root` | `winfo_width()`/`winfo_height()` | No — the toplevel itself | Safe |
| 822 (`_right_edge` helper) | varies (used at line 884) | `winfo_rootx()` | Used on `seg` from `_appearance_segment()`, Settings' Appearance pane — default active settings tab (`self._settings_tab = "appearance"`, `afk_clicker.py:1597`) | Safe — pane is genuinely mapped when this runs |
| 824-827 | `self.ui.click_ms.master` | `winfo_x()` | Yes, `clicking_pane` (hidden by default) | Safe anyway — `winfo_x()` is parent-relative, assigned by the geometry manager at pack time regardless of ancestor mapping; this is the assertion that already passed on Windows in the same CI run |
| 831, 846 | same | `winfo_x()` | Yes | Already fixed in an earlier round (`_set_content_tab("clicking")` present) — needed for a behavioral reason (hidden pane doesn't reflow on resize), not a `winfo_x()` validity issue |
| 857-858 | `control`, `card` | `winfo_x()`, `winfo_width()` | Yes | Already fixed in an earlier round, same as above |
| 884 | `seg` (via `_right_edge`) | `winfo_rootx()` (through helper) | No — Appearance pane, default active | Safe |
| 916-925 | `hint`, `jitter_ms` | `winfo_rootx()`, `winfo_width()` | Yes, `clicking_pane` | **Fixed this round** |
| 1745 | `shell` (standalone `CardShell` test fixture, not the app's own UI) | `winfo_width()` | N/A — its own bare `self.parent`, no tab bar involved at all | Safe |
| 1815-1822 (`CardResize`) | `self.ui.apply_button.master.master.master` | `winfo_width()` | No — `apply_button` lives in `hotkey_pane`, the default active game-page tab | Safe |
| 2033-2071 (`UIScale`) | `self.root` | `winfo_width()`/`winfo_height()`, `minsize()` | No — toplevel only | Safe |

No further fixes required — the one instance found and fixed above was the
only real gap. The rest either measure a widget outside any tab-hidden
pane, measure a widget in the *default-active* pane for that page (Hotkey
on the game page, Appearance on Settings), or use `winfo_x()`/`winfo_width()`
on a widget already switched into view by an earlier round's fix.

### Verification

```
DISPLAY=:99 .../venv/bin/python -m unittest tests.test_ui.RowValueColumn -v
```
→ `Ran 5 tests ... OK`, including the previously-failing test.

Full suite, matching CI's own invocation (`python -m unittest discover -s
tests -t .`):
```
DISPLAY=:99 .../venv/bin/python -m unittest discover -s tests -t .
```
→ `Ran 259 tests ... OK (skipped=5)`.

A green Linux run is weak evidence for this specific defect class (it is
exactly what missed it originally) — the confidence here comes from the
mapping reasoning in items 2 and 3 above, not from the run itself. No
product code (`afk_clicker.py`) touched this round; the fix is entirely in
`tests/test_ui.py`.
