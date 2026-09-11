# Implementation: Row value-column alignment (story #24, Feature 1 of 5)

## Summary
`Row` now lays out its label and control in two `grid` columns instead of
`pack`ing a flexible label against a fixed-width control. Column 0 (the
label) has a fixed `minsize` of `int((ROW_LABEL_W + ROW_LABEL_GAP) * s)`, so
every control across all 10 `Row` call sites now starts at the same offset
from the row's left edge no matter how wide a stretched card gets; any extra
width becomes trailing margin after the control instead of a growing gap
before it. Two new module-level constants (`ROW_LABEL_W = 140`,
`ROW_LABEL_GAP = 12`) drive this. `Row`'s signature and `.control` attribute
are unchanged, so no call site needed edits.

## Root cause
N/A — this is a feature/alignment fix, not a bugfix with a defect root cause
in the strict sense. The mechanism behind the reported "gulf" is described in
`docs/spec.md`'s Summary/Background: the old `Row` packed its label frame
with `side="left", fill="x", expand=True` and its control with
`side="right"` and no fill/expand, so the label frame (not its text) grew to
consume all space up to the control, which itself stayed pinned to the row's
actual (stretchable) right edge — the label-to-control gap tracked window
width directly.

## Changes by file
- `afk_clicker.py:167-171` — new constants `ROW_LABEL_W = 140` and
  `ROW_LABEL_GAP = 12`, placed immediately after `CARD_INNER_W`, matching
  the surrounding constants' inline-comment style.
- `afk_clicker.py:1421-1445` (`Row.__init__`) — replaced the two `pack()`
  calls on `text`/`self.control` with `grid()`, added
  `self.grid_columnconfigure(0, minsize=int((ROW_LABEL_W + ROW_LABEL_GAP) * s))`,
  and added `wraplength=int(ROW_LABEL_W * s)` + `justify="left"` to both the
  label and hint `tk.Label`s (following the existing `game_note` precedent
  at `afk_clicker.py:1807-1810`). `Row`'s signature and `.control` attribute
  are untouched.
- `afk_clicker.py:1899-1917` (`_build_settings`) — reworded the two inline
  comments that previously justified the Theme/UI-scale `Segmented` widths
  against `CARD_INNER_W` in terms of the old expanding-label model and a
  stale `docs/spec.md §5`/`§1` reference (from a prior story). They now cite
  `ROW_LABEL_W`/`ROW_LABEL_GAP` and the actual fixed-column arithmetic
  (`152 + 180 = 332`, `152 + 220 = 372 <= 396`). No other stale
  `docs/spec.md §N` references in the file were touched — there are 39 such
  references total and fixing them wholesale is out of scope for this
  feature per the task instructions.
- `tests/test_ui.py:764-833` — new `RowValueColumn(UITestCase)` test class,
  placed directly after `WindowResize` (before `Selftest`), with 5 new
  tests (see below).

## Key decisions / tradeoffs
- Followed the spec's proposed `Row` implementation verbatim (constants,
  `grid` structure, `wraplength`/`justify`) — no alternative design was
  considered since the spec had already argued down the alternatives
  (fixed control-column width, proportional label column, wraplength-only,
  `pack_propagate(False)`).
- For the new tests, `winfo_x()` alone is only relative to a widget's
  *immediate* parent, which isn't enough to compare a control several
  frames deep (control frame -> Row -> card inner Frame) against the card's
  own width. Added a small `_right_edge(widget, ancestor)` helper using
  `winfo_rootx()` deltas (absolute screen coordinates both share) rather
  than walking `winfo_x()` up through every intermediate frame — confirmed
  correct against a manual script before committing to it in the test file.
- The "Random jitter" hint-wrap test reaches the hint `Label` directly via
  `row.grid_slaves(row=0, column=0)[0].winfo_children()` (the `text` frame's
  two children, label then hint) rather than adding another generic
  widget-tree-walking helper — `tests/test_ui.py` already has two
  near-identical `walk()` helpers for locating a `Segmented` by its bound
  variable (`_appearance_segment` in `UITestCase`, `_find_segmented_for` in
  `NumBoxFocus`); this case has a known, fixed structure so a direct lookup
  was more precise and didn't warrant a third copy of that pattern.
