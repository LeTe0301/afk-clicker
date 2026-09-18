# Design: macOS font-size floor (`fs(base, s)`)

## Summary
This hotfix introduces a module-level helper function `fs(base, s)` that computes font point sizes with a floor of 6pt, eliminating illegibly small 5pt labels on macOS at 90% UI scale. No new UI surface, components, colors, or layouts—purely a legibility fix applied through ~20-30 call-site substitutions. The floor value (6pt) is chosen to match the already-shipping macOS 100% baseline, preserving all existing visuals while fixing only the newly-broken case.

## ui-ux-pro-max choices
- **Style**: No change — all existing widget styles, glassmorphism, and spacing remain unchanged.
- **Palette**: No change — no new color usage.
- **Typography**: The only change is a legibility floor: font sizes can no longer fall below 6pt, matching the already-accepted minimum on macOS 100% scale. This is a constraint, not a choice—6pt is the current shipped floor, this hotfix just extends it to all scale steps uniformly.
- **Relevant UX guidelines applied**: 
  - **Minimum readable font size**: 6pt (Tkinter on macOS, 72-dpi convention) has already shipped successfully as the macOS 100% baseline and remains legible. Clamping at this same floor ensures consistency and prevents regression to sub-legible 5pt on the 90% step.
  - **Consistency across platforms and scale steps**: Applying the same floor uniformly across all ~20-30 font-size call sites prevents accidental drift—some sites getting floored while others don't—which would create visual inconsistency. Windows/Linux platforms (DPI ~1.0) are unaffected since no font falls below 6pt there at any scale step; the floor is a no-op on non-macOS platforms.
  - **No compound regressions**: The spec's "compound scale lesson" (macOS's 0.75 DPI multiplied by 90% UI scale = 0.675 effective scale) was already identified in `backlog.md` as a risk; this hotfix neutralizes it by design.

## Component reuse
- **Reused**: All existing widget components (`Button`, `Segmented`, `ToggleCheckbox`, `TabBar`, `StatusPill`, etc. in `afk_clicker.py`) — no changes to their class definitions. Each widget already multiplies font sizes by `self.s`; they continue doing exactly that, and the new `fs()` helper is applied at the call sites that pass the computed size to them.
- **New (if any)**: No new component. The `fs()` function is a pure module-level helper, not a component or class — it encapsulates the legibility floor logic once so it can be reused across all font-size expressions uniformly.

## States
This hotfix has no UI state changes—all interactive, loading, populated, error, and expanded states in the existing UI remain visually identical except for the font-size floor.

**Before this change**:
- macOS at 90% UI scale (worst case): some labels render at 5pt (illegible).
- macOS at 100% scale: labels render at 6pt (legible, already shipped).
- All other platforms/scales: unchanged (already above 6pt floor).

**After this change**:
- macOS at 90% UI scale: the seven affected labels (bases 8 and 8.5) now render at 6pt instead of 5pt, matching the legibility of macOS 100% scale.
- macOS at 100% scale: unchanged (already at 6pt, floor is a no-op).
- All other platforms/scales: unchanged (already above 6pt floor).

No visual reflow, no layout changes, no new empty/loading/error states. The fix is purely within-label typography, invisible to the user except that previously illegible text is now readable.

## Accessibility & platform notes
- **Touch target sizes**: Unchanged — all widget sizes, padding, and hit areas are computed from `int(base * s)` expressions that do not involve `fs()`. This hotfix affects font point sizes only, not widget dimensions.
- **Color contrast**: Unchanged — no color changes, no new text/background pairings. Legibility improves because text is no longer rendered at 5pt; contrast ratios remain the same (already-computed for all existing pairings).
- **Font legibility (typography accessibility)**:
  - **The floor value (6pt) is justified by precedent, not arbitrary**: This app already ships successfully with 6pt as the minimum on macOS 100% scale. Extending that same floor to the 90% scale step is a consistency fix, not an opinion about legibility in a vacuum.
  - **Worst-case scale (0.675 on macOS 90%)**: A base of 8pt × 0.675 scale = 5.4pt → `int()` truncates to 5pt (illegible). `fs()` clamps to 6pt (legible and consistent with 100% scale). A base of 9pt × 0.675 scale = 6.075pt → `int()` already gives 6pt; `fs()` is a no-op.
  - **Non-macOS platforms (DPI ~1.0)**: A base of 8pt × 0.9 scale (90%) = 7.2pt → `int()` gives 7pt (well above floor); `fs()` is a no-op. No legibility regression on Windows/Linux.
  - **macOS at 115%/130% scales**: Base 8pt × 0.75 DPI × 1.15 scale = 6.9pt → 6pt after `int()`, already at floor; `fs()` no-op. Base 8pt × 0.75 DPI × 1.30 scale = 7.8pt → 7pt after `int()`, above floor; `fs()` no-op. The floor does not over-fire at these less-extreme scales.
