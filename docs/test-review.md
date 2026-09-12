# Test & Review: Window minimum height is sized for the pre-tab layout (G#28 / GH#48)

## Scope
Testing pass against `docs/spec.md`'s acceptance criteria for the
`afk_clicker.py` diff between `65478aa` (base) and `dd94193` (HEAD, branch
`feature/ac-28/window-minimum-height`): `WINDOW_MIN_H = 560` replacing the
bare `690` literal in `_apply_minsize()`, plus the four new
`WindowMinimumHeight` tests and the settling-loop change to
`VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping`.
The review pass was not reached — see verdict.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | `app.WINDOW_MIN_H < 690` | automated | pass | `tests/test_ui.py::WindowMinimumHeight::test_minimum_height_shrunk_from_the_pre_tab_split_floor`, 5 consecutive runs, all OK |
| 2 | Fresh app: `minsize()[1] == winfo_height() == int(WINDOW_MIN_H * s)` | automated | pass | `tests/test_ui.py::WindowMinimumHeight::test_default_launch_height_equals_the_floor`, 5 consecutive runs |
| 3 | Tallest pane (Minecraft/Clicking) fits at the floor, `natural <= winfo_height()`, native scale | automated | pass (as measured) — but see defect below for what this invariant does *not* catch | `tests/test_ui.py::WindowMinimumHeight::test_tallest_pane_still_fits_at_the_floor`, 5 consecutive runs |
| 4 | Same, at worst-case compound scale `s≈0.675` | automated | pass | `tests/test_ui.py::WindowMinimumHeight::test_tallest_pane_still_fits_at_worst_case_compound_scale`, 5 consecutive runs |
| 5 | Full suite passes at 285 baseline + 4 new, no unlisted test changed | automated | pass | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` → `Ran 289 tests ... OK (skipped=5)`, run twice |
| 6 | `test_floor_case_still_splits_symmetrically_with_no_clipping` still asserts the same thing, now via a settling loop | automated | pass, and the loop fails closed | 5 consecutive runs green; independently sabotaged `_fill_pane()`'s split math in a scratch copy and confirmed the loop does *not* converge and the final assertion fails (see "Sabotage check" below) |
| 7 | Reentrancy gap behind the settling loop is genuinely pre-existing at the old `690` floor, not introduced by this diff | manual/scripted probe | pass (claim holds, narrowly) | see "Independent verification of the developer's claim" below |
| 8 | **A real user, at the app's own default (floor) window size, on the Minecraft profile + Clicking tab, does not see visibly wrong/clipped layout** | manual, live app, screenshots | **FAIL** | see Defect 1 below |

## Regression check
Full suite: `DISPLAY=:99 /tmp/.../scratchpad/venv/bin/python -m unittest discover -s tests -t .` — `Ran 289 tests in 57.2s, OK (skipped=5)`, run twice back to back, no crash, matches the 285-baseline + 4-new expectation. `WindowMinimumHeight` class and the modified `VerticalFill` test each additionally run 5x standalone for determinism — all green.

## Independent verification of the developer's claim (item 1 of the brief)
Wrote a throwaway probe (`/tmp/claude-1000/.../scratchpad/probe_old_floor_reentrancy2.py` and `probe_new_floor.py`) that reproduces the un-looped body of `test_floor_case_still_splits_symmetrically_with_no_clipping` directly against the real `afk_clicker` module, monkeypatching `app.WINDOW_MIN_H` before construction:

- At `WINDOW_MIN_H = 690` (old floor), `_select("minecraft")` → `_set_content_tab("clicking")` → one `root.update()`: **0/8 failures**, deterministic (`top=72, bottom=73, extra=145`).
- At `WINDOW_MIN_H = 560` (this diff, unmodified), same call sequence: **8/8 failures**, deterministic (`top=49, bottom=1, extra=49`).

Since the diff changes *only* the `WINDOW_MIN_H` numeric literal — confirmed via `git diff 65478aa..HEAD -- afk_clicker.py`, no line inside `_fill_pane()`, `_select()`, or `_set_content_tab()` changed — this difference in outcome cannot be a new code path; it is the same pre-existing convergence algorithm behaving differently because the leftover-space budget (`extra`) shrank from ~145px to ~49px. The developer's claim that the mechanism itself is pre-existing, not introduced by this diff, holds. What does **not** hold is the developer's downstream characterization of severity — see Defect 1.

## Sabotage check (item 3 of the brief)
Copied `afk_clicker.py` into the scratchpad (never the tracked file — confirmed `git status --short` clean before and after) and injected `top_h = int(extra * FILL_TOP_SHARE) + 30` into `_fill_pane()`. Re-ran the exact settling-loop body from the updated test against this sabotaged copy (`/tmp/claude-1000/.../scratchpad/probe_sabotage_check.py`): the loop runs all 10 iterations without ever reaching `in_sync`, and the final assertion correctly fails. The settling-loop *technique* is sound and does fail closed.

## Defects found

### Defect 1: The Eating card's "Hold for" row is genuinely clipped at the new floor, in ordinary usage, and does not self-correct — contradicting the implementation doc's "very likely invisible" / "self-heals within a fraction of a second" claim
- **Severity: blocking.** This is exactly the acceptance-criteria scenario the spec cares about (no scrolling anywhere ⇒ clipped content is unreachable content), and it is reachable without any contrived setup.
- **Repro (order A — matches the app's own new/updated tests exactly, i.e. `_select("minecraft")` then `_set_content_tab("clicking")`)**:
  1. Launch the app fresh (window opens at its own default/floor size, `WINDOW_MIN_H = 560`).
  2. Select the Minecraft profile in the sidebar.
  3. Click the "Clicking" tab.
  4. Wait — no further interaction.
  - **Observed**: `clicking_pane`'s spacers land at `top=49px, bottom=1px` (should split ~evenly, ~5px/5px, `extra=49`) and stay there indefinitely — confirmed unchanged after 100 real `root.update()` cycles over ~2 seconds of continuous event-loop servicing (`/tmp/claude-1000/.../scratchpad/probe_screenshot_settled.py`, live screenshot `settled_2s_broken.png` and `order1_select_then_tab_settled.png`). The "Hold for" input row is rendered right at the bottom edge of the window with essentially no margin, one row of vertical breathing room away from actually being cut — this order alone is a visible defect (heavy, permanent top-heavy asymmetry violating feature 4's own centering contract) even before the second, worse repro below.
- **Repro (order B — equally ordinary: click "Clicking" tab first while still on the default Global profile, then select Minecraft — this is the branch inside `_select()`, `afk_clicker.py:2595-2599`, that calls `_fill_pane()` synchronously right after packing `eat_card`)**:
  1. Launch the app fresh.
  2. Click the "Clicking" tab (still on Global — no Eating section).
  3. Select the Minecraft profile in the sidebar.
  4. Wait — no further interaction.
  - **Observed**: `top=48, bottom=96` — `top + bottom = 144`, which is **triple** the actual leftover space (`extra=48`). Tk's packer cannot fit `48(top) + 201(canvas) + 21(frame) + 103(canvas) + 96(bottom)=469px` of children into the pane's fixed 393px (`pack_propagate(False)`), so it **unmaps the bottom spacer entirely** (`bottom.winfo_ismapped() == False`, confirmed via `/tmp/claude-1000/.../scratchpad/probe_diagnose_clip.py`) and the Eating card's own canvas is left stuck at a partial height (103px instead of its converged ~141px). Screenshot `realistic_broken_split.png` / `settled_2s_broken.png`: the "Hold for" row's input box is visibly sliced off at the very bottom edge of the window — no label, no unit text visible, box itself truncated. Confirmed stable (not a mid-paint artifact) after 2 full real seconds of continuous `root.update()` churn.
  - This state is **not transient**: it persists until an *additional* pane-triggering interaction happens (e.g., switching to Hotkey and back to Clicking twice — confirmed convergence to `top=5,bottom=5,natural=383` only after 2-3 more tab cycles in `/tmp/claude-1000/.../scratchpad/probe_persistence.py`, or repeated explicit `_fill_pane()` calls — 4-5 of them, `/tmp/claude-1000/.../scratchpad/probe_realistic_order_settling.py`). A real user has no reason to know that resizing the window or cycling tabs twice will fix a clipped control they're looking at right now.
- **Comparison at the old `690` floor, same order B**: `top=81, bottom=64` — asymmetric (off by 17px, itself a minor pre-existing imprecision the original suite never caught, since its own tests only ever exercised order A) but `sum == extra` exactly (145 == 145), no overflow, nothing unmapped, no clipping. The much larger old margin absorbed the same underlying imprecision without visible harm; the new, smaller margin turns it into real content clipping. This is precisely the "was tolerable, now surfaces" risk the task brief flagged, and it is not hypothetical — it reproduces every time.
- **Expected**: per the spec's own binding constraint ("no scrolling anywhere... clipped content is unreachable content, not merely tight"), the tallest pane's content must be fully visible at the floor regardless of the order in which the user reaches Minecraft + Clicking.
- **Actual**: content is genuinely clipped (order B) or left in a heavily lopsided, permanently-wrong margin state (order A), in the exact scenario the acceptance criteria target, via ordinary clicking, with no self-correction.
- **Root cause, as far as this pass traced it (not fully bottomed out — that's the developer's job)**: `_fill_pane()`'s explicit calls from `_select()`/`_set_content_tab()` (`afk_clicker.py:2510`, `:2597`) run before the Eating `card()`'s own `<Configure>`-triggered `_redraw()` (`afk_clicker.py:1383-1408`) has finished growing the card to its real `inner.winfo_reqheight()`. Nothing subsequently re-triggers `_fill_pane()` for that pane once the card *does* finish growing, because a child's internal growth inside a `pack_propagate(False)` pane produces no `<Configure>` on the pane itself (the same "Empirical grounding #2" the code's own comments already document for a different call site). The fix belongs in the app (e.g., the card's own `_redraw()` re-triggering `_fill_pane()` for its owning pane after it finishes growing, or `_select()`/`_set_content_tab()` deferring their explicit call past the card's settle), not in the test suite.
- **Why this blocks**: the implementation doc's "Deviations from spec" section explicitly downgrades this to a test-harness artifact ("very likely invisible in the live, running app," "self-corrects within a fraction of a second," "not raised as a blocker here") and defers the real fix to an unfiled backlog item. Live-app measurement directly contradicts both of those claims: this pass observed 2+ real seconds of continuous event-loop servicing with zero self-correction, in both plausible click orders, with one of the two producing an actual clipped control — not decorative asymmetry.

## Overall verdict
**Blocked.** Stop here per process — no review pass was performed since the testing pass surfaced a blocking defect. Route back to the developer.

### Must-fix before re-review
1. Fix the underlying `_fill_pane()`/card-growth reentrancy at the app level (not test-only) so the tallest pane (Minecraft + Clicking, at or near `WINDOW_MIN_H`) never leaves the Eating card's "Hold for" row clipped or the pane's spacers unmapped, regardless of whether the user reaches that state via `_select()` then `_set_content_tab()` or the reverse order. A concrete direction: have `card()`'s `_redraw()` notify/re-trigger `_fill_pane()` for its owning pane (via a small callback or a pane-level `<Configure>`-equivalent hook) once it has actually settled, rather than relying on however many recursive `update_idletasks()` passes happen to land inside one synchronous call.
2. Once fixed, extend the automated coverage to cover **both** orders (`_select` then `_set_content_tab`, and vice versa) for the Minecraft/Clicking case at the floor — the current four `WindowMinimumHeight` tests and the updated `VerticalFill` test only exercise order A, which is why this shipped without being caught.
3. Re-derive/re-confirm the settling loop is no longer needed once the app-level fix lands (a real fix should make `VerticalFill.test_floor_case_still_splits_symmetrically_with_no_clipping` converge in the very first `_fill_pane()` call again, same as it did at the old floor) — if the loop is still needed after the app-level fix, that itself is a sign the fix didn't address the actual race.

### Not blocking, but worth the developer's attention when back in this code
- `WINDOW_MIN_H = 560`'s own derivation and margin are sound as far as this pass could independently check (native scale and the `s≈0.675` compound worst case both hold with the four new tests green across 5 runs each) — no change needed to the constant itself, only to the settling defect above.
- The floor/default height coupling reasoning in `docs/spec.md` ("Why height doesn't get the width axis's floor/default split") was not re-litigated since it wasn't in question — no issue found there.

## Evidence index (scratchpad only, nothing added to the repo tree)
- `probe_old_floor_reentrancy2.py`, `probe_new_floor.py` — order A determinism, old vs. new floor
- `probe_realistic_order.py`, `probe_realistic_order_oldfloor.py`, `probe_realistic_order_settling.py` — order B, old vs. new floor, and manual re-convergence
- `probe_diagnose_clip.py` — per-widget mapped/unmapped/geometry dump proving the pack overflow
- `probe_persistence.py` — convergence behavior across repeated tab cycles and a manual resize
- `probe_sabotage_check.py` + `afk_clicker_sabotaged.py` — settling-loop technique fails closed
- `screenshot_probe.py`, `screenshot_probe2.py`, `probe_screenshot_realistic.py`, `probe_screenshot_settled.py`, `probe_screenshot_order1.py` — live-app screenshot capture scripts
- Screenshots: `realistic_broken_split.png`, `realistic_after_tab_cycle.png`, `settled_2s_broken.png`, `order1_select_then_tab_settled.png`
- All under `/tmp/claude-1000/-home-dev-projects-afk-clicker/55c5887c-a42c-438d-b08e-f1ad54920e0e/scratchpad/`; tracked working tree confirmed clean (`git status --short`) throughout.
