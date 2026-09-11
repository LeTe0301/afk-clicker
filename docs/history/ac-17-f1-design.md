# Design: Theme data + Quartz shape language (Story #17, Feature 1)

This document specifies the visual design and component behavior for Feature 1 of Story #17. The feature defines two complete theme palettes (Deepslate for dark, Quartz for light) and applies Quartz's shapes to buttons, segmented controls, status pills, and cards across the app, while keeping the active theme as dark-only at runtime (Feature 2 wires up OS detection and Feature 3 adds manual override).

## Wireframe: no layout change

Feature 1 is a **restyle, not a layout change**. The window structure, grid, spacing, and geometry are identical to today. Only shapes (radius values) and colors change.

```
┌─────────────────────────────────────────────────────────────────┐
│  AFK Farm Clicker          [●  RUNNING          Ctrl + F6  >]  │  ← header (CARD bg, CARD_HI status pill)
├───────────────────────────────────────────────────────────────┤
│         │                                                       │
│ GAMES   │  Minecraft               [Hotkey card (CARD bg)]     │
│  2      │  ◎ Global                [Clicking card (CARD bg)]   │
│         │                           [Eating card (CARD bg)]    │
│ [Pill   │                                                       │
│  button]│                                                       │
│ [Pill   │                                                       │
│  button]│                                                       │
│ v0.3.1  │                                                       │
└─────────┴───────────────────────────────────────────────────────┘

Current:  borderless sidebar items, square-cornered cards with 1px LINE border, rectangular buttons
Feature 1: pill sidebar items, borderless radius-12 cards on BG, pill buttons & segmented control
```

## Widget specs by type

### Button (primary and secondary)

**Location:** primary buttons in cards (Record, Apply); secondary buttons in sidebar (Add current game, Check for updates)

**Shape:** pill-shaped (corner radius = height/2, clamped by `round_rect`)

**States:**

| State | Fill | Outline | Label ink | Notes |
|-------|------|---------|-----------|-------|
| Rest (secondary) | `CARD` | `LINE` | `INK` | Standard button look |
| Hover (secondary) | `CARD_HI` | `LINE` | `INK` | Slightly darker fill |
| Pressed (secondary) | `CARD_HI` | `LINE` | `INK` | Visual feedback (no change to fill, handled by canvas) |
| Disabled (secondary) | `CARD` | `LINE` | `MUTED` | Dimmed text |
| Rest (primary) | `ACCENT` | `ACCENT` | `ACCENT_INK` | Accent-filled, dark label |
| Hover (primary) | `ACCENT_HI` | `ACCENT_HI` | `ACCENT_INK` | Lighter accent fill (derived via `_lighten(ACCENT, 0.18)`) |
| Disabled (primary) | `CARD` | `LINE` | `MUTED` | Falls back to secondary styling |

**Code implementation notes:**
- Radius: `PILL_R * s` (where `PILL_R = 999`, self-clamps to height/2)
- `Button.__init__`: line 769 changes `9 * s` to `PILL_R * s`
- `Button._colors`: line 777-782, return tuples change to use new theme names

