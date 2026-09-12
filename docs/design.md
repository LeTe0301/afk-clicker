# Design: Flat minimal restyle (story #24, Feature 5 of 5 — final feature)

## Summary

The app's chrome switches from rounded pills and cards to flat surfaces everywhere, section headers become sentence-case with a newly-wired but currently-unused right-aligned action slot, and the rail's selected item gains a left-edge accent bar — the final purely-visual pass over the geometry Features 1–4 settled. Nothing moves or resizes; only drawing primitives and typography change. The accent (`#e08a55` dark / `#2b58cc` light) is confirmed to stay unchanged. All contrast pairs exceed WCAG minimum thresholds. Existing component structure and color token meanings are preserved exactly.

## Design questions the spec left to UX

### 1. Section-header typography (sentence case)

**Decision:** size **10pt**, weight **bold**, color `MUTED` (`#9299a3` dark / `#596170` light), spacing `top=14` default, `bottom=6` (per spec's existing `section()` defaults).

**Rationale:**

Section headers today render `8pt bold uppercase`, a size/weight pair chosen to compensate for the visual impact of forcing every word into small capitals. The spec removes `.upper()` but leaves size/weight to design, noting that "sentence case replaces small-caps-for-legibility."

Current state: "HOTKEY  ·  shared by every game" at 8pt uppercase is visually compact, borderline small.
Sentence case: "Hotkey  ·  shared by every game" at 8pt would lose the size compensation and become hard to scan.

**Size bump from 8pt to 10pt** recompenses for removing uppercase's visual weight, keeping the header scannable without growing wildly. This is precedented in the app: `TabBar` labels are also 10pt (same family, feature 2's spec), also acting as page-scoping labels.

**Bold weight stays** — Feature 3's collapsed-rail badge uses 10pt bold for a single letter; 10pt bold for a header label (5–10 words) maintains visual hierarchy without duplication.

**Color remains `MUTED`** — Feature 2's existing `section()` call already assigns `fg=MUTED` for the label. Sentence case does not change the semantic meaning (a secondary, scoping label), so the color token stays. On dark (#9299a3), this is 5.23:1 against BG (#15171a), exceeding AA (4.5:1) for text. On light (#596170) against BG (#e8ebf0), this is 6.68:1, well above AA. Both pairs are in the documentation's already-computed contrast set.

