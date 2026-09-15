# Implementation: Warn when the Minecraft interval minus jitter drops below 650 ms (G#22/GH#33)

## Summary
Minecraft's Clicking pane now shows a conditional hint under the **Interval**
row, computed from the same `click_ms`/`jitter_ms` numbers `_persist()`
already coerces via `_num()`: no hint at an effective minimum
(`max(50, click_ms - jitter_ms)`) of 650 ms or more, `MUTED` "Java sweeps may
miss" from 550–649 ms, and `BAD` "Java sweeps likely fail" below 550 ms.
Global and every custom ("add current game") profile never show it, driven
by a new data-only `"min_sweep_ms"` key on the profile dict (`DEFAULT_CLICK_MS`
on Minecraft, `None` everywhere else) — the same shape as the existing
`"eating"` boolean, not a hardcoded `profile["id"] == "minecraft"` check.
`Row` gained an additive, opt-in mutable hint (`set_hint`/`clear_hint`) to
carry this; every existing static `hint=` call site (jitter, auto-stop) is
untouched. The hint updates live at every keystroke, on profile switch, and
survives a theme/UI-scale rebuild without touching a not-yet-built or
already-destroyed widget, by mirroring G#21/PR #78's `_note_save`/
`_paint_save_notice` split exactly.

## Changes by file