- Used `self.ui.click_ms.master` as the sampled row control per the spec's
  own suggestion (`docs/spec.md` Acceptance criteria) — `click_ms` is a
  `NumBox` packed directly into `row.control`, so `.master` is exactly the
  control frame `grid`ded into column 1.

## Deviations from spec
None. Implemented the constants, `Row` structure, comment updates, and test
class exactly as specified in `docs/spec.md`'s Proposed approach and
Acceptance criteria, using the 900x760 stretched-window size the spec
recommends (not the ticket's literal 1200x820) for the same CI-clamping
reason called out there.

One number came out different from the spec's own worked example, flagged
here since the task asked to report if the rendered fit came out tighter
than predicted: it came out **looser**, not tighter. The spec's fit-check
table computes margins from unscaled constants at `s=1` (e.g. "UI scale"
row: `152 + 220 = 372` vs `CARD_INNER_W = 396`, "24px of margin"). In this
dev environment `self.ui.s` is not exactly `1.0` at the default DPI/scale
step (measured `1.042311860016286`, presumably `_dpi_s` reading this
display's actual DPI) — every quantity in the fit check scales by that same
`s`, including `CARD_INNER_W`, `ROW_LABEL_W`, `ROW_LABEL_GAP`, and each
control's explicit `width=`, and the actual rendered card width also picks
up the Tk `Canvas`/`Frame` padding from `card()`. Measured directly: at
`s=1.0423`, the "UI scale" row's `Segmented` right edge sits at 387px inside
a 415px-wide card at default size, and the fit holds (with margin to spare)
at all four UI-scale steps (90/100/115/130) and at the 900x760 stretched
size — confirmed by the new `test_ui_scale_row_never_overflows_its_card_at_
any_scale_step` test, which checks the actual rendered geometry, not just
the constant-level arithmetic. Font substitution (DejaVu Sans in place of
Segoe UI, per the spec's own Open question) is the likely source of any
remaining gap between the `s=1` paper numbers and this environment's
render, but since the ratio-invariance argument held and every rendered
check passed with margin, this isn't a blocker — just recorded because the
task explicitly asked to report the real fit rather than only the paper fit.

## Known limitations
- Per `docs/story.md`'s "Forward-compatibility with Feature 3" note, the
  152px label column + widest 220px control (372px incompressible content)
  is a known constraint that Feature 3 (icon-rail collapse /
  `_apply_minsize()` change) will need to re-check against its own
  narrower minimum-window target. Nothing here pre-empts that; it's
  explicitly left to Feature 3's own spec stage, per both `docs/spec.md`
  and `docs/design.md`.
- The "Random jitter" row is now visibly taller than its neighbours because
  its hint wraps to two lines at the 140px label column width. This is
  accepted and intentional per the spec/design (not a defect); no
  special-casing was added to prevent it, per the task instructions.

## How to verify locally
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-24
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/c3f4ab6d-63eb-4d27-b601-121c74c66331/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
Result (run twice, both clean): **245 tests, OK (skipped=5)** — the
240-test baseline plus the 5 new `RowValueColumn` tests below. The known
pre-existing `Tcl_AsyncDelete` shutdown flake (~1 run in 4, exit 134, no
summary) was not observed in either run; it is unrelated to this change per
the task's own note.

New tests (`tests/test_ui.py`, class `RowValueColumn(UITestCase)`):
- `test_control_sits_at_the_fixed_label_column_offset`
- `test_offset_is_unchanged_when_the_card_stretches`
- `test_extra_width_becomes_trailing_margin_not_a_growing_gap`
- `test_ui_scale_row_never_overflows_its_card_at_any_scale_step`
- `test_random_jitter_hint_wraps_instead_of_overlapping_the_control`

To run only the new class:
```
DISPLAY=:99 .../venv/bin/python -m unittest tests.test_ui.RowValueColumn -v
```

No existing test was modified, per `docs/spec.md`'s "Test impact" section —
confirmed the full suite still reports the same baseline count plus exactly
the 5 new tests.
