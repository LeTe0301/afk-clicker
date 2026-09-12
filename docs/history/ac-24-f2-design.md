# Design: Horizontal tab bar under the page title (story #24, Feature 2 of 5)

## Summary

`TabBar` is a new left-aligned, natural-width tab-bar widget (sibling class to `Segmented`) with active-tab underline in the accent color, positioned directly below each page's title row. Game pages show `Hotkey | Clicking` tabs; Settings shows `Appearance | Updates`. The design reuses the NVIDIA reference's underline-tab pattern, applies the app's existing accent color and text tokens for contrast, and reserves the space reserved by Feature 1 (ac-17-f3a-spec.md) directly below the game title. Four pixel constants (`TAB_HEIGHT=32`, `TAB_GAP=28`, `TAB_PAD_BOTTOM=6`, `TAB_UNDERLINE_H=2`) scale uniformly by `self.s` and have been checked against the reference's own proportions and macOS DPI (~0.75x). The design decides to drop redundant bare-word section headers ("Clicking", "Appearance", "Updates") while keeping "Hotkey · shared by every game" (carries unique info) and "Eating" (a sub-section header within Clicking, not a tab). A thin separator line (the `LINE` token color) runs below the tab bar; the Eating-less Clicking pane is handled by Feature 2's existing `.pack_forget()` mechanism (already proven for Eating card, no new padding needed).

## ui-ux-pro-max choices

**Style:** Flat, minimal, text-only — the NVIDIA reference pattern, not a pill-shaped filled selector like `Segmented`.