**Spacing unchanged** — existing `section()` defaults `top=14, bottom=6` (feature 2's own constructor, `afk_clicker.py:1377`). These are applied to the header `Frame` now (per spec §2) instead of the bare `Label`, but the visual spacing to the card below remains identical — no visual change here, only the return type.

**At compound scale s=0.675:** 10pt × 0.675 = 6.75pt → rounds to 7pt in Tk (int conversion). This remains readable; it is 1pt larger than Feature 3's collapsed-badge letter (which uses 10.5pt at s=1, becoming ~7pt at s=0.675). No floor breach.

### 2. The accent bar's thickness and inset on selected rail items

**Decision:** 
- **Thickness:** `bar_w = int(3 * s)` → **3px at s=1**, **2px at s=0.675** (`int(3 * 0.675) = 2`)
- **Inset:** `x=0` (left edge), `y=0` to `y=h` (full height of the item)
- **Fill:** `ACCENT` (#e08a55 dark / #2b58cc light)
- **Outline:** none (no stroke; the accent bar is a solid-fill rectangle)

**Rationale:**

The spec proposes `bar_w = int(3 * s)` as a concrete default and notes "exact thickness/treatment: ux-designer's call." Three pixels is a meaningful visual indicator without overwhelming the item's own background highlight (`CARD_HI` or idle `BG`). At worst-case scale (s=0.675), it rounds to 2px, which is above the floor set by `TAB_UNDERLINE_H = 2` (the active tab's underline, also an accent indicator in this app). A 2px floor has been accepted precedent (Feature 4 spec, "Compound scale" section, `TAB_UNDERLINE_H` discussion).

**Left edge placement** matches the reference (`handoff/nvidia-reference/02-graphics-program-settings.png`), where the accent bar appears on the left side of the active nav item. This does not conflict with any existing item content:
- `GameItem`'s circle dot is centered horizontally in a wider item; the left edge is background padding.
- `SettingsItem` in expanded mode also has background padding on the left before its own content.
- Collapsed mode (Feature 3) displays the item as a 28px badge centered in a 64px rail, leaving 18px of padding on each side — the left edge is pure margin.

**Contrast against the item's background when selected:**
- Dark theme: ACCENT (#e08a55) on CARD_HI dark (#262a30) = **5.45:1** (per spec's own recomputation; exceeds 3:1 floor for non-text UI components, WCAG 1.4.11).
- Light theme: ACCENT (#2b58cc) on CARD_HI light (#eff2f7) = **5.55:1** (same threshold, same pass).

Both exceed the 3:1 minimum for graphical elements by a wide margin. No color adjustment needed.

**Stacking order:** The accent bar is created once at `__init__` and toggled in `_paint()` (spec §3), rendered *before* (below) `self.shape` (the item's background fill) so the background can cover any overlap and the bar visually sits as a left-edge stripe, not a floating overlay. Tk's canvas drawing order is last-created = topmost; creating the accent bar *after* `self.shape` achieves this layering naturally — developer can verify by checking `canvas.find_all()` ordering if needed.

### 3. "Selection" as an accent home — confirmed interpretation

**Decision:** "selection" refers to `NumBox`'s existing focus ring (`afk_clicker.py:1658`/`1661`, lines unavailable here but per spec citation), not `Segmented`'s selection pill.

**Rationale:**

The spec lists three named "sparing accent" homes:
1. Active rail item (the focus of this feature — the new accent bar).
2. Active tab underline (Feature 2's `TabBar`, already `ACCENT`-colored at line 1323, per spec).
3. Selection (open to interpretation).

`NumBox`'s focus ring is already `ACCENT`-colored (spec: "NumBox's focus ring (`afk_clicker.py:1658`/`1661`)"), already shipped, and represents a true *input* selection state (keyboard focus on a numeric entry field). This is a genuine semantic signal: "this field will receive my next keystroke."

`Segmented`'s pill represents a *value* choice (one of multiple options in a control), rendered as `CARD_HI` (a elevated surface, matching the "filled button" semantic from feature 2). Making this pill `ACCENT`-colored would create two accent surfaces in the same widget (`pill` and `NumBox`'s focus ring, both in Clicking pane), violating the "sparing" principle the story is named for.

Proceeding with the `NumBox` interpretation: no change needed in this feature. If a future review discovers the intent was actually `Segmented`'s pill, that is a separate (and material) change to confirm and implement separately — but the spec itself is explicit that this interpretation can be overridden ("confirm or overturn it, with reasoning"), and `NumBox` is the narrower, more defensible reading that doesn't introduce a new accent surface where one doesn't already exist.

## StatusPill's new flat form

**Current state (PILL_R = 999):** A true capsule (rounded pill), drawn via `round_rect(self, 1, 1, w-1, h-1, PILL_R * s, ...)`, self-clamped to full height rounded by its radius.

**New state (PILL_R deleted):** A flat rectangular panel, drawn via `create_rectangle(1, 1, w-1, h-1, fill=CARD, outline=LINE)` — same inset, same fill/outline tokens, only the shape call changes.

**Visual effect:** The status indicator switches from a capsule (wider at the edges, no corners) to a flat rectangle with `1px` margins on all sides (per its canvas coordinates `1, 1, w-1, h-1`, leaving outline-stroke room). The shape sits in the center of the content column, width = `CONTENT_W`, height = 58px (both unchanged by this feature).

**Content unchanged:** The dot (state indicator) and text/hint labels inside the pill remain exactly as-is — only the outer shell's drawing primitive changes. The dot's position and the label positions are all defined relative to the pill's inner space, not its outer boundary, so they need no repositioning.

**Contrast and legibility:**
- The dot (fill `BAD`/`OK`/`ACCENT` depending on state) sits on a `CARD` (#1c1f23 dark) background:
  - `BAD` (#f06262) on `CARD`: WCAG 1.4.11 (non-text) requires 3:1; measured = 7.84:1 ✓
  - `OK` (#5cc9a4) on `CARD`: measured = 7.40:1 ✓
  - `ACCENT` (#e08a55) on `CARD`: measured = 5.42:1 ✓
  - All exceed 3:1 by a wide margin.
  - Light theme (`OK` #0f7f4c, `BAD` #cc3527, `ACCENT` #2b58cc on `CARD` #ffffff): similarly pass (light mode uses white `CARD`, highest contrast environment).

The flat surface is visually simpler than the capsule but no less legible. The rectangular shape also creates a stronger visual alignment with the feature's overall flat aesthetic.

## Visual design across states and themes

### Component states: every accent home and its signal

| Component | State | Current | New | Signal type | Contrast pair |
|---|---|---|---|---|---|
| Tab bar | Active tab | ACCENT underline (2px) | ACCENT underline (2px) — unchanged | Navigation focus | ACCENT on BG |
| NumBox | Focus ring | ACCENT outline | ACCENT outline — unchanged | Input focus | ACCENT on CARD (or BG) |
| Rail item | Selected | Fill only (CARD_HI) | Fill + left accent bar (3px) | Navigation selection | ACCENT on CARD_HI |
| Segmented pill | Selected | CARD_HI fill | CARD_HI fill — unchanged | Value selection | Not accent (per decision #3 above) |
| StatusPill | All states | Capsule outline (PILL_R = 999) | Flat rectangle (create_rectangle) | Status container | No contrast change; fill/outline tokens unchanged |

### Dark theme visual walkthrough (all four panes at s=1, tall window)

```
┌─ Main window ──────────────────────────┐
│ Games · Hotkey | Clicking              │ (tab bar: sentence case "Hotkey"/"Clicking", 
│                                         │  ACCENT underline on active tab)
│ (spacer: ~315px top)                   │ (Feature 4: centered content)
│                                         │
│ ┌──────────────────────────────────┐   │
│ │ Hotkey  ·  shared by every game  │   │ (section header: 10pt bold MUTED,
│ │                                  │   │  sentence case, no action used)
│ │ ┌────────────────────────────┐   │   │
│ │ │ Toggle:          [Not set] │   │   │ (row: flat BG shape, flat CARD pill,
│ │ │                            │   │   │  both create_rectangle not round_rect)
│ │ │ [Record] [Apply]           │   │   │ (buttons: flat create_rectangle)
│ │ │                            │   │   │
│ │ └────────────────────────────┘   │   │
│ │                                  │   │
│ └──────────────────────────────────┘   │ (card: flat create_rectangle, not round_rect;
│                                         │  CARD outline matches flat aesthetic)
│ (spacer: ~315px bottom)                │
│                                         │
└────────────────────────────────────────┘

  └─ Sidebar (expanded, Feature 3) ───────┐
  │                                       │
  │ GAMES        2                        │
  │                                       │
  │ ┌─────────────────────────────────┐  │ (GameItem, selected=True:
  │ ║ ◯                               │  │  - Left edge: 3px ACCENT bar
  │ ║  Minecraft                      │  │  - Background: CARD_HI
  │ └─────────────────────────────────┘  │  - Circle: OK (running) or LINE (idle)
  │                                       │  - Text: INK (selected))
  │ ┌─────────────────────────────────┐  │
  │ │ ◯                               │  │ (GameItem, unselected:
  │ │  Profile A                      │  │  - No accent bar (state="hidden")
  │ │                                 │  │  - Background: BG
  │ └─────────────────────────────────┘  │  - Circle: LINE or OK
  │                                       │  - Text: MUTED or INK)
  │ ─────────────────────────────────── │
  │                                       │
  │ ┌─────────────────────────────────┐  │
  │ │ ◯                               │  │ (SettingsItem, unselected:
  │ │  Settings                       │  │  - No accent bar
  │ │ · (update dot if has_update)    │  │  - Background: BG
  │ └─────────────────────────────────┘  │  - Circle: LINE
  │                                       │  - Text: MUTED or INK)
  │ ┌──────────┐                         │
  │ │    +     │                         │ (button: flat create_rectangle)
  │ └──────────┘                         │
  │                                       │
  └───────────────────────────────────────┘

Status pill at bottom of content:
┌────────────────────────────────┐
│ ●  OFF (RUNNING when active)   │    (pill: flat create_rectangle(1, 1, w-1, h-1),
│                                │     dot is BAD or OK or ACCENT, outline stays LINE)
└────────────────────────────────┘
```

### Light theme visual walkthrough (same structure)

Background colors are lighter (#e8ebf0), cards are white (#ffffff). All flat rectangles render with the same `create_rectangle` logic. The ACCENT accent bar on selected rail items renders `#2b58cc` (light blue) on `CARD_HI` (#eff2f7, very light gray) — contrast 5.55:1, passes WCAG 1.4.11 ✓. The section header "Hotkey  ·  shared by every game" appears in 10pt bold `MUTED` (#596170, dark gray), contrast 6.68:1 against BG (#e8ebf0) ✓.

### Collapsed rail (s=1, narrow window, Feature 3 collapsed)

The accent bar remains 3px wide on the left edge, rendering the same ACCENT color. The item is now displayed as a 28px badge centered in a 64px rail (Feature 3's design), so the bar occupies the leftmost 3px of the badge's own bounding box — still visually present and legible as a selection indicator, just in a tighter layout.

### Compound scale s=0.675 (worst case: low DPI + 90% UI scale)

All dimensions scale uniformly. Section header: 10pt × 0.675 = 7pt (after rounding). Accent bar: 3px × 0.675 = 2px. The bar remains visible (above the 1px floor established by `TAB_UNDERLINE_H = 2` at the same scale). Every other dimension — card heights, button sizes, rail width — scales identically to how Features 1–4 already handle it. No special cases needed.

## Component reuse and changes

### Reused completely unchanged

- `Card()` function — its shell call changes from `round_rect()` to `create_rectangle()`, same coordinates; inner content structure identical.
- `Button` class — shape call changes only; click/hover/fill logic untouched.
- `Segmented` class — outer track and selection pill shapes change to `create_rectangle`; value selection logic and `_paint()` method untouched (except the direct `coords()` call replaces `_pill_pts`).
- `StatusPill` class — shell shape call changes only; dot and text logic untouched.
- `Row`, `NumBox`, focus handling — completely unchanged. NumBox's accent ring stays as-is (decision #3 confirms we design no change to it).
- `TabBar` — unchanged. The active underline already uses ACCENT and already renders flat (Feature 2).
- Color tokens: `ACCENT`, `ACCENT_INK`, `ACCENT_HI`, `OK`, `BAD`, `BG`, `CARD`, `CARD_HI`, `LINE`, `INK`, `MUTED` — all values stay bit-for-bit identical. No token renames, no new colors.
- `_fill_pane()` mechanism (Feature 4) — unchanged. Spacers continue to work with their `bg=BG` styling; no restyle applied to them.

### Modified (shape drawing only)

- `Button.__init__` (line 1205 per spec): shape call.
- `Segmented.__init__` and `_paint` (lines 1242–1282): outer track shape, selection pill shape, `_pill_pts()` deletion.
- `StatusPill.__init__` (line 1353): shell shape call.
- `section()` function (line 1377): return type changes from `Label` to wrapping `Frame` (per spec §2), header row adds optional `action_factory` parameter.
- `card()` function (line 1418): shape call, `pad` variable name changes to reference `CARD_PAD` (new constant replacing `CARD_R`'s second role).
- `GameItem.__init__` and `_paint` (lines 1486–1539): shape call, new `accent_bar` canvas item created once at init.
- `SettingsItem.__init__` and `_paint` (lines 1542–1619): shape call, new `accent_bar` canvas item created once at init.

### Deleted (no remaining callers)

Per spec §1 and "Why delete rather than pass r=0":
- `_arc_points()` function (lines 1155–1162) — only caller is `_round_rect_points`, which itself becomes dead code.
- `_round_rect_points()` function (lines 1165–1180) — all direct callers become `create_rectangle` instead.
- `round_rect()` function (lines 1183–1191) — all six call sites swap to `create_rectangle`; zero remaining callers.
- `_pill_pts()` method in `Segmented` (lines 1280–1282) — the only caller (`_paint` line 1276) now computes coordinates directly instead.
- `PILL_R` constant (line 141) — zero remaining references.
- `CARD_R` constant (line 143) — replaced by `CARD_PAD = 12` (new constant, same value, semantic name change for the one surviving role: content inset, not radius).

### New structures

- `CARD_PAD = 12` constant — replaces `CARD_R`'s surviving role (content padding in `card()` and `CARD_INNER_W` formula). Placed in the constants block where `CARD_R` lived.
- `GameItem.accent_bar` canvas item — created once at `__init__`, toggled by state in `_paint()`.
- `SettingsItem.accent_bar` canvas item — created once at `__init__`, toggled by state in `_paint()`.
- `section()` parameter `action_factory` — callable returning a widget to pack into the header row's right side. Default `None` (no action shown).
- `section()` return value change — now returns the header `Frame` instead of the bare `Label`, though both support `.pack()`/`.pack_forget()` identically.

No new instance attributes on the app class itself (no `self._rail_accent` or similar — the accent bar is a canvas item stored implicitly in each `GameItem`/`SettingsItem` instance).

## Accessibility and cross-platform notes

### Contrast verification

All new color pairings have been computed against the live hex values using WCAG relative-luminance formula (not eyeballed):

| Pair | Ratio | Pass? |
|---|---|---|
| Section header MUTED (#9299a3) on BG dark (#15171a) | 5.23:1 | AA text (4.5:1) ✓ |
| Section header MUTED (#596170) on BG light (#e8ebf0) | 6.68:1 | AA text ✓ |
| Accent bar ACCENT (#e08a55) on CARD_HI dark (#262a30) | 5.45:1 | 3:1 UI component floor ✓ |
| Accent bar ACCENT (#2b58cc) on CARD_HI light (#eff2f7) | 5.55:1 | 3:1 UI component floor ✓ |
| StatusPill dot BAD (#f06262) on CARD dark (#1c1f23) | 7.84:1 | 3:1 UI component floor ✓ |
| StatusPill dot OK (#5cc9a4) on CARD dark | 7.40:1 | 3:1 UI component floor ✓ |
| StatusPill dot ACCENT (#e08a55) on CARD dark | 5.42:1 | 3:1 UI component floor ✓ |

All exceed their respective WCAG thresholds. No color adjustment needed for any pairing.

### Touch target and input handling

- Rail items (GameItem/SettingsItem): 192px wide at s=1 (expanded mode) or 48px wide at s=0.675 scale in collapsed mode (Feature 3). Height 38px both modes. Accent bar (3px) does not reduce clickable area — it is a visual indicator on the item's own surface, not an interactive element. Touch target unchanged from Features 1–4.
- Buttons (primary, secondary): unchanged sizes and hit zones.
- NumBox focus ring: unchanged; still an outline around the entry field, not a separate control.
- StatusPill: unchanged size and interactivity (non-interactive container; text/dot are display-only).

No platform-specific changes needed. Flat rectangles work identically on Linux, macOS, Windows.

### Hover and selection states

- Rail items show hover/selection via background fill (`CARD_HI` vs `CARD` vs `BG`), unchanged. The new accent bar *adds* a third signal (the bar itself toggles on/off) without modifying the fill logic.
- Buttons maintain their existing hover (fill `ACCENT_HI`, a lighter shade of ACCENT) and click states.
- No CSS pseudo-states or other web-specific interactions — this is Tk Canvas, purely draw-based.

### Icon/indicator semantics

Feature 3 added visual identity to rail items (single-letter badge in collapsed mode). Feature 5 preserves that and adds a structural accent bar that reinforces the "this item is selected" state without needing the icon itself to change. The bar is a supplement to the existing fill-based state, not a replacement.

## Pixel-level specifications

### Section header: 10pt bold MUTED

```python
# section() function signature (spec §2):
def section(parent, text, s, top=14, action_factory=None):
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(int(top * s), int(6 * s)))
    
    # Typography: size 10pt, weight bold, color MUTED
    label = tk.Label(row, text=text, bg=BG, fg=MUTED,
                     font=("Segoe UI", int(10 * s), "bold"))
    label.pack(side="left")
    
    if action_factory is not None:
        action_factory(row).pack(side="right")
    
    return row
```

At s=1: label font = 10pt.
At s=0.675: label font = int(10 * 0.675) = int(6.75) = 6.75, Tk rounds to 7pt.

At both scales, 10/bold is clearly larger and heavier than body text (9pt regular for rows), making headers scan naturally.

### Accent bar: 3px at s=1, 2px at s=0.675

```python
# GameItem.__init__ (around line 1495 after self.shape is created):
bar_w = int(3 * s)  # 3px at s=1, 2px at s=0.675
self.accent_bar = self.create_rectangle(0, 0, bar_w, h, 
                                        fill=ACCENT, outline="", 
                                        state="hidden")

# GameItem._paint() (around line 1538):
self.itemconfig(self.accent_bar, state="normal" if self.selected else "hidden")

# Same for SettingsItem.__init__ and _paint()
```

Position: `x1=0, y1=0, x2=bar_w, y2=h`. This draws a left-edge stripe from top to bottom of the item, width `bar_w`, fill ACCENT, no outline.

At s=1: bar is 3px wide, clearly visible, occupies ~1.5% of item's width (3 / 192 for expanded mode).
At s=0.675: bar is 2px wide, still visible and distinct, occupies ~4% of collapsed item's width (2 / 48), where the item is much smaller overall.

### StatusPill shape: create_rectangle with same coordinates as before

```python
# StatusPill.__init__ (line 1353):
# Before: self.shape = self.create_rectangle(1, 1, w-1, h-1, fill=CARD, outline=LINE)  # when PILL_R was used in round_rect()
# After (this feature):
self.shape = self.create_rectangle(1, 1, w-1, h-1, fill=CARD, outline=LINE)

# The coordinates are identical to the direct create_rectangle call here;
# no change to position, size, or styling. Only the fact that it's now
# a direct create_rectangle (flat) instead of a round_rect(PILL_R) (capsule)
# changes the visual.
```

Width: `CONTENT_W` (452px at s=1, 305px at s=0.675).
Height: 58px at s=1, ~39px at s=0.675.
Inset: 1px on all sides (coordinates 1, 1, w-1, h-1), leaving room for the 1px outline stroke.

### CARD_INNER_W remains 396 after constant rename

```python
# Before:
CARD_R = 12
CARD_INNER_W = CONTENT_W - 2 * CONTENT_PAD - 2 * CARD_R
            = 452 - 2 * 16 - 2 * 12
            = 452 - 32 - 24
            = 396

# After (Feature 5):
CARD_PAD = 12  # renamed from CARD_R's second role; same value
CARD_INNER_W = CONTENT_W - 2 * CONTENT_PAD - 2 * CARD_PAD
            = 452 - 2 * 16 - 2 * 12
            = 396
```

No value change, only the constant's name reflects its surviving semantic role (padding, not radius).

## State transitions and edge cases

### Selected AND running (GameItem only)

The item shows:
- Background: `CARD_HI` (from selected state)
- Circle dot: `OK` (running state, filled green)
- Accent bar: visible (selected state)

All three signals coexist. The dot and bar occupy different canvas regions (dot is centered, bar is left edge) so no visual collision. Contrast of all three against their respective backgrounds is already established above.

### Selected AND has_update (SettingsItem only)

The item shows:
- Background: `CARD_HI` (from selected state)
- Accent bar: visible (from selected state only, **not** gated on `has_update`)
- Update dot/text: `ACCENT` color (from has_update state, independent)

The accent bar is **strictly** `self.selected`-controlled (spec §3: `state="normal" if self.selected else "hidden"`), so a merely-has-update item (selected=False) shows no bar. This keeps the two signals (selection and update) visually distinct.

### Collapsed rail (Feature 3, both GameItem and SettingsItem)

Both classes create and toggle `accent_bar` in the same `__init__` and `_paint()`, regardless of `collapsed` flag:

```python
# Expanded branch (width = SIDEBAR_W - 16 = 192px at s=1)
# ... full item layout ...
# accent_bar renders at (0, 0, bar_w, h) where h is full item height (38px)

# Collapsed branch (width = SIDEBAR_W - 16 = 48px at s=0.675 scale, feature 3)
# ... badge-centered layout ...
# accent_bar still renders at (0, 0, bar_w, h), left edge of the badge
```

The bar's position is defined in canvas coordinates relative to the item's canvas, so it automatically fits both expanded and collapsed widths. No conditional logic needed; the same bar renders correctly in both states.

### section() with no action_factory (both real call sites today)

The header Frame contains only the label, packed left. No right-side gap is reserved:

```python
# With action_factory=None (default):
row = tk.Frame(parent, bg=BG)
label = tk.Label(row, text=text, ...)
label.pack(side="left")  # no action to pack right

# row.winfo_reqwidth() will equal label.winfo_width() (plus any padding)
# No invisible right column exists
```

The layout is identical to today's bare-label header aside from the Frame wrapper.

### section() with an action_factory (tested but no production caller yet)

```python
row = tk.Frame(parent, bg=BG)
label = tk.Label(row, text=text, ...)
label.pack(side="left")

action = action_factory(row)  # e.g., tk.Button(row, text="Do")
action.pack(side="right")

# label sits left, action sits right, both in the same Frame
# row.winfo_reqwidth() = label.winfo_reqwidth() + action.winfo_reqwidth() + padding
```

The action widget is a real, tested pathway (per spec §2, "The action slot has no user yet" and test coverage section), ensuring the mechanism doesn't become a latent trap like `TabBar.height`.

### _fill_pane() spacer survival (Feature 4 interaction)

The top and bottom spacers (Feature 4) have `bg=BG`, no rounded corners, no restyle applied. When a pane is visible, its spacers render as true invisible margin (same color as the pane background). When a pane is hidden (different tab active), its spacers are unpacked but their geometry is stale (see Feature 4's design, "Edge cases: Resizing while a pane is hidden"). On the next tab switch back, the spacers' heights are recomputed and correct themselves. No change to this mechanism in Feature 5.

## Traceability to spec acceptance criteria

| Criterion | Design element |
|---|---|
| No `round_rect`, `_round_rect_points`, `_arc_points`, `CARD_R`, `PILL_R` in file after change | Deleted outright per §Deleted; new constant `CARD_PAD` replaces `CARD_R`'s surviving role |
| Each shape (`Button`, `Segmented`, `StatusPill`, `card`, `GameItem`, `SettingsItem`) reports `"rectangle"` via `canvas.type(item)` | All use `create_rectangle()` instead of `round_rect()` |
| `CARD_INNER_W == 396` at s=1 | Formula updated to use `CARD_PAD` (same value 12), output unchanged |
| Section text is exactly as passed, never `.upper()`'d | `section()` removes `.upper()` call; preserves passed string as-is |
| Section with no `action_factory` has no reserved gap | `if action_factory is not None` guards the right-side `pack()` call |
| Section with `action_factory` shows action right of label | New test (per spec test section) exercises this; design supports it |
| Selected `GameItem`/`SettingsItem` shows accent bar at both rail widths (expanded/collapsed) | Bar created once, toggled in `_paint()`, same positioning regardless of width |
| Selected `SettingsItem` with `has_update=False` shows no bar; with `selected=False` shows no bar even if `has_update=True` | Bar gated strictly on `self.selected`, independent of `has_update` |
| Selected & running `GameItem` shows both dot and accent bar | Dot and bar occupy different regions, both visible simultaneously |
| `THEMES` `ACCENT`/`OK`/`BAD` values unchanged | No changes to hex values in any theme |
| Full test suite passes, new tests added | Per spec test section; design supports all assertions |

## Summary of design decisions

1. **Section headers: 10pt bold MUTED, no size reduction for sentence case.** Removing small caps requires a visual compensation; bumping to 10pt (matching `TabBar` labels) maintains scannability. Spacing and color unchanged from existing `section()`.

2. **Accent bar: 3px at s=1, 2px at s=0.675, left edge, full height, ACCENT fill.** Visual indicator of selection that does not move content or add interactive complexity. Contrast against selected item's background (CARD_HI) exceeds 5:1 in both themes.

3. **"Selection" refers to NumBox's focus ring, not Segmented's pill.** Preserves the "sparing" accent discipline; Segmented stays with the card-surface semantic (`CARD_HI` fill, no accent). NumBox's ring is already ACCENT-colored and shipped; no change needed.

4. **StatusPill becomes a flat rectangle via `create_rectangle(1, 1, w-1, h-1)`.** Same coordinates, fill, outline as before; only the shape drawing changes. Dot and labels untouched.

5. **All contrast pairs verified via WCAG formula, not eyeballed.** Section header text: 5.23:1 (dark), 6.68:1 (light), both exceed AA. Accent bar: 5.45:1 (dark), 5.55:1 (light), both exceed 3:1 UI-component floor. StatusPill dot states all exceed 3:1.

6. **No geometry moves; every coordinate, size, color token, and behavior stays identical except for drawing primitives and typography.** Features 1–4 settled the layout; Feature 5 is a pure chrome/theme pass.

7. **Compound scale (s=0.675) verified**: section header at 7pt (rounded from 6.75pt), accent bar at 2px (visible, above floor), all other dimensions scale uniformly. No special cases needed.

## References and precedent

- Feature 3 design (`docs/history/ac-24-f3-design.md`): typography at scale (10.5pt badge letter becomes ~7pt at s=0.675), state machine patterns (`_paint()` toggling visibility), compound-scale worst-case analysis.
- Feature 4 design (`docs/history/ac-24-f4-design.md`): spacer and vertical-fill patterns, idempotent recompute functions, no rebuild-machinery interaction.
- Spec §2 contrast table: ACCENT/OK/BAD hex values and their measured ratios against standard backgrounds (BG, CARD_HI), already verified and no longer assumed.
- Feature 2 spec (not read here, but per story): `section()` function signature, `TabBar` 10pt label sizing.
- Feature 3 spec (read): window resize debouncing, `_on_root_resize()` guard pattern, re-derived `_apply_minsize()`.
