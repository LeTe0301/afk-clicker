# Design: Duplicate a macro (G#64 / GH#113)

## Summary
A text-only "Duplicate" button joins the macro row's existing Run/Edit/Delete group, and the row becomes two lines so that the new button and the `" (copy)"` suffix both fit. The decisive finding: the current single-line row has almost no free width for a name (about 50 logical px at default scale with an interval set), so adding one 80 px button on that line pushes the name column to zero and hides the "(copy)" suffix that identifies the duplicate. The fix is a two-line row plus a suffix-preserving display truncation: the row layout lives in `_refresh_macros_pane`, and the truncation is one small helper beside `_truncated_dialog_name`.

## ui-ux-pro-max choices
Note: the `ui-ux-pro-max` skill was read (`/home/dev/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/SKILL.md`) but its `search.py` engine was not executed, because this session has no shell. The choices below apply the skill's priority list (accessibility/contrast, touch and interaction, typography and color, feedback) to the existing Tk theme. Nothing new is introduced.

- Style: existing dark glass-card look (`card()`, `CARD` surface). No new style.
- Palette: existing `THEMES["dark"]` tokens only. No new color. No raw hex in the row code.
- Typography: existing `("Segoe UI", fs(9.5, s), "bold")` on the button (from `Button`), `("Segoe UI", fs(9.5, s))` for the name, `("Consolas", fs(9, s))` for the hotkey, `("Segoe UI", fs(9, s))` for the interval.
- Relevant UX guidelines applied:
  - Text labels, no icon-only controls (skill priority 1: icon-only buttons without labels are an anti-pattern). Siblings are text-only, so the new button is too.
  - No emoji and no glyph icons (skill priority 4).
  - Duplicate is neutral (not `primary`, not `danger`): it is additive and reversible, so it must not look like the accent action or the destructive one.
  - Feedback: the row list reflects the change immediately (Run/Edit/Delete rows already rebuild this way on save). No flash or toast, because the app has no existing transient-success pattern; `_note_save` only reports write failures, and the status pill reports run state.
  - Hover feedback comes from the existing `Button` hover (`CARD_HI`). The Tk desktop app has no touch target minimum applied here beyond the existing 34 px button height.

## Component reuse
- Reused: `Button` (existing, `afk_clicker.py` line 2157) for the new "Duplicate" control, same constructor and pack pattern as Run/Edit (`width=80` instead of 60/70; see Placement).
- Reused: `card()`, `tk.Frame` row, `tk.Label` name/hotkey/interval labels, `Hotkey.from_json(...).label()`, `fs()`, theme tokens `CARD`, `INK`, `MUTED`.
- Reused: `_duplicate_macro(macro)` calls `_save_macro(self.current, None, ...)` exactly as the spec's proposed approach shows. `_save_macro` already refreshes the pane and rearms hotkeys and intervals.
- New (one small pure helper, because no existing one fits):
  - `_truncated_row_name(name, limit=40)`, placed directly under `_truncated_dialog_name` (line 2148). Returns `name` when `len(name) <= 40`, else `name[:31] + "…" + name[-8:]` (exactly 40 characters). It is display-only and never touches the stored name. Why not reuse `_truncated_dialog_name`: it keeps the head and drops the tail, which deletes the `(copy)` suffix; that is the exact failure this design prevents. The middle ellipsis keeps the last 8 characters, which covers ` (copy)`.

## Placement and layout

### Why the single-line row cannot take the button
Measured against the code, not guessed. Logical px at `s = 1.0`:
- Usable row width: `CARD_INNER_W = CONTENT_W - 2*CONTENT_PAD - 2*CARD_PAD = 452 - 2*16 - 2*12 = 396` (constants at around lines 223, 250 and 251).
- Today's controls: Run 60 + 6, Edit 60 + 6, Delete 70 = 202.
- Adding Duplicate 80 + 6 = 288.
- Hotkey plus interval labels, typical: "F9"-class hotkey about 40 + 12 pad, "every 500 ms" about 80 + 12 pad. That is about 144, so 288 + 144 = 432, which is already above 396 before any name is drawn.
- Pack order is controls first, name last, so the name label is the one starved. At typical settings it gets zero width, and "(copy)" disappears.
- Estimates use about 6 to 6.5 px per character for Segoe UI at 9 to 9.5 pt. The developer must verify with `tkinter.font.Font(family="Segoe UI", size=fs(9.5, s), weight="bold").measure("Duplicate")` and the Consolas hotkey label width before finalizing. The conclusion holds even at the low end of these estimates.

### Proposed two-line row (per macro)
```
+--------------------------------------------------------------+
| Long macro name that goes on an…n (copy)          F9         |   line 1
| every 500 ms            [Run][Duplicate][Edit][Delete]       |   line 2
+--------------------------------------------------------------+
   (8*s px between this row and the next macro's row, as today)
```
- Line 1 (`row_top`, `tk.Frame` inside the row): name label `side="left", fill="x", expand=True, anchor="w"`, text = `_truncated_row_name(macro["name"])`; hotkey label `side="right"`, text as today (`hotkey.label()` or "No hotkey" in MUTED), `padx=(0, 0)`.
- Line 2 (`row_bottom`): interval label `side="left"` only when `macro.get("interval_ms")` (MUTED, `every N ms`, same text as today). Buttons `side="right"`, packed in this order (same as today, plus the new one between Edit and Run):
  1. Delete, `width=70`, no padx (rightmost, unchanged).
  2. Edit, `width=60`, `padx=(0, int(6 * s))`, unchanged.
  3. Duplicate, `width=80`, `padx=(0, int(6 * s))`, new.
  4. Run, `width=60`, `padx=(0, int(6 * s))`, unchanged.