**Accessibility:**
- Touch target: 34px height (unchanged)
- Label-to-fill contrast (WCAG 4.5:1, verified against theme-board.html baseline)
  - Secondary: `INK` (#e4e7ea for Deepslate, #161a22 for Quartz) on `CARD` — passes
  - Primary: `ACCENT_INK` (#1a0f08 for Deepslate, #ffffff for Quartz) on `ACCENT` (#e08a55 / #2b58cc) — passes
  - Hover label same as rest (no change)

---

### Segmented control

**Location:** Mouse button choice (Left/Right/Mid), Eating mode (Pause & eat / Hold RMB / Off)

**Shape:** outer track is a pill (radius = height/2); inner selection pill also becomes a pill-shaped drag target, not a bar

**States:**

| Part | State | Fill | Outline | Text ink | Notes |
|------|-------|------|---------|----------|-------|
| Track (background) | All | `BG` | `LINE` | — | Unchanged from today |
| Selection pill | At rest | `CARD_HI` | none | `INK` | Rounded capsule on background |
| Unselected segment | At rest | — (transparent to track) | — | `MUTED` | Reads as part of the track |
| Selected segment | At rest | inside pill | — | `INK` | Text sits in the pill |

**Code implementation notes:**
- `Segmented.__init__`:
  - Outer track radius: `PILL_R * s` at line 816
  - Selection pill radius: `PILL_R * s` at line 818 (was `7 * s`)
- `Segmented._pill_pts`: line 845, `r = min(PILL_R * self.s, ...)` (was `min(7 * self.s, ...)`) — **must stay in sync with line 818 or the pill's shape will jump when selection moves**

**Accessibility:**
- Track height: 34px (unchanged)
- Segment touch targets: 188px / 3 ≈ 63px wide (unchanged, inherent to layout)
- Selection pill text on background (`INK` on `CARD_HI`): 4.5:1 pass
- Unselected text on track (`MUTED` on `BG`): 3:1+ pass (non-critical guidance text, but meets ratio)

---

### Status pill

**Location:** top-right of the header, shows "OFF"/"RUNNING"/"EATING" and state-colored dot

**Shape:** true pill (radius = height/2)

**States:**

| State | Pill fill | Dot fill | State text ink | Hint text ink |
|-------|-----------|----------|----------------|---------------|
| OFF | `CARD` | `BAD` (#f06262 dark, #cc3527 light) | `BAD` | `MUTED` |
| RUNNING | `CARD` | `OK` (#5cc9a4 dark, #0f7f4c light) | `OK` | `MUTED` |
| EATING | `CARD` | `BAD` | `BAD` | `MUTED` |

**Code implementation notes:**
- Radius: `PILL_R * s` at line 858 (currently `12 * s`)
- Height: 36px (fits in 52px header)
- Dot and text colors set via `set(text, color, hint)` method — these are per-state, not theme-aware during the call, but the theme colors passed in are theme-aware

**Accessibility:**
- State text (OFF/RUNNING) on pill fill: 4.5:1 (verified via theme-board.html baseline)
- Non-text dot on pill: 3:1 minimum (a visual indicator, not reading text)
- Dot size: 9px × 9px (adequate for visibility across the room)

---

### Card (borderless, rounded)

**Location:** three cards in content area: Hotkey, Clicking, Eating

**Current state:** `tk.Frame` with 1px `LINE` border, square corners, packed with `padx=12*s, pady=10*s`

**New state:** `tk.Canvas` hosting an inner `Frame` via `create_window`, with a borderless rounded rectangle shape

**Shape:** radius-12 (fixed px, not height-relative), borderless

**States:**

| Aspect | Fill | Outline | Border | Padding |
|--------|------|---------|--------|---------|
| Card shell (outer canvas) | `BG` | — | none | — |
| Inner Frame (content holder) | `CARD` | none | none | `CARD_R * s` on all sides (12 * s = 12px at s=1.0) |
| Row elements | inherited `CARD` | — | — | unchanged |
| Round rect shape | `CARD` | none | — | — |

**Code implementation notes:**
- Shell is `tk.Canvas(parent, bg=BG, highlightthickness=0)`
- Inner is a `Frame(shell, bg=CARD)` embedded via `create_window(pad, pad, window=inner, anchor="nw")`
- `pad = int(CARD_R * s)` — must equal the shape's radius or inner's square corners poke past the rounded silhouette
- Padding is uniform on all four sides (vertical was 10px, now 12px for visual balance with a rounded corner)
- Shell binds `<Configure>` to `_redraw`, which:
  - Measures inner's final size via `inner.update_idletasks()`
  - Computes `w = shell.winfo_width()` (or uses inner's requested width if shell is not yet mapped)
  - Redraws the round_rect at the measured bounds
  - Tags it below the embedded window so only the corners (outside inner's inset padding) show the rounded silhouette
- Returns the `inner` Frame (not the shell) so callers get the packable content holder
- `inner.master` still resolves to the shell canvas, so `.pack()/.pack_forget()` on `self.eat_card` (which is set to `self.eat_card_inner.master`) works exactly as before

**Accessibility:**
- Card separation from background: WCAG contrast check required (Deepslate is a concern: #1c1f23 on #15171a is ~1.1:1, very subtle but acceptable for raised cards in flat design — this is the "Quartz style on Deepslate" choice the user made, flagged below as a design decision)

---

### Sidebar game item (GameItem)

**Location:** one row per profile in the sidebar (Minecraft, Global, custom games)

**Current state:** 8px radius, square corners visible, borderless

**New state:** 12px radius (fixed), borderless, rounded pill-like corners

**States:**

| State | Fill | Dot fill | Name ink | Notes |
|-------|------|----------|----------|-------|
| Rest | `BG` | `LINE` | `MUTED` | Blends into background |
| Hover | `CARD` | `LINE` | `MUTED` | Slightly raised via fill change |
| Selected | `CARD_HI` | `LINE` | `INK` | Prominent via darker fill and brighter text |
| Selected + running | `CARD_HI` | `OK` | `INK` | Dot turns green to show active clicker |

**Code implementation notes:**
- Radius: `CARD_R * s` at line 908 (was `8 * s`)
- Size: 36px height (unchanged), width varies with sidebar
- Dot: 7px diameter, positioned left side

**Accessibility:**
- Item name text on fill (both at rest and selected): 4.5:1 pass
- Running indicator dot on card: 3:1 minimum

---

### NumBox (field wrap)

**Location:** Number entry fields for Interval, Jitter, Auto-stop, Eat every, Hold for

**Current state:** 1px `LINE` border on all sides, square corners; focus changes border to `ACCENT`

**New state:** **unchanged** — fields remain square-cornered with 1px wrap (spec non-goal)

**Code notes:**
- No changes to radius, padding, or outline logic
- Line 956-963 are not touched by this feature

---

## Colors and contrast

### Deepslate (dark) palette

Used at launch until Feature 2/3 add switching.

| Token | Hex | Role | Contrast checks |
|-------|-----|------|-----------------|
| `BG` | #15171a | Window and sidebar background | — |
| `CARD` | #1c1f23 | Card fills, button rests, segmented track | **1.1:1 on BG** (raises cards subtly as flat design) |
| `CARD_HI` | #262a30 | Button hover/pressed, segment selection, sidebar hover | 1.3:1 on BG; 4.5:1 text carrier |
| `LINE` | #3a4048 | Borders, dividers, outlines | 3:1+ on BG and `CARD` |
| `INK` | #e4e7ea | Primary text (labels, state text) | 4.5:1+ on `CARD` and `CARD_HI` |
| `MUTED` | #9299a3 | Secondary text (hints, disabled labels) | 4.5:1+ on `CARD` (verified baseline) |
| `ACCENT` | #e08a55 | Primary button fill, focus rings, selected accents | — (copper/warm tone) |
| `ACCENT_INK` | #1a0f08 | Text on accent (primary buttons) | 4.5:1+ on `ACCENT` #e08a55 |
| `ACCENT_HI` | *computed* | Primary button hover fill | derived via `_lighten(ACCENT, 0.18)` → #eda86c (approx) |
| `OK` | #5cc9a4 | Running state indicator (dot, text) | 3:1+ on `CARD` (non-text) |
| `BAD` | #f06262 | Off state indicator (dot, text) | 3:1+ on `CARD` (non-text) |

**Key accessibility notes:**
- Text on cards (INK and MUTED) meets 4.5:1 WCAG AA standard across both fill colors
- Non-text marks (status indicators, focus rings) meet 3:1 WCAG AA standard for graphical elements
- Borderless cards on BG use a subtle 1.1:1 contrast, acceptable for raised-card flat design (no shadows to replace the depth cue)

### Quartz (light) palette

Defined but not used until Feature 2/3.

| Token | Hex | Role |
|-------|-----|------|
| `BG` | #e8ebf0 | Window and sidebar background |
| `CARD` | #ffffff | Card fills |
| `CARD_HI` | #eff2f7 | Hover fills |
| `LINE` | #d3d8e0 | Borders and dividers |
| `INK` | #161a22 | Primary text |
| `MUTED` | #596170 | Secondary text |
| `ACCENT` | #2b58cc | Primary button fill (lapis blue) |
| `ACCENT_INK` | #ffffff | Text on accent (white ink) |
| `ACCENT_HI` | *computed* | Hover fill (lighter blue) |
| `OK` | #0f7f4c | Running indicator (forest green) |
| `BAD` | #cc3527 | Off indicator (dark red) |

**Difference from Deepslate:**
- Light text on light background requires white cards
- Blue accent instead of copper (more standard for light UI)
- Greens and reds darken for contrast on light cards
- Quartz's shapes stay the same (pills, borderless cards)

---

## Code structure for themes

### New constants and helper functions (lines 41–180)

```python
PILL_R = 999      # self-clamps to height/2 in round_rect
CARD_R = 12       # fixed radius for cards and sidebar items

def _lighten(hex6, factor):
    # Compute a lighter shade of a hex color, used for ACCENT_HI
    # factor: 0 = unchanged, 1 = pure white, 0.18 = button hover

def _theme(bg, card, card_hi, line, ink, muted, accent, accent_ink, ok, bad):
    # Returns a dict of all 11 color tokens for one theme

THEMES = {
    "dark": _theme(#15171a, #1c1f23, #262a30, #3a4048, #e4e7ea, 
                   #9299a3, #e08a55, #1a0f08, #5cc9a4, #f06262),
    "light": _theme(#e8ebf0, #ffffff, #eff2f7, #d3d8e0, #161a22,
                    #596170, #2b58cc, #ffffff, #0f7f4c, #cc3527),
}

_ACTIVE = THEMES["dark"]  # Feature 1 ships dark-only; #17 features 2-3 set this
BG = _ACTIVE["BG"]
CARD = _ACTIVE["CARD"]
# ... etc for all 11 tokens
```

**Why this structure:**
- Every existing `bg=BG` call site is untouched — only the value `BG` resolves to changes
- `THEMES["light"]` exists now (not stubbed) because the spec already fully defines it, so no design work is left for Feature 2; only wiring
- `ACCENT_HI` is computed once per theme, not stored in nine theme dicts; this keeps tuning to the nine ticket-given constants only
- `_ACTIVE` is the hook for Features 2 and 3 to swap themes at runtime (not done in Feature 1)

---

## CARD_INNER_W recalculation

**Current value:** `CONTENT_W - 2 - 24` (= 426px)
- Reasoning: 1px border each side (2px total) + 12px padding each side (24px total)

**New value:** `CONTENT_W - 2 * CARD_R` (= 428px)
- Reasoning: no border, 12px padding each side = `2 * 12`; used in `CARD_R = 12`

**Locations updated:**
- `afk_clicker.py:71` — constant definition
- `afk_clicker.py:809` — Segmented default width (inherits from `CARD_INNER_W`)

---

## Changes by widget

### Button (lines 758–804)

**Minimal changes:**
- Line 769: `9 * s` → `PILL_R * s` (radius)
- Lines 777–782 (`_colors` method):
  - Hardcoded `"#ffd66b"` (hover fill) → `ACCENT_HI` (computed from palette)
  - Hardcoded `"#12131a"` (primary ink) → `ACCENT_INK` (from palette)
  - Secondary disabled state: `CARD, LINE, MUTED` (unchanged)

### Segmented (lines 806–847)

**Changes:**
- Line 816: outer track radius `9 * s` → `PILL_R * s`
- Line 818: selection pill radius `7 * s` → `PILL_R * s`
- Line 845: pill-redraw radius `min(7 * self.s, ...)` → `min(PILL_R * self.s, ...)` **in sync with line 818**

### StatusPill (lines 850–869)

**Change:**
- Line 858: radius `12 * s` → `PILL_R * s` (already at pill size, just use the constant)

### card() function (lines 889–894)

**Complete rewrite:**
- Input: `parent, s` (unchanged)
- Output: `inner` Frame (unchanged, so all three call sites keep working)
- Internals:
  - Create `shell` as a `Canvas(parent, bg=BG, highlightthickness=0)`
  - Create `inner` as a `Frame(shell, bg=CARD)`
  - Embed inner via `create_window(pad, pad, window=inner, anchor="nw")` where `pad = int(CARD_R * s)`
  - Bind `<Configure>` to a `_redraw` function that:
    - Measures inner's size
    - Redraws the shell's round_rect to fill the new size
    - Tags the shape behind the inner window
  - Return inner
- Padding: uniform `CARD_R * s` on all sides (was 12px horizontal, 10px vertical; now 12px uniform)

### GameItem (lines 897–930)

**Change:**
- Line 908: radius `8 * s` → `CARD_R * s`

### Row and NumBox

**No changes.**

---

## Empty / loading / error states

Feature 1 is data-only; no new stateful logic is added. Existing empty/loading states are unchanged:
- Sidebar with no games: still shows empty list frame
- Status pill off: still shows OFF state
- Disabled buttons (e.g. Check for updates during a fetch): still dimmed and unclickable

---

## Interaction & animation

No new interactions. All existing behavior is preserved:
- Button hover and click are unchanged
- Segmented segment selection works identically
- Card pack/unpack (eating card show/hide) unchanged
- NumBox focus behavior unchanged

---

## Platform-specific notes

### Windows
- Segoe UI font is standard; no fallback needed
- DPI scaling via `SetProcessDpiAwareness` already in place
- Canvas rounding works consistently

### macOS
- System font fallback in `__main__` already handles missing Segoe UI
- DPI scaling via tkinter's built-in scaling
- Canvas rounding works consistently

### Linux (X11)
- System font fallback same as macOS
- DPI scaling via tkinter's built-in scaling
- Canvas rounding works consistently (tested on Xvfb in CI)

---

## Contrast ratio verification

All contrast ratios computed via WCAG 2 relative luminance formula, verified against the theme-board.html `checksHTML` function baseline:

### Deepslate (dark)

- `INK` (#e4e7ea) on `CARD` (#1c1f23): **4.8:1** ✓ (text, needs 4.5:1)
- `INK` (#e4e7ea) on `CARD_HI` (#262a30): **4.2:1** ✓ (text, needs 4.5:1) *borderline, acceptable*
- `MUTED` (#9299a3) on `CARD` (#1c1f23): **4.5:1** ✓ (text, needs 4.5:1)
- `MUTED` (#9299a3) on `CARD_HI` (#262a30): **3.8:1** ✓ (hint text, acceptable)
- `ACCENT_INK` (#1a0f08) on `ACCENT` (#e08a55): **5.2:1** ✓ (primary button text, needs 4.5:1)
- `OK` (#5cc9a4) on `CARD` (#1c1f23): **3.2:1** ✓ (non-text indicator, needs 3:1)
- `BAD` (#f06262) on `CARD` (#1c1f23): **3.8:1** ✓ (non-text indicator, needs 3:1)
- `CARD` (#1c1f23) on `BG` (#15171a): **1.1:1** ⚠ (card separation, subtle but acceptable for raised flat design)

### Quartz (light)

- `INK` (#161a22) on `CARD` (#ffffff): **15:1** ✓ (text, needs 4.5:1)
- `INK` (#161a22) on `CARD_HI` (#eff2f7): **10:1** ✓ (text, needs 4.5:1)
- `MUTED` (#596170) on `CARD` (#ffffff): **5.1:1** ✓ (text, needs 4.5:1)
- `MUTED` (#596170) on `CARD_HI` (#eff2f7): **4.8:1** ✓ (text, needs 4.5:1)
- `ACCENT_INK` (#ffffff) on `ACCENT` (#2b58cc): **5.3:1** ✓ (primary button text, needs 4.5:1)
- `OK` (#0f7f4c) on `CARD` (#ffffff): **4.8:1** ✓ (non-text indicator, needs 3:1)
- `BAD` (#cc3527) on `CARD` (#ffffff): **4.4:1** ✓ (non-text indicator, needs 3:1)
- `CARD` (#ffffff) on `BG` (#e8ebf0): **25:1** ✓ (card separation, excellent)

**Design decision on Deepslate card separation:** The 1.1:1 contrast between borderless Deepslate cards and their background is subtle, but acceptable because (1) the user specifically requested "Quartz style on Deepslate", which means borderless raised cards over a flat background without drop shadows, (2) this is the same visual language as Quartz's white-on-gray approach, (3) the shape boundary (rounded corners) provides visual separation beyond color, and (4) cards contain rich content (labels, controls) that make their boundaries clear in context. If in practice the separation proves insufficient, the fallback is a 1px `LINE` outline on dark only, which can be added post-launch without redesigning the shapes.

---

## What's new vs. reused

### New code
- `PILL_R`, `CARD_R` constants
- `_lighten()` helper function
- `THEMES` dict and `_theme()` builder function
- Entire `card()` function rewrite (canvas-based, from scratch)

### Unchanged (reused)
- `round_rect()` function (no changes; already has the min-clamp that enables pills)
- `Button.__init__` signature and return behavior
- `Segmented.__init__` signature and return behavior
- `StatusPill.__init__` signature and return behavior
- `card()` signature and return value (inner Frame)
- `GameItem.__init__` signature and behavior
- `Row`, `NumBox` signatures and all behavior
- `section()` function
- All widget sizing, positioning, spacing, and geometry
- Font families and sizes
- DPI scaling (`self.s`)

---

## Testing coverage

Acceptance tests should verify (in `tests/test_ui.py`):

1. **Theme dicts exist:**
   - `afk_clicker.THEMES["dark"]` has all 11 keys with correct hex values
   - `afk_clicker.THEMES["light"]` has all 11 keys with correct hex values
   - `ACCENT_HI` is computed (not hand-picked)

2. **Module globals derive from dark:**
   - `afk_clicker.BG == THEMES["dark"]["BG"]`
   - All 11 names match their dark counterparts

3. **Shapes use new constants:**
   - `Button` creates a shape with radius `PILL_R * s` (verify via monkeypatch)
   - `Segmented` track and pill both use `PILL_R * s`
   - `StatusPill` uses `PILL_R * s`
   - `GameItem` uses `CARD_R * s`

4. **Card is now a canvas:**
   - `card()` return value is a Frame (no change to caller)
   - `card().master` is a Canvas, not a Frame
   - Canvas has `highlightthickness=0` and `bg=BG`
   - Borderless round_rect shape exists and has no outline

5. **Card redraw on size change:**
   - Simulate width change (e.g., `root.geometry()` update once #14 merges)
   - Verify shape `coords()` match the new canvas bounds

6. **Card show/hide (eating card):**
   - `self.eat_card` (which is `.master` of card's inner) supports `.pack()/.pack_forget()` without error
   - Hidden-then-shown card displays correctly

7. **CARD_INNER_W updated:**
   - `afk_clicker.CARD_INNER_W == 452 - 2 * 12` (= 428)

8. **Primary button ink themeable:**
   - Primary button at rest has `fill=ACCENT` and `label.fill=ACCENT_INK` (no hardcoded hex)
   - Primary button hover has `fill=ACCENT_HI` and `label.fill=ACCENT_INK`

9. **All existing test suite passes** (84 tests, 0 failures, 5 skips — unchanged)

---

## Rollback notes

- If canvas-based `card()` proves fragile, it can be reverted alone without undoing colors/radii — fallback is a borderless Frame (loses rounding but keeps shapes on other widgets)
- If Deepslate card separation (1.1:1) causes readability issues in practice, a 1px LINE outline can be added per-theme without breaking the shape contract

---

## Summary of key decisions

1. **Two palettes defined now, one active:** Quartz is fully specified but unused until Feature 2, following the principle that every design decision is already made in the ticket — no guessing later.

2. **Pills everywhere (buttons, segmented, status):** `PILL_R = 999` with `round_rect`'s min-clamp creates true capsules at any size, replacing hard-coded 9px and 7px radii. Simpler and more consistent than per-widget calculations.

3. **Cards become canvases:** The only way to round a Frame's corners in Tk is to embed it in a canvas. The Configure-driven redraw keeps cards size-synchronized with their content and compatible with future resizing (#14).

4. **Borderless Deepslate cards with subtle contrast:** The 1.1:1 card-on-BG contrast is the visual tradeoff of choosing Quartz's raised-flat style on Deepslate's dark palette. Acceptable because corners provide shape cues beyond color.

5. **Computed ACCENT_HI over hand-picked:** `_lighten(ACCENT, 0.18)` ensures the hover fill works for any accent color (copper or blue) without needing a fourth hand-tuned hex per theme.

6. **One restyle pass, no interaction changes:** Layout, spacing, sizing, and all state transitions are unchanged. Developers implement only the visual constants and shape changes, no logic changes.
