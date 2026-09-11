# Spec: Row value-column alignment (story #24, Feature 1 of 5)

## Summary
`Row` (`afk_clicker.py:1416-1429`) currently packs its label `side="left",
fill="x", expand=True` and its control `side="right"` with no fill/expand, so
the control chases the card's true right edge; when a stretched card (a wide
window hands `content` extra `pack` space today, per `docs/story.md`'s
architecture notes) grows, the label stays where its text is but the *frame*
holding it grows to fill everything up to the control, so the gap between
label and control grows unbounded. This feature gives every `Row` a fixed-
width label column, so the control always starts at the same offset from the
row's left edge regardless of how wide the card gets — any extra width from a
wide window becomes trailing margin to the right of the control, not a
growing gulf between label and control.

## Goals
- Close the "gulf" reported in the ticket at 1200px width, on every existing
  `Row` in `_build_content` and `_build_settings`, at every UI-scale step.
- Keep the fix mechanical and local to `Row` itself — no other class changes
  shape or behavior.

## Non-goals
- No tab bar (Feature 2), no icon rail / `_apply_minsize()` change (Feature
  3), no vertical space fill (Feature 4) — none of those are touched.
- No visual restyle: `CARD_R`, `PILL_R`, colors, fonts, and `round_rect()` are
  untouched. This is an alignment/geometry fix, not a chrome pass.
- No change to `CONTENT_W`, `SIDEBAR_W`, `CONTENT_PAD`, or `CARD_INNER_W` —
  the card's own width and the app's minimum window size are unaffected.
- No change to any control's own internal layout: `NumBox`'s right-aligned
  entry+unit, `Segmented`'s fixed pixel widths, and `hotkey_label`'s
  `side="right"` packing inside `row.control` all keep their current
  internal behavior. Only where `row.control` itself sits within `Row`
  changes.
- No new `Row` call sites, no change to which controls exist.

## Background / current state
`Row.__init__` (`afk_clicker.py:1416-1429`):
```python
class Row(tk.Frame):
    def __init__(self, parent, label, s, hint=None):
        super().__init__(parent, bg=CARD)
        text = tk.Frame(self, bg=CARD)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=label, ...).pack(fill="x")
        if hint:
            tk.Label(text, text=hint, ...).pack(fill="x")
        self.control = tk.Frame(self, bg=CARD)
        self.control.pack(side="right")
```
`text` has no `wraplength` and expands to consume all leftover width; `control`
has no fill/expand and is packed flush against the row's actual right edge,
which — because `Row.pack(fill="x")` at every call site — tracks the card's
own (stretchable) width, not a bounded value column.

There are 10 `Row(...)` call sites, all in `_build_content`
(`afk_clicker.py:1794-1858`) and `_build_settings` (`afk_clicker.py:1860-1946`):

| Line | Card | Label | Control | Control width |
|---|---|---|---|---|
| 1814 | `hk` (Hotkey) | "Toggle" | `tk.Label` (`self.hotkey_label`), packed `side="right"` inside `row.control` | shrink-wrapped to text |
| 1829 | `cl` (Clicking) | "Interval" | `NumBox` | shrink-wrapped (~90px @ s=1) |
| 1832 | `cl` | "Random jitter" (+ hint) | `NumBox` | shrink-wrapped |
| 1835 | `cl` | "Auto-stop" (+ hint) | `NumBox` | shrink-wrapped |
| 1837 | `cl` | "Mouse button" | `Segmented`, `width=180` | 180 |
| 1849 | `eat_card_inner` (Eating) | "Eat every" | `NumBox` | shrink-wrapped |
| 1851 | `eat_card_inner` | "Hold for" | `NumBox` | shrink-wrapped |
| 1883 | `ap` (Appearance) | "Theme" | `Segmented`, `width=180` | 180 |
| 1900 | `ap` | "UI scale" | `Segmented`, `width=220` | **220 (widest)** |
| 1938 | `up` (Updates) | "Version" | `tk.Label` (`self.version_label`) | shrink-wrapped |

(The Updates card's "Check for updates" `Button` at `afk_clicker.py:1943` is
packed directly into `up`, not into a `Row`, and is unaffected.)

Measured via `tkinter.font.Font.measure()` under this environment's
available fonts (`Segoe UI` falls back to DejaVu Sans here — the real target
font may render slightly differently, see Open questions) at `s=1`:

| Label text | Measured width (px) |
|---|---|
| "Mouse button" | 88 |
| "Random jitter" | 86 |
| "Auto-stop" | 63 |
| "Eat every" | 60 |
| "Hold for" | 49 |
| "Interval" | 48 |
| "Version" | 48 |
| "UI scale" | 50 |
| "Theme" | 44 |
| "Toggle" | 43 |
| hint "spreads the rhythm so it is not exact" | 210 |
| hint "0 means never" | 86 |

`CARD_INNER_W = 396` (`afk_clicker.py:163`) is the nominal/floor inner width
every card gets at the default (unstretched) window size; a stretched card
only ever has *more* room than this, never less, so `CARD_INNER_W` is the
binding constraint for "does the label column + widest control fit."

## Proposed approach
Give `Row` a fixed-width label column via `grid` (not `pack`) inside `Row`
itself, and two new module-level constants next to `CONTENT_W`/`CONTENT_PAD`
(`afk_clicker.py:160-163`):

```python
ROW_LABEL_W = 140    # widest existing Row label ("Mouse button"/"Random
                      # jitter", ~88px measured @ s=1) plus headroom for
                      # font-metric differences on the real target font.
ROW_LABEL_GAP = 12    # breathing room between the label column and the
                      # value column that starts right after it.
```

`Row` becomes:
```python
class Row(tk.Frame):
    def __init__(self, parent, label, s, hint=None):
        super().__init__(parent, bg=CARD)
        self.grid_columnconfigure(0, minsize=int((ROW_LABEL_W + ROW_LABEL_GAP) * s))
        text = tk.Frame(self, bg=CARD)
        text.grid(row=0, column=0, sticky="w")
        tk.Label(text, text=label, bg=CARD, fg=INK, anchor="w", justify="left",
                 wraplength=int(ROW_LABEL_W * s),
                 font=("Segoe UI", int(9.5 * s))).pack(fill="x")
        if hint:
            tk.Label(text, text=hint, bg=CARD, fg=MUTED, anchor="w", justify="left",
                     wraplength=int(ROW_LABEL_W * s),
                     font=("Segoe UI", int(8 * s))).pack(fill="x")
        self.control = tk.Frame(self, bg=CARD)
        self.control.grid(row=0, column=1, sticky="w")
```