- Visual left-to-right in line 2: `[Run] [Duplicate] [Edit] [Delete]`. The spec's code order (Edit, then Duplicate, then Run) produces this, and Delete stays at the far right edge, away from the common actions.
- Line gap: `pady=(int(6 * s), 0)` on `row_bottom`.
- Width budget (logical px): line 2 = 60 + 6 + 80 + 6 + 60 + 6 + 70 = 288, plus interval up to about 90 (for example "every 60000 ms") = 378, which fits 396. Line 1 = name up to 40 chars at about 6.5 px = about 260, plus hotkey up to about 112 = 372, which fits 396.
- Which existing controls move: all three existing buttons drop from the single line to line 2. Delete and Edit keep their x-positions against the right edge. Run shifts left by 86*s to make room for Duplicate. The name moves to line 1 and the interval to line 2; the hotkey label stays on the right, now on line 1. Nothing is removed.
- Row height: today one line of about 34*s. New: about 18*s (line 1) + 6*s gap + 34*s (line 2), about 58*s, so each macro row grows about 24*s. That is the one visible cost of this design.

### Why not the alternatives
- Smaller Duplicate button (for example width 72 or label "Copy"): width 72 is still about 28 px over budget at default scale on a single line (280 + 144 = 424 vs 396), and "Copy" is ambiguous next to the clipboard meaning of copy. Rejected.
- Icon-only button: the skill's accessibility rule says no. Also there is no tooltip infrastructure to name it. Rejected.
- Single line with ellipsis and no layout change: the "(copy)" suffix is still hidden in the common case. Rejected, since the acceptance criterion is that the duplicate is recognizable as "X (copy)" in the list.

## Label truncation
- Rule: display-only. The stored `macro["name"]` is never changed. The Edit dialog shows the full name.
- Threshold: 40 characters. Chosen to fit line 1 at its worst case (see width budget). Same convention as the file's `_truncated_dialog_name(limit=40)`.
- Shape: head 31 characters, `…`, tail 8 characters. Every duplicate's name ends in ` (copy)` (7 characters), so the 8-character tail always shows it in full, whatever the length of the original name. The head keeps enough of the original to tell macros apart.
- Names of 40 characters or fewer are unchanged, so the common case is untouched.
- This helper also applies to every row, not only duplicates. That is intentional: today's long names are clipped silently by Tk, and the same fix stops the duplicate suffix from being cut. It is a display change to existing rows, flagged here so the developer does not treat it as scope creep.

## Feedback on duplicate
- No flash, no highlight, no status text. The new row appears at the bottom of the list, because `_save_macro` appends (`macros.append(validated)`, line 5940) and the list is in insertion order. This is the same way a macro created in the editor appears today.
- The row is the feedback. The "(copy)" suffix is the visual proof that the click worked, which is why the truncation rule above matters.
- Known gap (pre-existing, not changed): the list does not auto-scroll to the new row. If the pane is already full, the new row may be below the visible area. Creating a macro in the editor has the same behavior today. The pane-fill machinery (`_request_pane_fill`) measures natural height; the developer should confirm whether the window grows or the list clips, and report it.

## States

### Empty (no macros for this game)
Unchanged: "No macros yet for this game." label (MUTED). The Duplicate button does not exist here, since there is no row. The "+ New macro" button below the list is unchanged.

### Loading
No loading state. Macros are read from `self.store` synchronously in `_refresh_macros_pane`, same as today.

### Populated
```
+-- macro card -----------------------------------------------------+
| Farm north wood (copy)                                   F9      |
| every 500 ms                  [Run][Duplicate][Edit][Delete]     |
|                                                                  |
| Quick click                                          No hotkey   |
|                               [Run][Duplicate][Edit][Delete]     |
|                                                                  |
|                                    [ + New macro ]               |
+------------------------------------------------------------------+
```
- A macro with no interval has an empty left side on line 2 (buttons only).
- A macro with no hotkey shows "No hotkey" in MUTED on line 1, as today.

### Error
- Save failure: `_save_macro` returns False if `_validate_macro` rejects the blob. A valid macro cannot become invalid through duplication (the steps are re-validated and rebuilt, per the spec). If it does return False, the click does nothing visible. Do not add a dialog for this; it cannot happen for macros that exist. Report it in implementation.md if the developer ever sees it.
- Persistence failure: `_save_macro` calls `self._note_save(self.store.save())`, which surfaces the existing read-only-config notice. No new error UI.

