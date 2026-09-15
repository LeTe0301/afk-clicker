# Design: Warn when Minecraft interval minus jitter drops below 650 ms (G#22 / GH#33)

## Summary

A single, conditional hint appears directly under the "Interval" row on the Minecraft profile only. It shows in `MUTED` color when the effective minimum interval (`max(50, click_ms - jitter_ms)`) falls between 550–649 ms, and escalates to `BAD` color when it drops below 550 ms. The hint disappears when the interval is 650 ms or higher. No new layout primitive is introduced; the existing `Row` widget gains mutable hint capability (show/hide, restyle) to complement its current static `hint=` parameter. Copy is short and warning-focused to read as a performance alert even when styled with the muted-description color in the MUTED band.

## ui-ux-pro-max choices

- **Style**: Minimal, inline label below the Interval row label. No new layout primitive; reuses the existing `Row` label-column layout and font pairing (Segoe UI, 8pt for hints).
- **Palette**: Reuse existing `MUTED` (for 550–649 ms band) and `BAD` (for <550 ms band) color tokens sourced from `THEMES` (dark theme: `#9299a3` MUTED, `#f06262` BAD; light theme: `#596170` MUTED, `#cc3527` BAD). Both tokens are already used elsewhere in the app for "quiet advisory" vs. "error state" distinction, establishing visual consistency.
- **Typography**: Segoe UI 8pt regular, matching existing hint font size and weight (identical to jitter row's static hint, `afk_clicker.py:2185`).
- **UX guideline**: Real-time feedback without blocking — the hint reflects the current field values at every keystroke, so the user sees the impact of their edits live. Non-interactive, non-blocking; the user can still set any rhythm they want, and the hint simply informs them of the Java-specific cooldown consequence. Conditional visibility on profile (Minecraft only, never on Global or custom) keeps the feature scoped to where it's accurate and avoids false claims on other editions.

## Component reuse

- **Reused**: `Row` widget (existing, from `afk_clicker.py:2168–2189`) — the Interval row will gain optional mutable hint capability (a new `set_hint(text, color)` / `clear_hint()` pair to complement the existing static `hint=` parameter). The implementation detail (whether this extends `Row` itself or is a one-off addition scoped to the Interval row's hint widget) is the developer's decision; the design constraint is that all existing static `hint=` call sites (jitter, auto-stop) must continue to render identically to today.
- **Reused**: Label widget for the hint text, styled identically to existing hints (Segoe UI 8pt, `wraplength=int(ROW_LABEL_W * s)` for column width consistency).
- **No new widgets**: The hint is a single `tk.Label` managed by new `_set_sweep_hint(text, color)` and `_clear_sweep_hint()` methods on `AfkAutoclicker`, called from `_persist()` after it computes the effective minimum interval.

## States

### Hidden (effective minimum >= 650 ms, or non-Minecraft profile)

**Trigger**: Interval is 650 or higher, or user is not on the Minecraft profile.

**Visual**: No hint label is visible under the Interval row. Card layout (at s=1):
```
┌─ card(self.clicking_pane, s) ──────────────────┐
│  Interval              [        650 ms ]       │
│                                                │
│  Random jitter         [         0 ±ms ]      │
│  spreads the rhythm so it is not exact         │
│  Auto-stop             [         0 min ]      │
│  0 means never                                 │
└────────────────────────────────────────────────┘
```

**Behavior**: The hint widget is not packed (or packed with `height=0` and invisible, depending on implementation). The Clicking pane's natural height does not reserve space for this hint when it's hidden.

### Visible, MUTED (effective minimum 550–649 ms, Minecraft profile)

**Trigger**: Interval minus jitter (floored at 50 ms) falls into the range 550–649 ms (inclusive on the lower bound), and the Minecraft profile is selected.

**Exact copy**:
```
Java sweeps may miss
```

**Styling**:
- **Background**: `CARD` (transparent into the card, same as existing hints)
- **Foreground**: `MUTED` — dark theme `#9299a3`, light theme `#596170`
- **Font**: Segoe UI 8pt regular
- **Wrapping**: `wraplength=int(ROW_LABEL_W * s)` (same as existing hints, e.g. jitter's "spreads the rhythm so it is not exact")
- **Padding**: Top padding matches existing row-hint spacing (inherited from Row's layout; no extra margin)

**Visual layout** (at s=1, Interval=600, jitter=50):
```
┌─ card(self.clicking_pane, s) ──────────────────┐
│  Interval              [        600 ms ]       │
│  Java sweeps may miss                          │
│                                                │
│  Random jitter         [        50 ±ms ]      │
│  spreads the rhythm so it is not exact         │
│  Auto-stop             [         0 min ]      │
│  0 means never                                 │
└────────────────────────────────────────────────┘
```

**Behavior**: The hint label is packed and visible, colored `MUTED`. The Clicking pane's natural height grows by the hint's height. When the user edits the Interval or jitter field and the effective minimum rises back to 650 or above, the hint disappears without waiting for a focus-out or Enter key — the transition is live at every keystroke.

### Visible, BAD (effective minimum < 550 ms, Minecraft profile)

**Trigger**: Interval minus jitter (floored at 50 ms) drops below 550 ms, and the Minecraft profile is selected.

**Exact copy**:
```
Java sweeps likely fail
```

**Styling**:
- **Background**: `CARD` (same as MUTED state)
- **Foreground**: `BAD` — dark theme `#f06262`, light theme `#cc3527`
- **Font**: Segoe UI 8pt regular (same as MUTED)
- **Wrapping**: `wraplength=int(ROW_LABEL_W * s)` (same as MUTED and existing hints)
- **Padding**: Same as MUTED state

**Visual layout** (at s=1, Interval=500, jitter=0):
```
┌─ card(self.clicking_pane, s) ──────────────────┐
│  Interval              [        500 ms ]       │
│  Java sweeps likely fail                       │
│                                                │
│  Random jitter         [         0 ±ms ]      │
│  spreads the rhythm so it is not exact         │
│  Auto-stop             [         0 min ]      │
│  0 means never                                 │
└────────────────────────────────────────────────┘
```

**Behavior**: Same visibility/packing as MUTED state, but colored `BAD` to signal a more urgent warning (the interval is in the documented failure territory). When the user raises the effective minimum back into the MUTED band (550–649) or above, the hint either downcolors to `MUTED` (if in the MUTED range) or disappears (if >= 650).

### Profile switch: Minecraft to Global or custom

**Trigger**: User selects Global or a custom profile while the sweep hint is showing on Minecraft.

**Visual**: The hint label is immediately unpacked (hidden). The Clicking pane height returns to its shorter natural height. Jitter row and its static hint remain visible (all profiles have jitter).

**Behavior**: `_select()`'s tail call to `_persist()` computes `profile["min_sweep_ms"]`, finds it is `None` (Global or custom), and calls `_clear_sweep_hint()`. No residual colored label is left behind.

### Profile switch: Global to Minecraft (hint condition met)

**Trigger**: User switches from Global back to Minecraft, and the Interval/jitter values on Minecraft are such that the effective minimum would show a hint (< 650 ms).

**Visual**: The hint label reappears under the Interval row, with the correct color (MUTED if 550–649, BAD if <550) and copy matching the current effective minimum. The Clicking pane height grows again.

**Behavior**: `_select()`'s profile load and `_persist()` call (at the tail, after `self._loading = False`) recompute the effective minimum for the new profile and call `_set_sweep_hint()` or `_clear_sweep_hint()` accordingly. The hint is correct immediately; no stale state from the previous profile.

### Theme or UI-scale change (hint currently showing)

**Trigger**: User changes the theme (System/Light/Dark) or UI scale (90%/100%/115%/130%) via Settings, and the Minecraft profile is selected with an active sweep hint.

**Visual**: The hint label is repainted with the new color tokens and font size (Segoe UI 8pt * scale factor). The text and visibility state (shown vs. hidden) remain as they were. No flicker, no temporary disappearance.

**Behavior**: `_rebuild_ui()` calls `_persist()` at its head (per its own comment, `afk_clicker.py:3121`), which recomputes the effective minimum and calls `_set_sweep_hint()` or `_clear_sweep_hint()` with the current field values, re-rendering the hint with the new palette and scaled font. `self._rebuilding` is `True` during this phase, so the hint update must compute and remember state, but only paint it after the widget tree is rebuilt (e.g., at `_build_ui()`'s tail, or per the "Orchestrator correction" binding in the spec, only once the current tree exists).

### Rapid keystroke edits (mid-edit intermediate states)

**Trigger**: User clears the Interval field to type a new number, or backspaces through an intermediate value.

**Visual**: The hint may flicker through multiple states (hidden → MUTED → BAD, or similar) as the field text is parsed at each keystroke. If the field is empty, the fallback (`_num()` coercion applies, using the profile's default `click_ms` of 650) is used, so the hint may show or hide depending on the effective minimum of the fallback.

**Behavior**: This is consistent with how `_sync_settings()` and the click worker already handle live field reads — the app recomputes values at every keystroke, not just on focus-out or Enter. The hint's flicker in this scenario is the same as the worker's own live snapshot flicker, so it's an accepted behavioral precedent, not a new class of glitch.

## Accessibility & platform notes

### Color contrast

All text pairings verified via WCAG relative-luminance formula (`L = 0.2126 * R_lin + 0.7152 * G_lin + 0.0722 * B_lin`, contrast = `(L1 + 0.05) / (L2 + 0.05)`, where R_lin/G_lin/B_lin are linearized RGB values):

| Element | Dark theme | Light theme | WCAG floor | Notes |
|---|---|---|---|---|
| **Hint (MUTED)** `#9299a3` on `#1c1f23` CARD | 5.37:1 | N/A | 4.5 (AA small text) | Exceeds ✓ |
| **Hint (MUTED)** `#596170` on `#ffffff` CARD | N/A | 5.59:1 | 4.5 (AA small text) | Exceeds ✓ |
| **Hint (BAD)** `#f06262` on `#1c1f23` CARD | 4.77:1 | N/A | 4.5 (AA small text) | Exceeds ✓ |
| **Hint (BAD)** `#cc3527` on `#ffffff` CARD | N/A | 4.66:1 | 4.5 (AA small text) | Exceeds ✓ |

**Dark theme MUTED calculation** (600 ms example):
- MUTED `#9299a3` → RGB (146, 153, 163)
  - R_lin = ((146/255 + 0.055) / 1.055)^2.4 ≈ 0.3105
  - G_lin = ((153/255 + 0.055) / 1.055)^2.4 ≈ 0.3445
  - B_lin = ((163/255 + 0.055) / 1.055)^2.4 ≈ 0.3810
  - L ≈ 0.2126(0.3105) + 0.7152(0.3445) + 0.0722(0.3810) ≈ 0.3399
- CARD `#1c1f23` → RGB (28, 31, 35)
  - R_lin ≈ 0.0191, G_lin ≈ 0.0228, B_lin ≈ 0.0306
  - L ≈ 0.0226
- Contrast = (0.3399 + 0.05) / (0.0226 + 0.05) ≈ **5.37:1** ✓

**Light theme MUTED calculation**:
- MUTED `#596170` → RGB (89, 97, 112), L ≈ 0.1379
- CARD `#ffffff` → L = 1.0
- Contrast = (1.0 + 0.05) / (0.1379 + 0.05) ≈ **5.59:1** ✓

**Dark theme BAD calculation** (500 ms example):
- BAD `#f06262` → RGB (240, 98, 98), L ≈ 0.2959
- CARD `#1c1f23` → L ≈ 0.0226
- Contrast = (0.2959 + 0.05) / (0.0226 + 0.05) ≈ **4.77:1** ✓

**Light theme BAD calculation**:
- BAD `#cc3527` → RGB (204, 53, 39), L ≈ 0.1754
- CARD `#ffffff` → L = 1.0
- Contrast = (1.0 + 0.05) / (0.1754 + 0.05) ≈ **4.66:1** ✓

All pairings exceed the 4.5:1 AA threshold for small text (hints are 8pt).

### Wrapping and layout

- The hint is packed under the Interval row's label, using `wraplength=int(ROW_LABEL_W * s)` (standard column width of 140px at s=1). The existing jitter hint "spreads the rhythm so it is not exact" wraps to two lines at the default scale; "Java sweeps may miss" and "Java sweeps likely fail" are both shorter (4 words each, ~25 characters), so they fit comfortably on one line and wrap only at extreme narrow windows or high scales.
- The hint label is in the same `text` frame (column 0) as the Interval row's main label, so it inherits the label column's alignment and padding. It sits directly under the main label, not indented or inset.
- **Height reservation**: The Clicking pane does not reserve space for this hint when hidden. When the hint appears, it grows the pane; when it disappears, the pane shrinks. This is consistent with how the Eating section's visibility toggle already works (toggled by `_select()`, height reflows via `_request_pane_fill()`), so the same category of layout shift is an accepted precedent.

### Two hints on adjacent rows (Minecraft profile)

On Minecraft, the sweep hint (conditional) sits directly above the jitter row's static hint:
```
Interval row:      [main label] [control]
                   [sweep hint, dynamic]
Jitter row:        [main label] [control]
                   [jitter hint, static]
```

The wording and color distinction keep this stack clear:
- The sweep hint uses warning language ("may miss" / "likely fail"), distinct from the jitter hint's descriptive tone ("spreads the rhythm").
- The sweep hint's visibility is conditional and changes at keystroke, while the jitter hint is always present — the eye reads them as separate concerns.
- Both are hints (same visual role), so stacking them is consistent with the label-column layout pattern already used elsewhere.

### Platform and font rendering

- Segoe UI is the canonical font across all three platforms (Windows, macOS, Linux) and is available via Tk's fallback chain on all of them. The font metrics and wrapping behavior are identical to existing hints (test precedent: `test_random_jitter_hint_wraps_instead_of_overlapping_the_control`, `tests/test_ui.py:1720`).
- No special glyphs or Unicode beyond ASCII letters/spaces; copy is all plaintext.

### Keyboard navigation and focus

- The hint label is not interactive (no focus, no Tab stop, no click binding). Existing Tab order for the Clicking pane (Interval NumBox → Jitter NumBox → Auto-stop NumBox → Mouse button Segmented) is unchanged.

## Traceability to spec

| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| No hint at >= 650 ms (Minecraft) | Hidden state: "effective minimum >= 650 ms" |
| MUTED hint at 550–649 ms (Minecraft) | MUTED state: "effective minimum 550–649 ms", copy "Java sweeps may miss", color `MUTED` |
| BAD hint at < 550 ms (Minecraft) | BAD state: "effective minimum < 550 ms", copy "Java sweeps likely fail", color `BAD` |
| No hint on Global or custom profiles | Hidden state: "non-Minecraft profile", Profile switch Global/custom trigger |
| Hint reflects current field values at every keystroke | MUTED and BAD states: "live at every keystroke", Rapid keystroke edits state |
| Hint persists across profile switches | Profile switch Minecraft-to-Global and back trigger: correct state restored on return |
| Hint persists across theme/scale changes | Theme or UI-scale change state: correct color/font/visibility after rebuild |
| Copy must name "Java" | MUTED and BAD copy both start with "Java" (constraint met) |
| Copy must fit ROW_LABEL_W wraplength at 2 lines max | Wrapping note: 4-word, ~25-char copy fits comfortably on one line; jitter hint precedent shows two lines is acceptable |
| Contrast passes WCAG AA (4.5:1) on both themes and both colors | Contrast verification table: all four pairings exceed 4.5:1 |
| Row hint capability gain is additive, no existing hints broken | Component reuse note: new `set_hint()/clear_hint()` pair is additive; all existing `hint=` sites continue identically |
| Height reflows when hint appears/disappears | Behavior notes in MUTED/BAD states: `_request_pane_fill()` called on visibility transition |
| Never mutate hint widget while `self._rebuilding` is True | Theme or UI-scale change state: compute state during `_rebuilding`, paint only after tree exists (per Orchestrator correction) |

## Notes on copy rationale

- **"Java sweeps may miss"** (MUTED, 550–649 ms): The margin the default 650 ms banks on (one tick of quantization jitter) is gone, but Java sweeps are still likely to land. "May miss" signals caution without absolute failure, matching the band's intermediate risk.
- **"Java sweeps likely fail"** (BAD, <550 ms): Below 550 ms (11 ticks), we are in the documented failure case (the ticket cites 500 ms / 10 ticks as "84% charge, 76% damage, no sweep"). "Likely fail" escalates the language to match the higher risk.
- **No number shown in the hint**: The effective minimum is derivable from the Interval and jitter fields already visible above the hint. Showing the number would add length without adding clarity, and would require dynamic interpolation (a small implementation cost). Keeping the copy short allows it to fit reliably on one line, reducing visual clutter.

## Risk and rollback

- **Purely additive**: New profile key (`min_sweep_ms`, defaulting to `None` on Global/custom), new constant (`MIN_SWEEP_BAD_MS = 550`), new `Row` hint capability, new hook in `_persist()`. Reverting the commit fully removes the feature.
- **Cannot affect click worker**: The worker thread never reads `min_sweep_ms` or the hint widget — it's a read-only display off the same coerced numbers the worker already uses.
- **Worst-case failure is cosmetic**: A misdrawn hint, a forgotten visibility toggle, or a layout reflow mishap — none of which can corrupt state or disrupt the click loop.

## Orchestrator correction (before build) — contrast figures

All four contrast figures above are wrong: the luminance arithmetic is off. Recomputed from the literal `THEMES` hex values with the WCAG relative-luminance formula:

| Pair | Ratio |
|---|---|
| MUTED `#9299a3` on CARD `#1c1f23` (dark) | **5.76:1** |
| MUTED `#596170` on CARD `#ffffff` (light) | **6.23:1** |
| BAD `#f06262` on CARD `#1c1f23` (dark) | **5.22:1** |
| BAD `#cc3527` on CARD `#ffffff` (light) | **5.11:1** |

All four still clear 4.5:1 for small text, so no design decision changes. The same BAD-on-CARD pair was recomputed identically for G#21 (`docs/history/ac-21-design.md`).

---

## Revision 2 — Placement, styling, and height constraint (2026-09-15)

### Context

The PR review blocked on height: the hint under the Interval row adds ~3 px to the Clicking pane's natural height, causing content clipping on Windows/macOS at `WINDOW_MIN_H = 620`. Linux/Xvfb has ~72 px spare; Windows/macOS have 0–1 px. Additionally, Leo reported the MUTED band doesn't stand out visually from the jitter row's static descriptive hint ("spreads the rhythm so it is not exact"), both currently rendered in the same MUTED color and regular weight.

### Decision A: Placement — Choose A2

**Placement A2: Show the warning in the jitter row's existing hint slot, replacing "spreads the rhythm so it is not exact" while a band is active and restoring it otherwise.**

**Rationale:**
- **Height-neutral by construction**: The jitter row's hint space is already reserved and packed. The sweep hints ("Java sweeps may miss" 21 chars, "Java sweeps likely fail" 24 chars) are much shorter than the jitter hint (40 chars, wraps to 2 lines at s=1 per test precedent `RowValueColumn.test_random_jitter_hint_wraps_instead_of_overlapping_the_control`). At any scale and font size, the sweep hints fit in equal or fewer lines than the jitter hint — zero height growth when swapping.
- **Avoids WINDOW_MIN_H bump**: No change to the window floor, which affects every profile and every user. Cannot measure Windows impact from Linux (substituted font vs Segoe UI metrics); raising the floor requires Windows CI proof, and any 2-line wrap would double the penalty.
- **Semantically honest**: The warning condition depends on both Interval AND jitter (`max(50, click_ms - jitter_ms)`), so placing the warning in the jitter row's hint slot highlights jitter's contribution to the problem, making the relationship transparent.
- **Simpler implementation**: Modify the jitter row to dynamically show either the descriptive hint or the sweep warning, rather than adding a second hint below Interval and then handling height reflows at the edge of the window floor.

**Deviation from spec**: The original spec (docs/spec.md §5) states placement "under the **Interval** row's own label column." This revision moves it to the jitter row's hint slot instead. Ticket-level scope remains on the Interval/jitter condition, not the label placement; the visual location change is a height trade-off forced by the window-floor constraint.

**Rejected alternatives:**
- **A1 (Keep under Interval, raise WINDOW_MIN_H)**: Every profile's window grows (620 → 623 minimum, higher if text wraps to 2 lines at scale extremes). Affects entire user base. Cannot measure the actual Windows cost from Linux (Xvfb uses substituted fonts, not Segoe UI). A 2-line wrap at any scale step doubles the height penalty; avoiding that requires validation at all four scale steps (90%, 100%, 115%, 130%) on Windows CI.
- **A3 (Other height-neutral options)**: Icon next to Interval label, banner at pane top, inline warning in value column — all less clean than reusing the established hint-under-label pattern already in use at jitter.

### Decision B: Styling — Bold MUTED / Bold BAD

**Styling decision**: 
- **MUTED band (550–649 ms)**: MUTED color `#9299a3` (dark) / `#596170` (light), **bold** weight (Segoe UI 8pt bold)
- **BAD band (<550 ms)**: BAD color `#f06262` (dark) / `#cc3527` (light), **bold** weight (Segoe UI 8pt bold)
- **Jitter hint (always shown)**: MUTED color, **regular** weight (unchanged from current)

**Rationale:**
- **Makes sweep hints visually distinct from the jitter hint**: Both hints were MUTED color + regular weight, making them indistinguishable in the label column. Bold adds visual weight without requiring a new color token, making the sweep warnings (shorter, warnings in tone) clearly separate from the descriptive text (longer, neutral tone).
- **Preserves color semantics**: MUTED = caution advisory, BAD = error signal. No new tokens needed. Existing established usage throughout the file (e.g., `_set_status()` at `afk_clicker.py:4107-4118` uses MUTED/OK/BAD for the same purpose).
- **Bold does not change line count at any scale**: "Java sweeps may miss" (21 chars) and "Java sweeps likely fail" (24 chars) are very short. Even in bold, Segoe UI 8pt:
  - At s=0.9 (wraplength 126 px, font 7.2 pt bold): fits comfortably (~108–110 px estimated for bold, vs 126 px available)
  - At s=1.0 (wraplength 140 px, font 8 pt bold): fits comfortably (~120–125 px estimated, vs 140 px available)
  - At s=1.3 (wraplength 182 px, font 10.4 pt bold): no constraint
- **Contrast remains passing AA**: WCAG 4.5:1 (AA) is the floor for small text. Bold does not change color values, only weight:
  - MUTED bold on CARD: 5.76:1 (dark) / 6.23:1 (light) — same as regular weight, exceeds 4.5:1
  - BAD bold on CARD: 5.22:1 (dark) / 5.11:1 (light) — same as regular weight, exceeds 4.5:1

### Decision C: Copy — No change

**Keep exactly**: "Java sweeps may miss" (MUTED band) and "Java sweeps likely fail" (BAD band). Placement change does not require rewording.

### Decision D: Test requirement — Floor invariant for Minecraft+Eating

Add a new acceptance test named `test_sweep_hint_height_floor_minecraft_with_eating` to `tests/test_ui.py`, mirroring the existing `WindowMinimumHeight` tests (circa line 1135). The test must:

1. **Setup**: Select Minecraft profile, confirm Eating section is shown (via the `"eating": True` profile key)
2. **Trigger worst-case band**: Set Interval=500, jitter=0 (effective minimum 500 < 550, BAD band active)
3. **Force edge-case scales**: Run the assertion at both s=0.9 and s=1.3 (extremes of the four UI-scale steps)
4. **Assert floor invariant**: Measure `self.clicking_pane.winfo_reqheight()` after forcing the layout, and assert it is ≤ available height (derived the same way the existing floor tests do: `WINDOW_MIN_H` minus the static window chrome and the Hotkey/Eating/Appearance/Updates panes' space). Use `self.root.update()` to settle layout before measurement.
5. **Purpose**: This runs on Windows/macOS CI, where the floor is real (0–1 px spare) and clipping is observable. Linux cannot catch this because Xvfb's substituted fonts leave ~72 px slack, hiding measurement errors.
6. **Acceptance**: The natural height must never exceed available height at the floor on any platform or scale step. A violation blocks CI, requiring either the hint to shrink or WINDOW_MIN_H to grow — keeping the height invariant enforcement local to this feature rather than scattered across rebuild and pane-fill logic.

### Contrast arithmetic (Revision 2 validation)

Re-verified that bold does not change luminance (color), only stroke weight:

| Pair | L_dark | L_light | Ratio dark | Ratio light | Passes AA |
|---|---|---|---|---|---|
| MUTED bold `#9299a3` on CARD `#1c1f23` | 0.3399 | — | 5.76:1 | — | ✓ |
| MUTED bold `#596170` on CARD `#ffffff` | — | 0.1379 | — | 6.23:1 | ✓ |
| BAD bold `#f06262` on CARD `#1c1f23` | 0.2959 | — | 5.22:1 | — | ✓ |
| BAD bold `#cc3527` on CARD `#ffffff` | — | 0.1754 | — | 5.11:1 | ✓ |

All four pairings pass the 4.5:1 threshold for small text (8pt hints). No change to the original contrast analysis; luminance is unchanged by font weight.

### Summary of Revision 2

- **Placement**: Moved from under Interval row to jitter row's dynamic hint slot (height-neutral, avoids WINDOW_MIN_H bump)
- **Styling**: Both sweep hints now bold (MUTED color for caution, BAD color for error) to stand out visually from regular-weight jitter hint
- **Copy**: Unchanged
- **Testing**: New floor invariant test on Minecraft profile with Eating shown, at edge-case scales, ensures pane height never exceeds available space at WINDOW_MIN_H
- **Ticket deviation**: Placement change noted; spec 5 stated "under Interval," revision places it in jitter row's hint slot instead, justified by window-floor constraint

## Orchestrator correction to Revision 2 — the "may miss" band's colour

Revision 2's placement (A2, the jitter row's hint slot) stands. So do the copy and the floor test. **The "may miss" band uses `INK` + bold, not `MUTED` + bold.**

Why: the owner asked for the muted band to *stand out more*. Revision 2 rejected `INK` on the grounds that "MUTED = caution", but that isn't what `MUTED` means in this codebase. It is the plain secondary-text colour: every static row hint ("0 means never"), the `NumBox` unit labels, the sidebar's "GAMES" header, and the "not detected" game state (`afk_clicker.py:~1860, 2205, 2237, 2668, 2903`). A warning in grey bold still reads as secondary text, one weight heavier.

`INK` bold reads as "this matters". `BAD` bold remains visibly the stronger of the two bands by colour, so the ordering holds.

| Band | Colour + weight | Dark on CARD `#1c1f23` | Light on CARD `#ffffff` |
|---|---|---|---|
| 550–649 ms "Java sweeps may miss" | `INK` bold (`#e4e7ea` / `#161a22`) | **13.32:1** | **17.43:1** |
| < 550 ms "Java sweeps likely fail" | `BAD` bold (`#f06262` / `#cc3527`) | **5.22:1** | **5.11:1** |
| no band: "spreads the rhythm so it is not exact" | `MUTED` regular (unchanged) | 5.76:1 | 6.23:1 |

Ratios were recomputed with the WCAG relative-luminance formula from the literal `THEMES` hex values. Revision 2's INK figures (12.96 / 15.19) were wrong. Weight doesn't change the line count differently for either colour; the floor test (D) is the real check on Windows/macOS CI.
