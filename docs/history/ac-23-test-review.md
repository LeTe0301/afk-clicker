# Test & Review: macOS font-size floor (`fs(base, s)`) — G#23/GH#35

## Scope
Covers every acceptance criterion in `docs/spec.md`: the `fs(base, s)` helper's
value correctness at all named scale points, the completeness of the 34-site
sweep, the `TabBar` font/measurer desync fix, the two widget-level scale-
simulation tests, and scope discipline (no `WINDOW_MIN_H`, no scale-step
changes, no G#38 creep). Environment: no real Mac available anywhere in this
pipeline (confirmed — this box has none), so macOS-specific behaviour is
verified the same way the developer verified it: the `_dpi_s`/`_apply_ui_scale`
simulation pattern already established by `WindowMinimumHeight`
(`tests/test_ui.py:1148-1168`). CI's macOS leg remains the only real-hardware
verification and is out of reach of this local pass — flagged below, not
treated as a gap in this review's own diligence.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | `fs(8, 0.75) == 6` (mac 100%, unchanged) | Automated (`FontSizeFloor`) | pass | Ran `unittest tests.test_ui.FontSizeFloor -v`, all 7 green |
| 2 | `fs(8, 0.675) == 6` (mac 90%, the reported 5pt case) | Automated | pass | Same run; additionally sabotage-verified (see below) |
| 3 | `fs(9.5, 0.675) == 6` (unaffected base, no-op) | Automated | pass | Same run |
| 4 | `fs(8, 1.0) == 8` (Windows/Linux 100%) | Automated | pass | Same run |
| 5 | `fs(8, 0.9) == 7` (Windows/Linux 90%) | Automated | pass | Same run |
| 6 | `fs(8, 0.8625) == 6` and `fs(8, 0.975) == 7` (mac 115%/130%, no-op) | Automated | pass | Same run |
| 7 | Every font-size `int(<literal> * s)` replaced with `fs(<literal>, s)`; grep shows only non-font hits remain | Manual grep, re-derived independently | pass | `grep -n 'int([0-9.]* \* s)' afk_clicker.py` → only padding/width/height/wraplength (`afk_clicker.py:1883,2089,2148,2280,2290-2291,2692,2697,2699,2718,2720,2725,2734-2735,2746,2956,2961,3001,3003,3035,3037,3039,3054,3057,3097,3141,3165,3208,3918-3919,3941,3949-3950,3956,3976,3980,3993,3996,4148,4154`); `grep -n 'font='` shows every hit uses `fs(...)`, `font=font` (TabBar's shared local), or `self._hint_size` (Row's shared local) — no bare `int(...)` inside a `font=` tuple or `tkfont.Font(size=...)` anywhere |
| 8 | `TabBar`'s label font and its width-measurer read the same computed value | Manual code read | pass | `afk_clicker.py:1793-1795`: `font_size = fs(9.5, s)` computed once, fed to both `font = (...)` (used at `create_text`, line 1815) and `measurer = tkfont.Font(..., size=font_size, ...)` (line 1795) — single source, cannot desync |
| 9 | Simulated mac 90% (`_dpi_s=0.75`, `_apply_ui_scale("90")`) → a real widget's rendered font size is 6, not 5 | Automated (`FontSizeFloorAtWorstCaseScale`) | pass | Ran `unittest tests.test_ui.FontSizeFloorAtWorstCaseScale -v`, both green; sabotage-verified (see below) |
| 10 | Simulated mac 100% → same widget still reports 6 (baseline unshifted) | Automated | pass | Same run |
| 11 | CI's macOS leg green | Not verifiable in this session | deferred | No real Mac / CI run available to this reviewer pass; spec explicitly calls this the only real verification and asks that it be called out in the PR description rather than treated as covered by a local run — noted, not silently assumed |

### Sabotage verification (backlog.md's own lesson: "the acceptance test is not
'it stopped failing' but 'it still fails when the product is broken'")
Reverted `fs()` to plain `return int(base * s)` (`afk_clicker.py:153`), leaving
everything else untouched, then re-ran the two new test classes:
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.FontSizeFloor tests.test_ui.FontSizeFloorAtWorstCaseScale -v
...
FAIL: test_mac_90_percent_worst_case_is_floored ... AssertionError: 5 != 6
FAIL: test_worst_case_mac_90_percent_floors_to_six ... AssertionError: 5 != 6
Ran 9 tests in 0.293s
FAILED (failures=2)
```
Exactly the two tests that assert the floor actually engaging went red; the
five no-op tests (100% mac, Windows/Linux, 115%/130%) correctly stayed green,
since a plain `int()` already gives their expected values — this is the right
shape of failure, not an over-broad one. Restored `afk_clicker.py` from a
pre-sabotage copy immediately after (`git diff --stat` back to the original 57
insertions / 33 deletions), then re-ran both classes to confirm green again.
No repo file was left modified or untracked by this process.

## Regression check
Full existing suite run:
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 423 tests in 74.191s
OK (skipped=10)
```
Matches the developer's reported baseline exactly (423 tests, skipped=10, same
pre-existing `ResourceWarning`/`invalid command name` noise from
`test_updater.py`/`test_ui.py`, both already documented as unrelated to this
diff). Environment: built a fresh venv (`pynput==1.7.7`) against the
already-running `Xvfb :99`, per this project's own established test-env
convention — no venv pre-existed in the container for this project, so one was
created in the session scratchpad, outside the repo tree.

