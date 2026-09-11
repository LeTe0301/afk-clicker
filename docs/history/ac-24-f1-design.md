# Design: Row value-column alignment (story #24, Feature 1 of 5)

## Summary
`Row` switches from expanding-label packing to a fixed-width label column via `grid`, with label and control aligned in separate grid columns. This closes the horizontal "gulf" when cards stretch: controls now sit at a fixed offset from the row's left edge instead of pinned to the card's right edge, with any extra width becoming trailing margin after the control. Design decision: `ROW_LABEL_W = 140px` and `ROW_LABEL_GAP = 12px` are confirmed; wrapping the "Random jitter" hint to two lines is acceptable; trailing margin behavior matches the NVIDIA reference exactly.

## ui-ux-pro-max rationale

This is a **layout/alignment feature, not a visual restyle** — no new colors, typography, shape, or spacing changes beyond what the alignment mechanism requires. The design is grounded in:

- **Reference pattern (NVIDIA app)**: The handoff screenshot `02-graphics-program-settings.png` shows row controls aligning vertically at the same x-position regardless of label width, with dead space (trailing margin) after the control column when rows don't extend to the full card width. Feature 1 replicates this exact pattern.
- **Grid over pack_propagate(False)**: `grid()`'s row height is computed from the tallest cell (max of label-stack height and control height), ensuring two-line label+hint stacks cannot clip — a strictly safer failure mode than `pack_propagate(False)`, which would freeze height and risk silently truncating the hint.
- **UX guideline applied**: Control-alignment consistency reduces cognitive load — every control's value-display starts at the same visual line, making it faster to scan rows and locate a specific setting without tracking label widths.

## Component reuse

- **No new components** — `Row` is modified in place, retaining its `__init__(parent, label, s, hint=None)` signature and its `.control` attribute for call-site compatibility.
- **Existing widgets unchanged** — `NumBox`, `Segmented`, `tk.Label` (hotkey/version labels) inside `row.control` continue to work as today, just now positioned at a fixed offset rather than the card's far edge.

## Layout & geometry decisions

### Row internal structure (the change)

**Current state (`Row` at lines 1416–1429):**
```
Row (pack, fill="x")
├── text frame (pack, side="left", fill="x", expand=True)
│   ├── label Label
│   └── hint Label (if present)
└── control frame (pack, side="right")
    └── [NumBox / Segmented / tk.Label]
```

The label frame expands to consume all leftover width; the control is pinned to the card's true right edge, which grows with window width. This creates the reported "gulf."

**After Feature 1 (`Row` with grid):**
```
Row (pack, fill="x")  [Row itself still packed by its parent]
├── grid_columnconfigure(0, minsize=int((140 + 12) * s))
├── text frame (grid, row=0, column=0, sticky="w")
│   ├── label Label (wraplength=int(140 * s))
│   └── hint Label (wraplength=int(140 * s), if present)
└── control frame (grid, row=0, column=1, sticky="w")
    └── [NumBox / Segmented / tk.Label]
```

**Column layout:**
- **Column 0** (label): fixed minsize = `int((ROW_LABEL_W + ROW_LABEL_GAP) * s)` = `int(152 * s)` at s=1.
- **Column 1** (control): left at default weight (0), so it does not grow on a stretched card.
- **Trailing space**: any extra width (from a wide window) sits as dead margin to the right of column 1, not distributed into either column.

### Constant definitions

```python
ROW_LABEL_W = 140    # max label width before wrapping (52px margin over the widest
                     # measured label at 88px, absorbing font-metric differences)
ROW_LABEL_GAP = 12   # breathing room between label column and control column
```

**Why these numbers hold:**

Fit check at `s=1` (all quantities scale by the same `s`, so ratios hold at every UI-scale step):
- **Tightest case**: "UI scale" row, `Segmented` control at `width=220` (widest in the file).
  - `ROW_LABEL_W + ROW_LABEL_GAP + 220 = 140 + 12 + 220 = 372px`
  - vs `CARD_INNER_W = 396px`
  - Trailing margin: **24px** ✓
- **"Mouse button" row**, `Segmented` at `width=180`:
  - `152 + 180 = 332px` → **64px trailing margin** ✓
- **Widest label** ("Mouse button" / "Random jitter", measured 88px):
  - Fits in 140px with **52px margin** ✓
- **All `NumBox` rows** (Interval/Random jitter/Auto-stop/Eat every/Hold for): shrink-wrap to <100px, no fit concern.

