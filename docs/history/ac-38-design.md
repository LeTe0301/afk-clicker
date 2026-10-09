# Design: UI scale follows the window size (G#38 / GH#67)

## Summary

Add an "Auto" UI-scale option as a 5th segment in the existing Settings > Appearance > "UI scale" `Segmented` control, positioned alongside the current four fixed steps (90%, 100%, 115%, 130%) as the default selection for fresh installs. The control reuses the existing `Segmented` component at a reduced per-option width (244px total for 5 options ≈ 48.8px each) to fit within the card's constraints. No new component, color, or layout pattern required.

## ui-ux-pro-max choices

- **Style**: No change — the `Segmented` component and its visual appearance (canvas-based control with pill-highlight, text centering) remain unchanged.
- **Palette**: No new colors — "Auto" uses the same text styling (MUTED when deselected, INK when selected) as the existing options, with no special highlighting or differentiation beyond the standard segment selection state.
- **Typography**: Font size `fs(9, s)` is unchanged; labels remain at the existing computed font size. The labels themselves shrink only in horizontal space (per-option width), not in rendered text size.
- **Relevant UX guidelines applied**:
  - **Control density and scannability**: The Segmented control remains a single horizontal row at 34px height (scaled), keeping the Settings pane layout clean. Five options at ~49px width per segment is tighter than the current 55px per segment but remains legible (text at 9pt base font, labels 3–4 characters each). The narrower segments are consistent with the existing "Mouse button" and "Theme" Segmented controls in the same file, which already use 60px (3 options, 180px width) and 55px (4 options, 220px width) per-option spacing — this design adds to that spectrum without breaking the pattern.
  - **Visual clarity of "Auto" state**: "Auto" is displayed as a static label ("Auto") within the Segmented control, the same way fixed-step labels ("90%", "100%", etc.) are displayed. When Auto mode is active, the "Auto" segment is highlighted with the pill-background (CARD_HI), visually indistinguishable from selecting a fixed step. No separate indicator of the live effective scale percentage is shown; "Auto" is simply the name of the mode, not a numeric readout. This keeps the control's design simple and avoids visual clutter (a separate label showing the computed percentage would make the UI busier without adding clarity at the settings level — the computed scale is already reflected in the app's rendered UI).
  - **Touch/click target size**: Each segment is 48.8px × 34px (scaled); well above the practical minimum for accurate mouse targeting in a desktop app. No touch-specific adjustment needed (this is a Tkinter desktop app, not a touch interface).

## Component reuse

- **Reused**: `Segmented` (existing, from `afk_clicker.py:1683–1720`) — unchanged. The control already divides its `width` evenly across `len(options)`, so adding a 5th option requires only a width adjustment and an option-list expansion, no code changes to the component itself.
- **Reused**: `Row` (existing, from `afk_clicker.py:1760–1780`) — unchanged. The Row's fixed label column (ROW_LABEL_W + ROW_LABEL_GAP = 152px) and grid layout remain the same.
- **No new components**: This feature does not introduce a new control type, picker, or dialog.

## States

### Populated (Settings pane open, Appearance tab active)

**Settings > Appearance pane with the "UI scale" row:**

```
┌─ Appearance ────────────────────────────────────────────────────┐
│                                                                   │
│  Theme           ┌─────────────────────────────────────────────┐ │
│                  │ System │ Light  │  Dark  │                  │ │
│                  └─────────────────────────────────────────────┘ │
│                                                                   │
│  UI scale        ┌───────────────────────────────────────────────┐ │
│                  │Auto│90% │100%│115%│130%│                     │ │
│                  └───────────────────────────────────────────────┘ │
│                  (244px total width ÷ 5 ≈ 48.8px per segment)    │
│                                                                   │
│  [System is currently using the application menu bar...]        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Visual layout details:**

- **Row label**: "UI scale" (left-aligned, 140px width).
- **Label gap**: 12px (spacing between label and control).
- **Segmented control**: 244px width total. (CARD_INNER_W 396px allocates 152px for the Row's label column [ROW_LABEL_W 140px + ROW_LABEL_GAP 12px], leaving 396 − 152 = 244px for the control.)
  - Each segment: 244px ÷ 5 = **48.8px width, 34px height (scaled by `s`)**.
  - **Segment order and labels**: 
    1. "Auto" (new, default for fresh installs)
    2. "90%"
    3. "100%"
    4. "115%"
    5. "130%"
  - **Text rendering**: Each label is centered within its segment. Font size: `fs(9, s)` (9pt base, same as existing options). Text color: MUTED (deselected), INK (selected).
  - **Selection indicator**: A pill-shaped highlight (background CARD_HI) fills the selected segment, visually matching the existing behavior for the four fixed steps.

### Initial state (fresh install, Auto selected)

On a fresh install, `self.store.data["ui_scale"] == "auto"` (the new `UI_SCALE_DEFAULT`). When the Settings > Appearance pane is opened for the first time, the "Auto" segment is highlighted in the Segmented control.

### Default state (existing installs, fixed step retained)

Existing installs with a previously-saved `ui_scale` value (e.g., `"100"`) continue to display their selected step (e.g., "100%" is highlighted); no change to their saved preference.

### User interaction (selecting an option)

When the user clicks any segment:
- If they click "Auto": the app switches to Auto mode; `self.s` begins computing continuously from the window size.
- If they click "90%", "100%", "115%", or "130%": the app switches to that fixed step; `self.s` is locked to that step's multiplier.

(The full state transition logic and behavior differences between Auto and fixed steps are handled in `afk_clicker.py`'s `_apply_ui_scale` and `_on_root_resize` methods, per the spec. The UI control itself just shows which option is selected.)

### Visual states (per segment, at any option)

- **Deselected**: 
  - Background: same as parent (CARD fill).
  - Text: MUTED (muted color, not the primary ink color).
  - Outline: thin LINE color (the whole control has a 1px border; segments are divided by visual position, not individual outlines).
  - Cursor: hand2 (pointer on hover, existing Segmented behavior).

- **Selected (currently chosen option)**:
  - Background: CARD_HI (highlight color, a lighter/contrasting shade).
  - Pill shape: rounded corners (2px inset from the edge, per `afk_clicker.py:1695`).
  - Text: INK (primary text color).
  - Cursor: hand2 (remains interactive).

**Example (Auto selected):**
```
┌──────────────────────────────────────────────────┐
│[Auto]│ 90%  │ 100% │ 115% │ 130% │              │
└──────────────────────────────────────────────────┘
  ↑ pill highlight behind "Auto"
