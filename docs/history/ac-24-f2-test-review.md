# Test & Review: Horizontal tab bar under the page title (story #24, Feature 2 of 5)

**Verdict history: changes requested (first pass, below) → changes requested,
different defect (round 2, `focus_and_settle()`'s MapNotify race) →
changes requested, a second, distinct mechanism in the same helper survives
the round-2 fix under load (round 3, appended at the end).**

## Scope
Every acceptance criterion in `docs/spec.md` for Feature 2: `TabBar` itself
(construction, real-click hit-testing, underline repaint), the pane-
visibility contract on both the game page (`Hotkey | Clicking`) and Settings
(`Appearance | Updates`), the "both panes always built, only pack toggles"
invariant, build order / hidden-pane geometry, rebuild survival, the
Eating-conditional-inside-Clicking nesting, the post-implementation
setter→var re-entrancy fix, and the full regression suite. Plus the specific
items named in the dispatch: the re-entrancy guard's sufficiency, a
per-assertion fragility audit of the 12 new tests, and confirmation nothing
else referenced the dropped section headers.

## Environment
`DISPLAY=:99` Xvfb, `/tmp/claude-1000/.../scratchpad/venv/bin/python`, run
against the uncommitted worktree at
`/home/dev/projects/.worktrees/afk-clicker/ac-24`
(`feature/ac-24/responsive-layout-icon-restyle`, based on merged `main`
`db20af2`). No changes were committed; every temporary edit made during
verification below was reverted immediately after (confirmed via
`git diff --stat` matching the original diff after each revert).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Fresh game page: `Hotkey` active, `hotkey_pane` packed, `clicking_pane` unpacked | Automated: `TabBarNavigation.test_hotkey_is_the_default_active_tab_on_a_fresh_game_page` | pass | `python -m unittest tests.test_ui.TabBarNavigation -v` → ok |
| 2 | Real `<Button-1>` at `Clicking`'s own measured x-range switches panes, moves `content_tab_var` | Automated: `test_clicking_the_clicking_tab_shows_only_the_clicking_pane` | pass | Same run; `_click_tab` helper reads `bar._tabs`' own computed bounds, not a hard-coded pixel |
| 3 | Either tab active: Clicking/Hotkey widgets exist and hold values regardless of packed state | Automated: `test_both_content_panes_widgets_exist_no_matter_which_is_packed` | pass | Same run. Independently re-verified: `probe_geometry.py` (scratchpad) — `click_ms.var.get()` readable (`250`) while `clicking_pane` is hidden, and `clicking_pane.winfo_width()==439` (not a 1×1 Tk placeholder) |
| 4 | Settings default: `Appearance` active, `update_button` exists (`hasattr` True) while hidden | Automated: `test_appearance_is_the_default_active_settings_tab` | pass | Same run |
| 5 | `Updates` clicked, update-state change reflects on `update_button`/`version_label` | Automated: `test_clicking_updates_shows_only_that_pane` + `test_the_updater_still_reflects_state_while_its_tab_is_active` + pre-existing `SettingsUpdates` (unmodified, still green) | pass | Same run. Note: the new test drives `_set_update_state` directly rather than the full `check_update()`→`_check_worker` async chain — reasonable, since that chain is untouched and already covered end-to-end by `SettingsUpdates`; this test's actual job (proving pane visibility doesn't gate it) is satisfied. Non-blocking observation, not a gap. |
| 6 | Eating packed for Minecraft, `pack_forget()`'d for non-Minecraft, both while `Clicking` active | Automated: `test_eating_stays_conditional_inside_the_clicking_pane` (uses `minecraft`/`global` profiles) | pass | Same run |
| 7 | Active tab survives `_rebuild_ui()` on both pages | Automated: `test_active_content_tab_survives_a_rebuild`, `test_active_settings_tab_survives_a_rebuild` | pass | Same run. Both trigger the rebuild via `_apply_appearance("light")` only, not also via UI-scale — acceptable, since both paths funnel through the identical `_rebuild_ui()`/`_build_ui()` code, so there is no plausible bug a UI-scale trigger would expose that an Appearance trigger wouldn't. Non-blocking. |
| 8 | **A running clicker survives a tab switch, both directions (top named risk)** | Automated: `test_a_running_clicker_is_unaffected_by_a_tab_switch` | **fails to test the claim — see Defect 1** | See below |
| 9 | Full suite passes at 245-baseline + this feature's tests, with exactly the required/recommended existing-test changes applied | Automated: full discovery run, twice | pass | `Ran 257 tests ... OK (skipped=5)`, both runs, exit 0. `git diff --stat -- tests/test_ui.py` confirms exactly the 3 existing tests documented as modified (`NumBoxFocus.focus_and_settle`, `BindAllBoundOnce`'s one test, `RowValueColumn`'s two resize tests) plus the new `TabBarNavigation` class — no other existing test touched. |
| 10 | Setter→var re-entrancy guard actually terminates, in every reachable path | Manual probe | pass | See "Re-entrancy guard" section below |

