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

---

## Round 2 (PR #80 review + `docs/design.md` Revision 2 + its Orchestrator
correction)

### Summary
PR #80's review blocked on cross-platform height: the hint under the
**Interval** row added new content to exactly the pane (Clicking+Eating,
Minecraft) whose height floor was already tuned to a measured 1px margin on
Windows CI, with no re-derivation and no test at the floor with the hint
visible. `docs/design.md` Revision 2 (Decision A2) moved the warning into
the **jitter row's own, already-reserved hint slot** instead of a new
widget under Interval: while a band is active, that slot shows the warning
(bold); otherwise it shows its original static text, "spreads the rhythm so
it is not exact", in `MUTED` regular, byte-for-byte as before. A later
Orchestrator correction to Revision 2 fixed the 550-649 ms band's colour to
`INK` bold (not `MUTED` bold as Revision 2 first proposed) — `MUTED` is this
codebase's plain secondary-text colour, so a warning in it would still read
as secondary text one weight heavier; `INK` bold reads as "this matters",
and `BAD` bold (<550 ms) stays the visibly stronger of the two by colour.

### Changes by file

#### `afk_clicker.py`
- **`Row`** (~line 2187-2245): `mutable_hint=True` no longer builds a bare,
  empty, unpacked label for a row with no static `hint=` (nothing needs
  that shape any more — the Interval row lost `mutable_hint` entirely).
  Instead, `mutable_hint=True` is now paired with a static `hint=` string
  (the jitter row's own): the label is built once, then immediately shown
  via the new `restore_hint()` at construction, so the row starts in its
  original static state. Every plain `hint=` site with no `mutable_hint=`
  (auto-stop) falls through to the untouched `elif hint:` branch,
  byte-for-byte the same code as before this feature ever existed.
  - `set_hint(text, colour, bold=False)` (new `bold` parameter): retexts,
    recolours, and reweights the font via a fresh `("Segoe UI", size,
    weight)` tuple, then packs (the hint is never actually unpacked any
    more — see `clear_hint()`'s removal below).
  - `restore_hint()` (new): back to this Row's construction-time static
    hint, `MUTED` and regular weight. Reads the bare module-level `MUTED`
    global *at call time*, not a value captured at construction or at
    `set_hint()` time, so a theme rebuild's repaint (which always runs
    after `set_active_theme()` has already reassigned it) picks up the new
    palette.
  - `clear_hint()` removed: nothing calls it any more, since round 2's
    hint slot is never hidden, only swapped between two texts.
- **Clicking pane build** (~line 2977-2988): `self.interval_row = Row(cl,
  "Interval", s)` — back to a plain `Row` with no hint capability at all,
  as it was before G#22 ever existed. The jitter row is now kept as
  `self.jitter_row = Row(cl, "Random jitter", s, hint="spreads the rhythm
  so it is not exact", mutable_hint=True)` (previously a throwaway local
  `r`), and `self.jitter_ms`'s `NumBox` is built into
  `self.jitter_row.control`.
- **`_note_sweep_hint`** (~line 3557-3586): unchanged shape (still records
  `self._sweep_hint_pending` from `_persist()`'s own `values`, still
  deferred-paints around `self._rebuilding`), except the 550-649 ms band's
  colour tuple is now `(SWEEP_HINT_MUTED, INK)` instead of
  `(SWEEP_HINT_MUTED, MUTED)` — the Orchestrator correction's own fix.
  `SWEEP_HINT_MUTED`/`SWEEP_HINT_BAD` (the copy strings) are unchanged;
  only the colour paired with the first one changed.
- **`_paint_sweep_hint`** (~line 3588-3617): now targets
  `self.jitter_row` instead of `self.interval_row`, calls
  `set_hint(text, colour, bold=True)` for an active band or
  `restore_hint()` otherwise (never `clear_hint()`, which no longer
  exists), and renamed the transition-tracking attribute
  `self._sweep_hint_visible` → `self._sweep_band_active` (see "Key
  decisions" below for why the old name stopped fitting). The
  `_request_pane_fill("clicking")` call is still guarded on an actual
  band-active/inactive transition, not every keystroke, and still only
  fires while the Clicking tab is visible — round 2 did **not** remove
  this guard, because the restored static text can still be 2 lines while
  the warning is 1 (docs/design.md Revision 2's own wrap-fit argument), so
  the row's height genuinely still changes on a transition.
  - **New guard, found and fixed this round, not requested by the task
    brief**: `if self._settings_open: return`, mirroring
    `_paint_save_notice()`'s own guard in the opposite direction. Root
    cause: `self.jitter_row` only exists in the content tree, which is
    torn down (and not rebuilt) while Settings is showing
    (`_build_ui()`'s `if self._settings_open:` branch never calls
    `_build_content()`) — so a call landing here while Settings is open
    (concretely: `on_close()`'s own unconditional `_persist()` call, with
    Settings left open by an earlier test step) retexts an already-
    destroyed widget. Round 1 never hit this: its "hidden" state used
    `clear_hint()` → `pack_forget()`, which Tk tolerates silently on a
    destroyed widget (confirmed empirically: `pack forget` on a gone
    window is a no-op, unlike `configure`, which raises
    `TclError: invalid command name ...`). Round 2's "always show
    something, never hidden" design means even the "no band" path now
    calls `restore_hint()` → `set_hint()` → `.config()`, which does not
    tolerate a stale widget — surfacing a latent gap that existed in both
    rounds' designs. Caught by the pre-existing
    `RowValueColumn.test_ui_scale_row_never_overflows_its_card_at_any_scale_step`
    regressing (it leaves Settings open across a `restart()`/`on_close()`
    boundary while sitting on the Global profile, so band state is always
    `None`); fixed with this guard, verified the regression is gone (see
    "Full suite result" below), and no round-2 test needed to be weakened
    to make it pass.
- **`AfkAutoclicker.__init__`** (~line 2336-2351): `_sweep_hint_pending`'s
  comment updated for the new meaning (`None` = static text showing, not
  "hidden"); `_sweep_hint_visible` renamed to `_sweep_band_active` with an
  updated comment.
- **`_build_ui()`'s tail** (~line 2745-2755): comment updated to say
  `self.jitter_row` instead of `self.interval_row`; the call itself
  (`self._paint_sweep_hint()`) is unchanged.

#### `README.md`
Added one sentence to the **Random jitter** row of the settings table
(`README.md:75`), in the existing German voice, describing the new
Minecraft-only warning behaviour and its 650 ms / 550 ms thresholds — the
round-1 review's "README wasn't updated" concern, closed for the feature as
it now actually behaves (jitter row, not Interval row).

#### `tests/test_ui.py`
- **`MinecraftSweepHint`** (rewritten in place, same location): every
  assertion now reads `self.ui.jitter_row.hint_label` instead of
  `self.ui.interval_row.hint_label`, via a `_hint()` helper returning
  `(text, colour, bold)` instead of `(text, colour)` or `None` — there is
  no more "hidden" state to represent as `None`; a `_static()` helper
  returns the expected static-text tuple for the "no band" case. Renamed
  throughout for the "band" vocabulary (`test_no_hint_at_650...` →
  `test_no_band_at_650_with_zero_jitter_shows_static_text`,
  `test_muted_hint_at_649` → `test_ink_bold_band_at_649`, etc.) to match
  round 2's actual behaviour rather than round 1's hide/show framing.
  Three genuinely new tests, not just renames:
  - `test_survives_theme_change_while_ink_band_visible` — the
    Orchestrator correction's own concern: `INK` (unlike `BAD`) has a
    materially different value per theme (`#e4e7ea` dark / `#161a22`
    light), so this is the one test that would silently pass if the paint
    ever captured a stale colour instead of re-reading the module global
    fresh (the sibling BAD-band test can't catch this, since `BAD`'s value
    happens to be theme-independent in neither direction that a stale
    capture would expose — both round 1 and round 2 already had a BAD
    variant; only the INK one is new).
  - `test_interval_row_has_no_hint_capability_anymore` — asserts
    `self.ui.interval_row.hint_label is None` and that its label column
    holds exactly one child (the main label), proving the capability
    removal the task explicitly asked for ("remove capability that
    nothing uses anymore").
  - `test_jitter_hint_defaults_to_the_static_text_with_no_band` — the
    restore-to-default path in isolation (Minecraft, no band), a case
    round 1 never needed a dedicated test for since "hidden" and "no
    static text to restore" were the same state.
  - `test_row_mutable_hint_is_additive_and_starts_hidden` →
    `test_row_mutable_hint_is_additive_and_restorable`: exercises the new
    `Row(..., hint=..., mutable_hint=True)` shape end to end — starts
    showing the default text, `set_hint(..., bold=True)` overrides it,
    `restore_hint()` brings the default back — in isolation, no
    `AfkAutoclicker` involved.
  - `test_existing_static_hints_are_unaffected` narrowed to auto-stop only
    (the one row that's still a plain, untouched static `hint=` site);
    jitter's own default rendering is covered by
    `test_jitter_hint_defaults_to_the_static_text_with_no_band` instead,
    since it's no longer "just a static hint", it's the jitter row's
    *restored* state.
- **`WindowMinimumHeight.test_sweep_hint_height_floor_minecraft_with_eating`**
  (new, placed directly after `test_tallest_pane_still_fits_at_worst_case_compound_scale`,
  mirroring its own span-measurement technique exactly): at 90% and 130%
  UI scale, Minecraft profile, Eating shown, forces the worst-case BAD
  band (`click_ms=500, jitter_ms=0`) and asserts the Clicking pane's
  natural height (same `max(child bottom) - min(child top)` span
  measurement the sibling floor tests use) is `<=` its allocated height at
  each scale step, then resets to `click_ms=650, jitter_ms=0` (static text
  restored) at the same scale and asserts the jitter row's own
  `winfo_reqheight()` with the warning shown was `<=` its height with the
  static text shown — the second half of docs/design.md Revision 2's
  height-neutral-or-shorter claim, checked directly rather than assumed.

### Key decisions / tradeoffs
- **`Row.restore_hint()` reads the bare `MUTED` global at call time, not a
  captured value.** Same reasoning `_note_sweep_hint()`'s own INK/BAD
  choice already relies on (see round 1's "Key decisions" for the
  `_note_save`/`_paint_save_notice` precedent this mirrors): every rebuild
  path calls `set_active_theme()` before the paint that reads these
  globals runs, so a plain bare-name lookup inside a method body, executed
  fresh each time it's called, is sufficient — no theme reference needs to
  be threaded onto `self` or `Row` anywhere, consistent with how every
  other widget in this file already reads `BG`/`CARD`/`INK`/... as module
  globals.
- **`_paint_sweep_hint()`'s new `self._settings_open` guard is a fix to a
  latent gap this round's own design change exposed, not a requirement
  copied from the task brief.** The task brief listed round 1's
  guarantees to keep (`_rebuilding`, paint at `_build_ui()`'s tail,
  profile-key-driven behaviour) but did not anticipate that swapping
  `clear_hint()`/`pack_forget()` for `restore_hint()`/`set_hint()`/
  `.config()` would turn a silently-tolerated stale-widget touch into a
  hard crash. Root-caused via `systematic-debugging` (traced the actual
  `TclError` back through `_rebuild_ui()`'s settings-branch skip of
  `_build_content()`, rather than papering over the one failing test with
  a try/except) and fixed with the same guard shape this file already
  uses for the symmetric case (`_paint_save_notice()`'s own
  `self._settings_open and self._settings_tab == "appearance"` check).
- **`clear_hint()` removed outright, not deprecated/kept-for-compatibility.**
  Round 2's design makes the jitter row's hint slot permanently visible
  (never hidden, only retexted), so nothing in this file or its tests
  calls it any more — keeping a dead method around would be exactly the
  "capability nothing uses" the task asked to remove.
- **`_sweep_hint_pending`/`_sweep_band_active` naming and comments updated,
  not just the jitter-row wiring.** `None` used to mean "hint hidden"; it
  now means "no band active, static text showing" — a real semantic
  change worth documenting at the attribute, not just inferable from the
  paint method's body.

### Deviations from spec / design
None beyond what `docs/design.md` Revision 2 and its Orchestrator
correction already document and justify (the Interval→jitter-row placement
change, and the MUTED→INK colour fix) — both are design-level decisions
this round implements as written, not developer-introduced deviations. The
`self._settings_open` guard above is a bug fix necessitated by the design
change, not a deviation from it: nothing in `docs/design.md` says the hint
slot may crash while Settings is open, and the guard is the minimal fix
that keeps every one of round 1's stated guarantees (listed in the task
brief) intact.

### Known limitations
- Carried from round 1, still true: the 650 ms / 550 ms cut points are the
  spec's own interpretation of the ticket's two cited numbers, not a
  re-measurement of Minecraft's cooldown table this session.
- The floor test's two scale steps (90%, 130%) do not exercise the
  documented worst-case *compound* scale (`_dpi_s=0.75` × 90%, the same
  combination `test_tallest_pane_still_fits_at_worst_case_compound_scale`
  covers) with the sweep band active. Not added here because the task's
  own Decision D and item 4 both specify "90% and 130% UI scale" plainly,
  not the compound case — and the jitter row's warning text is shorter
  than what it replaces at every scale step already proven by the
  height-comparison half of the same test, so the compound case is
  expected to hold by the same argument, just not independently asserted.

### How to verify locally
Same environment as round 1 (venv + Xvfb `:99`):
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```

#### This round's own tests
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.MinecraftSweepHint -v
# 25 tests, OK (22 round-1 tests, renamed/rewired for the jitter row +
# INK, plus 3 new)

DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.WindowMinimumHeight -v
# 6 tests, OK (5 pre-existing + the new floor test)
```

### Sabotage-verify performed this session
Both via in-process monkeypatch scripts run against `afk_clicker`/
`tests.test_ui` imported as modules, scratchpad-only, never written to a
repo file; deleted immediately after use. Confirmed via `git status
--short` before and after that no repo file was touched by either.

**The new floor test** — monkeypatched `app.SWEEP_HINT_BAD` to
`"Java sweeps likely fail " * 12`, re-ran
`test_sweep_hint_height_floor_minecraft_with_eating`:
```
AssertionError: 178 not less than or equal to 48      (scale='90')
AssertionError: 232 not less than or equal to 62      (scale='130')
```
Confirms the height-comparison half of the test (warning height <= static
height) catches an inflated warning at both scale steps.

**The restore-to-static-text path** — monkeypatched `app.Row.restore_hint`
to a no-op, re-ran the three tests that depend on it:
```
test_band_clears_live_on_the_very_keystroke_that_fixes_it: FAIL
  ('Java sweeps may miss', '#e4e7ea', True) != ('spreads the rhythm so it is not exact', '#9299a3', False)
test_band_restored_to_static_on_global_and_reshown_on_return_to_minecraft: FAIL
  ('Java sweeps likely fail', '#f06262', True) != ('spreads the rhythm so it is not exact', '#9299a3', False)
test_jitter_hint_defaults_to_the_static_text_with_no_band: FAIL
  ('', '#000000', False) != ('spreads the rhythm so it is not exact', '#9299a3', False)
```
Confirms restoring the jitter row's static text on leaving a band,
switching to Global, and on plain no-band construction are all genuinely
exercised by these tests, not vacuously true.

### Full suite result (this session, final state)
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 414 tests in 73.357s

OK (skipped=10)
```
414 = round 1's 410 + 4 new tests this round
(`test_survives_theme_change_while_ink_band_visible`,
`test_interval_row_has_no_hint_capability_anymore`,
`test_jitter_hint_defaults_to_the_static_text_with_no_band`,
`test_sweep_hint_height_floor_minecraft_with_eating`). Same skip count as
round 1. The pre-existing `ResourceWarning`s (`tests/test_updater.py`) are
unrelated to this diff, same as round 1's own note.

Also independently confirmed (before making the fix) that
`RowValueColumn.test_ui_scale_row_never_overflows_its_card_at_any_scale_step`
passes unmodified against the round-1 commit `df1d136` in a throwaway
detached worktree, and only started failing after this round's jitter-row
rewiring — pinning the regression to this round's own change rather than a
pre-existing flake, before writing the `self._settings_open` guard that
fixes it.

### Verification of scope
```
git status --short
 M README.md
 M afk_clicker.py
 M docs/implementation.md
 M tests/test_ui.py
```
(`docs/design.md` was already modified, with Revision 2 and its
Orchestrator correction, before this round started — untouched by this
round's own work.) No scratch file was left in the repo tree; the
sabotage-verification worktree was removed after use.

---

## Round 3 (PR #80 round-2 review, `docs/test-review.md` "Round 2" +
`pr80-round2-review.md` — CHANGES REQUESTED)

### Summary
Round 2's review found the new floor test
(`WindowMinimumHeight.test_sweep_hint_height_floor_minecraft_with_eating`)
present, named correctly, green — but structurally unable to catch the
exact overflow it exists to guard against, plus a should-fix README
inaccuracy. This round fixes both, and separately investigates (without
fixing) whether the three pre-existing sibling floor tests share the same
blind spot, as requested.

### Changes by file

#### `tests/test_ui.py`
- **`test_sweep_hint_height_floor_minecraft_with_eating`**
  (`tests/test_ui.py:~1170-1263`), rewritten in place, same location, same
  method name:
  - **New pane measurement.** The old `natural` was `max(child bottom) -
    min(child top)` over each mapped non-spacer child's *allocated*
    `winfo_y()`/`winfo_height()`. Replaced with a sum of each mapped
    non-spacer child's own `winfo_reqheight()` plus its pack `pady` (read
    via `pack_info()`, summing both sides of a 2-tuple or doubling a bare
    int) — i.e. the *required* space pack() would need to lay every child
    out untouched, the same accounting `_fill_pane()`'s own docstring
    insists on for the identical reason (a bare reqheight sum silently
    drops real pack()-consumed pady). Compared against the same
    `pane.winfo_height()` (available) as before. Spacers are excluded from
    the sum exactly as they were from the old span (`c not in (top,
    bottom)`), so their own intentional shrink-to-fit behavior is not
    counted against the pane.
  - **Fresh instance per scale step**, not `_apply_ui_scale()` mid-test:
    `self.ui.store.data["ui_scale"] = scale; self.ui.store.save(); ui =
    self.restart()`, the exact technique
    `RowValueColumn.test_ui_scale_row_never_overflows_its_card_at_any_scale_step`
    (`tests/test_ui.py:~1735-1759`) already established for the identical
    anti-pattern (`_apply_minsize(grow_only=True)` never shrinks, so a
    mid-test scale-down leaves the window at its larger pre-existing size).
    Each scale step now asserts `self.root.winfo_height() ==
    int(app.WINDOW_MIN_H * ui.s)` (and the same on `minsize()[1]`) before
    doing anything else, so the subTest is proven to have actually reached
    that scale step's genuine floor, not merely assumed to.
  - **Both bands, not only BAD.** Measured live: at 90% scale, INK ("Java
    sweeps may miss") uses 123px of a 131px wraplength vs. BAD ("Java
    sweeps likely fail") at 120px — INK is the *tighter* fit despite three
    fewer characters, because of where its words break. The rewritten test
    loops `(("bad", "500"), ("ink", "649"))` inside each scale step's
    `subTest`, asserting the pane-fit and the row-height-vs-static
    invariants for each band independently, rather than assuming BAD is
    the worse case.

### Key decisions / tradeoffs
- **`winfo_reqheight() + pack_info()["pady"]` per child, not a full
  reimplementation of `_fill_pane()`'s own span logic.** `_fill_pane()`
  itself deliberately measures allocated span (its own docstring explains
  why — it needs a number that's translation-invariant in the spacers'
  *current* height, for a live-resize recompute). The test's job is
  different: it needs a number that reflects what the pane's content
  *actually requires*, independent of whatever pack() was forced to give
  up to make it fit — the two measurements answer different questions on
  purpose, so reusing `_fill_pane()`'s own logic verbatim would have
  reproduced the same blindness in the test that measures its result.
- **Sabotage-proving both `SWEEP_HINT_BAD` and `SWEEP_HINT_MUTED`
  independently**, not just one. Since the test now loops both bands,
  either constant's inflation needed to be shown to fail only the
  matching band's subTest, not silently pass because the other band's
  iteration happened to still fit — confirmed below.
- **Did not touch the three pre-existing sibling tests.** Per the
  dispatch's explicit instruction, investigated whether they share this
  round's blind spot but left them exactly as written; findings recorded
  under "Known limitations / follow-up" for the orchestrator to ticket.

### Deviations from spec / design
None. This round is entirely a response to `docs/test-review.md`'s
"Round 2" CHANGES REQUESTED verdict and `pr80-round2-review.md`'s
must-fix/should-fix findings — no new product behavior, no design
decision revisited.

### Sabotage-verify performed this session
All via in-process monkeypatch scripts run against `afk_clicker`/
`tests.test_ui` imported as modules, scratchpad-only, never written to a
repo file; deleted immediately after use. `git status --short` before and
after each showed no repo file touched by the probes themselves (only the
two intended edits below, plus the reviewer's own pre-existing uncommitted
`docs/test-review.md` "Round 2" section).

**The new pane assertion, sabotaged with the reviewer's own exact
mechanism** (`app.SWEEP_HINT_BAD = app.SWEEP_HINT_BAD * 12`, matching
`pr80-round2-review.md` verbatim), re-running only the rewritten test:
```
FAIL: ... (scale='90', band='bad')
  AssertionError: 488 not less than or equal to 407
FAIL: ... (scale='130', band='bad')
  AssertionError: 672 not less than or equal to 594
```
The **pane** assertion itself (`self.assertLessEqual(natural,
pane.winfo_height())`) now fails, at both scale steps — not merely the
row-height half, which was already known to fail before this round. The
`band='ink'` subTests in the same run stayed green (as they should — only
the BAD band's text was sabotaged).

Repeated with `app.SWEEP_HINT_MUTED = app.SWEEP_HINT_MUTED * 12` (leaving
`SWEEP_HINT_BAD` real): the mirror result —
```
FAIL: ... (scale='90', band='ink')
  AssertionError: 488 not less than or equal to 407
FAIL: ... (scale='130', band='ink')
  AssertionError: 672 not less than or equal to 594
```
— confirming the INK band's own coverage is equally load-bearing, not
just present.

**Confirmed against the real, unsabotaged code**, both constants at their
real values, the full rewritten test passes cleanly at both scale steps
and both bands (see "Full suite result" below) — the new measure is
discriminating in both directions, not merely stricter.

**Underlying numbers, read directly** (not sabotaged), confirming why the
old measure could never have caught this: real code, scale 90%, BAD band
— `pane.winfo_height()` (avail) 407px; the old allocated-span `natural`
332px; the new required-sum `natural` also 332px (no clipping occurring
on real code, so the two measures agree exactly when nothing is actually
overflowing). Under the reviewer's 12x `SWEEP_HINT_BAD` sabotage at the
same scale: allocated-span `natural` stayed at 406px (still `<=` 407,
still "passing"), while the Eating card's canvas was independently
confirmed squeezed to 56px allocated vs. 125px still-required — the
required-sum `natural` for the same scenario is 475px, correctly `>`
407px.

### Investigate, don't fix: the three pre-existing sibling floor tests
Sabotaged in-process (never touching a repo file) by monkeypatching
`app.Row.__init__` so the Eating card's "Eat every" row is built with an
artificially long hint string (`"SABOTAGE " * 80`), inflating that row's
`winfo_reqheight()` well past what the pane can actually hold at the
tightest scale steps these three tests exercise. This targets the Eating
card specifically because these three tests build one long before the
sweep-hint feature exists in their own scenario — `SWEEP_HINT_BAD`/
`_MUTED` never enter their code path at all (none of the three touches
the jitter row's band state), so sabotaging those two constants would not
have reached them; a different lever was needed to actually inflate this
pane's own required content for their specific test setup.

Direct, side-by-side measurement (scratchpad probe, not committed) at
each of the three tests' own exact widget-construction sequence:

| Test | allocated `natural` | avail | required `natural` | Verdict on the old (allocated) assertion |
|---|---|---|---|---|
| `test_tallest_pane_still_fits_at_the_floor` | 454 | 455 | 932 | passes (blind) |
| `test_tallest_pane_still_fits_at_the_floor_reverse_order` | 454 | 455 | 932 | passes (blind) |
| `test_tallest_pane_still_fits_at_worst_case_compound_scale` | 520 | 521 | 610 | passes (blind) |

Then ran the actual three tests, unmodified, under this same sabotage via
`unittest`:
```
test_tallest_pane_still_fits_at_the_floor ... ok
test_tallest_pane_still_fits_at_the_floor_reverse_order ... FAIL
  AssertionError: 0 is not true   (self.assertTrue(bottom.winfo_ismapped()))
test_tallest_pane_still_fits_at_worst_case_compound_scale ... ok
```
**Result: all three share the identical blind spot the round-2 review
found in the sweep-hint floor test.** Each one's own `natural <=
pane.winfo_height()` assertion silently passes under a sabotage that
provably causes ~470-480px of real, required content to be squeezed into
~455-521px of available room — the allocated-span measurement always
comes in at (or one pixel under) the pane's available height, by
construction of how Tk's packer clips an overflowing child, never above
it. `..._reverse_order` is the one test of the three that happens to
*fail* under this sabotage, but not because its height assertion caught
anything: it fails on its own separate, unrelated
`self.assertTrue(bottom.winfo_ismapped())` check (the bottom spacer gets
unmapped entirely once the packer runs out of room), which the other two
tests don't have. Strip that one line out mentally and all three would go
green under a sabotage that clips ~200-475px of real content. Not
changed, per the dispatch's instruction — left exactly as written, for
the orchestrator to ticket.

### Full suite result (this session, final state)
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 414 tests in 73.176s

OK (skipped=10)
```
Same count as round 2 (414 = round 2's own total; this round rewrote one
existing test in place rather than adding a new one). Same skip count.
Pre-existing `ResourceWarning`s from `tests/test_updater.py`'s unclosed
temp files are unchanged from prior rounds' own notes.

```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.WindowMinimumHeight -v
Ran 6 tests in 0.732s

OK
```

### `README.md`
`README.md:75`'s Random-jitter row sentence previously read (translated)
"...gives way to a warning below 650 ms, and becomes bold from 550 ms..."
— implying only the <550 ms band is bold. Live-probed in round 2 (and
re-confirmed unchanged this round): the 550-649 ms band is already
`{Segoe UI} 8 bold`, identical weight to the <550 ms band; only the
no-band static text is regular weight. Reworded to: "...weicht dieser
Text einer fett hervorgehobenen Warnung, sobald Intervall minus Jitter
unter 650 ms sinkt, und wechselt ab 550 ms zusätzlich auf eine
auffälligere Farbe, weil dann der Java-Sword-Sweep wahrscheinlich
ausbleibt." — bold starts at 650 ms, and 550 ms is now described as an
additional colour escalation, matching the actual `INK`/`BAD` behavior.

### Verification of scope
```
git status --short
 M README.md
 M docs/test-review.md
 M tests/test_ui.py
```
`docs/test-review.md`'s modification is the reviewer's own pre-existing
uncommitted "Round 2" section (present before this round started, per the
dispatch) — not edited by this round's own work, and not committed here.
Only `README.md` and `tests/test_ui.py` were touched, matching the
dispatch's must-fix/should-fix scope exactly; no scratch file was left in
the repo tree.