### `afk_clicker.py`
- **New constants** (~line 150, next to `DEFAULT_CLICK_MS`): `MIN_SWEEP_BAD_MS
  = 550`, with the why-comment from `docs/spec.md` verbatim (the ticket's own
  two cited numbers: 500 ms/10-tick failure case, 650 ms/12-tick+margin
  default). `SWEEP_HINT_MUTED`/`SWEEP_HINT_BAD` hold the two exact copy
  strings from `docs/design.md` ("Java sweeps may miss" / "Java sweeps likely
  fail") — both name "Java" explicitly, per the spec's fixed wording
  constraint (Bedrock has no sweep cooldown to lose, so an unscoped claim
  would be flatly false for that edition).
- **`PROFILES`** (~line 1361-1387): `"min_sweep_ms": DEFAULT_CLICK_MS` on the
  Minecraft dict, `"min_sweep_ms": None` on Global. **`make_profile()`**
  (~line 1401): `"min_sweep_ms": None` on every custom profile.
- **`Row`** (~line 2168-2225): a new `mutable_hint=False` constructor
  parameter, additive alongside the existing static `hint=`. When
  `mutable_hint=True` (and no static `hint=` string given), a `Label` is
  built once, empty and unpacked, and kept as `self.hint_label`; every other
  `Row` (no `hint=`, no `mutable_hint=`) keeps `self.hint_label = None`,
  unchanged from before this feature. Two new methods, `set_hint(text,
  colour)` (retext/recolour, then `.pack(fill="x")`) and `clear_hint()`
  (`.pack_forget()`) — both operate only on `self.hint_label`, so an existing
  static-hint Row (which never sets `mutable_hint=True`) can't reach them
  meaningfully and its own construction-time `Label` is untouched.
- **Clicking pane build** (~line 2917-2921): the Interval row is now kept as
  `self.interval_row = Row(cl, "Interval", s, mutable_hint=True)` (previously
  a throwaway local `r`); `self.click_ms`'s `NumBox` is built into
  `self.interval_row.control` instead of the local's.
- **`AfkAutoclicker.__init__`** (~line 2293-2306): two new instance
  attributes next to `self._save_failed`: `self._sweep_hint_pending` (the
  `(text, colour)` tuple or `None` last computed by `_note_sweep_hint()`) and
  `self._sweep_hint_visible` (bookkeeping for detecting an actual shown/hidden
  *transition*, independent of Tk's own `winfo_ismapped()` — see "Key
  decisions" below for why that distinction matters).
- **Two new methods**, placed immediately before `_persist()`:
  - `_note_sweep_hint(profile, values)` — computes `effective_min = max(50,
    values["click_ms"] - values["jitter_ms"])` from `_persist()`'s own
    already-`_num()`-coerced `values` (no second, independent coercion), sets
    `self._sweep_hint_pending` unconditionally, and paints immediately
    *unless* `self._rebuilding` is `True` — mirroring `_note_save()`'s own
    gate exactly, for the identical reason (see "Key decisions").
  - `_paint_sweep_hint()` — the one place that actually calls
    `self.interval_row.set_hint(...)`/`.clear_hint()`. Calls
    `self._request_pane_fill("clicking")` only on an actual visibility
    transition (`now_visible != self._sweep_hint_visible`) and only while the
    Clicking tab is the active one (`self._content_tab == "clicking"`),
    reusing `_select()`'s own identical guard.
- **`_persist()`** (~line 3510-3524): one new line,
  `self._note_sweep_hint(profile, values)`, right after the `values` dict is
  built and before the `profile.get("custom")` branch — exactly
  `docs/spec.md`'s proposed diff.
- **`_build_ui()`** (~line 2695-2703): one new line in the content (non-
  Settings) branch, `self._paint_sweep_hint()`, right after
  `self._select(self.current, persist=False)` — the safe paint point once
  `self.interval_row` has just been (re)built fresh, mirroring the Settings
  branch's own unconditional `self._paint_save_notice()` call at the same
  tail.

### `tests/test_ui.py`
One new class, `MinecraftSweepHint(UITestCase)`, placed directly after
`RowValueColumn` (22 tests):
- Profile-conditionality: `test_profile_key_is_data_driven` (Minecraft/
  Global/a real `_add_game()`-created custom profile's own `min_sweep_ms`),
  `test_global_profile_never_shows_hint_at_any_numbers`,
  `test_custom_profile_never_shows_hint_at_any_numbers`.
- Thresholds, both boundaries: `test_no_hint_at_650_with_zero_jitter`,
  `test_muted_hint_at_649`, `test_muted_hint_at_550_boundary_is_inclusive`
  (600/50), `test_bad_hint_at_549` (600/51), `test_bad_hint_at_500`,
  `test_bad_hint_floored_at_50_never_negative_or_garbage` (100/500).
- Invalid/empty text: `test_empty_interval_field_falls_back_to_profile_default`,
  `test_invalid_interval_text_falls_back_to_profile_default`.
- Live update, no focus-out: `test_hint_disappears_live_on_the_very_keystroke_that_fixes_it`.
- Profile switch away and back: `test_hint_hidden_on_global_and_restored_on_return_to_minecraft`.
- Pane-fill on transition, not on every keystroke:
  `test_pane_fill_requested_only_on_visibility_transition` (spies on
  `self.ui._request_pane_fill`, the same technique
  `test_hidden_tabs_own_margin_does_not_desync_the_visible_one` already
  uses; deliberately calls no `root.update()` so the assertion isolates this
  feature's own synchronous call from the pane's unrelated `<Configure>`-
  bound one).
- No-crash-and-still-correct (the orchestrator correction's own added
  acceptance criterion): `test_survives_theme_change_while_hint_visible`,
  `test_survives_ui_scale_change_while_hint_visible`,
  `test_survives_opening_and_closing_settings_while_hint_visible` (closes
  Settings via `self.ui._select(self.ui.current, persist=False)`, the same
  mechanism `docs/history/ac-21-implementation.md` Round 2's own regression
  tests use), `test_survives_startup_with_minecraft_already_the_saved_selection`
  (writes `"selected": "minecraft"` to disk via a real persisted `_select()`,
  then `self.restart()`s a fresh `AfkAutoclicker` against that file).
- Geometry, same property as the jitter precedent:
  `test_hint_wraps_at_the_same_wraplength_and_does_not_overlap_the_control`
  (mirrors `RowValueColumn.test_random_jitter_hint_wraps_instead_of_overlapping_the_control`'s
  own `text.winfo_children()` unpack and `winfo_rootx()` comparison).
- `Row`'s own additive capability, in isolation:
  `test_row_mutable_hint_is_additive_and_starts_hidden` (a bare `app.Row(...,
  mutable_hint=True)`, no `AfkAutoclicker` involved), `test_row_without_mutable_hint_has_no_hint_label`.
- Existing static hints unaffected: `test_existing_static_hints_are_unaffected`
  (jitter's and auto-stop's hint text/colour, read directly) — on top of the
  full suite's own unchanged `RowValueColumn` run.

## Key decisions / tradeoffs
- **`_note_sweep_hint`/`_paint_sweep_hint` split, mirroring `_note_save`/
  `_paint_save_notice` exactly.** The orchestrator correction named this
  precedent directly (G#21/PR #78 round 1's Defect 1: `_rebuild_ui()`'s
  leading `_persist()` call runs while the outgoing widget tree is being (or
  is about to be) torn down and the new one doesn't exist yet). Recording the
  computed state unconditionally but deferring the paint whenever
  `self._rebuilding` is `True`, then painting explicitly once from
  `_build_ui()`'s own tail (after the fresh tree exists), closes the same two
  paths `_note_save`'s docstring documents: a first-ever build where
  `self.interval_row` doesn't exist yet, and a later rebuild where it still
  resolves to an already-destroyed widget from an earlier generation.
- **`self._sweep_hint_visible`, a plain Python attribute, not
  `winfo_ismapped()`.** The Interval row's hint can be logically packed
  (visible, in the sense this feature cares about) while its ancestor
  Clicking pane is unmapped because a different content tab is showing —
  `winfo_ismapped()` would read `False` in that case regardless of the
  hint's own pack state, making it useless for detecting *this* feature's
  own shown/hidden transition. Tracking the boolean directly, alongside the
  `(text, colour)` tuple, gives an unambiguous transition signal independent
  of whatever tab happens to be active — and the pane-fill call itself is
  still separately guarded on `self._content_tab == "clicking"`, so a
  transition that happens while the pane is hidden never touches its
  geometry (the exact hazard `_on_eat_card_settled()`'s own docstring warns
  about).
- **`Row.hint_label` is always built once, up front, never lazily on first
  `set_hint()`.** A caller that reaches `self.interval_row.hint_label`
  before `set_hint()`/`clear_hint()` has ever run (e.g. a test, or a future
  caller) never hits a missing attribute — matching the same "always build,
  only toggle visibility" convention story #24 feature 3 already established
  for `count_label`.
- **`_note_sweep_hint` reuses `_persist()`'s own `values` dict verbatim, no
  second `_num()` call.** Guarantees the hint can never disagree with what
  the worker actually runs with (`_sync_settings()` reads the same two
  fields through the same `_num()` fallbacks) — the spec's own reasoning for
  hooking into `_persist()` rather than adding an independent read path.

## Deviations from spec / design
None. Every acceptance criterion in `docs/spec.md` is covered by a test
(enumerated above), the exact copy/colours/placement from `docs/design.md`
are used verbatim, and the orchestrator correction's binding constraint (never
touch the hint widget while `self._rebuilding` is `True`, paint only once the
current tree exists) is implemented exactly as directed, via the same
`_note_*`/`_paint_*` split precedent it names. The one place `docs/spec.md`
left open (Open question 3: whether `Row` should always support a mutable
hint, or only opt in) was resolved as an opt-in `mutable_hint=` parameter,
per the spec's own "developer's call, additive only."

## Known limitations
- `_paint_sweep_hint()`'s pane-fill guard reads `self._content_tab` directly
  (not a parameter) — consistent with every other pane-fill call site in this
  file (`_select()`, `_on_eat_card_settled()`), but it does mean a caller from
  a different context would need the same guard duplicated rather than
  passed in. Not a problem today: this feature has exactly one caller
  (`_note_sweep_hint()`) plus the one explicit tail call in `_build_ui()`.
- The MUTED/BAD cut points (650/550 ms) are the spec's own stated
  interpretation of the ticket's two cited numbers, not a re-measurement of
  Minecraft's cooldown table this session — flagged as Open question 1 in
  `docs/spec.md` itself, carried here unchanged. Both are named constants
  (`DEFAULT_CLICK_MS`, `MIN_SWEEP_BAD_MS`), so revising either is a one-line
  change if a different cut is preferred later.

## How to verify locally
Environment (this repo's convention: venv + Xvfb `:99`, confirm nothing else
is running first):
```
pgrep -a Xvfb            # :99 should already be up
pgrep -af "[u]nittest"   # nothing else running
cd /home/dev/projects/afk-clicker
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```

### This feature's own tests
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.MinecraftSweepHint -v
# 22 tests, OK

DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.RowValueColumn -v
# 5 tests, OK -- unchanged by this feature (existing static-hint precedent)
```

### Sabotage-verify performed this session
All three via in-process monkeypatch scripts, scratchpad-only, never written
to `afk_clicker.py` on disk; deleted immediately after use.

**The `_rebuilding` gate** — replaced `AfkAutoclicker._note_sweep_hint` with a
version that always calls `_paint_sweep_hint()`, dropping the
"skip-while-rebuilding" guard entirely, then re-ran
`test_survives_opening_and_closing_settings_while_hint_visible`:
```
_tkinter.TclError: invalid command name ".!frame2.!frame3.!frame.!frame3.!canvas.!frame.!row.!frame.!label2"
```
Confirms the guard is load-bearing — this is the exact destroyed-widget crash
shape `docs/history/ac-21-implementation.md`'s Defect 1 describes for
`_note_save()`, reproduced here for `_note_sweep_hint()`.

**The BAD/MUTED band boundary** — replaced the `<` comparison against
`MIN_SWEEP_BAD_MS` with `<=`, then re-ran `test_muted_hint_at_550_boundary_is_inclusive`:
```
AssertionError: Tuples differ: ('Java sweeps likely fail', '#f06262') != ('Java sweeps may miss', '#9299a3')
```
Confirms the `>= 550` inclusive-MUTED boundary is load-bearing.

**The no-hint/MUTED band boundary** — replaced the `<` comparison against
`profile["min_sweep_ms"]` with `<=`, then re-ran
`test_no_hint_at_650_with_zero_jitter`:
```
AssertionError: ('Java sweeps may miss', '#9299a3') is not None
```
Confirms the `>= 650` no-hint boundary is load-bearing.

`git status --short` after this session, both before and after each sabotage
script ran, shows only the two files below — no sabotage script ever touched
a repo file.

### Full suite result (this session, final state)
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 410 tests in 72.580s

OK (skipped=10)
```
410 = the documented 388-test baseline + 22 new tests this cycle. Same
skip count as the baseline. The pre-existing `ResourceWarning`s (unclosed
files in `tests/test_updater.py`/`tests/test_ui.py`) and the
`invalid command name "..._poll_games"`/`"..._drain_ui"` ("after" script)
console noise are unrelated to this diff — `git diff` confirms none of those
lines changed, and they are already documented as pre-existing in
`docs/history/ac-21-implementation.md`.

### Verification of scope
```
git status --short
 M afk_clicker.py
 M tests/test_ui.py
?? docs/design.md
?? docs/spec.md
```
No file outside `afk_clicker.py`/`tests/test_ui.py` was touched
(`docs/implementation.md` itself is this document); no scratch file was left
in the repo tree.