## Regression check
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-24
DISPLAY=:99 .../venv/bin/python -m unittest discover -s tests -t .
```
Run 1: `Ran 257 tests in 56.389s` → `OK (skipped=5)`, exit 0.
Run 2: `Ran 257 tests in 56.906s` → `OK (skipped=5)`, exit 0.

Matches developer's reported 245 baseline + 12 new `TabBarNavigation` tests.
The known pre-existing `Tcl_AsyncDelete`/exit-134 shutdown flake did not
appear in either run — not chased, per instructions. Also ran the isolated
`TabBarNavigation` class alone (`-v`): all 12 pass individually.

**Post-implementation-fix verification (own hands, not trusting the doc's
claim):** reverted just the two `if var.get() != value: var.set(value)`
guard lines in both setters (`afk_clicker.py:2157-2200`) and reran
`TabBarNavigation` — exactly the two setter-direction tests
(`test_calling_the_setter_directly_also_moves_the_tab_indicator`,
`test_calling_the_settings_setter_directly_also_moves_the_indicator`) failed
(`AssertionError: 'hotkey' != 'clicking'` / `'appearance' != 'updates'`),
all 10 others still passed. Restored the fix; all 12 pass again. Confirms
the fix is real and these two tests genuinely exercise it, not merely green
by coincidence.

## Re-entrancy guard: is it sufficient everywhere?

Traced the reachable call graph and probed it directly (scratchpad
`probe_reentrancy.py`, not committed):

- **Click path** (`_click()` → `var.set(value)` → both write traces fire):
  `_set_content_tab` runs once, sees the var already holds `value` (Tcl
  updates the variable before firing traces), guard is false, no re-entry.
  Measured max call depth = 1.
- **Direct-call path with a differing value** (e.g. `_build_content`'s own
  trailing `self._set_content_tab(self._content_tab)`, or a test calling
  the setter directly): the outer call sets the var, which re-enters the
  setter once via the var's own trace; that inner call finds the var
  already correct and returns immediately. Measured max call depth = 2 (one
  level of re-entry, terminating exactly as the implementation doc claims).
- **Trace registration order** (`TabBar.__init__`'s `_paint` trace is
  registered before `_build_content`'s `_set_content_tab` trace): both
  handlers re-read `var.get()` fresh rather than using a stashed value, so
  whichever fires first, the outcome is identical — order-independent by
  construction, unlike the pre-existing Appearance/UI-scale ordering
  concern this file documents elsewhere (`afk_clicker.py:2051-2064`), which
  matters only because that pair can trigger a *synchronous* rebuild
  mid-trace; the tab bar's own trace never does (confirmed:
  `_set_content_tab`/`_set_settings_tab` never call `_request_rebuild()`).
- **A rebuild mid-tab-switch, or a tab change mid-build**: not reachable
  through real Tk event dispatch — `_rebuild_ui()` runs synchronously to
  completion once started (its own docstring at `afk_clicker.py:1791`
  explains the only reentrancy hazard here is `update_idletasks()`
  servicing *other pending idle callbacks*, not real X events like a mouse
  click), and `_apply_appearance`/`_apply_ui_scale` — the only rebuild
  triggers — live on entirely different `StringVar`s than the tab bars. As
  an adversarial stress test beyond what's naturally reachable, I forced a
  var-write via monkeypatch injected mid-`_build_content()` (right between
  building `hotkey_pane` and the pane-hiding tail line) to simulate a
  worst-case "tab flips while the tree is half-built": no crash, no
  `TclError`, no infinite loop — it converges to a consistent final state
  (`content_tab=clicking`, `hotkey_pane` unpacked, `clicking_pane` packed,
  var in agreement). The guard holds even under a more hostile scenario
  than production can produce.

**Conclusion: the guard is correct and sufficient in every path I could
construct, including ones outside what real Tk event dispatch can reach.**

## Defects

### Defect 1 (must-fix): `test_a_running_clicker_is_unaffected_by_a_tab_switch` never actually switches tabs

`tests/test_ui.py`, `TabBarNavigation`, ~line 1039-1057 (new in this diff):

```python
def test_a_running_clicker_is_unaffected_by_a_tab_switch(self):
    ...
    self.ui.start()
    self.pump(0.4)
    self.ui._set_content_tab("hotkey")   # <-- already "hotkey"; a no-op
    self.root.update()
    self.ui.mouse.clicks.clear()
    self.pump(0.4)
    self.ui.stop()
    ...
    self.assertTrue(self.ui.mouse.clicks, "...")