- **Web vs. native differences**: This is a Tkinter desktop app (macOS/Windows/Linux), no web version. The fix applies uniformly to all native platforms, with macOS being the only one affected (the one with the low 0.75 DPI factor).

## Traceability to spec

| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| **`fs(8, 0.75) == 6` (mac 100%, already-shipping, unchanged)** | No visible change to macOS 100% scale baseline; the floor is a no-op since `int(8 * 0.75) = 6` already. Preserves existing visual appearance. |
| **`fs(8, 0.675) == 6` (mac 90%, the reported 5pt case, now fixed)** | Seven bases (8, 8.5) that were rendering at 5pt (illegible) on macOS 90% scale now render at 6pt (legible). Users on macOS with 90% UI scale will see legible labels instead of sub-pixel text. Examples: `ToggleCheckbox` checkmark (line 1726), sidebar hints (line 2213/2223), secondary labels (lines 1830, 2692, 2931, 3141). |
| **`fs(9.5, 0.675) == 6` (unaffected bases are no-ops)** | Bases 9 or higher already truncate to ≥6pt at worst-case scale (0.675), so `fs()` is a no-op at these call sites. They're still converted for consistency and G#38 reuse, but render identically to before. No visual change expected. |
| **`fs(8, 1.0) == 8` and `fs(8, 0.9) == 7` (Windows/Linux unchanged)** | Non-macOS platforms with DPI ~1.0 have no bases that fall below 6pt at any scale step (100%, 90%, 115%, 130%). The floor is a no-op on Windows/Linux; all fonts render at their existing sizes. No visual change for non-macOS users. |
| **Every font-size `int(<literal> * s)` expression replaced with `fs(<literal>, s)`** | The spec provides a complete table (lines 65–91) with 20–30 call sites across the UI. The blanket replacement ensures uniform legibility guarantees across all labels, not just the seven that were broken. Prevents future regressions if a new label is added with a small base. |
| **`TabBar`'s label font and width-measurer read the same `fs()` value** | Line 1770–1791: the font size is computed once as a local variable and fed to both the canvas text item and the `tkfont.Font` measurer, preventing desync. This is a code pattern, not a visual change, but critical for correct tab layout. |
| **No visual change to already-shipped appearance (mac 100%, all non-mac scales)** | By design—the floor value (6pt) is the current already-shipped minimum. Only the newly-broken mac 90% case is fixed up to parity. No user-visible change except that previously illegible text is now readable. |

## Notes for implementation
1. **Pure function, no platform detection**: `fs(base, s) = max(6, int(base * s))` has no conditional logic, no reference to DPI or scale factors, and no module-state dependencies. This keeps it simple, testable, and reusable for G#38's continuous scaling without modification.
2. **No changes to widget classes**: All of `Button`, `Segmented`, `ToggleCheckbox`, `TabBar`, etc. remain unchanged. They already take `s` as a parameter and multiply font sizes by it; the floor is applied at the call site where the final size is computed, not inside the widget class.
3. **Careful not to floor non-font sizes**: Padding, widget widths/heights, `wraplength`, and other non-font `int(x * s)` expressions remain as-is. The `fs()` helper is for font sizes only. The spec's table and grep patterns verify this distinction.
4. **Test pattern precedent**: The spec reuses the existing `_dpi_s`/`_apply_ui_scale` simulation pattern from `tests/test_ui.py:1148–1168` (`WindowMinimumHeight`) and `tests/test_ui.py:1222–1226` (`MinecraftSweepHint`), so test setup is consistent with prior art in the codebase.