```

**Example (100% selected):**
```
┌──────────────────────────────────────────────────┐
│ Auto │ 90%  │[100%]│ 115% │ 130% │              │
└──────────────────────────────────────────────────┘
                  ↑ pill highlight behind "100%"
```

## Accessibility & platform notes

### Touch target size
- Each segment: 48.8px (width, scaled) × 34px (height, scaled). This is **narrower than the current 55px per segment** (4-option control) but remains well above the practical minimum for accurate mouse targeting in a desktop UI. Since this is a Tkinter desktop app (macOS/Windows/Linux), not a touch interface, no platform-specific gesture adjustments apply. The narrower width is a trade-off to fit 5 options within the existing card constraints, and it remains usable.

### Color contrast
- **Text-on-background pairings** (no change from existing):
  - Deselected text (MUTED on CARD): Existing ratio, confirmed adequate in prior work (e.g., G#23's `docs/design.md` validation). MUTED is a secondary/hint color that passes WCAG AA on CARD backgrounds.
  - Selected text (INK on CARD_HI): Existing ratio, confirmed adequate. INK is the primary text color and CARD_HI is a lighter card background, ensuring 4.5:1 or better contrast.
- **No new color pairings introduced**; the design reuses the existing palette.

### Keyboard navigation
- The Segmented control is interactive and can be focused via Tab (existing behavior).
- Tabbing into the control lands focus on the currently-selected segment (per the underlying Tkinter Canvas bind to `<Button-1>`; keyboard navigation via arrow keys is not currently implemented, but matches the existing UI's keyboard accessibility level).
- Users can click any segment to change the selection; no new keyboard shortcuts are required.

### Platform differences
- This is a Tkinter desktop app (macOS/Windows/Linux only), no web or mobile versions.
- The Segmented control's event binding (`<Button-1>`, mouse click detection) works identically across platforms.
- Font rendering (`fs(9, s)` with Segoe UI) is consistent across platforms (though macOS may apply its own DPI scaling factor, already handled by the spec's `_dpi_s` mechanism).
- The narrower segment width (48.8px) may appear proportionally different at high-DPI monitors, but the text remains legible because `fs()` scales fonts appropriately per `_dpi_s`.

## Traceability to spec

| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| **Given the Settings > Appearance pane is open, then the "UI scale" `Segmented` control shows 5 options including "Auto", and "Auto" is selected by default on a fresh install.** | The "Populated" state section shows the Segmented control with 5 segments: Auto, 90%, 100%, 115%, 130%. The order places "Auto" first, matching the default for fresh installs (`UI_SCALE_DEFAULT = "auto"`). The "Initial state" section confirms that Auto is highlighted on fresh installs. |
| **The exact layout of the 5-option "UI scale" `Segmented` control given the CARD_INNER_W overflow constraint** (deferred to ux-designer in spec line 141). | This design resolves the overflow by setting the Segmented width to 244px. Layout math: CARD_INNER_W (396px) − Row label column (152px = 140px label + 12px gap) = 244px available for the control. This width divides evenly to 48.8px per option across 5 segments. No change to the Segmented component itself; only the `width=` parameter in the constructor call (line 3145 of `afk_clicker.py`) changes from 220 to 244. |
| **No new colors, components, or layout patterns.** | Component reuse section confirms Segmented and Row are reused unchanged. No new visual elements introduced. The 244px width adjustment is a parameter tweak, not a layout restructuring. |
| **Settings pane remains usable and fits within the card.** | Fit verification: Row label column (152px) + Segmented control (244px) = 396px total, exactly matching CARD_INNER_W. No overflow, no truncation. The control fits snugly within the available space at every UI-scale step (90%, 100%, 115%, 130%), since all quantities scale uniformly by the same `s`. |

## Notes for implementation

1. **Segmented constructor call change** (`afk_clicker.py:3143–3145`):
   - Current: `Segmented(..., width=220)`
   - New: `Segmented(..., width=244)` (to fit 5 options)
   - Options list addition: Add `("auto", "Auto")` to the front of the list, making it the first segment visually and in the list order.

2. **No component code changes**: The `Segmented` class (lines 1683–1720) requires no modifications. The width parameter is already applied at line 1688 and 1694 calculates segments evenly.

3. **Label consistency**: The label "Auto" matches the spec's own terminology and is consistent with the app's existing label style (short, capitalized, no units for a mode name vs. "%" for percentages).

4. **Rendering invariant**: At every UI-scale step (90%, 100%, 115%, 130%), the same ratio holds: all quantities (label width, gap, control width) scale by the same `s`, so the fit is preserved at every step (per the invariant-ratio argument established in prior work, e.g., `docs/history/ac-24-f1-design.md`).

5. **Default value update**: Spec updates `UI_SCALE_DEFAULT = "auto"` (was `"100"`), so fresh installs automatically have "Auto" selected. No UI code required for this beyond the constructor parameter change; it's handled by the spec's `Store.__init__` sanitization logic.