```

`self.ui._content_tab` is `"hotkey"` by default on a fresh `UITestCase`
instance (each test method gets its own `self.ui` via `setUp()`), and
nothing earlier in this test changes it. `self.ui._set_content_tab("hotkey")`
is therefore called with the value it already holds — a genuine no-op, not
a tab switch.

**Proven, not inferred**: I removed that line entirely (scratchpad copy,
reverted immediately after) and reran the test in isolation — it still
passes, identically. The assertion never observes a tab switch happening;
it only proves a clicker keeps clicking while nothing is touched, which
several other pre-existing tests already establish. This is exactly the
"silent, hollow test coverage" class of risk `docs/spec.md`'s own "Risk /
rollback notes" section calls out — it slipped past the two `RowValueColumn`
fixes that section named and into this brand-new test instead.

This matters because the dispatch named "a running clicker survives a tab
switch in both directions" as **the single highest-risk invariant this
feature could break** — `_sync_settings()`'s 200ms poll feeds the live
click-worker thread from Clicking-pane widgets unconditionally, with zero
guard on which tab is showing. Right now, no test in the suite actually
exercises that combination.

**The underlying feature is not broken** — verified independently: patching
the same test to genuinely switch (`_set_content_tab("clicking")`, pump,
`_set_content_tab("hotkey")`, pump) still passes, and clicks are still
produced throughout and cleanly stopped afterward. So this is a
test-authorship gap, not a product regression — but it must be fixed before
this criterion can be called covered.

**Fix**: change the no-op call to an actual switch away from the default and
back, e.g.:
```python
self.ui.start()
self.pump(0.4)
self.ui._set_content_tab("clicking")
self.root.update()
self.ui.mouse.clicks.clear()
self.pump(0.4)
self.ui._set_content_tab("hotkey")
self.root.update()
self.ui.mouse.clicks.clear()
self.pump(0.4)
self.ui.stop()
...
```
exercising both directions (per the dispatch's own ask), re-verifying clicks
accumulate in each pumped window before asserting.

## Spec-to-code traceability

| Acceptance criterion | Implemented | Tested | Notes |
|---|---|---|---|
| Hotkey default active on fresh game page | yes | yes | |
| Real click on Clicking switches panes + var | yes | yes | |
| Widgets exist/hold values regardless of packed pane | yes | yes | also independently probed |
| Settings default Appearance + `update_button` exists hidden | yes | yes | |
| Update check reflects state while Updates active | yes | yes (indirect, see table row 5) | non-blocking note |
| Eating conditional inside Clicking, both profile shapes | yes | yes | |
| Active tab survives rebuild, both pages | yes | yes (Appearance trigger only) | non-blocking note |
| **Running clicker survives a tab switch** | **yes (verified manually)** | **no — hollow test** | **Defect 1, must-fix** |
| Full suite green at baseline + feature tests, exact test-impact changes | yes | yes | |

## Fragility audit (12 new `TabBarNavigation` tests + 3 modified)

- **`_click_tab` helper** (used by 2 tests): computes the click point from
  `bar._tabs`' own runtime-measured x-ranges (built from `tkfont.Font(...)`
  against whatever font actually resolves on the running machine), not a
  hard-coded pixel — self-consistent regardless of font substitution, DPI,
  or screen size. Not fragile.
- **Geometry-independent tests** (10 of 12): read `winfo_manager()`,
  `hasattr`, `.var.get()`, direct method return values, or button/label
  `itemcget` text — none depend on font metrics, screen resolution, or
  window manager presence. Not fragile.
- **`test_a_running_clicker_is_unaffected_by_a_tab_switch`**: timing-based
  (`self.pump(0.3/0.4/0.2)`), but this is the same pre-existing `pump()`
  technique already used at this exact scale (0.2-0.8s) throughout the file
  (e.g. lines 219-555, 1046-1054, 2434-2478) — not a new fragility class
  introduced by this feature. Its actual defect is coverage, not flakiness
  (Defect 1 above).
- **The 3 modified existing tests** (`NumBoxFocus.focus_and_settle`,
  `BindAllBoundOnce`'s theme test, `RowValueColumn`'s two resize tests):
  each adds `self.ui._set_content_tab("clicking"); self.root.update()` — a
  direct method call, not a click; no new font/DPI/screen dependency
  introduced.
- No CI-failure-prone patterns (real screen resolution assumptions, WM
  focus assumptions beyond the existing `focus_force()` precedent, absolute
  pixel constants) found in any of the 12 new tests.

## Dropped section headers

Confirmed by grep across `afk_clicker.py` and `tests/test_ui.py`: the
literal strings `"Clicking"`, `"Appearance"`, `"Updates"` only appear as (a)
`TabBar` tab labels and (b) comments explaining their header was dropped —
no other code or test references the old `section(body, "Clicking"/
"Appearance"/"Updates", s)` calls. `"Hotkey · shared by every game"` and
`"Eating"` are kept verbatim, unchanged wording, correctly still read as
sub-section headers rather than tab labels.

## Correctness / simplicity / security review

- **`TabBar` vs. `Segmented`**: the implementation confirms the spec's
  argument — opposite geometry model (natural per-label width vs. equal
  division), opposite hit-test math, opposite paint model (underline vs.
  filled pill drawn behind text), no shared state. Retrofitting `Segmented`
  would have meant branching its entire constructor/`_click()`/`_paint()`
  body on a style flag. A ~60-line sibling class is the smaller, safer diff
  — the spec's "cannot serve" argument holds up against the actual code,
  not just the sketch.
- **Build order**: confirmed both panes are built and packed, in the
  documented order, before `_set_content_tab()`/`_set_settings_tab()`'s
  trailing call hides one (`afk_clicker.py:1899-1973`, `:1975-2085`).
  Confirmed empirically that a hidden pane's card geometry is real (439px,
  not a placeholder) and that a hidden pane correctly does not track a live
  resize until shown (439 → 651 on switch), matching the spec's own
  documented edge case exactly.
- **No security-relevant surface** — pure Tkinter layout change, no new I/O,
  no new external input, no new persisted state (confirmed: `_content_tab`/
  `_settings_tab` are plain instance attributes, never touched by
  `Store`/`settings.json`).
- **No scope creep** — diff is exactly what `docs/spec.md`'s "Affected
  areas" describes: one new class + 4 constants, 2 attributes + 2 methods,
  and re-parenting of existing widget-construction calls with zero
  construction-call changes. No drive-by refactors found in the diff.
- **Contrast claims independently recomputed**: recomputed WCAG relative
  luminance from the literal hex values in `afk_clicker.py:78-80` (not
  trusted from `docs/design.md`'s prose) — dark: INK/BG 14.47:1, MUTED/BG
  6.25:1, ACCENT/BG 6.79:1; light: INK/BG 14.58:1, MUTED/BG 5.22:1,
  ACCENT/BG 5.21:1; LINE/BG 1.72:1 dark / 1.20:1 light. All match
  `docs/design.md`'s stated numbers exactly and clear their required
  thresholds (4.5:1 text, 3:1 graphical for the ACCENT underline); the
  sub-3:1 LINE separator is correctly scoped as decorative (WCAG 1.4.11
  doesn't apply — it conveys no state) rather than papered over as passing.

## Findings, ranked

1. **[Must-fix]** `tests/test_ui.py`, `TabBarNavigation.test_a_running_
   clicker_is_unaffected_by_a_tab_switch` (~line 1039-1057) — the tab-switch
   call is a no-op (`_set_content_tab("hotkey")` when already `"hotkey"`),
   so the test provides zero coverage of its own named scenario, which is
   this feature's single highest-risk invariant. See Defect 1 above for the
   proof and the fix.
2. **[Non-blocking]** `test_active_content_tab_survives_a_rebuild`/
   `test_active_settings_tab_survives_a_rebuild` only trigger the rebuild
   via `_apply_appearance`, not also via a UI-scale change. Both funnel
   through the identical `_rebuild_ui()` path, so this is not a real gap —
   noted for completeness, not required to fix.
3. **[Non-blocking]** `test_the_updater_still_reflects_state_while_its_tab_
   is_active` drives `_set_update_state()` directly rather than the full
   `check_update()` → `_check_worker` async chain while the Updates tab is
   active. Reasonable scoping (that chain is unchanged and independently
   covered by `SettingsUpdates`), but worth knowing this criterion's "when
   an update check is then run" wording is satisfied at one remove.

## Overall verdict (first pass): **changes requested**

The feature itself is sound — I independently verified the build-order/
hidden-geometry contract, the re-entrancy guard (including an adversarial
scenario beyond what real Tk dispatch can produce), and, by hand-patching
the broken test, that a running clicker genuinely does survive a real tab
switch in both directions. The one blocker is Finding 1: a new test that
does not test what it claims to test, on exactly the criterion flagged as
this feature's biggest risk. Fix the no-op tab switch in
`test_a_running_clicker_is_unaffected_by_a_tab_switch` (tests/test_ui.py,
`TabBarNavigation`) so it genuinely exercises both directions, then this is
ready for approval — nothing else found blocks it.

---

# Delta verification pass (round 2)

Scope: only what changed since the first pass above — the blocker fix, the
two optional items, and a flakiness investigation the coordinator asked for.
Not re-deriving anything already established above.

## 1. The blocker fix: verified, non-vacuous, asserts at the right moments

`tests/test_ui.py:1063-1103`, `TabBarNavigation.test_a_running_clicker_
is_unaffected_by_a_tab_switch`, now:
```
start() -> pump(0.4) -> assert clicks produced (baseline, before any switch)
assert _content_tab == "hotkey"
_set_content_tab("clicking") -> pump(0.4) -> assert running, assert clicks
_set_content_tab("hotkey")   -> pump(0.4) -> assert running, assert clicks
stop() -> pump(0.2) -> assert not running
```
This is a genuine switch each time (not the earlier no-op), asserts
`running` and non-empty `clicks` **after each switch** rather than only at
the end, and includes the pre-switch baseline the earlier version lacked.
Structurally sound.

**Re-ran the developer's own mutation, myself, from scratch** (not trusting
the report): edited `_set_content_tab()` in place
(`afk_clicker.py:2157-2200`) to add `self.running = False` right after
`self._content_tab = value`, ran the test in isolation:
```
FAIL: test_a_running_clicker_is_unaffected_by_a_tab_switch
  File "tests/test_ui.py", line 1088, in test_a_running_clicker_is_unaffected_by_a_tab_switch
    self.assertTrue(self.ui.running)
