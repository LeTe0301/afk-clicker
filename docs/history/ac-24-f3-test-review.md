# Test & Review: Icon rail — collapsing sidebar + rederived minimum width (story #24, Feature 3 of 5)

## Scope
Covers every acceptance criterion in `docs/spec.md` for this feature: the app not
launching pre-collapsed, minsize/default-launch decoupling, threshold-crossing
collapse/re-expand with no hysteresis, click-navigation while collapsed,
debounced rebuild coalescing, the "Add current game" button surviving collapse,
and the full regression suite. Also independently verifies the developer's
documented deviation (the `event.widget is not self.root` guard in
`_on_root_resize`) and the two known trap classes (`docs/history` unmapped-widget
hazard, shared-display focus contention) called out for this story.

Diff reviewed: `git diff f20e21b..HEAD` in
`/home/dev/projects/.worktrees/afk-clicker/ac-24` (branch
`feature/ac-24/responsive-layout-icon-restyle`, HEAD `9696fb7`) —
`afk_clicker.py` +201/-16, `tests/test_ui.py` +125.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Fresh app: `_rail_collapsed is False`, `side.winfo_width() == SIDEBAR_W*s`, `root.winfo_width() == (SIDEBAR_W+1+CONTENT_W)*s` | Automated: `RailCollapse.test_rail_starts_expanded_at_default_launch` | pass | Ran `tests.test_ui.RailCollapse -v` on `:99`, DISPLAY set — `ok` |
| 2 | `root.minsize()[0]` is `(SIDEBAR_RAIL_W+1+CONTENT_W)*s`, strictly `<` default launch width | Automated: `RailCollapse.test_default_geometry_still_matches_the_old_expanded_minimum`, `WindowResize.test_minsize_reflects_the_collapsed_rail_floor` | pass | Same run, both `ok` |
| 3 | Resize below threshold → rail width `SIDEBAR_RAIL_W*s`, `_rail_collapsed is True`, `GameItem` text becomes single initial letter | Automated: `WindowResize.test_shrinking_past_the_threshold_collapses_the_rail`; manually re-verified initial-letter text via probe | pass | `ok`; probe `collapsed_update_dot.py` output: `badge letter text: S` for `SettingsItem`, and separately confirmed `GameItem` badge draws `profile["name"][:1].upper()` (read in `afk_clicker.py:1451`) |
| 4 | Real `<Button-1>` on a collapsed `GameItem`/`settings_item` still navigates | Automated: `RailCollapse.test_collapsed_items_still_navigate_by_click` | pass | `ok` |
| 5 | Resize back above threshold from collapsed → re-expands to `SIDEBAR_W*s`, no hysteresis | Automated: `WindowResize.test_growing_back_past_the_threshold_re_expands_the_rail` | pass | `ok` |
| 6 | Window grown well above threshold: rail stays `SIDEBAR_W*s`, content keeps growing | Automated: `WindowResize.test_rail_stays_at_expanded_width_on_a_wide_window` | pass | `ok` |
| 7 | Live-drag-style multi-crossing resize coalesces to ≤1 rebuild; a resize that never crosses triggers 0 | Automated: `RailCollapse.test_repeated_threshold_crossings_coalesce_to_one_rebuild`, `test_a_resize_that_never_crosses_the_threshold_triggers_no_rebuild`. Independently re-verified with a harsher 200-event flood (own probe, not just the shipped 5/3-event tests) | pass | `debounce_stress.py`: 200 oscillating synthetic events → `rebuild calls=1`; 50 non-crossing events → `rebuild calls=0`; exact-threshold width (`width == threshold`) stays expanded, confirming the documented strict-`<` edge case |
| 8 | Collapsed rail: "Add current game" still calls `add_current_game`, shorter `"+"` label | Automated: `RailCollapse.test_add_current_game_button_survives_collapse` | pass | `ok` |
| 9 | Full suite passes at baseline + new `RailCollapse` tests, no other test modified beyond what spec's "Test impact" required | Automated: `unittest discover -s tests -t .` on `:99`, run twice | pass | Run 1: `Ran 267 tests in 63.029s / OK (skipped=5)`; Run 2 (captured to log, checked exit code): `Ran 267 tests in 59.677s / OK (skipped=5)`, `EXIT=0` both times |
| 10 | Deviation claim: `root.bind("<Configure>", ...)` without a widget guard fires for every descendant, not just root, and crashes construction | Manual: stripped the guard line from a loaded copy of `afk_clicker.py` in-memory and constructed the app under Xvfb | pass (claim verified) | `no_guard_repro.py`: reproduces the exact crash — `AttributeError: 'AfkAutoclicker' object has no attribute 'click_ms'` inside `_persist()` via `_rebuild_ui()`; 115 of 116 `_on_root_resize` calls during construction had a non-root widget (e.g. `.!frame` width=689, `.!frame.!statuspill` width=260) |
| 11 | Guard, as shipped, suppresses the spurious calls without masking real ones | Manual: same construction with the guard intact, tracing `event.widget is self.root` per call | pass | `with_guard_check.py`: 115/116 calls are non-root and now correctly no-op; `_rail_collapsed` stays `False` after construction |
| 12 | `winfo_ismapped()` guard genuinely needed — first `_build_ui()` call is pre-mapped | Manual: instrumented `_build_ui` to record `winfo_ismapped()`/`winfo_width()` at entry | pass | `mapped_check.py`: first call shows `ismapped=0 width=1` (Tk's unmapped placeholder, exactly the hazard class the spec/design describe) — guard correctly leaves `_rail_collapsed` at `False` |
| 13 | `_rail_collapsed` re-derives correctly on a UI-scale change alone, with root's real pixel width never moving | Manual (no automated test exists for this scenario — see Spec coverage gap below) | pass | `scale_rederive.py`: fixed real window width `758px` unchanged before/after `_apply_ui_scale("130")` (`root.winfo_width()` logged identical, `758`), yet `_rail_collapsed` flips `False → True` purely from the re-derivation in `_build_ui()`, `side.winfo_width()` becomes `86px == SIDEBAR_RAIL_W*s130` |
| 14 | `_apply_minsize(grow_only=True)` never yanks an already-collapsed window back wide on a scale bump | Manual | pass | `collapsed_scale_bump.py`: window pinned at its 100%-scale collapsed floor (`539px`), scale bumped to 130% → window grows only to the new *rail-based* floor (`700px`), not to the full-expanded equivalent (`896px`); `_rail_collapsed` stays `True` |
| 15 | `SettingsItem` collapsed `has_update` corner-dot indicator (no text swap while collapsed) | Manual (no automated test exists — see Spec coverage gap below) | pass | `collapsed_update_dot.py`: no pending update → `update_dot` state `hidden`, letter stays `"S"`; after setting `_pending` and forcing a rebuild while still collapsed → `update_dot` state `normal`, letter still `"S"` (not text-swapped) |
| 16 | `GameItem` running/idle legibility while collapsed is carried by color, not text | Manual | pass | Same probe: idle dot fill `#3a4048` (`LINE`), running dot fill `#5cc9a4` (`OK`), selected text fill `#e4e7ea` (`INK`) — matches design's palette table exactly |
| 17 | G#23 independence: implementation does not assume a particular resolution | Code read + `implementation.md` cross-check | pass | `docs/design.md:221-229` states independence explicitly; `docs/implementation.md` "Known limitations" confirms G#23 was not re-opened and no pixel-exact macOS-scale check was performed, consistent with that stated independence — nothing in the diff hardcodes a `_dpi_s` assumption |

## Regression check
Full existing suite run twice: `DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .`
— `Ran 267 tests in ~60s` / `OK (skipped=5)`, exit 0 both times. No `Tcl_AsyncDelete`
flake observed in either run (pre-existing, out of scope either way). Targeted
run of `RailCollapse`, `WindowResize`, `UIScale` (20 tests) also green,
matching `docs/implementation.md`'s own claim exactly.

Geometry-assertion audit (the trap this story already paid for once, Feature
2): every new/changed `winfo_width()`/`winfo_rootx()`-style assertion in this
diff (`test_rail_stays_at_expanded_width_on_a_wide_window`,
`test_shrinking_past_the_threshold_collapses_the_rail`,
`test_growing_back_past_the_threshold_re_expands_the_rail`,
`test_rail_starts_expanded_at_default_launch`,
`test_default_geometry_still_matches_the_old_expanded_minimum`) queries
`self.ui.side`, `self.ui.content`, or `self.root` directly — all three are
always-visible top-level panes (never a widget inside a hidden/unmapped tab
pane the way Feature 2's Clicking-pane widgets were), and every query is
preceded by a real `root.geometry(...)` + `root.update()`. No unmapped-widget
risk found in this feature's new assertions. `itemcget()`-based assertions
(badge text, button label, update-dot state) don't depend on mapping at all.

No stress test against the shared-display focus-contention trap was needed —
this feature introduces no focus-dependent behavior, and no concurrent
Tk-process test was run.

## Spec coverage
All 9 formal acceptance-criteria checkboxes in `docs/spec.md` are implemented
and covered by an automated test that passed (criteria 1–8 above map directly;
criterion 9, the full-suite pass, is case 9).

Two items are in `docs/spec.md`'s "Edge cases" / design's own worked examples
but have **no automated regression test** in the diff, despite being real,
independently-verified behavior:
- The UI-scale-only re-derivation of `_rail_collapsed` (spec's own edge case:
  "A UI-scale change flips the derived state without root's raw pixel width
  ever moving"). Verified correct by hand (case 13) but nothing in
  `tests/test_ui.py` would catch a regression here — e.g. if a future change
  moved the re-derivation out of `_build_ui()` or made it read a stale `self.s`.
- `SettingsItem`'s collapsed `has_update` corner-dot behavior (case 15) — no
  test exercises `has_update=True` combined with `collapsed=True`, despite this
  being an explicit `docs/implementation.md` callout ("item 7" of design's
  checklist) as needing special `_paint()` handling distinct from `GameItem`.

Both are should-fix follow-ups, not blockers — I independently verified both
are implemented correctly, so there's no known-broken behavior shipping, only
a coverage gap that would let a future regression through silently.

## Findings (most severe first)

### 1. No automated test for `SettingsItem`'s collapsed `has_update` corner dot — should-fix
- File: `tests/test_ui.py` (no such test exists); implementation at `afk_clicker.py:1538-1548`
- Issue: this is the one place `_paint()` needed real branching for collapsed
  mode (per `docs/implementation.md`'s own note), and it's also the one
  interaction point between two features (updates + rail collapse) most likely
  to regress independently of each other later. Nothing in the suite currently
  pins `update_dot`'s `state` to `has_update` while collapsed.
- Failure scenario: a future edit to `check_update()`/`_offer_update()` or to
  `SettingsItem._paint()`'s collapsed branch could silently stop showing (or
  incorrectly keep showing) the update indicator while the rail is collapsed,
  and the full suite would stay green.

### 2. No automated test for `_rail_collapsed` re-derivation on a pure UI-scale change — should-fix
- File: `tests/test_ui.py` (no such test exists); implementation at `afk_clicker.py:1815-1826` (the `_build_ui()` top-of-function re-derivation)
- Issue: `docs/spec.md`'s own "Edge cases" section calls this out by name as a
  case Writer 1 exists specifically to handle, distinct from the `<Configure>`
  handler. It's covered by neither `RailCollapse` nor `UIScale`'s existing tests
  — `UIScale`'s tests never resize the window to sit between two scale steps'
  thresholds, and `RailCollapse`'s tests never change `self.s`.
- Failure scenario: a future refactor that moved this re-derivation to only
  fire from `_on_root_resize` (removing the `_build_ui()`-level check) would
  pass every existing test yet silently break exactly this case — a user on
  a narrow-ish window picking a bigger UI-scale step would see the rail fail
  to collapse even though the badge/content math already assumes it has.

No must-fix findings. The central deviation (the `event.widget is not
self.root` guard) is a correct, necessary fix to a real bug in both
`docs/spec.md` and `docs/design.md`'s proposed code, verified by direct
crash reproduction with the guard removed and confirmed-clean behavior with
it present — this is a case where the spec/design need correcting, not the
implementation. No security issues (no external input, no new I/O). No
scope creep — the diff matches `docs/spec.md`'s "Affected areas" section
line for line, and `_apply_minsize()`'s change is exactly the two lines the
spec called for.

## Follow-ups (non-blocking)
- Add a `RailCollapse` test that resizes to a fixed width sitting strictly
  between two UI-scale steps' thresholds, applies `_apply_ui_scale()` across
  that boundary, and asserts `_rail_collapsed` flips with no `<Configure>`
  involved (mirrors this review's `scale_rederive.py` probe).
- Add a test combining `has_update=True` with a collapsed rebuild, asserting
  `settings_item.update_dot`'s Tk `state` toggles correctly and the badge
  letter never text-swaps (mirrors this review's `collapsed_update_dot.py`
  probe).
- `docs/spec.md` and `docs/design.md` should both be corrected to include the
  `event.widget is not self.root` guard in their proposed `_on_root_resize`
  code — as written, both would ship the crash this feature's implementation
  had to independently discover and fix. This is a correction to the
  upstream docs, not a change requested of this diff.

## Overall verdict
Approve with follow-ups.