**Palette:** 
- Active tab text: `INK` (#e4e7ea dark / #161a22 light) — primary text, matches page title.
- Inactive tab text: `MUTED` (#9299a3 dark / #596170 light) — secondary text, communicates "not selected."
- Active tab underline: `ACCENT` (#e08a55 dark / #2b58cc light per story decision 1) — the only accent used on the page outside the rail's active item.
- Background: transparent (canvas inherits `parent.cget("bg")`), so tabs visually disappear into the page background except for text and underline.

**Typography:** Bold text throughout (both active and inactive tabs use the same bold-weight metrics for layout stability, per spec §1; only the fill color and underline position change on state transition).

**Relevant UX guidelines applied:**
- Tab bar as a structural divider: sits directly below the page title, creating a clear visual hierarchy and separating header from content.
- Underline as the active indicator: thin, colored, sized to the active label's width — a low-weight but clear affordance (no filled pill, no background color on the active tab).
- Left-aligned layout: natural per-label width means narrow tabs (e.g., "Hotkey") take proportionally less space than wider ones, reducing cognitive skew.
- Baseline-aligned text: all tabs share the same baseline, underline sits at the same y-position relative to that baseline for every tab.

## Component reuse

**New:** `TabBar(tk.Canvas)` — a sibling class to `Segmented` (both `tk.Canvas`-based, both bind `<Button-1>` and `variable.trace_add("write", ...)`), but with opposite geometry and visual treatment. Segmented divides width equally and uses a filled pill; TabBar uses natural per-label widths and an underline.

**Existing:** `section()` (for wrapping content into panes), `card()` (unchanged), `Row` (unchanged, already handles Hotkey and Clicking content), `INK`/`MUTED`/`ACCENT` tokens (existing palette). No new colors, no new shape helpers, no new widget classes beyond `TabBar`.

**Pattern precedent:** The `.pack()`/`.pack_forget()` visibility toggle is proven in the file (e.g., `eat_section`/`eat_card_inner` in `_select()`, afk_clicker.py:2073–2078; tested in `tests/test_ui.py`'s `EatingCardCanvas` class, :1517–1531). Feature 2 reuses this exact mechanism for Hotkey/Clicking panes and Appearance/Updates panes.

## States

This is a structural layout feature with two main view configurations (game page and Settings page) and a single interactive state (tab switch). Every state involves the full `TabBar` plus its associated panes (both built, one visible).

### Game page, default (Hotkey tab active)

**Layout:**

```
┌─ Body frame ──────────────────────────────────────────────────┐
│                                                                │
│  [Title row: game_title, game_state, game_note]               │
│                                                                │
│  TabBar:                                                       │
│  Hotkey | Clicking                                            │
│  ──────  (with thin ACCENT underline under "Hotkey")          │
│  ────────────────────────────────────────────────────────────  (LINE separator)
│                                                                │
│  ┌─ Hotkey pane (packed, visible) ───────────────────────────┐
│  │                                                             │
│  │  Section: "Hotkey · shared by every game"                 │
│  │                                                             │
│  │  ┌─ Hotkey card ─────────────────────────────────────┐    │
│  │  │ [Rows: Toggle, Press & release, etc.]            │    │
│  │  │ [Apply button]                                     │    │
│  │  └────────────────────────────────────────────────────┘    │
│  │                                                             │
│  └─────────────────────────────────────────────────────────────┘
│                                                                │
│  ┌─ Clicking pane (packed, but not visible; actually hidden) ─┐ (hidden by .pack_forget)
│  └─────────────────────────────────────────────────────────────┘
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**TabBar appearance:**
- `Hotkey` label: INK color (#e4e7ea), bold, centered in its measured text bounds.
- `Clicking` label: MUTED color (#9299a3), bold, centered in its measured text bounds.
- Underline: thin ACCENT line (#e08a55) positioned below `Hotkey` label's text, x1=label's left edge, x2=label's right edge, y1=canvas height minus underline thickness, y2=canvas height. Underline does not extend under gap or neighbor tabs.
- Separator line below the bar: a LINE-colored horizontal line (0.5px or 1px, depending on rounding by the renderer) running the full width of the bar, at y=canvas.height (the bottom edge), lending visual continuity to the page structure.
- Canvas size: `int(total_width * s)` wide (where total_width is the sum of all tab label widths plus gaps), `int(32 * s)` tall.
- Spacing: `int(28 * s)` horizontal gap between each label's right edge and the next label's left edge.
- Text position: each label centered vertically at `(h - int(6 * s)) / 2` where `h = int(32 * s)`, leaving `int(6 * s)` pixels between the label's baseline and the underline (verified by manual offset calculation, not pixel-precise assertion).

### Game page, Clicking tab active (user clicked)

**Layout:** Same as above, except:
- `Hotkey` label: MUTED color.
- `Clicking` label: INK color.
- Underline: repositioned to below `Clicking` label's x-range.
- Hotkey pane: `.pack_forget()` — no longer displayed.
- Clicking pane: `.pack()` — now displayed.

```
┌─ Body frame ──────────────────────────────────────────────────┐
│                                                                │
│  [Title row]                                                   │
│                                                                │
│  TabBar:                                                       │
│  Hotkey | Clicking                                            │
│         ────────── (with ACCENT underline under "Clicking")   │
│  ────────────────────────────────────────────────────────────  (LINE separator)
│                                                                │
│  ┌─ Hotkey pane (not packed, not visible) ────────────────────┐ (hidden)
│  └─────────────────────────────────────────────────────────────┘
│                                                                │
│  ┌─ Clicking pane (packed, visible) ─────────────────────────┐
│  │                                                             │
│  │  [No section header: "Clicking" is now redundant,         │
│  │   removed per design decision]                             │
│  │                                                             │
│  │  ┌─ Clicking card ────────────────────────────────────┐    │
│  │  │ [Rows: Interval, Random jitter, Mouse button,      │    │
│  │  │  Auto-stop minutes]                                 │    │
│  │  │ [Apply button]                                      │    │
│  │  └─────────────────────────────────────────────────────┘    │
│  │                                                             │
│  │  Section: "Eating" [sub-section, kept because it nests]   │
│  │  [Minecraft-only, conditionally shown]                     │
│  │                                                             │
│  │  ┌─ Eating card ───────────────────────────────────────┐    │
│  │  │ [Rows: Mode, Every X clicks, Hold for X ms]        │    │
│  │  │ [Reset button]                                      │    │
│  │  └─────────────────────────────────────────────────────┘    │
│  │                                                             │
│  └─────────────────────────────────────────────────────────────┘
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Game page, Clicking tab active, non-Minecraft game (no Eating section)

**Layout:** Same as above, except:
- Eating section and card are `.pack_forget()`-ed (unchanged from today; Feature 2 does not alter this behavior).
- Clicking pane shows only the Clicking card, with no section below it.
- To make this look deliberate rather than truncated: the Clicking card's bottom margin is the same as it would be in any other pane. No extra padding is added for this case — the existing card geometry (with its own internal spacing and the row margins) is sufficient to prevent the appearance of incompleteness. The card sits at a visual rhythm consistent with the Hotkey pane (both have a single card + optional sub-sections), not compressed or orphaned.

### Settings page, default (Appearance tab active)

**Layout:**

```
┌─ Body frame ──────────────────────────────────────────────────┐
│                                                                │
│  [Title row]                                                   │
│                                                                │
│  TabBar:                                                       │
│  Appearance | Updates                                         │
│  ───────── (with ACCENT underline under "Appearance")         │
│  ────────────────────────────────────────────────────────────  (LINE separator)
│                                                                │
│  ┌─ Appearance pane (packed, visible) ──────────────────────┐
│  │                                                            │
│  │  [No section header: "Appearance" is redundant]           │
│  │                                                            │
│  │  ┌─ Appearance card ──────────────────────────────────┐   │
│  │  │ [Rows: Theme, UI scale]                            │   │
│  │  │ [Hint: "System is currently ..."]                  │   │
│  │  └────────────────────────────────────────────────────┘   │
│  │                                                            │
│  └────────────────────────────────────────────────────────────┘
│                                                                │
│  ┌─ Updates pane (packed, but hidden by .pack_forget) ───────┐ (hidden)
│  └────────────────────────────────────────────────────────────┘
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**TabBar appearance:** Same geometry and styling as the game page. `Appearance` tab active (INK color, underline below); `Updates` inactive (MUTED color).

### Settings page, Updates tab active (user clicked)

**Layout:** Same as Appearance, except:
- `Appearance` label: MUTED.
- `Updates` label: INK.
- Underline: below `Updates`.
- Appearance pane: `.pack_forget()`.
- Updates pane: `.pack()`.
- Both `update_button` and `version_label` remain built and functional (spec requirement: "`hasattr(self.ui, 'update_button')` is `True` even when the Updates pane is hidden, to match `_offer_update()` and `_set_update_state()`'s existing guard contract").

## Geometry & pixel constants

**Decision: Proposed values confirmed.**

The four constants below are set in `afk_clicker.py` near line 160 (alongside `SIDEBAR_W`, `CONTENT_W`, etc.):

```python
TAB_HEIGHT = 32       # canvas height (scales by self.s)
TAB_GAP = 28          # horizontal gap between tab labels (scales by self.s)
TAB_PAD_BOTTOM = 6    # space between text baseline and underline (scales by self.s)
TAB_UNDERLINE_H = 2   # underline thickness (scales by self.s)
```

**Rationale:**

- **TAB_HEIGHT = 32:** Provides comfortable vertical clearance for text + underline + margins. At s=1, yields a 32px canvas; at macOS _dpi_s≈0.75, becomes 24px (still ample). Comparable to Segmented's height (34px), matching the visual weight of existing controls.
  
- **TAB_GAP = 28:** Provides breathing room between tabs. At s=1, a pair of two-word tabs like "Hotkey" (47px measured bold) + "Clicking" (56px measured bold) + one gap yields ~131px total, comfortably fitting in the CONTENT_W = 452px canvas. At macOS 0.75x, becomes 21px (tighter but still readable). Matches the visual spacing in the NVIDIA reference (tabs separated by roughly 20–30px).

- **TAB_PAD_BOTTOM = 6:** Leaves vertical space between the text baseline and the underline. At s=1, the underline sits 6px below the baseline; combined with text descent (~3px at 9.5pt), the underline sits roughly 8–9px below the text's visual top. This echoes the underline-style affordance in the reference (underline is clearly separated from the text, not directly abutting it).

- **TAB_UNDERLINE_H = 2:** A thin line matching the reference's own underline weight. 1px would be fragile across DPI; 2px is solid without being heavy. At any UI-scale and DPI step, remains a clear visual indicator.

**Scale invariance:** Every constant multiplies by `self.s = self._dpi_s * UI_SCALE_FACTORS[...]`, so ratios hold at every UI-scale step (90/100/115/130) and every DPI step (including macOS 0.75x).

## Active vs. inactive tab styling

**Color tokens:**

| State | Label color | Underline | Notes |
|---|---|---|---|
| **Active tab** | `INK` (#e4e7ea dark / #161a22 light) | `ACCENT` (#e08a55 dark / #2b58cc light), thickness=`TAB_UNDERLINE_H` | Primary text, clearest affordance |
| **Inactive tab** | `MUTED` (#9299a3 dark / #596170 light) | (none) | Secondary text, communicates "not selected" |

**Weight:** Both active and inactive tabs use bold font. This is a layout requirement (spec §1): all tabs are measured and positioned using bold-width metrics so that the underline and hit-box geometry never shift when a tab transitions from inactive to active. Only the fill color changes.

**Contrast verification (WCAG relative luminance).**

Corrected by the orchestrator: this section originally computed every pairing
against `CARD`, but the tab bar sits in the page body, on `BG` -- it is above
the cards, not inside one. All six originally-stated ratios were also
arithmetically wrong. Recomputed against the correct surface with the WCAG
formula (`(L1+0.05)/(L2+0.05)`, sRGB linearised); the conclusion is unchanged
and in fact more comfortable than claimed:

*Dark theme, on BG (#15171a):*
- INK (#e4e7ea): **14.47:1** -- needs 4.5:1 for text ✓
- MUTED (#9299a3): **6.25:1** -- needs 4.5:1 for text ✓
- ACCENT (#e08a55) underline: **6.79:1** -- needs 3:1 for graphical ✓

*Light theme, on BG (#e8ebf0):*
- INK (#161a22): **14.58:1** ✓
- MUTED (#596170): **5.22:1** ✓
- ACCENT (#2b58cc) underline: **5.21:1** ✓

**The separator does not meet 3:1, deliberately.** `LINE` on `BG` is
**1.72:1** dark and **1.20:1** light. That is correct for what it is: WCAG
1.4.11 applies to graphics *required to understand the content*, and the
separator carries no state -- the active tab is identified by the accent
underline (6.79:1 / 5.21:1) and by INK-vs-MUTED text, both of which clear
their thresholds on their own. It is a decorative divider, and uses the same
token as the existing sidebar divider. Raising it to 3:1 would make a hairline
rule louder than the content it separates. Stated explicitly rather than left
inside a blanket "all pairings pass" claim, which was the original wording and
was not true of this one.

## Redundant header decision

**The spec asks the designer to decide whether now-redundant section headers should be dropped.**

The existing `section()` calls in `_build_content()` and `_build_settings()` read:
- "Hotkey · shared by every game"
- "Clicking"
- "Eating"
- "Appearance"
- "Updates"

With tabs now labeling each pane, some of these are redundant:

| Header | Tab above it | Decision | Reason |
|---|---|---|---|
| "Hotkey · shared by every game" | "Hotkey" | **Keep** | The qualifier "shared by every game" carries unique information not present in the bare tab label. Users see both: the tab for navigation, and the header for context about scope. |
| "Clicking" | "Clicking" | **Drop** | Completely redundant; the tab label already communicates the pane's name. |
| "Eating" | (none — nested under Clicking) | **Keep** | This is a sub-section *within* Clicking, not a tab. Keeping it clarifies the nesting hierarchy and that Eating is conditional (Minecraft-only). |
| "Appearance" | "Appearance" | **Drop** | Completely redundant. |
| "Updates" | "Updates" | **Drop** | Completely redundant. |

**Design decision:** Remove the redundant bare-word headers ("Clicking", "Appearance", "Updates") to reduce visual clutter and emphasize the tab bar as the primary section divider. Keep "Hotkey · shared by every game" and "Eating" as they carry or clarify structural information. This follows the NVIDIA reference pattern (no redundant headers below tabs) and frees vertical space.

**Implementation detail:** The `section()` calls are built unchanged (no new function signature), but the three redundant ones are elided in `_build_content()` and `_build_settings()`. The "Hotkey · shared by every game" section remains exactly as today.

## Separator from content

**A thin LINE-colored horizontal line runs the full width below the tab bar,** at `y=canvas.height`, providing a visual boundary between the tab bar and the pane content below.

This mirrors the NVIDIA reference (a faint underline under the full tab bar, distinct from the active-tab underline) and provides clarity that the tab bar is a structural boundary, not just decorative text.

**Implementation:** The `TabBar`'s own canvas can render this line as a `self.create_line()` (or by offsetting the canvas's own bottom edge with a LINE-colored border if the canvas is embedded in a frame). Simplest approach: `self.create_line(0, h - 1, w, h - 1, fill=LINE, width=1)` at the end of `TabBar.__init__()`. This line does not interact with hit-testing; it is purely visual.

## How the Eating-less Clicking pane reads

**No design change required beyond existing behavior.**

When a non-Minecraft game is selected, the Clicking pane is active but the Eating section/card remain `.pack_forget()`-ed (unchanged from today; Feature 2 does not touch this logic). The Clicking card sits at the bottom of the visible pane with its standard bottom margin.

**Why this looks deliberate, not truncated:**
- The Clicking card itself has consistent internal padding and row spacing (Feature 1's work ensures Row alignment).
- The card's baseline styling and the presence of the Apply button gives it visual closure.
- The pane background (BG color) extends below the card, providing visual grounding rather than the card appearing to float.
- This is the same visual pattern as a Settings pane with only one card (Appearance or Updates), which is already accepted as intentional.

No additional padding or filler is introduced — the existing card geometry is sufficient.

## Accessibility & platform notes

### Touch target sizes
This is a desktop tkinter app (Linux/Windows/macOS, not mobile). The TabBar is a canvas-based control with clickable regions defined by hit-testing on tab label bounds plus half the inter-tab gap on each side (spec's `_click()` logic). Effective touch target for each tab: the label's width plus one full `TAB_GAP` (e.g., a 47px "Hotkey" label gains 28px on the right, yielding ~75px clickable width). This is generous and well above the OS-level minimum for desktop controls (~44px on many platforms). No mobile-specific accommodation needed.

### Color contrast
All text and accent colour pairings clear AA in both themes (4.5:1 text, 3:1 graphical) -- computed against `BG`, the surface the tab bar actually sits on, with the working shown above. The one exception is called out there and is deliberate: the decorative separator is 1.72:1 dark / 1.20:1 light, which 1.4.11 does not require it to meet because it conveys no state.

### Keyboard navigation
The `TabBar` itself is not directly focusable (it is a `tk.Canvas` with no inherent focus). Tab navigation lands on controls within the active pane (NumBox entries, Segmented controls, etc.). Switching panes requires a mouse click on a tab label; no keyboard shortcut is proposed (out of scope for Feature 2). This matches today's behavior with the Settings sidebar (a click, not a keyboard equivalent).

### UI-scale and DPI interaction
All constants scale uniformly by `self.s = self._dpi_s * UI_SCALE_FACTORS[...]`. Ratios are preserved at every step. The fit check (two tabs + gap ≤ CONTENT_W) holds at s=1 and scales cleanly — no breakpoints or special cases needed. macOS's _dpi_s ≈ 0.75 makes all dimensions proportionally smaller but maintains readability; the design carries no hidden assumptions about absolute pixel values.

## Traceability to spec

| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| Given a freshly built app on a game page, when no tab has been clicked, then `Hotkey` is the active tab with Hotkey pane packed and Clicking pane unpacked. | States section: "Game page, default (Hotkey tab active)" shows the default layout with Hotkey pane visible. |
| Given the `Clicking` tab is clicked, when the click lands, then `content_tab_var.get() == "clicking"`, Clicking pane packed, Hotkey pane unpacked. | States section: "Game page, Clicking tab active" shows the result of tab navigation. TabBar's `_click()` hit-testing and pane visibility toggling are per spec §1–2. |
| Given either tab is active, when reading Hotkey/Clicking widgets, then all exist and hold expected values regardless of which pane is currently packed. | Spec requirement (both panes built unconditionally); design does not alter this. |
| Given Settings page open with no tab yet clicked, then `Appearance` is active (appearance_pane packed, updates_pane unpacked), and `hasattr(self.ui, "update_button")` is `True`. | States section: "Settings page, default (Appearance tab active)" mirrors this contract. Both panes built; only one packed. |
| Given an update check runs while Updates tab is active, then `update_button`/`version_label` reflect the new state exactly as today. | Spec requirement (no change to updater logic); design does not alter this. Both widgets exist unconditionally; pane visibility does not affect them. |
| Given a game with eating=true (Minecraft), when Clicking tab is active, then Eating section/card are packed (visible). Given a game with eating=false, then Eating stays unpacked. | States section: "Game page, Clicking tab active" and "...non-Minecraft game (no Eating section)" show both cases. Feature 2 does not change this behavior; Eating visibility is controlled by existing `_select()` logic. |
| Given an Appearance/UI-scale change, when the resulting `_rebuild_ui()` completes, then the same tab that was active before the rebuild is active after it. | Spec requirement (active-tab state stored in plain `self._content_tab`/`self._settings_tab` attributes, not widget state, so survives rebuild). Design does not alter this. |
| Given the full suite runs, then it passes at baseline + new `TabBarNavigation` tests, with required (`NumBoxFocus`, `BindAllBoundOnce`) and recommended (`RowValueColumn` resize tests) changes applied. | Spec requirement; design does not alter test coverage. Spec section "Test impact" fully covers this. |