AssertionError: False is not true
```
Failed at the **first** post-switch assertion (line 1088), not the last —
confirming the test catches the regression at the earliest point it
happens, not only eventually. Reverted the mutation
(`git diff --stat` back to the original 191-line diff), reran
`TabBarNavigation` (all 14 tests) and the full suite once more — clean.
**The blocker is fixed and the fix is real, verified firsthand.**

## 2. Both optional items: applied correctly

- `test_active_content_tab_survives_a_ui_scale_rebuild` /
  `test_active_settings_tab_survives_a_ui_scale_rebuild`
  (`tests/test_ui.py:1039-1061`): mirror the Appearance-triggered versions
  exactly, via `_apply_ui_scale("115")`. Read and agree: no `tearDown`
  concern here unlike the Appearance-triggered pair, since `ui_scale` lives
  in each test's own temp-file `Store`, never in module-level state the way
  the active theme does.
- **The `SettingsUpdates` async-chain coverage claim — checked, not
  trusted**: read `tests/test_ui.py`'s `SettingsUpdates` class directly.
  `test_offer_lands_through_a_real_worker_thread_with_settings_closed` and
  `..._with_settings_open` (`tests/test_ui.py:2419-2470`) spawn
  `self.ui._check_worker` as a real background `threading.Thread` and use
  `pump_until` to observe the result land via `_offer_update`/
  `_set_update_state`; `test_a_fresh_check_supersedes_a_superseded_offer`
  drives `self.ui.check_update()` directly. The claim that the async chain
  "already has dedicated coverage elsewhere" is **true, confirmed by
  reading**, not merely asserted.

## 3. The flakiness investigation

### What happened, honestly, including my own mistake

I first ran my own stress loop without checking for concurrent activity and
it **overlapped with the coordinator's own dedicated 14-run loop on the
same shared `DISPLAY=:99`**, producing 4 spurious `NumBoxFocus` failures
from that collision alone. I killed my orphaned process
(confirmed via `ps -ef --forest` — an orphaned child of my own earlier
`pkill`, reparented to init, still running against the shared display) and
did not let that contaminated data influence anything below. Lesson
applied, not just noted: everything that follows was either observed in the
coordinator's own dedicated loop after I had cleared my interference, or in
my own isolated runs verified to have no competing process at the time
(checked via `ps aux` before and after each stress batch).

### Confirming the coordinator's diagnosis

I independently reproduced the same failure signature in isolated,
uncontended runs of `NumBoxFocus` alone (not the full suite): **3 failures
in 6 back-to-back runs**, then, after regenerating comparable load with a
background full-suite loop, **1 failure in 8** — always the identical
assertion:
```
tests/test_ui.py:655, in focus_and_settle
  self.assertEqual(self.root.focus_get(), numbox.entry, ...)
