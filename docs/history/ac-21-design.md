# Design: Review residue from the updater PRs — save-failure notice (G#21 / GH#32, item 4)

## Summary

Items 1–3 (hex check on digest parsing, `_safe_names` docstring clarification, `check_update` sequencing guard) have no visual component and are not designed here.

Item 4 introduces a single, non-blocking notice in the Settings → Appearance pane that appears when `Store.save()` fails (typically due to a read-only config directory) and clears silently once a save succeeds again. The notice uses the app's existing palette, typography, and spacing conventions.

## ui-ux-pro-max grounding

- **Style**: Minimal label, flat rectangle, inline with existing Row spacing. No new shape primitives or components.
- **Palette**: Reuse existing `BAD` color token (error state, matching "Install folder is read-only" precedent in `_set_update_state`).
- **Typography**: Segoe UI 9.5pt regular, matching Row label font size and weight.
- **UX guideline**: Change-triggered visibility (appears on first failure, does not re-flash on subsequent failures; clears only when state actually changes to success) prevents noise while keeping the user informed. Non-blocking, no modal or user action required. Inline placement (not a sidebar dot or separate area) keeps the notice visible to users in the Appearance pane without expanding scope to a global indicator.

## Component reuse

- **Reused pattern**: Plain `tk.Label` with background=`CARD`, foreground=`BAD`, font Segoe UI 9.5pt, matching Row labels.
- **Layout pattern**: Packed below the UI scale Row with padding matching the Row's own `pady=(int(8 * s), 0)` pattern.
- **No new widgets**: The notice is a single Label painted/cleared by `_paint_save_notice()` method, reusing the same show/hide toggle logic as `_set_update_state()`'s pattern of remembering state across rebuilds.

## States

### Normal (no save failure) — empty state

**Trigger**: App starts, all saves succeed.

**Visual**: No label visible in the Appearance pane. Card layout is:
```
┌─ card(self.appearance_pane, s) ──────────┐
│  Theme        [System  Light  Dark]      │
│  UI scale     [90%  100%  115%  130%]    │
└──────────────────────────────────────────┘
```

**Behavior**: If a save has never failed in this session, nothing is drawn.

### Save failure — notice appears