No type-check/lint step exists in this project (`.github/workflows/ci.yml` runs
only `unittest discover` on three OSes; no `flake8`/`mypy`/`pyproject.toml`
config present) — nothing else to run.

## Spec coverage
Every acceptance criterion in `docs/spec.md` maps to a test case above (1-10
automated/verified this session, 11 explicitly out of local reach and flagged
rather than assumed). No criterion was found unimplemented or untested.

Sweep completeness re-derived independently, not trusted from
`docs/implementation.md`'s own count: `grep -n '\bfs(' afk_clicker.py` shows 33
occurrences — 1 definition, 1 `font_size = fs(9.5, s)` local (TabBar), and 31
direct call sites embedded in `font=`/`tkfont.Font(size=...)` expressions.
Combined with the two "compute once, reuse" sites (`TabBar`'s `font_size` used
twice; `Row`'s `self._hint_size` used at construction and at two later
`set_hint()`/`restore_hint()` call sites), this accounts for every font-size
expression the spec's table names, and the `grep -n 'int([0-9.]* \* s)'` /
`grep -n 'font='` cross-check independently confirms no font call site still
uses a bare `int()` and no non-font `int(x * s)` expression (padding, pixel
width/height, `wraplength`) was wrongly converted to `fs()`.

Scope discipline, re-derived from the diff and `backlog.md`, not assumed:
- `WINDOW_MIN_H` (`afk_clicker.py:204`): untouched — confirmed no diff hunk
  near it.
- `UI_SCALE_FACTORS` (`afk_clicker.py:130`): value unchanged
  (`{"90": 0.9, "100": 1.0, "115": 1.15, "130": 1.3}`), no step dropped.
- No G#38 (continuous/"Auto" scaling) code present — `fs()` takes a plain
  `(base, s)` pair with no reference to `UI_SCALE_FACTORS`' four keys, exactly
  as the spec asks so G#38 can reuse it unmodified later.
- `git diff --stat` touches only `afk_clicker.py` and `tests/test_ui.py` — no
  other file in the sweep's blast radius.
- Branch name `hotfix/ac-23/macos-font-size-floor` matches the
  `hotfix/{ab}-{ticket}/{description}` convention (`ac` = afk-clicker, ticket
  23 = Gitea #23/GitHub #35, confirmed real and tracked in
  `backlog.md:157,563,600-610`).

## Findings (most severe first)
None at must-fix or should-fix severity.

### Nit: acceptance-criteria count language in `docs/implementation.md`
`docs/implementation.md` states "34 call sites"; a direct count of `fs(` in the
final file is 33 (1 definition + 32 usages, 2 of which are the shared
`font_size`/`self._hint_size` locals rather than fresh `fs()` calls at their
reuse points). The actual coverage is correct and complete either way — this
is a documentation precision nit, not a functional gap, and doesn't change any
verdict.

## Follow-ups (non-blocking)
- None beyond what's already tracked: CI's macOS leg is the real gate for this
  change per the spec's own Risk notes — worth calling out explicitly in the
  PR description (as the spec asks), not a review blocker.

## Overall verdict
**Approve.** All spec acceptance criteria verifiable outside of real macOS
hardware are implemented, tested, and independently re-verified in this
session (including a sabotage check proving the new tests actually detect a
broken `fs()`, not just a passing one). The sweep is complete and precise —
no font call site missed, no non-font expression wrongly converted. The
`TabBar` desync concern is addressed at the source (single computed local).
Scope is disciplined: no `WINDOW_MIN_H` touch, no scale-step change, no G#38
creep, diff confined to `afk_clicker.py` + `tests/test_ui.py`. Full regression
suite is green (423 tests, skipped=10, matching baseline). The only
unverified item — CI's macOS leg — is explicitly out of reach for any local
reviewer pass on this box and is already called out as such in
`docs/implementation.md`; it is the next real gate, not a defect in this cycle.