AssertionError: <tkinter.Tk object .> != <tkinter.Entry object ...>
```
One more data point gathered incidentally while A/B-testing the fix below:
a full-suite run started concurrently with my isolated-loop testing (i.e.
under still-heavier combined load) hit **6 failures in one run, all
`NumBoxFocus` via `focus_and_settle`** — closely matching the coordinator's
own "7 failures in one verbose run" independently.

**I confirm the coordinator's diagnosis exactly.** `focus_and_settle()`
(`tests/test_ui.py:641-656`, the fix this feature's *first* round made to
`NumBoxFocus`'s shared helper) does: `_set_content_tab("clicking")` ->
`root.update()` -> `focus_set()` -> `root.update()` -> assert. The
mechanism: `_set_content_tab("clicking")` maps `clicking_pane` for the
first time in that test's lifetime (it starts hidden, `hotkey_pane` is the
default-active pane). Mapping a previously-unpacked window is an
asynchronous X11 round trip (the client requests `MapWindow`, the server
must respond with `MapNotify` before the window is genuinely *viewable*
and eligible to receive input focus). A single `root.update()` drains
pending Tk events but does not *guarantee* that round trip has completed
under load — so `focus_set()` sometimes runs against a window that is
mapped from Tk's synchronous point of view but not yet viewable at the X
server, and Tk does not queue/retry that focus request; it is simply
dropped. `self.root.focus_get()` then still reports the toplevel, matching
every observed failure exactly.

### Validated fix (built and stress-tested myself, not applied to the diff)

Patched a scratch copy of `focus_and_settle` to gate on viewability before
focusing and use the file's own already-proven `pump_until()` helper
(`tests/test_ui.py:129-147`, already used elsewhere, e.g. `SettingsUpdates`)
instead of a single `update()`:
```python
def focus_and_settle(self, numbox):
    self.ui._set_content_tab("clicking")
    self.root.update()
    self.pump_until(lambda: numbox.entry.winfo_viewable(), timeout=1.0)
    numbox.entry.focus_set()
    self.pump_until(lambda: self.root.focus_get() == numbox.entry, timeout=1.0)
    self.assertEqual(self.root.focus_get(), numbox.entry,
                     "setup failed to focus the entry")
```
**A/B tested under matched induced load** (a background full-suite loop
running concurrently, to reproduce comparable system pressure to the
coordinator's own stress loop): original helper, **1 failure in 8** runs of
`NumBoxFocus`; patched helper, **0 failures in 18** runs (10 without
induced load + 8 under the same induced load the control was tested
under). Reverted the scratch edit immediately after
(`git diff --stat -- tests/test_ui.py` back to the original 244-insertion
diff, confirmed via checksum). **This is a validated, working fix, not a
guess** — I did not apply it to the tracked file per the coordinator's
explicit instruction not to fix it myself.

**Recommendation for the developer**: apply exactly the patch above to
`focus_and_settle()` (`tests/test_ui.py:641-656`). It uses only the
file's own already-established `pump_until` pattern — no new technique,
no new dependency — and both waits it adds fail closed (via the existing
`assertEqual` at the end, which still reports a genuine regression if the
window somehow never becomes viewable/focused within 1s).

### Item 3: `RunningClickerSurvivesRebuild` — a distinct problem, not the same class

`tests/test_ui.py:2519-2526`,
`test_worker_running_and_clicks_continue_across_a_scale_change` — **entirely
pre-existing code, not touched anywhere in this feature's diff** (confirmed:
absent from `git diff main -- tests/test_ui.py`; it is a Feature-4-era test
class, `ac-17-f4`). The failure was `[] is not true : no clicks landed
after the rebuild` — **zero** clicks in a 300ms window at a nominal 60ms
interval (should be ~5), not one-fewer-than-expected. That signature
matches a different mechanism than the focus race: total starvation of the
background click-worker thread for the whole pumped window, which the
file's own `pump()` docstring already documents as a known risk ("a
tighter loop spends most of its time holding the GIL inside
`root.update()`, which starves the clicking thread"). This is a GIL/CPU-
contention symptom under extreme system load (many concurrent Tk-heavy
Python processes competing for the same CPU and the same Xvfb, which is
exactly the load our own stress-testing this round created), not a timing
margin that is inherently too tight for normal single-run operation, and
not the same root cause as the `focus_and_settle` race (no window-mapping
or X-focus involved here at all — the worker thread never touches Tk).

**Verdict on item 3**: distinct problem, out of this feature's scope (the
test predates it and this diff never touches it), and not something to fix
as part of this PR. Worth a follow-up ticket if it recurs outside of
artificially-induced stress-loop conditions (the same `pump_until`-based
"wait for at least one click" pattern would harden it identically), but not
a blocker here.

### Item 4: does this change my assessment of the product code?

**No — confirmed, not assumed.** Across this entire investigation (my two
original clean runs, the coordinator's 14-run dedicated loop, my own ~40+
additional isolated/induced-load runs of `NumBoxFocus` and
`TabBarNavigation`, and my own mutation-test of the blocker fix), **every
single attributed failure traced to test-harness code** — either the
`focus_and_settle` window-mapping race (test code introduced by this
feature's first round) or the pre-existing, feature-unrelated
`RunningClickerSurvivesRebuild` GIL-starvation symptom. Not one failure was
ever observed in `TabBar`, `_set_content_tab`/`_set_settings_tab`,
`_build_content`/`_build_settings`, or the pane-visibility/click-worker
interaction itself — including `test_a_running_clicker_is_unaffected_by_a_
tab_switch`, the test specifically named as the top suspect, which passed
in every run across this entire investigation (respected the coordinator's
instruction not to harden it speculatively: **its margins are fine, leave
it as-is**). The product code is sound.

### Correcting the coordinator's stated hypothesis

The coordinator's working hypothesis (margins on the new timing-dependent
`test_a_running_clicker_is_unaffected_by_a_tab_switch`) is **not supported
by the evidence** — that test did not fail once across the full
investigation. The actual, now-identified and now-fixable defect is in
`focus_and_settle()`, a helper this feature's *first* round modified (not
part of this round's own delta, but part of this feature's overall diff and
squarely this PR's responsibility to fix), plus one unrelated pre-existing
flake this diff does not touch.

## Overall verdict (delta pass): **changes requested**

Not for the reason originally suspected, and not because the product is
broken — it is not, confirmed by direct reproduction above. **Must-fix**:
apply the validated `focus_and_settle()` patch (`tests/test_ui.py:641-656`,
patch shown above) before this feature is called done. It is a two-line
change using a technique already proven in this file, I have already
verified it eliminates the failure under matched induced load, and at a
demonstrated ~15-30% failure rate under load this is no longer in the
"known pre-existing flake, don't chase" category the project already
tolerates — it is a specific, fixable defect in code this feature's own
diff is responsible for.

**Everything else is approved as-is**: the original blocker
(`test_a_running_clicker_is_unaffected_by_a_tab_switch`) is genuinely
fixed and re-verified; both optional items are correctly applied and their
claims independently checked; `RunningClickerSurvivesRebuild`'s failure is
a distinct, pre-existing, out-of-scope issue that does not block this PR.
Once `focus_and_settle()` is patched, this is ready for approval — I would
expect no further rounds on this feature.

---

# Delta verification pass (round 3)

Scope, per dispatch: (1) confirm the round-2 must-fix patch to
`focus_and_settle()` was applied verbatim and actually works, re-reproducing
under comparable induced load since an unloaded green run proves nothing
here; (2) hands-on re-verify the two round-2 items that had only been
code-read, not executed, before (`test_a_running_clicker_is_unaffected_by_a_
tab_switch`'s rewrite, and the two new UI-scale rebuild-survival tests); (3)
confirm nothing else in the diff changed since round 2. Environment: same
worktree, same `DISPLAY=:99`, same venv python
(`/tmp/claude-1000/.../scratchpad/venv/bin/python`), HEAD `774ebfe`.

## 1. The must-fix patch: applied verbatim

Read `tests/test_ui.py:641-666` directly. `focus_and_settle()` now reads
exactly:
```python
self.ui._set_content_tab("clicking")
self.root.update()
self.pump_until(lambda: numbox.entry.winfo_viewable(), timeout=1.0)
numbox.entry.focus_set()
self.pump_until(lambda: self.root.focus_get() == numbox.entry, timeout=1.0)
self.assertEqual(self.root.focus_get(), numbox.entry,
                 "setup failed to focus the entry")