Font-metric buffer: DejaVu Sans (this dev environment's substitute for Segoe UI) and Segoe UI are comparable general-purpose sans-serif fonts — a 52px margin on the label fit and 24px on the control fit provide reasonable headroom for weight/size differences on the real target font (Segoe UI on Windows/macOS).

### Wrapping behavior

**Labels:** "Random jitter" is the widest at 86px (measured), leaving 54px margin in the 140px column — labels do not wrap.

**Hints:** Only one hint exceeds 140px:
- "Random jitter" hint ("spreads the rhythm so it is not exact"): 210px measured → **wraps to two lines** at `wraplength=140px`.
- "Auto-stop" hint ("0 means never"): 86px → fits on one line.
- All other rows have no hint, so no wrapping.

**Wrapping acceptance:** A two-line label+hint stack makes that row taller than most others — but this is an accepted, deliberate consequence of bounding the label column. Alternatives (wider label column, shorter hint, hint text reflow) would either tighten already-tight margins elsewhere or reduce readability. The stack remains scannable; the height difference is minor (roughly one line = 8–10px at s=1, depending on line spacing). This is flagged in the spec's Edge cases section as intentional.

### Trailing margin reference alignment

The NVIDIA reference (`02-graphics-program-settings.png`) shows exactly this behavior in the "In-Game Settings | Current Value" table:
- "Display Mode" control, "Far Object Detail (LOD)" control, etc. all align vertically at the same x-position.
- Beyond the rightmost control, there is unused (empty) space extending to the card's right edge.
- The reference does not attempt to fill this space or stretch controls — dead margin is acceptable.

Feature 1 replicates this: grid column 0 has a fixed minsize; column 1 is not expanded into any extra width from a stretched card. Any width overflow becomes trailing space, matching the reference.

## States

This is a layout change, not a component with interactive states. The single state is "Row built and laid out":

### Row populated (single state)

**At default window size (CONTENT_W = 452, CARD_INNER_W = 396):**

```
┌─ Row (pack, fill="x") ────────────────────────────────────┐
│  [Label column]    [gap] [Control]  [trailing margin]     │
│  (≤140px wide)      (12px) (shrink-wrap or fixed width)    │
│  With optional    │                                        │
│  hint below       │                                        │
│  (wraplength=140) │                                        │
└────────────────────────────────────────────────────────────┘
```

**Example with no hint (e.g., "Toggle" hotkey row):**
```
┌─ Row ─────────────────────────────────────────────────────┐
│  Toggle             [gap] [hotkey_label]  [trailing]      │
│  (43px @ s=1)       (12px) (shrink-wrap)                   │
└────────────────────────────────────────────────────────────┘
```

**Example with hint ("Random jitter" clicking row):**
```
┌─ Row ─────────────────────────────────────────────────────┐
│  Random jitter     [gap] [NumBox]  [trailing]             │
│  spreads the rhythm... (12px) (≈90px)                      │
│  so it is not exact     │                                  │
│  (label 86px + 2-line                                      │
│  hint at wraplength 140px)                                 │
└────────────────────────────────────────────────────────────┘
```

**At stretched window (e.g., 900x760, per test recommendation):**

Same layout — the row height doesn't change, the trailing margin simply grows. All control x-positions remain at the same offset from the row's left edge (the grid column 0 boundary).

```
┌─ Row ──────────────────────────────────────────────────────────────────┐
│  [Label column] [gap] [Control]  [extra trailing margin from stretch]  │
│  (152px)        (12px) (fixed/shrink-wrap)  (grows as card stretches)  │
└────────────────────────────────────────────────────────────────────────┘
```

## Accessibility & platform notes

### Touch target sizes
This is a desktop tkinter app (Linux/Windows/macOS), not a mobile interface. Cursor-clickable elements (buttons, controls) retain their existing sizes — no change from this feature.

### Color contrast
No new color usage; all text (label, hint) reuses existing `INK` and `MUTED` tokens against the `CARD` background. No change from today.

### Keyboard/focus navigation
`Row` is a container, not directly focusable. Focus lands on `row.control`'s children (NumBox, Segmented, Label) — no change in tab order or focus behavior.

### UI-scale and DPI interaction
Every dimension (`ROW_LABEL_W`, `ROW_LABEL_GAP`, control `width=`s, `CARD_INNER_W`) scales by the same `self.s = self._dpi_s * UI_SCALE_FACTORS[...]`. Ratios are scale-invariant; the fit check at `s=1` holds at every UI-scale step (90/100/115/130) and every DPI value (including macOS `_dpi_s ≈ 0.75`, per ticket #23). No new UI-scale-specific logic needed.

## Forward-compatibility with Feature 3

**Question posed in the spec:** "Feature 3 will let the window get *much* narrower (collapsed rail plus usable content column). A fixed 152px label column plus a 220px control = 372px incompressible row. What does that imply for how narrow the window can ever become, and should the design anticipate it now or leave it to Feature 3?"

**Answer: Leave it to Feature 3's spec stage.**

- Today's minimum window width: `(SIDEBAR_W + 1 + CONTENT_W) * s` = `(208 + 1 + 452) * s` = 661px at s=1.
- Feature 3 will collapse the sidebar to icon-only (estimated ~80–100px) and rederive `_apply_minsize()`.
- At that point, the minimum content width becomes a binding constraint: if a row's 372px incompressible content + card padding (2 × 16px) = 404px required content width, and the desired minimum window width is 484px (collapsed rail + content), the row *will* fit with tight margins.
- **If rows overflow at Feature 3's projected minimum, Feature 3's spec is explicitly scoped to handle it**: either (a) set the window's hard minimum wide enough to prevent clipping, or (b) add responsive behavior (control wrapping, stacking, or smaller controls) at narrower widths.

**Design does not preempt Feature 3** because:
1. Feature 3's spec will literally derive the floor based on "the narrowest row that must not clip at the smallest UI-scale step" (story.md, Decisions, point 4).
2. Changing row structure now (e.g., reducing control widths or adding conditional wrapping) to avoid a problem Feature 3 will measure anyway risks over-constraining both features.
3. The 152 + 220 = 372px baseline is known; Feature 3 has the data to decide if that fits its target minimum or needs adjustment.

**Design assumption for Feature 3 implementers:** Rows with the current incompressible widths will either (a) fit at the projected minimum window size, or (b) trigger a spec update to Feature 3 that changes row structure (narrower controls, stacking, etc.) or raises the minimum window width. This is expected and covered by Feature 3's scope.

## Traceability to spec

| Acceptance criterion | Where addressed | Notes |
|---|---|---|
| `control.winfo_x()` equals `int((ROW_LABEL_W + ROW_LABEL_GAP) * s)` at default window size | Layout structure: grid column 0 minsize = 152px; control in column 1, aligned left. Verified by new test `RowValueColumn` in `tests/test_ui.py`. | This is the single-source-of-truth for label column offset. |
| Same `control.winfo_x()` when window resized to 900x760 (stretched card) | Same layout structure: grid columns do not grow; only trailing space after column 1 grows. Verified by comparison before/after `self.root.update()`. | Confirms the gulf is closed — no growth in label-to-control distance. |
| Non-zero trailing margin at stretched window (right edge of control < right edge of card) | Grid column 1 weight = 0, so extra width is not distributed into either column; it sits as trailing space. Verified by `control.winfo_x() + control.winfo_width() < card.winfo_width()`. | Matches NVIDIA reference behavior. |
| No overflow at each UI-scale step (90/100/115/130) for widest control ("UI scale" Segmented, width=220) | Fit check: 152 + 220 = 372 ≤ 396. Ratio preserved at every step. Verified by explicit per-scale assertion in `RowValueColumn` test. | Covers font-metric buffer and all scale factors. |
| "Random jitter" hint `wraplength = int(ROW_LABEL_W * s)` and hint wraps without overlapping control | Hint Label has `wraplength=int(140 * s)` applied in Row.__init__. Two-line stack tested via measured widget height. | Wrapping is intentional; verified that hint does not overflow into control column. |
| All 10 Row call sites build without exception; every control present and shows expected value | No call-site changes required; Row signature unchanged. Verified by unmodified app-builds-cleanly tests and new RowValueColumn class. | Call-site compatibility preserved. |
| Full test suite (240 tests + new RowValueColumn tests) passes at baseline | New tests added; no existing tests modified (per spec's Test impact section). | Zero existing coverage lost. |

## Implementation checklist (for developer)

- [ ] Add constants `ROW_LABEL_W = 140`, `ROW_LABEL_GAP = 12` near line 160–163 (alongside `CONTENT_W`, `CONTENT_PAD`, `CARD_INNER_W`).
- [ ] Refactor `Row.__init__` (lines 1416–1429) to use `grid()` for text/control frames; apply `wraplength=int(ROW_LABEL_W * s)` and `justify="left"` to label and hint Labels.
- [ ] Update inline comments at lines 1886–1889 and 1893–1899 to reference the new constants and this feature instead of stale documentation.
- [ ] Write `RowValueColumn` test class (new, in `tests/test_ui.py`) with the five state/measurement assertions from Acceptance criteria.
- [ ] Verify `Tcl_AsyncDelete` flake at shutdown remains pre-existing (~1 in 4 runs, exit 134, no summary); re-run once if hit, do not chase.

