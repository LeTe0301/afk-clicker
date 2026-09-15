# Test & Review: Pane content sits directly under its tab bar (G#37 / GH#66)

## Scope
Covers all acceptance criteria in `docs/spec.md`: `FILL_TOP_SHARE` 0.5 → 0.0
(`afk_clicker.py:221`) so every pane's content hugs its tab bar instead of
centering, with the leftover collecting in the bottom spacer; the
`VerticalFill` test-class assertion updates in `tests/test_ui.py` that go
with it; and the developer's flagged deviation on the two floor-case tests.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Hotkey (tall window): top spacer at 1px floor, bottom holds the leftover | automated + manual | pass | `test_short_tab_gains_margin_on_a_tall_window` green; `min_hotkey.png`/`min130_hotkey.png` visually confirm |
| 2 | Same top-hugging on Clicking, Settings→Appearance, Settings→Updates | manual (screenshots, all 4 panes, floor + tall window) | pass | developer's `large_*`/`min_*` shots (all 8 reviewed) + my own `min130_*` shots (all 4 panes, most-crowded 130% scale) — no pane shows a dead band above its content |
| 3 | Floor window: `natural <= winfo_height()`, both spacers stay mapped | automated + manual re-derivation | pass | `WindowMinimumHeight` (4 tests, unmodified) green; `VerticalFill` floor tests green; I independently measured the live app at the floor: `natural=383, avail=455, extra=72, top=1, bottom=71` |
| 4 | Live resize: spacer heights update continuously, no `_rebuild_ui()` call | automated | pass | `test_live_resize_drag_updates_margin_without_a_rebuild`, unmodified, green |
| 5 | Full suite passes, only `VerticalFill` assertions changed | automated | pass | `git diff --stat` confirms only `afk_clicker.py` (1 constant+comment) and `tests/test_ui.py` (`VerticalFill` class only) touched; full suite `314 tests, OK, skipped=10` |
| 6 | Screenshots at floor + tall window, all 4 panes, dead band below not above | manual | pass | see #2 |
| 7 (sabotage) | `FILL_TOP_SHARE=0.5` must turn top-alignment tests red | manual sabotage | pass | reverting to 0.5 fails exactly 3 tests: both floor-case tests (`36 not <= 1`) and `test_short_tab_gains_margin...` (`314 not <= 1`) — the other `VerticalFill` tests correctly stay green (directional, not split-specific), matching implementation.md's own claim |
| 8 (sabotage) | Reintroducing the `_select()` `if self._content_tab == "clicking":` → `if True:` desync bug must fail the rewritten hidden-tab test | manual sabotage | pass | `test_hidden_tabs_own_margin_does_not_desync_the_visible_one` fails (`'clicking' unexpectedly found in ['clicking']`) — this is the actual guard at `afk_clicker.py:2936`, correctly re-pointed after the +9-line shift from the `FILL_TOP_SHARE` comment expansion |
| 9 (sabotage) | A sabotage that genuinely clips a row at the floor must fail | manual sabotage | pass | shrinking `WINDOW_MIN_H` to 500 fails both reverse-order tests (`bottom` unmapped) via the untouched mapped-check; shrinking to 400 fails even the non-reverse floor test via the untouched sum invariant (`2 != 7`) |
| 10 (sabotage) | Reading `top` instead of `bottom` in `test_switching_tabs_recomputes_each_panes_own_margin` must fail under `FILL_TOP_SHARE=0.0` | manual sabotage | pass | `1 not greater than 1` — confirms the top→bottom swap is load-bearing, not cosmetic |
| 11 | No other code encodes centering | grep | pass | `FILL_TOP_SHARE` used at exactly one site (`afk_clicker.py:1645`); no other `top_h`/spacer-split logic anywhere |
| 12 | Edited tests never read a hidden pane's geometry (Windows 0/1 vs. stale-X11 hazard) | code read | pass | every geometry-reading `VerticalFill` test only reads spacers while that pane is the active tab; the one test that used to infer state from a hidden pane's geometry (`test_hidden_tabs_own_margin_does_not_desync_the_visible_one`) was rewritten to spy on `_request_pane_fill` instead, precisely to avoid this |

All sabotage checks were performed on the actual `afk_clicker.py`/`tests/test_ui.py` working tree and reverted immediately after (confirmed via `git diff` byte-identical to the pre-sabotage diff each time, and a final full-suite green run after the last revert).

