# Implementation: Flat minimal restyle (story #24, Feature 5 of 5 — last feature)

## Summary
Every rounded-corner shape in the app (`Button`, `Segmented`'s outer track and
selection pill, `StatusPill`, `card()`'s shell, `GameItem`, `SettingsItem`)
now paints a plain `create_rectangle` instead of `round_rect()`; `round_rect()`,
`_round_rect_points()`, `_arc_points()`, `CARD_R`, and `PILL_R` are deleted
outright, with `CARD_R`'s surviving padding role renamed `CARD_PAD = 12`.
`section()` drops `.upper()`, goes 10pt bold (per `docs/design.md`), and gains
an optional right-aligned `action_factory` slot, now returning its header
`Frame` instead of the bare `Label`. `GameItem`/`SettingsItem` gain a left-edge
`accent_bar` canvas item, created once and toggled strictly on `self.selected`
in `_paint()`. No geometry, persisted state, or color-token value changed. The
full suite (276 baseline + 8 net new) passes clean twice in a row under Xvfb.

## Changes by file

- `afk_clicker.py`
  - Deleted `import math` (its only caller, `_arc_points()`, is gone).
  - Deleted `PILL_R`/`CARD_R`; added `CARD_PAD = 12` in `CARD_R`'s place.
    `CARD_INNER_W`'s formula now reads `CARD_PAD` in place of `CARD_R` —
    verified `== 396` unchanged.
  - Deleted `_arc_points()`, `_round_rect_points()`, `round_rect()` — zero
    remaining callers after the swap below.
  - `Button.__init__`: shape call → `create_rectangle(1, 1, w-1, h-1, ...)`.
  - `Segmented.__init__`/`_paint`: outer track and selection pill shape calls
    → `create_rectangle`; `_paint()`'s pill reposition now calls
    `self.coords(self.pill, seg*idx+2, 2, seg*(idx+1)-2, self.h-2)` directly
    instead of through `_pill_pts`, which is deleted (its only caller).
  - `StatusPill.__init__`: shape call → `create_rectangle`.
  - `section(parent, text, s, top=14, action_factory=None)`: now builds a
    `tk.Frame` (`row`), packs it with the same `pady` as before, packs a
    `Label` (sentence case, no more `.upper()`, 10pt bold per
    `docs/design.md` §1) inside it `side="left"`, and — only if
    `action_factory` is given — calls `action_factory(row).pack(side="right")`.
    Returns `row`, not the label; both real call sites
    (`hotkey_pane`'s header, `self.eat_section`) only ever call
    `.pack()`/`.pack_forget()` on the return value, which a `Frame` supports
    identically to the old `Label`.
  - `card()`: `pad = int(CARD_PAD * s)`; shape call → `create_rectangle(0, 0,
    w, h, fill=CARD, outline="")`. Docstring and the `tag_lower` comment
    updated — both previously described rounding that no longer happens.
  - `GameItem.__init__`/`_paint`: shape call → `create_rectangle`; new
    `self.accent_bar = self.create_rectangle(0, 0, bar_w, h, fill=ACCENT,
    outline="", state="hidden")` created once, right after `self.shape`
    (per `docs/spec.md` §3's literal code sample — this ordering matters,
    see "Key decisions"), `bar_w = int(3 * s)`. `_paint()` gains
    `self.itemconfig(self.accent_bar, state="normal" if self.selected else
    "hidden")`.
  - `SettingsItem.__init__`/`_paint`: identical treatment — shape call, new
    `accent_bar` created and toggled the same way, gated strictly on
    `self.selected`, independent of `self.has_update`.
- `tests/test_ui.py`
  - `test_card_inner_w_has_no_border_allowance_left` (`ThemeValues`-adjacent
    global test): formula updated to `app.CARD_PAD` in place of
    `app.CARD_R`; still asserts `== 396`.
  - `PillAndCardRadii` → **`FlatChrome`** (full rewrite, not a touch-up —
    its premise, "every shape call goes through `round_rect`," no longer
    holds): `test_no_widget_calls_round_rect`,
    `test_card_r_and_pill_r_are_gone`, one `test_*_shape_is_a_plain_rectangle`
    per widget (`Button`, `Segmented`'s outer track, `StatusPill`,
    `GameItem`, `SettingsItem`, `card()`'s shell), and
    `test_segmented_selection_pill_moves_to_the_correct_segment` (position
    assertion, replacing the two deleted true-capsule-geometry tests — that
    geometry no longer exists). `test_round_rect_draws_a_true_capsule_...`
    is deleted outright (tested a function this feature removes).
  - `RoundedCanvasBackgrounds`: kept the class name (spec's own "Test
    impact" section refers to it as the thing being rewritten, not
    replaced under a new name) but rewrote `_rounded_canvases` →
    `_flat_bg_canvases`, re-keyed off widget *classes*
    (`Button`/`Segmented`/`StatusPill`/`GameItem`/`SettingsItem`, plus
    `type(widget) is tk.Canvas` — exact type, not `isinstance`, to catch
    only `card()`'s shell, the sole bare `tk.Canvas()` construction in the
    file, grep-confirmed) instead of "any canvas holding a polygon item."
    Same underlying invariant (a full-bleed background canvas's own `bg`
    must match its parent's), same test method purpose, new finder.
  - New `SectionHeader(unittest.TestCase)`: `test_section_text_is_not_uppercased`,
    `test_section_with_no_action_has_no_reserved_gap`,
    `test_section_action_factory_is_actually_wired` — the direct regression
    test against `section()`'s slot mechanism (see "Deviations" for the one
    assertion-strictness change from the spec's own sketch).
  - New `RailAccent(unittest.TestCase)`:
    `test_selected_game_item_shows_the_accent_bar` /
    `test_unselected_game_item_hides_the_accent_bar` (each parametrized over
    `collapsed=True/False` via `subTest`),
    `test_settings_item_accent_bar_is_independent_of_has_update`,
    `test_running_dot_and_accent_bar_coexist`.

## Key decisions / tradeoffs

- **Accent bar creation order.** `docs/design.md`'s prose ("rendered
  *before* (below) `self.shape`... creating the accent bar *after*
  `self.shape` achieves this layering") is internally inconsistent — Tk's
  last-created-is-topmost rule means creating the bar *after* the shape
  puts it *on top of*, not below, the shape. Followed the design's own
  literal code sample instead (`docs/spec.md` §3 and `docs/design.md`'s
  pixel-level spec both place the `accent_bar` creation call directly after
  `self.shape`'s), which is also the only ordering that actually renders a
  visible bar: `self.shape` spans `x=1..w-1`, and the accent bar's leftmost
  column (`x=0..1`) is the only part `self.shape` never covers, so a bar
  created *before* the shape would have ~all of its width painted over.
- **`RoundedCanvasBackgrounds` re-keyed by class, not bbox heuristic.** The
  spec offered two options (widget classes, or "a rectangle's own bbox
  spans its canvas's full width/height"). Went with widget classes: it
  sidesteps `card()`'s shell having no fixed `width` option (its real width
  only exists at pack-time, via `winfo_width()`), which would have forced a
  mapped-widget geometry read the story has repeatedly flagged as a hazard
  (stale-but-plausible on X11, `0`/`1` on Windows). Class-based matching
  needs no `winfo_*` call at all — `cget("bg")` is stable regardless of
  mapped state — and `type(widget) is tk.Canvas` (exact type) cleanly
  isolates `card()`'s shell from the five `tk.Canvas` *subclasses* without
  needing a bbox comparison for it at all.
- **Kept `RoundedCanvasBackgrounds`'s class name.** The spec's own "Test
  impact" section refers to this class by its existing name while
  describing its rewrite ("`RoundedCanvasBackgrounds` (`:2206-2230`) —
  rewritten per..."), never proposing a new name the way it explicitly did
  for `PillAndCardRadii` → `FlatChrome`. Renamed only the now-inaccurate
  internal docstring/method name (`_rounded_canvases` → `_flat_bg_canvases`,
  test method `test_every_rounded_canvas_...` →
  `test_every_flat_bg_canvas_...`), not the class.

## Deviations from spec

- **`test_section_action_factory_is_actually_wired`'s assertion strictness.**
  The spec's own sketch (`docs/spec.md` "New tests needed") uses
  `assertGreater(action.winfo_x(), label.winfo_x() + label.winfo_width())`.
  Run against the real `section()`/`pack()` layout, the action widget's
  `winfo_x()` lands exactly *equal* to `label.winfo_x() + label.winfo_width()`
  (adjacent packing, no gap) — `assertGreater` failed on a correct
  implementation. Changed to `assertGreaterEqual`, which still proves "right
  of the label, same row" (the actual acceptance criterion) without
  demanding a gap the spec never asked `section()` to reserve. Verified by
  running the test against the real implementation, not by assuming the
  spec's sketch was exactly right.
- Everything else matches `docs/spec.md`/`docs/design.md` as written — no
  other deviations.

## Known limitations

- The accent bar's exact thickness (3px at s=1 / 2px at s=0.675) and the
  section header's 10pt size are `docs/design.md`'s own calls, not
  independently re-derived here; visual acceptance against
  `handoff/nvidia-reference/*.png` side-by-side is the story's own
  end-to-end pass, not this feature's.
- `RoundedCanvasBackgrounds`'s class-based finder is a fixed list
  (`Button`, `Segmented`, `StatusPill`, `GameItem`, `SettingsItem`, plus
  `card()`'s bare-`tk.Canvas` shell) that would need a manual update if a
  future widget adds a new full-bleed background canvas — the same
  maintenance shape the spec itself accepted as the tradeoff for dropping
  the now-broken "any polygon" invariant.

## How to verify locally

```
DISPLAY=:99 <venv-python> -m unittest discover -s tests -t .
```

Ran twice (once against `:99`, once against `:98`) — both `OK (skipped=5)`,
284 tests (276 baseline + 9 `FlatChrome` − 8 old `PillAndCardRadii` [net +1],
+3 `SectionHeader`, +4 `RailAccent`; `RoundedCanvasBackgrounds` is a
rewrite-in-place with no test-count change).

Spot checks also run directly:
```python
import afk_clicker as app
app.CARD_INNER_W          # 396
hasattr(app, "round_rect")   # False
hasattr(app, "CARD_R")       # False
hasattr(app, "PILL_R")       # False
```

Not independently verified in this session (CI-only): the Windows/macOS legs
of the matrix, and a pixel-level side-by-side against
`handoff/nvidia-reference/*.png` — that comparison is the story's own
closing end-to-end pass per `docs/spec.md`'s final section, not this
feature's job.