### Interactive / hover / pressed states
- Duplicate idle: `CARD` fill, `LINE` outline, `INK` text (existing `Button` default).
- Duplicate hover: `CARD_HI` fill, same outline, `INK` text (existing `Button` hover).
- Duplicate click: runs `_duplicate_macro(m)` immediately, no confirm dialog (spec decision).
- No press-down visual: the existing `Button` has none; not added.

## Accessibility & platform notes
- Touch target sizes: this is a Tk desktop app, not a touch UI. The new button is `80*s` by `34*s` logical px, the same height as its siblings. Its hit area is larger than Run/Edit/Delete at the same height. Where a touch target minimum applies, the existing 34 px height is inherited, not changed.
- Color contrast (computed from the literal theme hex values, WCAG 2.x relative luminance, sRGB linearization with the 0.03928 threshold):
  - `INK` #e4e7ea on `CARD` #1c1f23: L = 0.7959 vs 0.0135; ratio (0.7959 + 0.05) / (0.0135 + 0.05) = **13.3:1**. Passes AA (4.5:1) for the Duplicate label and the hotkey label. Passes AAA too.
  - `INK` #e4e7ea on `CARD_HI` #262a30 (hover): L = 0.0228; ratio 0.8459 / 0.0728 = **11.6:1**. Passes AA.
  - `MUTED` #9299a3 on `CARD` #1c1f23 (used for "No hotkey" and "every N ms", same as today): L = 0.3155; ratio 0.3655 / 0.0635 = **5.8:1**. Passes AA (4.5:1). Unchanged by this design, since these labels are not new pairings.
  - `LINE` #3a4048 on `CARD` #1c1f23 (button outline, non-text, needs 3:1 under WCAG 1.4.11): L = 0.0503; ratio 0.1003 / 0.0635 = **1.6:1**. **Fails 3:1.** This is pre-existing: every `Button` in the app uses this outline, and this design reuses it without change. Fixing it means changing the global `LINE` token or the `Button` outline, which affects every button and is out of scope for G#64. Flagged for a separate ticket. The Duplicate button is identifiable by its label, which is `INK` at 13.3:1.
  - No new color pairings were introduced, so no new computations are needed for the new button.
- Keyboard: `Button` is a `tk.Canvas` with mouse bindings only (`<Button-1>`, `<Enter>`, `<Leave>`). It is not focusable. This is pre-existing for Run/Edit/Delete, and Duplicate inherits it. Flagged for a separate ticket, not changed here.
- Web vs. native differences: none. The app is Tk-only (Windows target). Hover (`CARD_HI`) is the existing desktop hover and works as-is.
- Scale: all dimensions use `s` and `fs()`, so the layout scales with `ui_scale` (90, 100, 115, 130, auto). The width budget above is at `s = 1.0`; the ratio holds at other scales because every term scales.

## Design-is pass (Dieter Rams)
Run against the draft, and the outcomes are folded into the layout above:
- Innovative / minimal: no icon, no new color, no flash, no dialog. The only new element is one button and one helper.
- Useful: the duplicate must be recognizable, so the two-line row and the suffix-preserving truncation are required. The first draft (one line, plain truncation) failed this check and was replaced.
- Honest: the layout cost (row height +24*s) is stated, and the pre-existing contrast and keyboard gaps are named, not hidden.
- Thorough to the last detail: spacing matches the existing 6*s button gaps and 12*s label gaps, and Delete keeps its right-edge position.
- Unobtrusive: text-only, neutral style, no emphasis on the new action.

## Traceability to spec
| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| Duplicate creates "{name} (copy)" with same hotkey label, "every N ms" label, and steps | Placement section (button wiring via `_duplicate_macro`); Label truncation keeps " (copy)" visible in the list; Populated wireframe |
| No hotkey and no interval: duplicate shows "No hotkey" and no interval label | Populated wireframe (no-hotkey row, empty left side on line 2); line 1 hotkey label rule |
| Hotkey chord triggers both original and duplicate | Out of visual scope (no UI change); `_save_macro` rearms hotkeys (Placement) |
| Interval duplicate timer fires independently | Out of visual scope; `_save_macro` calls `_arm_macro_intervals` (Placement) |
| Duplicating does not alter or remove the original | Label truncation is display-only (never writes `macro["name"]`); Placement section appends, no removal |
| New macro persists across a game switch | `_save_macro` persists via `self.store.save()` (Error section) |
| Spec Non-goals: no dialog, no collision check, no counter | Interactive states (no confirm), Feedback section (no flash, no counter) |
| Spec Affected areas: one method and one button | Component reuse. Also one small display helper and a two-line row, which the spec did not anticipate; stated above as a deliberate deviation |

## Deviations from the spec's premise (for product-manager awareness)
The spec says "one new button ... no layout change." That premise does not hold at default width (see "Why the single-line row cannot take the button"). This design adds two things the spec did not list:
1. The macro row becomes two lines (every row about 24*s taller).
2. A display-only name truncation helper (`_truncated_row_name`), applied to all rows.
Both are required for the duplicate's "(copy)" suffix to be visible. If Leo prefers to keep one line, the alternative is to accept that the suffix is hidden for typical names, which breaks the spec's own recognizability intent. Developer should implement the two-line row unless product-manager says otherwise.