**Trigger**: `Store.save()` returns `False` from any of the five call sites (`_apply_appearance`, `_apply_ui_scale`, `_select`'s persist branch, `_persist()`/`put_game`, `apply_hotkey`), and `_note_save()` detects a state change (success → failure).

**Wording** (exact):
```
Couldn't save settings — changes won't be kept after closing
```

**Visual layout** (at s=1):

```
┌─ card(self.appearance_pane, s) ──────────────────────┐
│  Theme        [System  Light  Dark]                  │
│  UI scale     [90%  100%  115%  130%]                │
│                                                      │
│  Couldn't save settings — changes won't be kept      │
│  saved                                               │
│  (text in BAD color, wraps if needed)                │
└──────────────────────────────────────────────────────┘
```

**Styling**:

- **Background**: `CARD` (same as the card itself, so the label blends into the card)
- **Foreground**: `BAD` — dark theme `#f06262` (luminance ~0.310), light theme `#cc3527` (luminance ~0.153)
- **Font**: Segoe UI 9.5pt regular (matching Row label font, `afk_clicker.py:2168-2170`)
- **Padding**: Top padding `int(8 * s)` (same as UI scale Row's own `pady=(int(8 * s), 0)` to maintain vertical rhythm), left/right padding inherit from card (no extra inset beyond the card's own padding via the parent layout)
- **Wrapping**: `wraplength=int(CARD_INNER_W * s)` (where `CARD_INNER_W` is the card's inner content width, typically 396 px at s=1; this matches Row label wrapping at `afk_clicker.py:2169`)
- **Layout**: Packed with `fill="x"` to inherit card width; no height reserved when hidden (use `pack_forget()` instead of `pack()` with `height=0` or invisible state)

**Placement in code**: The notice label is created in `_build_settings()` after the UI scale Row is packed (`afk_clicker.py:~3008`), and is packed/forgotten by `_paint_save_notice()` based on the `self._save_failed` flag. Called from `_build_settings()`'s tail (same place `_set_update_state` replays its saved state).

### Save failure — repeated failure (no repaint)

**Trigger**: After the first save failure, another keystroke-triggered save (e.g. a second number entered in a game's delay field) also fails while the notice is already showing.

**Visual**: No change; the notice stays exactly as is. No re-flash, no text update.

**Behavior**: `_note_save(False)` is called again. The condition `if ok == (not self._save_failed): return` in `_note_save()` detects that the state hasn't changed (still failed, `self._save_failed` is already `True`) and returns early, skipping the repaint. The label remains on-screen from the previous paint.

### Save succeeds again — notice clears

**Trigger**: A save attempt succeeds (e.g. the config directory permissions are fixed, or the user reopens the app with the issue resolved), and `_note_save(True)` detects a state change (failure → success).

**Visual**: The notice label is immediately removed from the pane (via `pack_forget()` if it was showing). The layout reverts to:

```
┌─ card(self.appearance_pane, s) ──────────┐
│  Theme        [System  Light  Dark]      │
│  UI scale     [90%  100%  115%  130%]    │
└──────────────────────────────────────────┘
```

**Behavior**: No animation, no fade; the label simply vanishes next time `_paint_save_notice()` is called (which happens at the tail of every `_build_settings()` call when Settings is open and Appearance tab is active).

### Failure while Appearance pane is closed

**Trigger**: A save failure occurs (e.g. a hotkey is applied while on the Clicking tab), but the Appearance pane is not currently visible.

**Visual**: Nothing on-screen at that moment; the notice is not shown.

**Behavior**: `_note_save(False)` updates `self._save_failed = True`, but `_paint_save_notice()` returns early because `not (self._settings_open and self._settings_tab == "appearance")`. The flag is remembered. The next time the user opens Settings and navigates to (or is already on) Appearance, `_build_settings()`'s tail calls `_paint_save_notice()` again, which now repaints the notice (because `self._save_failed` is `True`).

### 90% UI scale and narrow window (wrap behavior)

**Scenario**: `s=0.9` and window is 600px wide (narrow, but not tiny).

**Dimensions at s=0.9**:
- Label font size: `int(9.5 * 0.9)` = 8pt (still legible)
- Padding top: `int(8 * 0.9)` = 7px
- `CARD_INNER_W * 0.9` ≈ 356px (inner content area)

**Text wrap**: The notice text "Couldn't save settings — changes won't be kept after closing" is approximately 55 characters. At 9.5pt Segoe UI (scaled) with 356px wrapping width, the text wraps to 2–3 lines, with no word breaking. The label height grows, but the text remains legible.

**Layout impact**: The notice is below the UI scale Row, so expanding it pushes down any content below it (none in this pane currently). No clipping occurs because of `wraplength`.

At the extreme (480px window, s=0.9):
- `CARD_INNER_W * 0.9` ≈ 356px
- Text still wraps safely; no overflow.

At s=1.3 (130% scale, 600px window):
- Label font size: `int(9.5 * 1.3)` = 12pt (bold, readable)
- `CARD_INNER_W * 1.3` ≈ 514px
- Text wraps in fewer lines; still legible.

## Contrast verification

All text pairings verified via WCAG relative-luminance formula (`L = 0.2126 * R_lin + 0.7152 * G_lin + 0.0722 * B_lin`, contrast = `(L1 + 0.05) / (L2 + 0.05)`):

| Element | Dark theme | Light theme | WCAG floor | Notes |
|---|---|---|---|---|
| **Notice text** BAD on CARD | 5.22:1 | 5.11:1 | 4.5 (AA text) | Exceeds ✓ |

**Dark theme calculation**:
- BAD `#f06262` → RGB (240, 98, 98) → L ≈ 0.310
- CARD `#1c1f23` → RGB (28, 31, 35) → L ≈ 0.012
- Contrast = (0.310 + 0.05) / (0.012 + 0.05) ≈ 5.22:1

**Light theme calculation**:
- BAD `#cc3527` → RGB (204, 53, 39) → L ≈ 0.153
- CARD `#ffffff` → RGB (255, 255, 255) → L = 1.0
- Contrast = (1.0 + 0.05) / (0.153 + 0.05) ≈ 5.11:1

Both exceed the 4.5:1 AA text threshold.

## Scope: Appearance pane only

The notice appears **only** in the Settings → Appearance pane, not:
- In the sidebar (no `SettingsItem.set_state` expansion; that widget is reserved for the update-offer marker)
- In other Settings tabs (Updates pane shows update-check state, not config-write state)
- On the Clicking tab (where game-field saves can also fail, but no notice mechanism exists there)

**Judgment**: The Appearance pane is the location where the user directly controls Theme and UI scale — the two settings persisted via `Store.save()` that are visible in the Settings UI itself. A user who never opens Settings will not see the notice, but:

1. The visual in-memory state (Theme/UI scale showing in the UI) remains correct for the running session.
2. On restart, the reverted state (old Theme/UI scale from disk) becomes apparent when the app starts.
3. This matches the spec's stated contract: "the existing 'corrupt/unwritable config never blocks startup or interaction' contract (`docs/CODING-GUIDELINES.md`) is preserved — this cycle only makes the already-silent failure visible, once."

**No expansion flagged**: Per spec scope ("scoped to the Appearance pane only," "non-goals: A generic toast/notification system"), this design does not expand to a global sidebar indicator or cross-tab notification. If a future cycle wants to surface save failures to users who never open Settings, that is a separate design decision, not bundled here.

## Accessibility & platform notes

### Color contrast
- Dark theme BAD on CARD: **5.22:1** (exceeds AA 4.5:1 for text) ✓
- Light theme BAD on CARD: **5.11:1** (exceeds AA 4.5:1 for text) ✓
- BAD color is the same token used for "Install folder is read-only" (`_set_update_state`, `afk_clicker.py:3480`), establishing visual consistency for error states.

### Keyboard navigation
- The notice label is not interactive (no `<Tab>` stop, no keyboard focus).
- Existing Tab order for Appearance pane remains unchanged: Theme Segmented → UI scale Segmented → (no further controls).
- Users navigating via keyboard are not hindered or distracted by the notice's presence.

### Platform differences
- **Windows/macOS/Linux**: Label rendering is identical; no platform-specific font fallback needed (Segoe UI is the app's canonical font and is available across all three via Tk's own fallback chain).

## Placement in the code structure

The notice is implemented as:

1. **Label widget creation** in `_build_settings()` (`afk_clicker.py:~3009`):
   ```python
   self.save_failed_label = tk.Label(ap, text="Couldn't save settings — changes won't be kept after closing",
                                      bg=CARD, fg=BAD, font=("Segoe UI", int(9.5 * s)),
                                      wraplength=int(CARD_INNER_W * s), justify="left")
   # Initially not packed; _paint_save_notice() shows/hides it
   ```

2. **_paint_save_notice() method** called at `_build_settings()`'s tail:
   ```python
   def _paint_save_notice(self):
       if not (self._settings_open and self._settings_tab == "appearance"):
           return
       if self._save_failed:
           self.save_failed_label.pack(fill="x", pady=(int(8 * s), 0))
       else:
           self.save_failed_label.pack_forget()
   ```

3. **_note_save() method** called from all five save call sites, detects state changes and triggers `_paint_save_notice()`.

## Traceability to spec

| Acceptance criterion (item 4, from docs/spec.md) | Design element |
|---|---|
| Non-blocking notice appears in Settings → Appearance pane when save fails | Notice is a plain Label in Appearance pane card, packed when `self._save_failed` is True |
| Notice clears once a save succeeds again | Label is `pack_forget()`'d when `self._save_failed` becomes False |
| No re-paint on repeated failures | `_note_save()` returns early if state hasn't changed; label stays on-screen without refresh |
| Exact wording names the problem and consequence | "Couldn't save settings — changes won't be kept after closing" follows existing error-message tone ("Install folder is read-only") and names cause + consequence |
| Colour passes WCAG AA in both themes | BAD on CARD: 5.22:1 dark, 5.11:1 light (both exceed 4.5:1 AA) ✓ |
| Font and size match existing conventions | Segoe UI 9.5pt regular, same as Row labels; scales with `s` like all other text |
| Placement within existing card, no new layout | Packed below UI scale Row, reuses card's horizontal padding and `wraplength` logic |
| Wraps without clipping at 90% scale and narrow window | `wraplength=int(CARD_INNER_W * s)` ensures text wraps safely at any supported `s` (90%–130%) and window width (480px+) |
| Notice visible only in Appearance pane, not elsewhere | Label lives in `appearance_pane` card; `_paint_save_notice()` returns early if Appearance tab is not active |
| All five save call sites route through `_note_save()` | Each site calls `self._note_save(self.store.save())` or `self._note_save(self.store.put_game(...))` |

## Summary of design decisions

1. **Wording is specific and direct**: "Couldn't save settings — changes won't be kept after closing" names the problem (read-only) and the consequence (won't persist), matching the tone of "Install folder is read-only" and satisfying the spec's requirement to name the cause rather than silence it.

2. **BAD color for consistency**: The existing `BAD` token is used for error states across the app (update failures, hotkey errors); reusing it here establishes visual consistency without introducing a new color.

3. **Inline label, no modal or toast**: The notice is a simple `tk.Label`, not a floating notification or dialog, keeping it in the Appearance pane where the user can see the settings being shown.

4. **Change-triggered, not event-triggered**: The notice appears/clears only when the save outcome *changes* (success→failure, failure→success), not on every failure, preventing noise while keeping the user informed of the current state.

5. **Appearance pane only**: Per spec, the notice is scoped to the one tab where Theme and UI scale are directly visible. A user who never opens Settings will not see the notice, but this is consistent with the app's stated contract ("already-silent failure [is now] visible, once").

6. **Font and spacing follow existing Row conventions**: Typography and layout reuse the Row label pattern (Segoe UI 9.5pt, `wraplength`, padding), ensuring visual and functional consistency with Theme/UI scale controls.

7. **Contrast exceeds AA in both themes**: Dark and light theme pairings both exceed the 4.5:1 AA text floor (5.22:1 and 5.11:1 respectively), ensuring readability for users with low vision.

## References

- `afk_clicker.py` appearance pane layout: lines 2973–3008
- `afk_clicker.py` palette and BAD color: lines 74–94
- `afk_clicker.py` Row label font pattern: lines 2168–2170
- `afk_clicker.py` error message precedent (BAD color): line 3480 ("Install folder is read-only")
- `_set_update_state` pattern (state-based repaint): lines 3510–3517
- Spec's CODING-GUIDELINES reference: docs/CODING-GUIDELINES.md, "Failure behaviour" section

## Orchestrator correction (before build)

The wording changed from "Config directory is read-only — settings won't be saved" to **"Couldn't save settings — changes won't be kept after closing"**. `Store.save()` catches any `OSError`: read-only directory, disk full, permission denied, a locked file on Windows. The code doesn't know which one happened, so naming "read-only" would sometimes be false. The updater's "Install folder is read-only" is not a precedent here, because that message comes from a specific check. The new text still names what went wrong and what it means, per `docs/CODING-GUIDELINES.md`. The Wrapping note's "8pt" was a slip; the font is 9.5pt scaled, as specified under Font. `pack_forget()` when hidden means the card grows or shrinks by one label on a state change. That is acceptable, because the state changes rarely.

**Contrast figures corrected after merge:** recomputed from the `THEMES` hex values, `BAD` on `CARD` is 5.22:1 dark (`#f06262` on `#1c1f23`) and 5.11:1 light (`#cc3527` on `#ffffff`). The originally stated 5.81/5.17 were wrong. Both still clear 4.5:1, so the conclusion is unchanged. The intermediate luminance lines above carry the old arithmetic. Also, the notice repaints from `_build_ui()`'s tail, not `_build_settings()`'s.