Why this shape, and why not the other options named in the ticket:
- **Fixed control-column width** (reserving a fixed width for `control`
  itself, still packed at the row's right edge): rejected — the boundary
  between label and control would still track the row's own (stretchable)
  right edge minus a constant, so the gulf still grows with window width,
  just starting from a different offset. This does not fix the reported bug.
- **A proportion of available width**: rejected — a percentage-based label
  column would still grow on a wide window, moving the value column away
  from the label instead of holding it in place, which is the opposite of
  what "column" means in the NVIDIA reference
  (`handoff/nvidia-reference/02-graphics-program-settings.png`): every row's
  value starts at the *same fixed x*, regardless of how much unused width
  exists further right.
- **A max-width cap on the label side only** (bound the label's own text
  width via `wraplength`, but leave `control` packed immediately after the
  label's own natural/wrapped width, no shared constant): rejected as the
  primary mechanism because it produces a different value-column x per row
  (a short label like "Theme" would put its control closer to the left edge
  than "Mouse button"'s control) — a jagged left edge for controls, not the
  single shared column the ticket and reference both show. `wraplength` is
  still used, just as a secondary safety net against clipping (see below),
  not as what determines the column's x position.
- **`grid` instead of `pack` for `Row`'s own two children**: chosen over
  `pack_propagate(False)` on the label frame (the more surface-level way to
  get a fixed width) because `pack_propagate(False)` freezes *height* too
  unless a real height is also configured — for a two-line label+hint stack,
  that risks silently clipping the hint. `grid`'s row height is computed as
  the tallest cell in that row (here, `max(text frame height, control frame
  height)`), which cannot clip either side, and `columnconfigure(0,
  minsize=...)` gives a fixed *minimum* rather than a hard freeze: if a
  future label's wrapped width somehow still exceeded `ROW_LABEL_W`, the
  column would grow to fit it instead of clipping — a strictly safer failure
  mode than `pack_propagate(False)`'s clipping. Column 1 (`control`) is left
  at its default weight (0), so any extra width `Row.pack(fill="x")` hands
  the row (from a stretched card) is *not* distributed into either grid
  column — it is left as trailing space after column 1, i.e. exactly the
  "acceptable" empty margin the reference itself shows to the right of its
  own value column (see the reference screenshot: "Full-screen" sits right
  after the "Current Value" column line, with a large unused margin further
  right — the fix is not "eliminate all whitespace," it's "stop the
  whitespace from separating the label from its value").

**Fit check** (why `ROW_LABEL_W = 140` is safe at every UI-scale step): every
quantity here (`ROW_LABEL_W`, `ROW_LABEL_GAP`, every explicit control
`width=`, `CARD_INNER_W`) is an unscaled constant multiplied by the same `s`
at render time, so their *ratios* are scale-invariant — a check at `s=1` holds
at every step (`self.s = self._dpi_s * UI_SCALE_FACTORS[...]`, `90/100/115/130`
`× _dpi_s`), modulo `int()` rounding of at most a pixel or two, which the
margins below comfortably absorb:
- Tightest case: the "UI scale" row (`afk_clicker.py:1900`, control
  `width=220`, the widest explicit control in the file). `ROW_LABEL_W +
  ROW_LABEL_GAP + 220 = 152 + 220 = 372 ≤ CARD_INNER_W (396)` — **24px of
  margin.**
- "Mouse button" (`afk_clicker.py:1837`, control `width=180`): `152 + 180 =
  332 ≤ 396` — 64px margin.
- "Theme" (`afk_clicker.py:1883`, control `width=180`): same, 64px margin.
- Every `NumBox`-backed row (Interval/Random jitter/Auto-stop/Eat
  every/Hold for) and the `tk.Label`-backed rows (Toggle/Version) shrink-wrap
  to well under 100px — no fit concern.
- Every label's own text (widest measured: "Mouse button"/"Random jitter" at
  86-88px) fits inside `ROW_LABEL_W` (140px) with 52px of margin, so under
  normal conditions **no primary label wraps** — only the one long hint
  ("spreads the rhythm so it is not exact", 210px measured) wraps, from one
  line to two. This is a deliberate, visible side effect (see Edge cases).

**Per-call-site correctness** (all 10 sites, `afk_clicker.py` line numbers
from the table above): every control is either shrink-wrapped (unaffected —
it just now starts at a fixed offset instead of the far right edge) or an
explicit-width `Segmented` that the fit check above covers. None needs any
change to its own construction call; only `Row`'s internals change. The two
inline comments at `afk_clicker.py:1886-1889` and `1893-1899` that currently
justify the "Mouse button"/"UI scale" `Segmented` widths against
`CARD_INNER_W` in terms of the *old* label-expands-to-the-right model (and
reference a stale `docs/spec.md §1`, from a previous story) should be updated
to reference `ROW_LABEL_W`/`ROW_LABEL_GAP` and this feature instead — small,
comment-only follow-up, called out here so it doesn't get missed as dangling
documentation once this `docs/spec.md` is overwritten by the next feature.

## Affected areas
- `afk_clicker.py` only, three spots, all in the same file/layer (no
  multi-layer split needed for this feature):
  - New constants `ROW_LABEL_W`, `ROW_LABEL_GAP` near `afk_clicker.py:160-163`.
  - `Row.__init__` (`afk_clicker.py:1416-1429`) — the layout change above.
  - The two stale inline comments in `_build_settings`
    (`afk_clicker.py:1886-1889`, `1893-1899`) — update their reasoning to
    reference the new constants.
- No data model, schema, or API changes. No new files.

## Edge cases
- **Empty hint** (`hint=None`, most call sites): unaffected — only the label
  `tk.Label` is created, same as today, just now inside a fixed-width column.
- **Long hint text wrapping**: "Random jitter"'s hint (`afk_clicker.py:1832`,
  "spreads the rhythm so it is not exact", 210px measured @ s=1) exceeds
  `ROW_LABEL_W` (140px) and will wrap to two lines where it previously rendered
  on one line with room to spare. This grows that Row's height slightly. This
  is accepted as a direct, minimal consequence of bounding the label column,
  not scope creep — flagged explicitly rather than silently shipped.
  "Auto-stop"'s hint ("0 means never", 86px) fits on one line, no wrap.
- **Font substitution**: label widths above were measured against DejaVu Sans
  (this dev environment's fallback for "Segoe UI", not installed here) — see
  Open questions. The 52px margin on the tightest label fit and the 24px
  margin on the tightest control fit are both sized to absorb reasonable
  font-metric differences on the real target font.
- **UI-scale steps** (90/100/115/130): covered analytically above — every
  quantity scales by the same `s`, so ratios (and therefore all margins) are
  preserved at every step.
- **Window narrower than default** (below `minsize`): out of scope — the
  window cannot get narrower than today's floor until Feature 3 changes
  `_apply_minsize()`; nothing here changes that floor, so this case does not
  arise for Feature 1.
- **A stretched (wide) card**: the entire point of this feature — covered by
  Acceptance criteria below.

## Test impact, argued per case
Per `docs/story.md`'s "Test impact" section, two tests are flagged for this
*story* — neither is triggered by *this feature*:
- `test_minsize_matches_todays_default_size` (`tests/test_ui.py:743-746`) and
  `test_growing_the_window_expands_content_not_the_sidebar` (748-754): both
  assert on `SIDEBAR_W`/`CONTENT_W`/the sidebar's own width, none of which
  this feature touches (`_apply_minsize()` and the sidebar are Feature 3's
  concern). **No change required.**
- `test_card_inner_w_has_no_border_allowance_left` (891-896): asserts
  `CARD_INNER_W == CONTENT_W - 2*CONTENT_PAD - 2*CARD_R == 396`, none of which
  this feature touches (`CARD_R` is Feature 5's concern). **No change
  required** — and this spec's own fit check above depends on `CARD_INNER_W`
  staying exactly 396, so a regression here would be a real signal, not noise
  to silence.
- No test in `tests/test_ui.py` currently asserts on `Row`'s internal
  geometry, `.control`'s position, or the label/control gap (confirmed by
  grep — the only existing `Row`-related test references,
  `tests/test_ui.py:1611` and `:2482`, are docstring/comment mentions of
  *which* Row a reentrancy probe targets, not geometry assertions on it).
  **This feature adds new tests; it does not modify any existing one.**
- No other test file (`test_hotkey.py`, `test_chords_slow.py`,
  `test_updater.py`) references `Row`, `NumBox`, `Segmented`, or any layout
  constant — confirmed by grep, matching `docs/story.md`'s own note that this
  story's blast radius is contained to `test_ui.py`.

**New tests needed** (see Acceptance criteria for the exact assertions): a
new test class, e.g. `RowValueColumn(UITestCase)` in `tests/test_ui.py`,
alongside the existing `WindowResize`/`UIScale` classes.

**A note on testing "a wide window" without depending on the WM**: the
context notes a hard lesson — a test asserting an exact window geometry can
fail on CI because the window manager clamps requests to the screen
(~1024x768 on the runners), and `test_growing_the_window_expands_content_not_
the_sidebar` already resizes to `900x900`-ish today (`geometry("1000x900")`)
seemingly without issue locally, but that height already exceeds 768. **This
feature's own "stretched card" tests must not repeat the ticket's literal
"1200x820"** (both dimensions would risk clamping on the 1024x768 runners).
Recommend `self.root.geometry("900x760")` (comfortably under both bounds,
comfortably above the default minsize width so `content` genuinely stretches)
for any acceptance criterion that needs a wider-than-default window, and pump
`self.root.update()` before reading `winfo_width()`/`winfo_x()` on anything,
per the existing convention. The literal 1200x820 case is still worth a manual
/exploratory check (a screenshot, as already taken this session) but should
not be what an automated test's pass/fail hinges on.

## Acceptance criteria
- [ ] Given the app built at its default (minsize) window size, when reading
      `control.winfo_x()` for a sampled Row's control frame relative to its
      `Row` parent (e.g. `self.ui.click_ms.master`, the "Interval" row's
      control in the Clicking card), then it equals
      `int((app.ROW_LABEL_W + app.ROW_LABEL_GAP) * self.ui.s)`.
- [ ] Given the window then resized to `900x760` (see Test impact note above
      for why not 1200x820) and `self.root.update()` pumped, when re-reading
      the same `control.winfo_x()`, then the value is **unchanged** from the
      previous criterion — the label-to-control gap does not grow when the
      card stretches. This is the literal fix for the reported "gulf."
- [ ] Given that same stretched window, when comparing the control's right
      edge (`control.winfo_x() + control.winfo_width()`) to the card's own
      inner width, then a non-zero trailing margin exists — the extra width
      became margin after the control, not a wider gap before it.
- [ ] Given each UI-scale step (`self.ui._apply_ui_scale("90"/"100"/"115"/
      "130")`), when measuring the "UI scale" row's own `Segmented` control
      (`_build_settings`, `afk_clicker.py:1900`, the widest explicit control
      at `width=220`), then it does not overflow its card:
      `app.ROW_LABEL_W + app.ROW_LABEL_GAP + 220 <= app.CARD_INNER_W` (a
      constant-level check, `152 + 220 = 372 <= 396`) and the built widget's
      own `winfo_x() + winfo_width()` stays within the card's
      `winfo_width()` at each step.
- [ ] Given the "Random jitter" row (`afk_clicker.py:1832`), when the UI is
      built, then its hint `Label`'s `wraplength` is
      `int(app.ROW_LABEL_W * self.ui.s)` (not `0`), and the hint's own
      rendered width does not exceed that value (i.e. it wraps instead of
      overlapping the control column).
- [ ] Given every existing `Row(...)` call site (all 10 listed in Background,
      spanning `_build_content` and `_build_settings`, including the
      Minecraft-only Eating card), when the app is built with a Minecraft
      profile selected (so the Eating card exists) and with Settings open,
      then no exception is raised and every control (`hotkey_label`,
      every `NumBox`, every `Segmented`, `version_label`) is present and
      shows its expected value — i.e. the existing app-builds-cleanly
      coverage (selftest, `HotkeyPersistence`, `Themes`-driven rebuilds)
      continues to pass unmodified.
- [ ] Given the full suite (`DISPLAY=:99 .../venv/bin/python -m unittest
      discover -s tests -t .`), when run after this change, then it passes
      at least the 240-test baseline (`OK (skipped=5)`) plus this feature's
      new `RowValueColumn` tests, with zero existing tests modified (per
      Test impact above). The known `Tcl_AsyncDelete` shutdown flake
      (~1 run in 4, exit 134, no summary) is pre-existing — re-run once, do
      not chase it.

## Open questions
- **Font-metric proxy**: label widths in Background/Proposed approach were
  measured with `tkinter.font.Font.measure()` against this Linux dev box's
  actual available font (DejaVu Sans — "Segoe UI" isn't installed here and
  Tk silently substitutes), not the real target font. Proceeding under the
  assumption that the 52px margin on the tightest label fit and 24px margin
  on the tightest control fit absorb the difference — both are comparable
  general-purpose UI sans-serif fonts at similar weight/size, so a large
  divergence is unlikely. Not a blocker; if the developer has access to a
  Windows box (or the CI runner's actual font) during implementation, a
  quick re-measurement there would tighten this from "should hold" to
  "confirmed," but isn't required to proceed.
- **`ROW_LABEL_W = 140` / `ROW_LABEL_GAP = 12` are proposed, not
  externally mandated** numbers — derived from the measurements and fit
  check above, not from any existing constant in the file. If the reviewer's
  hands-on test pass (screenshot comparison against
  `handoff/nvidia-reference/02-graphics-program-settings.png`) finds the
  column visually too close or too far from the labels, adjusting these two
  constants is a same-spec tweak, not a re-open of the approach.

## Risk / rollback notes
- Single class (`Row`) plus two new constants; every call site is
  unparameterized (`Row(parent, label, s, hint=None)` keeps its exact
  signature), so no call site needs edits. Revert is a one-file, single-class
  diff.
- The main risk is a control overflowing its card at some UI-scale step if
  the font-metric assumption above is wrong enough to blow through the 24px
  margin on the "UI scale" row — mitigated by the explicit per-scale-step
  acceptance criterion above, which would catch it before merge rather than
  in the field.
- `grid` and `pack` do not mix within the same *container* widget, but they
  are never asked to here: `Row` itself switches its own two children from
  `pack` to `grid`; every `Row` instance is still packed (`Row(...).pack(...)`)
  by its *parent* card exactly as before — that's a different container, so
  there is no grid/pack conflict introduced.
