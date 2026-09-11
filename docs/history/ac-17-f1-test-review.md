# Test & Review: Theme data + Quartz shape language (Story #17, Feature 1)

Worktree: `/home/dev/projects/.worktrees/afk-clicker/ac-17`, branch
`feature/ac-17/themes-follow-system-settings-tab`, on top of `main` at
`67c2eee`, reviewed against `git diff main` (`afk_clicker.py` +164/-39,
`tests/test_ui.py` +302, both uncommitted). This is round 4 of review — rounds
1-3 already fixed visual defects the orchestrator caught in screenshots
(smoothed-spline pills, Eating segmented-control clipping/centering, rounded
canvases not taking their parent's `bg`). This pass tests and reviews the
current, post-round-3 state.

## Scope

Every acceptance criterion in `docs/spec.md` for Feature 1: the `THEMES`
dict (Deepslate + Quartz, dark-only active at runtime), `PILL_R`/`CARD_R`
shape constants, the pill-shaped `Button`/`Segmented`/`StatusPill`, the
canvas-based borderless `card()`, `GameItem`'s radius, `Button._colors`'
themed primary ink/hover, and `CARD_INNER_W`'s recomputation. Also the
round-2/round-3 fixes (`round_rect`'s real-arc geometry, parent-derived
canvas `bg`) and the `#14` resize/`NumBoxFocus` non-regression contracts
called out in the dispatch.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | `THEMES["dark"]`/`["light"]` hold all 11 keys, exact ticket hex; `ACCENT_INK` matches mock | Automated (`Themes` class) + direct diff read of literal hex | pass | `tests/test_ui.py::Themes`, all subtests green in full run below; diff hex matches `docs/spec.md` Decision 1 literals exactly |
| 2 | Derived module globals (`BG`…`BAD`) equal `THEMES["dark"]` | Automated (`Themes.test_module_globals_still_ship_dark_only`) | pass | full suite run |
| 3 | `Button`/`Segmented` (track+pill)/`StatusPill` radius == `PILL_R*s`; `card()`/`GameItem` == `CARD_R*s` | Automated (`PillAndCardRadii`) + my own monkeypatch probe | pass | `reviewer_probe4.py`, full suite run |
| 4 | `card()` shell is a borderless `tk.Canvas` (`highlightthickness==0`, shape `outline==""`), returns a `Frame` | Automated (`CardShell`) + direct inspection | pass | full suite run |
| 5 | Eating card `.pack()`/`.pack_forget()` non-regression on the new Canvas shell | Automated (`EatingCardCanvas`) + manual `_select` toggling via `reviewer_probe.py` pattern | pass | full suite run |
| 6 | Card redraws on `<Configure>`, shape bbox tracks `winfo_width()`/`height()` | Automated (`CardShell.test_shell_redraws_when_the_content_pane_widens`, `CardResize`) + my own 5-step grow/shrink probe on the real hotkey card | pass | `reviewer_resize.py` output: item count stable at 2 across `1000x800→1200x900→700x750→500x600→1000x800`, bbox within 2px of `winfo_width()` at every step |
| 7 | `CARD_INNER_W == CONTENT_W - 2*CONTENT_PAD - 2*CARD_R == 396` | Automated (`Themes.test_card_inner_w_has_no_border_allowance_left`) | pass — but see Finding 1 | full suite run; **note:** `docs/spec.md`'s own Acceptance-criteria bullet still says `428` (pre-round-2 formula) |
| 8 | Primary `Button` rest/hover fill+label use `ACCENT`/`ACCENT_HI`/`ACCENT_INK`, not the old hardcoded `"#ffd66b"`/`"#12131a"` | Automated (`PrimaryButtonTheme`) + my own real `event_generate("<Enter>")`/`<ButtonPress-1>`/`<Leave>` on `ui.apply_button` after `set_enabled(True)` | pass | `reviewer_primary.py`: rest `#e08a55`/`#1a0f08`, hover `#e59f73`/`#1a0f08`, after leave back to `#e08a55` — exact theme values |
| 9 | Secondary `Button`/`GameItem` hover/rest colors via real events | Manual, `event_generate` | pass | `reviewer_probe3.py`: secondary rest `#1c1f23`→hover `#262a30`; non-selected `GameItem` rest `#15171a` (BG) → hover `#1c1f23` (CARD) |
| 10 | `round_rect` draws a true capsule, not a smoothed approximation (r=h/2 case) | Automated (`test_round_rect_draws_a_true_capsule_not_a_smoothed_approximation`) + visual crop | pass | full suite run; `f1-pill-zoom.png` shows continuous, gap-free capsule outline |
| 11 | Every rounded canvas's `bg` matches its parent's `bg` (round-3 fix) | Automated (`RoundedCanvasBackgrounds`) + visual crop | pass | full suite run; `f1-sidebar-zoom.png` shows no square artifact behind either sidebar button |
| 12 | `round_rect` degenerate inputs: zero/negative width or height, `r` > half the smaller dimension, `r` negative, `r == 0` | Manual probe | pass, no exceptions | `reviewer_geom.py`: all 8 cases return a valid polygon item, no crash; vertex count is stable (90 pts) across all positive-r calls used by any real call site, so `coords()`-based animation (`Segmented`'s selection pill) never changes vertex count mid-slide |
| 13 | Selection-pill `coords()` animate correctly when the selected segment changes | Manual, real `var.set()` | pass | `reviewer_probe4.py`: `len(before)==len(after)==90`, coordinates actually move |
| 14 | Resize (grow, then shrink back to `minsize`), no stale shapes / item-count growth | Manual, 5-step `root.geometry()` sweep including a request below `minsize` | pass | `reviewer_resize.py` / `reviewer_resize2.py`: item count stable at 2 throughout; a request below `minsize` (`300x300`) is clamped by Tk itself before any widget ever sees it, confirmed via `winfo_geometry()` staying at `688x719` |
| 15 | `THEMES["light"]` defined but never read at runtime | Manual `grep` | pass | `grep -n "THEMES\[.light.\]" afk_clicker.py` → no hits outside its own definition |
| 16 | Default size, 1000×800, DPI scale 1.5, RUNNING/EATING states — visual QA | Manual, own screenshots (not reused from implementation.md) | pass | `rv-default.png`, `rv-wide.png`, `rv-eating.png`, `rv-running.png`, `rv-dpi15.png` — capsules and radius-12 cards correct in every mode; status pill dot/text/hint colors correct per state |
| 17 | `#14` contracts: `NumBoxFocus`, `WindowResize` non-regression | Automated, targeted run | pass | `python -m unittest tests.test_ui.NumBoxFocus tests.test_ui.WindowResize -v` → 13/13 ok |
| 18 | Round-8 revert check: arc-point `round_rect` reverted alone | Manual revert via Edit tool, run, restore, diff-verified identical | **fails exactly as claimed** | see "Revert checks" below |
| 19 | Round-8 revert check: parent-`bg` derivation reverted alone (all 5 sites) | Manual revert via Edit tool, run, restore, diff-verified identical | **fails exactly as claimed**, catching all 3 real mismatches | see "Revert checks" below |
| 20 | `NumBox` field shape untouched (spec non-goal) | Manual code read | pass | `afk_clicker.py:1177-1199`, not present in `git diff main` at all |

## Revert checks (Round 8, done in place with the Edit tool, diff-verified restored)

- **`round_rect` arc-points → old smoothed spline.** Reverted only the
  function body (kept `_arc_points`/`_round_rect_points` intact). Ran
  `PillAndCardRadii` (8 tests): 7 passed, exactly
  `test_round_rect_draws_a_true_capsule_not_a_smoothed_approximation` failed
  on `assertEqual(cv.itemcget(item, "smooth"), "0")` → `'true' != '0'`. Then
  restored the exact original text and confirmed `git diff main --
  afk_clicker.py` byte-identical to the pre-revert capture
  (`diff diff_app.patch diff_app_after.patch` → no output, "IDENTICAL").
- **Parent-`bg` derivation → old hardcoded `bg=`, all 5 sites
  (`Button`, `Segmented`, `StatusPill`, `card()`, `GameItem`), including
  restoring `StatusPill`'s pre-round-3 hardcoded `BG`.** Ran
  `RoundedCanvasBackgrounds`: failed with exactly the 3 real mismatches —
  `statuspill` (`#15171a` vs `#1c1f23`) and both sidebar buttons (`#1c1f23`
  vs `#15171a`) — matching implementation.md's own documented round-3 red
  run precisely. Restored all 5 sites and confirmed `git diff --stat`
  unchanged (164/-39, 302/+0) and `git status --porcelain` shows only the
  same 2 modified + 4 untracked `docs/*.md` files as at dispatch start.

## Regression check

Full existing suite, twice (once before any revert probe, once after
restoring): `DISPLAY=:99 .../scratchpad/venv/bin/python -m unittest
discover -s tests -t .`

- Run 1: **155 tests, OK, skipped=7** (5 are the pre-existing
  `AFK_SLOW_TESTS` gate on `test_chords_slow.Firing`, unrelated to this
  change; 2 are `test_updater.LiveRepository` hitting GitHub's rate limit).
- Run 2 (after all revert-and-restore probes, tree confirmed byte-identical
  to before): **155 tests, OK, skipped=5** — same suite, the 2 network tests
  happened to succeed this time, consistent with them being genuinely
  flaky/network-dependent rather than broken.

No test outside the new theme/shape classes needed to change; the pre-#17
baseline (97 tests before this feature, confirmed in `docs/implementation.md`)
is untouched.

Type-check/lint: none configured for this project (`.github/workflows/`
runs only the `unittest` matrix across `ubuntu-latest`/`windows-latest`/
`macos-latest`; no `mypy`/`flake8`/`ruff` step exists to run).

## Spec coverage

Every bullet in `docs/spec.md`'s "Acceptance criteria" section is
implemented and covered by an automated test, independently re-verified by
me this session (test cases 1-20 above). No acceptance criterion is
unimplemented or untested.

One traceability gap, not a code defect: `docs/spec.md`'s own acceptance
bullet for `CARD_INNER_W` still reads `428` — the pre-round-2 value. Round 2
correctly changed the formula to account for `body`'s own `CONTENT_PAD`
inset (a real clipping bug in the original spec's Decision 3, confirmed via
screenshots), landing on `396`, and updated the test to assert `396`
("a deliberate value change, not a loosened assertion" per
`docs/implementation.md`). The code and test are correct; `docs/spec.md`
itself was never edited to match. See Finding 1.

## Findings (most severe first)

### 1. `docs/spec.md`'s acceptance criterion for `CARD_INNER_W` is stale (428 vs. shipped/tested 396) — should-fix
- File: `docs/spec.md` (Acceptance criteria section, the `CARD_INNER_W` bullet) and Decision 3's prose
- Issue: Round 2 fixed a real bug in the spec's own Decision 3 formula (it
  didn't account for `body`'s `CONTENT_PAD` inset, causing the Eating
  segmented control to run off the card's right edge) and correctly
  recomputed `CARD_INNER_W` to `396`. The code (`afk_clicker.py:99-104`) and
  the test (`tests/test_ui.py`, `Themes.test_card_inner_w_has_no_border_allowance_left`)
  both correctly assert `396`. `docs/spec.md` was never updated to match —
  it still states the formula and value (`428`) that round 2 proved wrong.
- Failure scenario: a future engineer reads `docs/spec.md` in isolation
  (e.g., building Feature 2/3 against it) and either "fixes" the working
  `396` code back to the spec's stale `428` formula (reintroducing the
  clipping bug it fixed), or spends time reconciling a false spec/code
  mismatch that a one-line spec update would have prevented.

### 2. `docs/design.md`'s WCAG contrast table has materially wrong numbers — nit
- File: `docs/design.md`, "Contrast ratio verification" section (Deepslate table)
- Issue: I recomputed every stated pairing directly from the WCAG 2 relative-luminance
  formula against the literal hex values in the diff. Design.md's Deepslate
  numbers are all understated: `INK`/`CARD` stated `4.8:1`, actual `13.3:1`;
  `MUTED`/`CARD` stated `4.5:1` ("exactly at the line"), actual `5.76:1`;
  `ACCENT_INK`/`ACCENT` stated `5.2:1`, actual `7.11:1`. (Matches the
  orchestrator's own corrected figures given in the dispatch: 13.3/5.8/7.1.)
  No wrong number reached a code comment — confirmed by grep, `afk_clicker.py`
  has zero contrast-ratio comments — so this has no runtime effect.
- Failure scenario: a future reviewer or Feature-2/3 developer trusts
  design.md's "borderline, acceptable" framing for `MUTED`/`CARD` and either
  avoids a legitimately-safe color combination, or — worse — trusts the same
  flawed arithmetic method for a *new* pairing in Quartz/Feature-3 and ships
  something that's actually below 4.5:1 while believing the math checks out.

### 3. Windows/macOS rendering unverified this session — informational, not a defect
- This review ran entirely under Xvfb/Linux. CI's matrix (confirmed in
  `.github/workflows/`) runs the *full test suite*, including every new
  geometry/`coords()`/canvas-`bg` assertion, on `windows-latest` and
  `macos-latest` too — so the logic is covered cross-platform. But no one
  has looked at actual rendered pixels of the new arc-based polygons or the
  `create_window` card shell on either platform. Per Round 7's instruction
  to say this plainly rather than imply coverage that doesn't exist: stating
  it here. This is the same pre-existing gap `ROADMAP.md` already tracks
  ("macOS verification... never run by a human"), not something Feature 1
  introduces or worsens.

No must-fix findings.

## Follow-ups (non-blocking)
- Update `docs/spec.md`'s `CARD_INNER_W` acceptance bullet (and Decision 3's
  worked formula) from `428` to `396` to match what actually shipped
  (Finding 1).
- Correct `docs/design.md`'s Deepslate contrast table to the actual computed
  ratios (Finding 2) so Feature 2/3 don't inherit the wrong method.

## Overall verdict
**Approve, with two non-blocking documentation follow-ups.** All 20 test
cases pass against real execution (full suite: 155 tests, OK, twice, tree
verified byte-identical before/after every revert probe); every acceptance
criterion in `docs/spec.md` is implemented and independently re-verified;
both round-8 revert checks reproduce the exact failures `docs/implementation.md`
claims; no must-fix correctness, security, threading, or scope issue found in
the diff.