## Regression check
Full suite: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .`
→ `Ran 314 tests ... OK (skipped=10)`, run at the start of this pass and again
after all sabotage/revert cycles — identical result both times. Also ran
`WindowMinimumHeight`/`FillPaneOverflow`/`VerticalFill` together 3x
back-to-back for determinism (14/14 green every run).

## Defects found
None. Testing pass is clean — proceeding to the review pass.

---

## Spec coverage
All four acceptance criteria checkboxes in `docs/spec.md` are implemented and
tested (see table above, cases 1-6). The "Open questions" section's
`FILL_TOP_SHARE=0.0 vs. small breathing-room share` question was pre-decided
by the task brief (ux-designer skipped, `FILL_TOP_SHARE=0.0` chosen) — not a
gap, a deliberate scope decision made above this pipeline stage.

## The floor-test deviation — scrutinized

**Conclusion: the deviation is correct, well-verified, and not a sign of a
new defect.** Independently re-derived rather than trusted:

- Recomputed `_fill_pane()`'s clamp arithmetic (`afk_clicker.py:1645-1667`)
  by hand for `extra=0` and `extra=1`: both converge to `top_h=1, bottom_h=0`
  regardless of `FILL_TOP_SHARE`, exactly matching `docs/spec.md`'s own
  worked proof. **The spec's proof is not wrong** — it correctly describes
  what happens at those two specific boundary values.
- The spec's mistake is scope, not arithmetic: `extra ∈ {0,1}` is the
  Windows-CI-tight boundary `WINDOW_MIN_H=620` was explicitly tuned to leave
  ~61px of margin against (`afk_clicker.py:163-188`'s own comment, itself
  derived from `docs/history/ac-28-implementation.md` round 4's live Windows
  trace: `natural=367, avail=368`). That same comment already documents that
  Linux's substituted font "never got closer than ~10px" to that boundary at
  the old `WINDOW_MIN_H=560`; moving the floor up to `620` (+60px) predicts
  almost exactly the ~70px this dev box now sits at.
- I independently measured the live app at the floor (not trusted from
  either doc): `natural=383, avail=455, extra=72, top=1, bottom=71` —
  matches the developer's reported "~70-72px" almost exactly, and is fully
  consistent with `WINDOW_MIN_H`'s own pre-existing, unrelated documentation
  of this exact cross-platform font-metric gap. **This is expected, already
  documented platform variance, not a new problem this ticket introduced.**
- The actual "no clipping" invariant — `assertEqual(top+bottom, max(2,
  extra))`, the same sum check `docs/history/ac-28-implementation.md`'s
  round 2/4 built and hardened across three platforms — is **completely
  unchanged** by this diff in both floor tests. Sabotage (case 9 above)
  confirms it's still load-bearing: shrinking `WINDOW_MIN_H` far enough
  produces a real `2 != 7` failure.
- The two new assertions the developer added (`top<=1`, `bottom>=extra-1`)
  are a correct, additional check of the `FILL_TOP_SHARE=0.0` split
  specifically, and they degrade safely rather than becoming a
  platform-specific false-failure risk: at the Windows/macOS `extra∈{0,1}`
  boundary they collapse to trivially-true statements (`bottom>=-1` or
  `bottom>=0`, always true; `top<=1` holds because the clamp forces `top` to
  the floor there regardless of share) — confirmed by hand from the same
  clamp arithmetic above — while providing real, sabotage-confirmed signal
  at this platform's actual ~70px floor slack.

Nothing here should route back to the developer — the rename, the
assertion swap, and the "no logic change needed" bucket being wrong for
this one platform are all correctly diagnosed and fixed, in the same style
as the rest of the diff.

## Findings (most severe first)

None at must-fix or should-fix severity.

### Nit: pre-existing stale line reference, unrelated to this diff
- File: `afk_clicker.py:1133` (comment: "the swap-script Popen call
  (afk_clicker.py:1528-1529)")
- This reference was already wrong on `main` before this branch (confirmed
  via `git show main:afk_clicker.py`) — the actual `Popen` calls are near
  line 967/973 on `main`. This diff's own +9-line insertion into the
  `FILL_TOP_SHARE` comment shifts it further out of date, but did not cause
  it. Out of scope for this ticket (minimal-diff discipline); flagging only
  as an FYI for whoever next touches that neighborhood, not a follow-up
  ticket.

## Follow-ups (non-blocking)
- Already flagged in `docs/spec.md`'s own "Open questions": whether to
  remove the now-structurally-inert top spacer as a separate, low-urgency
  cleanup ticket. Reviewed and endorsed as correctly out of scope here — the
  two-spacer shape is threaded through ~15 test call sites and five rounds
  of cross-platform hardening (`docs/history/ac-28-implementation.md`);
  reworking it now for a purely cosmetic gain would reopen that surface for
  no functional benefit, squarely the shared-conventions "don't
  rename/re-scope pre-existing hardened code as part of a feature" case.
- G#13's Macros branch and G#38 (UI scale following window size) both
  already correctly noted as out of scope in `docs/spec.md`'s non-goals.

## Overall verdict
**Approve.**