```
Character-for-character the patch I validated in round 2, plus two comments
explaining the MapNotify-race rationale (kept, not touched). Confirmed via
direct read, not the doc's claim.

## 2. Does it actually work under load? No — not fully

**Reproduced under a background full-suite loop running concurrently on the
same shared `DISPLAY=:99`** (the same induced-load technique round 2 used
and validated: `for i in 1..20; do unittest discover; done` in the
background, foreground runs against it). Three independent probes, in
increasing detail:

- **Real, unmodified `NumBoxFocus` in isolation, 12 runs**: **4/12 runs
  failed** (`test_a_game_item_still_selects`,
  `test_escape_blurs_without_reverting_the_value`,
  `test_click_elsewhere_drops_focus`,
  `test_click_a_different_numbox_switches_focus`), all at the identical
  assertion inside `focus_and_settle()`.
- **Instrumented copy of the same helper** (scratch probe, not committed,
  reverted — timed each stage): a second batch of 15 runs reproduced **4
  failing runs (6 individual test failures)**. Every failure shows
  `viewable_now=1` (the MapNotify race the round-2 fix targets is genuinely
  fixed — the widget is viewable well within budget every time) but
  `focus_wait` pins at the full `1.006`-`1.020s` timeout and
  `final_focus_get=None` — a **different** symptom than round 2's
  (`<tkinter.Tk object .>`, the toplevel keeping default focus). This time
  nothing has focus at all.
- **Same instrumented probe with the timeout raised 5x (5.0s instead of
  1.0s)**, to rule out "it just needs a slightly bigger margin": 8 runs (72
  individual tests), **1 run failed**, and that failure's own trace shows
  `focus_wait=5.001s, converged=False` — it did not converge even given 5x
  the budget. This is not a margin problem; the focus request genuinely
  never lands in that run.
- **Full suite (259 tests) under the same induced load, 8 runs**: run 2
  failed on exactly this mechanism (`test_click_a_different_numbox_switches_
  focus`, `test_enter_blurs_without_reverting_the_value`, both via
  `focus_and_settle`); runs 7 and 8 hit the pre-existing, already-tracked
  `Tcl_AsyncDelete`/exit-134 shutdown flake (`backlog.md`, ~1-in-4
  historical rate — out of scope, and its own rate here is consistent with
  that history, not worse); run 5 hit `LiveRepository`'s live-network test
  (unrelated, environment-dependent). **1/8 full-suite runs (12.5%) still
  failed on this feature's own test-harness code**, not on either
  documented out-of-scope flake.

**Control, no induced load**: 12/12 isolated `NumBoxFocus` runs clean, 0
failures — confirming this is load-correlated, not a baseline regression,
consistent with round 2's finding.

**Conclusion**: the round-2 fix is real and does what it was built for —
every failure I captured shows the widget was viewable well inside budget,
so the *original* MapNotify-before-viewable race is gone. But a **second,
distinct mechanism** in the same helper survives it: under the same class
of induced load, `focus_set()` on an already-viewable widget sometimes
never actually transfers real input focus, even given a 5-second wait —
`self.root.focus_get()` reports `None`, not the entry, and not the
toplevel either. This produces a comparable-order-of-magnitude failure rate
(~25-33% of isolated `NumBoxFocus` runs, ~12.5% of full-suite runs under
this load) to what round 2 reported *before* its own fix — this is not the
"known pre-existing flake, don't chase" category (that's `Tcl_AsyncDelete`,
confirmed present at its own separate, unchanged rate in the same batch,
and correctly out of scope). It also does not implicate the two other
observed flakes (`Tcl_AsyncDelete`, `LiveRepository`) — those are
pre-existing, unrelated to this feature's diff, and occurred at rates
consistent with their own documented history.

**This directly contradicts `docs/implementation.md`'s "Post-review fix
(round 3)" claim of 10/10 full-suite and 18/18 isolated `NumBoxFocus` runs
clean under matched induced load.** I do not have visibility into exactly
how heavy the developer's own induced load was, but mine used the same
technique documented in this file's own round 2 (a background full-suite
loop, concurrent, same shared `DISPLAY`), and reproduced the failure
repeatedly across three independently-constructed probes plus a real,
unmodified test run — this is not a fluke or a probe artifact.

**Root-cause hypothesis (not fully chased, flagged for the developer):**
this Xvfb has no window manager. With no WM to arbitrate real X input
focus between clients, and the induced-load process's own Tk root also
live on the same shared `:99` display concurrently, `focus_set()`'s
request can apparently be lost even after the *target* window is
confirmed viewable — plausibly because the X server's actual input focus
is transiently held by the *other* process's toplevel at that moment, and
nothing forces a handoff. This would mean the fragility is inherent to
running two Tk-owning processes against one shared, WM-less X display at
once, not merely a matter of CPU scheduling margins — which is why raising
the timeout from 1s to 5s did not fix the one run it still failed. Whether
that is representative of how CI actually runs this suite (one process at
a time against its own display) or specific to this stress-test rig is an
open question the developer/orchestrator should resolve before deciding
between "hardening the test further" and "this is an artifact of the
verification method, accept the round-2 fix as sufficient for real CI."

## 3. The two round-2 items, now verified hands-on (not just read)

- **`test_a_running_clicker_is_unaffected_by_a_tab_switch`**: read
  `tests/test_ui.py:1063-1103` directly — unchanged since round 2 (confirmed
  via diff), still genuinely switches `hotkey→clicking→hotkey` while
  running, asserting `running` and non-empty `mouse.clicks` after each
  switch plus a pre-switch baseline. Ran it in isolation, no load: **pass**.
  Round 2's own mutation test (breaking `_set_content_tab` to set
  `self.running = False`, watching it fail at the first post-switch
  assertion) already proved this non-hollow on identical code; not
  re-litigated per proportional verification depth — the code is
  byte-identical to what that mutation test already exercised.
- **`test_active_content_tab_survives_a_ui_scale_rebuild` /
  `test_active_settings_tab_survives_a_ui_scale_rebuild`**: read
  `tests/test_ui.py:1039-1061` — mirror the Appearance-triggered pair via
  `_apply_ui_scale("115")`. **Mutation-tested myself, from scratch**: edited
  `afk_clicker.py:1973`'s trailing `self._set_content_tab(self._content_tab)`
  to unconditionally call `self._set_content_tab("hotkey")` (simulating a
  rebuild that forgets to restore the active tab), reran both
  `test_active_content_tab_survives_a_ui_scale_rebuild` and
  `test_active_content_tab_survives_a_rebuild`: **both failed**,
  `AssertionError: 'hotkey' != 'clicking'`, at the exact assertion checking
  `self.ui._content_tab`. Reverted immediately
  (`git diff --stat -- afk_clicker.py` back to empty, confirmed byte-identical
  via `diff`). Both tests genuinely exercise the invariant they claim, and
  the UI-scale trigger is not redundant with the Appearance trigger — it
  goes through the identical code path and both broke identically, which is
  the expected result, not a sign either test is hollow.

## 4. Nothing else changed since round 2

`git diff db20af2..HEAD --stat`: `afk_clicker.py` 191+/10- (unchanged from
round 2's stat — no product code touched this round, confirming the
developer's own claim). `tests/test_ui.py` diff has exactly 5 hunks:
`NumBoxFocus.focus_and_settle` (the must-fix patch), the two `RowValueColumn`
resize-test additions, the new `TabBarNavigation` class, and
`BindAllBoundOnce`'s theme test — each hunk's content diffed byte-for-byte
identical to what rounds 1/2 already reviewed, except the must-fix patch
itself and the `TabBarNavigation` class's now-14 tests (12 previously
reviewed unchanged + 2 new UI-scale tests + the round-2 rewrite of the
running-clicker test, both covered above). No other pre-existing test was
touched.

## Overall verdict (round 3): **changes requested**

The must-fix from round 2 is applied verbatim and does fix the mechanism it
targeted (MapNotify-before-viewable) — confirmed by direct code read and by
every failure this round showing the widget already viewable well within
budget. But under the same class of induced load used to validate that fix,
`focus_and_settle()` still fails at a comparable rate (~25-33% of isolated
`NumBoxFocus` runs, 1/8 full-suite runs) via a **second, distinct**
mechanism: `focus_set()` on an already-viewable widget sometimes never
transfers real input focus at all, even given a 5-second wait — not a
margin problem, a genuine non-convergence in some runs. This contradicts
`docs/implementation.md`'s claimed 10/10 full-suite and 18/18 isolated
clean runs under matched load.

**Must-fix**: either (a) harden `focus_and_settle()` further to tolerate or
retry this second mechanism, or (b) if the developer/orchestrator determines
this is an artifact of the specific verification methodology (two Tk-owning
processes contending for real X focus on one shared, WM-less Xvfb display,
rather than something that can occur in a normal single-process CI run),
document that determination explicitly with supporting evidence and get the
reviewer to re-verify against that narrower claim — do not report "N/N clean
under matched load" without the load actually matching what reproduces the
failure. Either path needs to close the gap between the claimed reliability
number and what I directly reproduced this session, three independent ways,
including on the real, unmodified test file (not just my instrumented
probes).

**Everything else from rounds 1-2 remains approved as-is**: the original
blocker (`test_a_running_clicker_is_unaffected_by_a_tab_switch`) is fixed
and stays fixed; both optional items (UI-scale rebuild-survival tests,
`SettingsUpdates` async-chain claim) are correctly applied, and this round
mutation-tested the UI-scale pair directly rather than only reading them;
no product code or unrelated test was touched this round;
`RunningClickerSurvivesRebuild` and `Tcl_AsyncDelete` remain distinct,
pre-existing, out-of-scope issues, observed this round at rates consistent
with their own prior history, not worse.

## Round 4 (close-out)

Narrow re-check of the round-4 fix (`774ebfe..9e9e466`) against the reliability
question the orchestrator has now settled experimentally (see dispatch table:
0/16 fail on `main` and on feature 2 pre-fix under isolated `:98` load; 6/40
(15%) pre-fix vs 1/40 (2.5%) post-fix under shared `:99` load, with the
mechanism traced to `setUp`'s `root.focus_force()` at `tests/test_ui.py:79`
being a single global X-focus resource that a second Tk process on the same
WM-less display can steal out from under it). Not re-litigated here.

### 1. Diff review (`git diff 774ebfe..9e9e466`)

- **Scope**: touches exactly one file, `tests/test_ui.py`, and within it only
  `NumBoxFocus.focus_and_settle()` (24 insertions / 2 deletions). `git diff
  774ebfe..9e9e466 -- . ':!tests/test_ui.py'` returns empty — confirmed no
  product code is touched.
- **Assertion strength unchanged**: the terminal
  `self.assertEqual(self.root.focus_get(), numbox.entry, "setup failed to
  focus the entry")` is untouched — same widgets compared, same failure
  message, still fails closed on a genuine regression. The old single-shot
  `focus_set()` + one `pump_until` is replaced by a loop that calls the
  stronger `focus_get()` on the entry, but exits the same way (checks the
  identical condition) if the deadline is reached, so a real regression is
  still caught, not masked.
- **Bounded, cannot hang**: `deadline = time.monotonic() + 3.0`, loop body is
  `focus_force()` + `pump_until(..., timeout=0.5)` + a check — worst case
  ~6 iterations, ~3s total, then falls through to the same `assertEqual`.
  No unbounded retry, no swallowed exception path.
- **Consistent with the file's own precedent**: `setUp` (lines 74-79) already
  established that under this Xvfb, only `focus_force()` (not `focus_set()`)
  actually reacquires real X input focus, with the comment there explicitly
  scoped to a one-time use at setup. The round-4 fix applies the identical
  primitive at the point where the same real ownership can be lost again
  mid-test, and the diff's own comment correctly explains why forcing `root`
  again is insufficient (a no-op at the X level if root still nominally owns
  focus) and why forcing the entry directly is the right target. No new
  concept introduced, no drift from the file's established idiom.

### 2. Unloaded full-suite run

`DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .` at `9e9e466`,
no induced load, ran once as instructed:

```
Ran 259 tests in 57.402s
OK (skipped=7)
```

The 7 skips are the pre-existing `LiveRepository` GitHub-rate-limit skips,
unrelated. Also ran `NumBoxFocus` alone for a direct look: 9/9 pass in 1.26s.
No new failures, no regressions in unrelated suites.

### 3. Judgement call: keep or revert the retry loop?

**Recommendation: keep it.**

By the settled mechanism, this retry loop guards a hazard (a second Tk
process stealing global X focus on a shared, window-manager-less display)
that a real CI job — one test process, one display — cannot hit. Taken in
isolation, hardening against an unreachable scenario is exactly the kind of
complexity this pipeline's simplicity review is supposed to flag.

But "in isolation" isn't the situation here. Two things tip this specific
case toward keeping it:

- **Cost is genuinely low.** It's 24 lines confined to one test helper, uses
  a primitive (`focus_force()`) the file already established as correct for
  reacquiring lost real focus, is tightly bounded, and cannot weaken or mask
  a real regression (verified above). There's no product-code risk and no
  meaningful runtime cost in the common case (the loop's `if` breaks on the
  first successful iteration, so an already-focused entry pays for one cheap
  check, not the full 3s).
- **The trap is not hypothetical for how this box actually operates.** The
  dispatch itself says this suite gets repeatedly stress-tested by review
  agents on this box, and this exact mechanism has already cost two review
  rounds to diagnose from scratch. Reverting the fix doesn't remove the
  underlying shared-display hazard — it just guarantees the next stress run
  on `:99` rediscovers the identical 15% flake and burns a third round
  re-deriving a mechanism that's now fully documented. Keeping the fix
  converts a recurring investigation into a one-time, already-paid cost.

If this project's actual CI is confirmed to always run one process per job
on its own display (matching the `:98`-isolated column), the loop will
simply never fire there — the "keep" recommendation costs CI nothing. The
case for reverting would only get stronger if this box's own review habit of
sharing one display across concurrent processes changes; it hasn't.

## Overall verdict (round 4, close-out): **approved**

The round-4 fix is correctly scoped (test-only, single method), doesn't
weaken any assertion, is bounded, and is consistent with the file's existing
focus-handling idiom. The unloaded full-suite run is clean at `9e9e466`
(259 tests, 7 pre-existing unrelated skips, no failures). The reliability
question that blocked rounds 2 and 3 is closed by the orchestrator's
corrected, contamination-free experiment: feature 2 is not a functional
regression relative to `main`, and round 4 measurably shrinks its exposure
window on a shared display from 15% to 2.5%. Recommend keeping the retry
loop (see judgement call above) rather than reverting it before merge.
Feature 2 of 5 is done; ready to hand back to product-manager for the next
feature in story #24.
