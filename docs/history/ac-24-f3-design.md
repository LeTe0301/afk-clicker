# Design: Icon rail — collapsing sidebar (story #24, Feature 3 of 5)

## Summary

The sidebar collapses from a full-width rail with profile names to an icon-only rail below a width threshold. Every `GameItem` and `SettingsItem` retains its click target and functionality but displays as a centered circular badge with a single initial letter, centered both horizontally and vertically within the 64px-wide rail. The collapse is purely visual; navigation is unchanged. The window's minimum width floor is rederived to reflect the collapsed-rail state so the collapse threshold can actually be reached by the user dragging.

## ui-ux-pro-max: visual consistency and readability

**Style:** Minimal, flat, no new primitives — the app's existing `create_oval` circle and `create_text` letter reuse the drawing idioms already proven in `GameItem`'s dot and `StatusPill`.

**Palette:**
- Circle fill (state indicator): `OK` (#5cc9a4) when running, `LINE` (#3a4048) when idle
- Letter fill (selection indicator): `INK` (#e4e7ea) when selected/running, `MUTED` (#9299a3) when idle
- `SettingsItem` update dot: `ACCENT` (#e08a55) in the top-right corner, 5px diameter

**Typography:** "Segoe UI", 10.5pt, **bold**, uppercase letter — same family and weight as expanded `GameItem` text, but centered instead of left-anchored.

**Relevant UX guideline applied:**
- Icon legibility across all supported scales: A single capital letter must remain legible at the smallest compound scale (macOS 0.75x DPI × 90% UI-scale = s=0.675), where the badge becomes 18px and the font 7pt. See "Scale and DPI interaction" below for the full worst-case analysis.
- State through color, not shape: running/idle is circle color (not a separate badge), selection is text color (not a separate highlight).
- Touch target: 64px × 38px per rail item (full width, full height), same as expanded — no reduction in usability.

## Component reuse & new structures

**Reused unchanged:**
- `GameItem` and `SettingsItem` core structure (state machine, `_paint()` method)
- `create_oval` primitive (the same one `GameItem.dot` and `StatusPill.dot` already use)
- `create_text` primitive (same font stack, same color tokens)
- `_request_rebuild()` coalescing machinery (reused from Appearance/UI-scale triggers)
- `pack()`/`pack_forget()` visibility toggle for sidebar controls

**New constants (placed with `SIDEBAR_W`/`CONTENT_W`, after line 176 in afk_clicker.py):**

```python
SIDEBAR_RAIL_W = 64          # collapsed rail width, room for a centered
                              # COLLAPSED_BADGE_D badge plus ~18px margin
                              # on each side at s=1; survives to ~43px at
                              # worst-case compound scale (s=0.675)

RAIL_COLLAPSE_THRESHOLD = SIDEBAR_W + 1 + CONTENT_W
    # Same as today's minimum width -- below this, the expanded rail plus
    # full content no longer fit, so collapse

COLLAPSED_BADGE_D = 28        # badge diameter at s=1 (18px at worst-case
                              # compound scale s=0.675); survives as 18px
                              # diameter containing a 7pt letter
```

**New instance attribute** (placed near `self._settings_open`, around line 1587):

```python
self._rail_collapsed = False   # session-only, re-derived at top of _build_ui()
```

**New bound method** (placed after `__init__`'s first `self._build_ui(s)`
call returns, not before it — see the PR #41 round 3 correction below):

```python
self.root.bind("<Configure>", self._on_root_resize)
```

And the handler:

```python
def _on_root_resize(self, event):
    """Debounce the collapse check on threshold-crossing (spec §2).

    The `event.widget is not self.root` guard is load-bearing, not
    defensive: every widget's default bindtags include its toplevel's own
    pathname, so `root.bind(...)` -- unlike `root.bind_all(...)` -- also
    fires for every descendant's own <Configure>, not just root's. Without
    this guard, construction alone drives ~100+ spurious calls here for
    child Frames/Canvases before the rest of `__init__`'s state exists,
    crashing construction outright.
    """
    if event.widget is not self.root:
        return
    collapsed = event.width < int(RAIL_COLLAPSE_THRESHOLD * self.s)
    if collapsed != self._rail_collapsed:
        self._rail_collapsed = collapsed
        self._request_rebuild()
```

**Correction (PR #41 round 3):** the guard above is real and load-bearing,
but it is not sufficient by itself. It filters *spurious* `<Configure>`
events bubbling up from descendant widgets during construction; it does
nothing to stop a *genuine*, root-targeted `<Configure>` — the kind only a
real window manager generates, after mapping, and which Xvfb (no WM) never
produces. Binding `<Configure>` before `__init__`'s first `_build_ui(s)`
call finishes left exactly that door open: a genuine root event lands mid-
construction, passes the guard (it *is* `self.root`), and calls
`_request_rebuild()` before `self.click_ms` and other Clicking-tab
attributes exist — an `AttributeError` inside the reentrant rebuild that
`card()`'s own `update_idletasks()` triggers (confirmed on macOS CI, never
reproducible under Xvfb). The design that actually closes this: bind
`<Configure>` only *after* the first `_build_ui(s)` call has returned (see
`docs/spec.md`'s matching correction), so no root-targeted event —
spurious or genuine — can reach the handler until construction is done.

## States & visual design

### Expanded rail (normal, default on launch)

**Layout:**
```
┌─ Sidebar ─────┐
│               │
│ GAMES    2    │   (count label, visible)
│               │
│ ┌───────────┐ │
│ │ ◯         │ │   GameItem 1: "Profile A"
│ │  Profile A│ │   Circle: LINE (gray) / OK (green)
│ └───────────┘ │   Text: MUTED (idle) / INK (selected/running)
│               │
│ ┌───────────┐ │
│ │ ◯         │ │   GameItem 2: "Minecraft"
│ │ Minecraft │ │
│ └───────────┘ │
│               │
│ ─────────────── │   divider (LINE)
│               │
│ ┌───────────┐ │   SettingsItem
│ │ ◯         │ │   Circle: LINE / darker when selected
│ │ Settings  │ │   Text: MUTED / INK (selected)
│ │         · │ │   Small dot if has_update
│ └───────────┘ │
│               │
│ ┌─────────┐   │   "Add current game" button
│ │    +    │   │   (full-width, scaled text inside)
│ └─────────┘   │
└───────────────┘
```

**Geometry:** `side` width = `int(SIDEBAR_W * s)` = 208px at s=1.
- `count_label`: visible, packed at top with standard padding.
- `list_frame`: packed with `padx=8*s`.
- `GameItem`: width defaults to `SIDEBAR_W - 16 = 192px` at s=1, height 38px. Background circle and text positioned per existing code, unaffected.
- Divider: 1px LINE-colored frame.
- `SettingsItem`: width defaults to `SIDEBAR_W - 16 = 192px` at s=1, height 38px.
- "Add current game" button: label = "Add current game", width = `SIDEBAR_W - 28`.

**Colors (idle, unselected):**
- Background shape: `BG` (#15171a).
- Circle (dot): `LINE` (#3a4048).
- Text: `MUTED` (#9299a3).

**Colors (selected):**
- Background shape: `CARD_HI` (#262a30) on hover, `CARD` (#1c1f23) on click-select.
- Circle (dot): `LINE` (unchanged).
- Text: `INK` (#e4e7ea).

**Colors (running):**
- Circle (dot): `OK` (#5cc9a4).
- Text: `INK` (#e4e7ea).

Contrast check (dark theme, all on `BG` #15171a):
- `INK` (#e4e7ea) on `BG`: **14.47:1** ✓ (needs 4.5:1)
- `MUTED` (#9299a3) on `BG`: **6.25:1** ✓ (needs 4.5:1)
- `OK` (#5cc9a4) circle on `BG`: **6.17:1** ✓ (needs 3:1 for graphical)

### Collapsed rail (below threshold)

**Layout:**
```
┌─ Rail ─┐
│        │
│ ┌──┐   │   GameItem 1: "Profile A" → badge "A"
│ │A │   │   Circle: LINE / OK
│ └──┘   │   Letter: MUTED / INK
│        │
│ ┌──┐   │   GameItem 2: "Minecraft" → badge "M"
│ │M │   │
│ └──┘   │
│        │
│ ────── │   divider (LINE)
│        │
│ ┌──┐   │   SettingsItem → badge "S"
│ │S*│   │   Letter: MUTED / INK
│ └──┘   │   Small ACCENT dot in top-right (if has_update)
│        │
│ ┌──┐   │   "Add current game" button → "+"
│ │+■│   │   (full-width narrow button, full-height)
│ └──┘   │
│        │
└────────┘
```

**Geometry:** `side` width = `int(SIDEBAR_RAIL_W * s)` = 64px at s=1, 43px at s=0.675.
- `count_label`: **hidden**, `pack_forget()` (no room).
- `list_frame`: still packed but items are narrower.
- `GameItem`: width defaults to `SIDEBAR_RAIL_W - 16 = 48px` at s=1, height 38px. Constructor receives `collapsed=True`.
  - Inside `__init__`, if collapsed:
    - Circle centered at (w/2, h/2) = (24, 19) at s=1.
    - Diameter `COLLAPSED_BADGE_D * s` = 28px at s=1, 18px at s=0.675.
    - Circle coords: `(24 - 14, 19 - 14, 24 + 14, 19 + 14)` = `(10, 5, 38, 33)` at s=1.
    - Letter centered at (24, 19) using `create_text(..., text=initial, anchor="center")`.
    - Font: "Segoe UI", 10.5pt, bold at s=1 (7pt at s=0.675).
- Divider: 1px LINE-colored frame (unchanged).
- `SettingsItem`: width defaults to `SIDEBAR_RAIL_W - 16 = 48px`, height 38px. Constructor receives `collapsed=True`.
  - Circle and "S" letter centered per GameItem.
  - If `has_update and collapsed`: small `ACCENT` dot (`create_oval`, 5px diameter) at top-right corner of the circle. Positioned at approximately `(24 + 14 - 3, 19 - 14 + 3)` = `(35, 8)` at s=1 (top-right edge, inset slightly).
- "Add current game" button: label = "+", width = `SIDEBAR_RAIL_W - 28 = 36px`, same height.

**Colors:** Identical to expanded state (circle fill, text fill, all the same tokens).

**Contrast check:** Same pairings, same threshold, same result. Readability is maintained.

### Transition (threshold crossing)

**Behavior:** When the window's width crosses `RAIL_COLLAPSE_THRESHOLD * s`, the `<Configure>` event fires. The handler compares and, if the collapsed state flips, calls `_request_rebuild()`. This triggers a full `_rebuild_ui()` via `after_idle`, which destroys and rebuilds all widgets. The new rail state is determined by re-deriving `self._rail_collapsed` at the top of `_build_ui()`.

**Visual result:** An instant transition from expanded to collapsed (or vice versa) on the next event loop idle. No animation, no fade — the rebuild is complete and the window is redrawn in place. This is consistent with the existing behavior for Appearance and UI-scale changes.

**Edge case (exact threshold):** A window exactly at `width == threshold` stays expanded (strict `<` inequality). No flicker.

## Geometry & pixel-level details

### Constants (proposed and confirmed, with worst-case scale analysis)

```python
SIDEBAR_RAIL_W = 64
COLLAPSED_BADGE_D = 28
RAIL_COLLAPSE_THRESHOLD = SIDEBAR_W + 1 + CONTENT_W  # = 661 at s=1
```

**Worst-case compound scale (the constraint that bounds all measurements):**

Per `afk_clicker.py:1544`, `self.s = self._dpi_s * UI_SCALE_FACTORS[...]`. On macOS, `_dpi_s ≈ 0.75`; at the 90% UI-scale step, `UI_SCALE_FACTORS["90"] = 0.9`. These **multiply**:

```
Worst case: s = 0.75 × 0.9 = 0.675

At s=0.675:
  SIDEBAR_RAIL_W = 64 × 0.675 = 43.2px → int(43px)
  COLLAPSED_BADGE_D = 28 × 0.675 = 18.9px → int(18px)
  Letter font = 10.5 × 0.675 = 7.09pt → int(7pt)
```

This is logged as backlog entry **G#23 / GH#35**: "macOS reports `_dpi_s` ~0.75, so the 90% UI-scale step renders 5pt labels." The spec's assumption (story ac-17) that `_dpi_s >= 1.0` was simply wrong about macOS. See backlog.md for the three candidate resolutions to G#23 (add an `fs()` floor, drop 90% on low-DPI displays, or accept it).

**Rationale for these constants against the worst case:**

- **SIDEBAR_RAIL_W = 64:** At s=0.675, becomes 43px actual width. This is still sufficient for a centered 18px badge (with ~12.5px margin on each side). Readability is tight but acceptable given the existing codebase already renders 5–6pt labels at this scale (backlog G#23).

- **COLLAPSED_BADGE_D = 28:** At s=0.675, becomes 18px actual diameter. A 7pt letter in an 18px circle is marginal but legible — better than the 5–6pt baseline the app already ships. If G#23 is resolved by adding an `fs(base, s)` floor (preventing fonts below 8pt), this design automatically benefits without code changes; if G#23 is resolved by dropping the 90% step on macOS, the problem never arises. If G#23 is resolved by acceptance, this feature matches that same acceptance.

- **RAIL_COLLAPSE_THRESHOLD = 661 (at s=1):** The exact width at which the expanded sidebar plus full content exactly fits. Below this, one of them must shrink. The rail is the flexible component (it collapses); content stays fixed. This is deterministic and requires no guesswork. At s=0.675, the threshold becomes 661 × 0.675 = 446.2px, still reachable by dragging.

**Interaction with G#23 (open decision, explicitly noted):**

This design does **not** assume a specific resolution to G#23. It inherits the same scale hazard the existing code already carries:

- If G#23 chooses to add an `fs(base, s)` floor across ~20 font call sites, this feature's 7pt becomes a floored 8pt at worst case, improving readability.
- If G#23 chooses to drop the 90% step on low-DPI displays, the worst case becomes s=0.75 × 1.0 = 0.75, yielding 21px badge and 7.875pt ≈ 8pt font, improving readability further.
- If G#23 chooses to accept the status quo, this feature operates at the same marginal readability the app already accepts for other text.

The feature **does not depend on any of these outcomes** — it is usable under any resolution, and improves with any choice that benefits text rendering overall. This is by design: Feature 3 does not reopen G#23, but it also does not ignore it.

### Drawing order & layering

**GameItem, collapsed (`__init__`, inside `if collapsed:` branch):**

```python
w, h = int((SIDEBAR_RAIL_W - 16) * s), int(38 * s)  # e.g., 48, 38 at s=1; 32, 25 at s=0.675
cx, cy = w / 2, h / 2                                # e.g., 24, 19 at s=1; 16, 12.5 at s=0.675

# Circle (state indicator)
d = int(COLLAPSED_BADGE_D * s)                       # e.g., 28 at s=1; 18 at s=0.675
self.dot = self.create_oval(
    cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2,  # e.g., (10, 5, 38, 33) at s=1; (7, 3, 25, 21) at s=0.675
    fill=LINE, outline=""
)

# Letter (selection indicator)
initial = profile["name"][:1].upper() if profile["name"] else "?"
self.text = self.create_text(
    cx, cy, text=initial, anchor="center", fill=MUTED,
    font=("Segoe UI", int(10.5 * s), "bold")        # e.g., 10.5pt at s=1; 7pt at s=0.675
)
```

**SettingsItem, collapsed (same structure, plus update dot):**

```python
w, h = int((SIDEBAR_RAIL_W - 16) * s), int(38 * s)
cx, cy = w / 2, h / 2
d = int(COLLAPSED_BADGE_D * s)

# Circle
self.dot = self.create_oval(
    cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2,
    fill=LINE, outline=""
)

# Letter "S"
self.text = self.create_text(
    cx, cy, text="S", anchor="center", fill=MUTED,
    font=("Segoe UI", int(10.5 * s), "bold")
)

# Update indicator (small corner dot) — only if collapsed AND has_update
if has_update:
    corner_d = int(5 * s)
    corner_x = cx + d / 2 - corner_d / 2 - int(2 * s)  # inset 2px from edge
    corner_y = cy - d / 2 + corner_d / 2 + int(2 * s)
    self.update_dot = self.create_oval(
        corner_x - corner_d / 2, corner_y - corner_d / 2,
        corner_x + corner_d / 2, corner_y + corner_d / 2,
        fill=ACCENT, outline=""
    )
else:
    self.update_dot = None
```

**`_paint()` method (unchanged for both):**
The existing `_paint()` methods only call `itemconfig()` on stored canvas item ids (`self.dot`, `self.text`), so they work identically whether those items are a small dot-and-label pair or a centered badge-and-letter pair. No branching needed in `_paint()`.

### SettingsItem `has_update` visual design (collapsed)

**Decision: Initial-letter badge + corner accent dot (same mechanism as GameItem).**

The spec flagged this as an open question: bespoke gear glyph vs. same initial-letter "S" badge. I choose the initial-letter "S" because:

1. **Consistency:** One drawing mechanism, not two, matches the app's existing "uniform approach" philosophy (see spec's non-goals).
2. **Simplicity:** Guaranteed readability at all scales; a 28px gear drawn from primitives carries risk of becoming mush at the worst-case 18px.
3. **Precedent:** The reference's own "Redeem" icon (shown in 01-system-performance.png) uses an accent-dot-on-icon pattern for the pending-action signal — the exact same pattern the spec proposes here for `has_update`. We adopt the pattern, not the specific glyph.
4. **Future-proof:** If a bespoke gear becomes desirable (after seeing rendered result), it is a one-line change in `SettingsItem.__init__`'s collapsed branch only, with no impact on the rest of the system.

The small `ACCENT` corner dot (5px diameter) is drawn only when `collapsed and has_update`, positioned at the top-right of the badge with a 2px inset. This is:
- Visually distinct from the running-state circle color (which changes the circle fill, not adds a marker).
- Readable at all scales (5px × 0.675 = 3.4px, still distinguishable in a 18px circle).
- Consistent with the reference's own pending-action signal pattern.

### Sidebar visibility toggle

When `self._rail_collapsed` becomes `True`:

1. `count_label` is `pack_forget()`-ed (no room in 64px for "GAMES 2").
2. All `GameItem` instances are recreated with `collapsed=True` (via `_rebuild_ui()` → `_rebuild_list()`).
3. `SettingsItem` is recreated with `collapsed=True`.
4. "Add current game" button: text changes from "Add current game" to "+", width changes from `SIDEBAR_W - 28` to `SIDEBAR_RAIL_W - 28`.

When `self._rail_collapsed` becomes `False`:

1. `count_label` is `pack()`-ed again.
2. All `GameItem` instances are recreated with `collapsed=False`.
3. `SettingsItem` is recreated with `collapsed=False`.
4. "Add current game" button: text and width return to normal.

### Minimum window size change

**`_apply_minsize()` change:**

```python
def _apply_minsize(self, grow_only=False):
    minw = int((SIDEBAR_RAIL_W + 1 + CONTENT_W) * self.s)  # changed from SIDEBAR_W
    minh = int(690 * self.s)
    self.root.minsize(minw, minh)
    if not grow_only:
        default_w = int((SIDEBAR_W + 1 + CONTENT_W) * self.s)  # unchanged formula
        self.root.geometry(f"{default_w}x{minh}")
        return
    # grow_only branch unchanged
```

This change decouples the minsize floor from the default launch geometry:
- **Minsize floor:** `SIDEBAR_RAIL_W + 1 + CONTENT_W` (small, allows collapse).
- **Default launch size:** `SIDEBAR_W + 1 + CONTENT_W` (expanded, familiar).

**Result:** The app launches at the familiar expanded width (users see no change). The window can be dragged down to the smaller floor, triggering collapse at the threshold.

## Accessibility & platform notes

### Touch target and click precision

- Each `GameItem`/`SettingsItem` remains 64px wide × 38px tall at collapsed state (full rail width, full item height).
- Click hit-testing: The canvas itself is 64px wide, and the item's click binding (`<Button-1>`) is not reduced. No loss of hit-box.
- Desktop only: This app is tkinter on Linux/Windows/macOS; no mobile/touch-friendly constraints beyond "large enough for a mouse."

### Color contrast (collapsed state, dark theme)

All the same tokens are reused; contrast ratios are identical:

- `INK` on `BG`: **14.47:1** (text, needs 4.5:1) ✓
- `MUTED` on `BG`: **6.25:1** (text, needs 4.5:1) ✓
- `OK` circle on `BG`: **6.17:1** (graphical, needs 3:1) ✓
- `ACCENT` corner dot on `BG`: **6.79:1** (graphical, needs 3:1) ✓

Light theme (same pairings on `BG` #e8ebf0):

- `INK`: **14.58:1** ✓
- `MUTED`: **5.22:1** ✓
- `OK`: **4.89:1** ✓
- `ACCENT`: **5.21:1** ✓

### Keyboard navigation

This is a canvas-based widget; no keyboard input affects the rail itself. Tab navigation lands on controls within the active pane (in content), not on the rail. Click-only navigation for rail items, as is existing behavior.

### Scale and DPI interaction (worst-case analysis)

**Compound scaling:** `self.s = self._dpi_s * UI_SCALE_FACTORS[...]`. On all platforms, this multiplies, not adds:

- Linux/Windows: `_dpi_s ≈ 1.0 at 96 DPI` (typical) → worst case: `s = 1.0 × 0.9 = 0.9`
- macOS: `_dpi_s ≈ 0.75` → worst case: `s = 0.75 × 0.9 = 0.675`
- Very high DPI Linux/Windows: `_dpi_s > 1.0` → worst case: `s = high × 0.9`, but floor analysis still applies

At the true worst case (s=0.675):
- Rail width becomes 43px (from 64px)
- Badge diameter becomes 18px (from 28px)
- Letter font becomes 7pt (from 10.5pt)

All constants scale uniformly by `self.s`. There are no special cases or breakpoints; the design carries no assumptions about absolute pixel counts being available. Legibility at 18px/7pt is marginal (same tier as the existing 5–6pt labels the app already renders at this scale per G#23), and will improve with any resolution to G#23 that improves text rendering generally.

## Traceability to spec acceptance criteria

| Criterion | Design section |
|---|---|
| Rail launched expanded, never at the collapsed floor. | States: "Expanded rail." Top of `_build_ui()` checks `winfo_ismapped()` before re-deriving `_rail_collapsed`; on first launch, it's unmapped, so `_rail_collapsed` stays `False`. |
| Minsize floor is strictly smaller than default launch width. | Geometry: `_apply_minsize()` uses `SIDEBAR_RAIL_W` for floor, `SIDEBAR_W` for default. |
| Rail collapses below threshold; re-expands above; no hysteresis. | States: Collapsed/expanded layouts. `_on_root_resize()` uses strict `<` inequality; one threshold. |
| Collapsed items still navigate on click. | States: Collapsed rail. Click binding unchanged; only visual is different. |
| Debounce coalesces multiple threshold crossings. | Summary: Uses `_request_rebuild()` coalescing, proven for Appearance/UI-scale. |
| "Add current game" button works at collapsed width. | Geometry: Button label/width change, command unchanged. |
| SettingsItem `has_update` is visible when collapsed. | States: Collapsed SettingsItem, small `ACCENT` corner dot. |
| Full test suite passes. | Test impact (deferred to `docs/spec.md`, no change in design scope). |

## Implementation checklist

1. **Add three new constants** after line 176 (with existing sidebar/content constants).
2. **Add `self._rail_collapsed = False`** in `__init__` around line 1587.
3. **Add `self.root.bind("<Configure>", self._on_root_resize)`** in `__init__`, after the first `self._build_ui(s)` call returns — not earlier (PR #41 round 3 correction: binding it before that call leaves a genuine, WM-generated root `<Configure>` free to land mid-construction and crash, a hazard the `event.widget is not self.root` guard alone does not cover).
4. **Add `_on_root_resize()` method** around line 1620 (after `_request_rebuild()`).
5. **Modify `_build_ui()`:**
   - Top: add `if self.root.winfo_ismapped(): self._rail_collapsed = ...` check.
   - Sidebar width: `width=int((SIDEBAR_RAIL_W if self._rail_collapsed else SIDEBAR_W) * s)`.
   - `count_label.pack()` → conditional `if not self._rail_collapsed: self.count_label.pack(...)`.
   - "Add current game" button: `label = "+" if self._rail_collapsed else "Add current game"`, `width = (SIDEBAR_RAIL_W if self._rail_collapsed else SIDEBAR_W) - 28`.
6. **Modify `GameItem.__init__()`:**
   - Add `collapsed=False` parameter.
   - Add `width=None` parameter; resolve to `SIDEBAR_RAIL_W - 16` if collapsed, else default `SIDEBAR_W - 16`.
   - Inside, add `if collapsed:` branch (centered badge + letter).
   - Else: existing unexpanded branch (unchanged).
   - `_paint()` method: no changes.
7. **Modify `SettingsItem.__init__()`:**
   - Add `collapsed=False` parameter.
   - Add `width=None` parameter; same resolution.
   - Inside, add `if collapsed:` branch (centered badge "S", optional update dot).
   - Else: existing branch (unchanged).
   - `_paint()` method: handle update dot in collapsed mode (itemconfig if it exists).
8. **Modify `_rebuild_list()`:**
   - Pass `collapsed=self._rail_collapsed` to `GameItem()` constructor.
9. **Modify `_apply_minsize()`:**
   - `minw = int((SIDEBAR_RAIL_W + 1 + CONTENT_W) * self.s)`.
   - `default_w = int((SIDEBAR_W + 1 + CONTENT_W) * self.s)` in the `not grow_only` branch.

## Summary of key design decisions

- **Icon mechanism:** Centered circular badge (28px at s=1, 18px at worst case s=0.675) with the profile's first letter (uppercase, 10.5pt at s=1, 7pt at worst case) for both `GameItem` and `SettingsItem`.
- **SettingsItem glyph:** Initial-letter "S" (same mechanism as `GameItem`), not a bespoke gear. Consistent, simple, readable at all scales; bespoke glyph can be added later if desired.
- **Update indicator:** Small 5px ACCENT-colored dot in the top-right corner of the `SettingsItem` badge when `has_update` is true.
- **Collapse threshold:** Window width = `SIDEBAR_W + 1 + CONTENT_W` (661px at s=1, 446px at worst case). Below this, rail collapses; above, it expands.
- **Minimum floor:** `SIDEBAR_RAIL_W + 1 + CONTENT_W` (513px at s=1, 346px at worst case). Decoupled from default launch size (661px).
- **Transition:** Full rebuild via existing `_request_rebuild()` machinery, triggered by debounce-on-threshold-crossing in `<Configure>` handler. No animation, consistent with Appearance/UI-scale changes.
- **Pixel constants:** SIDEBAR_RAIL_W = 64, COLLAPSED_BADGE_D = 28 (both survive to usable sizes at the worst-case compound scale s=0.675; readability is marginal but acceptable, matching the existing codebase's G#23 baseline).
- **Scale interaction:** This design inherits G#23's unresolved challenge (macOS 0.75x DPI × 90% UI-scale = 7pt fonts) and is usable under any resolution to that ticket. It does not depend on a specific outcome, but improves with any choice that improves text rendering generally.
- **Reuse:** `create_oval`, `create_text`, existing color tokens, `_paint()` pattern, `_request_rebuild()` coalescing — no new drawing primitives, no new color tokens.
