# Design: Number fields drop focus on blur/click, and window is resizable

## Summary
NumBox entries drop their focus highlight (wrap: LINE) and release keyboard focus when the user clicks elsewhere, presses Enter, presses Escape, or the clicker starts via hotkey. The window becomes resizable with a sensible minimum floor (the current default size); extra width stretches the content pane unbounded while keeping the sidebar and controls pinned; extra height creates blank space below cards and breathing room in the sidebar's games list.

## Palette & visual choices
No new colors introduced. Existing tokens continue to apply:
- **Focused state**: NumBox wrap is ACCENT (#ffc542) on `<FocusIn>`, matching today's behavior.
- **Unfocused state**: NumBox wrap is LINE (#262a35) on `<FocusOut>` or when clicked away, matching today's behavior.
- **Validation/clamping**: No visual feedback added for out-of-range values during edit or on blur. Clamping happens at read time (`_num()` called by `_persist()` on every keystroke and by `_sync_settings()` every 200 ms), not at blur; the field text remains as typed. This is consistent with the app's existing validation model ("at the point of use, not at entry").

## Component and binding updates

### NumBox bindings (new)
Each NumBox entry gains two new key bindings alongside its existing `<FocusIn>`/`<FocusOut>`:
```python
entry.bind("<Return>", lambda e: e.widget.winfo_toplevel().focus_set())
entry.bind("<Escape>", lambda e: e.widget.winfo_toplevel().focus_set())
```
Both blur by setting focus to the toplevel (root), which fires `<FocusOut>` on the entry. `winfo_toplevel()` is used instead of passing a root reference to keep NumBox self-contained.

### Application-wide blur on non-Entry click (new)
One `bind_all("<Button-1>", ...)` handler at app init, after `protocol("WM_DELETE_WINDOW", ...)`:
```python
root.bind_all("<Button-1>", self._maybe_drop_focus)

def _maybe_drop_focus(self, event):
    if not isinstance(event.widget, tk.Entry):
        self.root.focus_set()
```
This fires after any widget's own `<Button-1>` handler (Tk's bindtag order), so buttons, segmented controls, and game items still execute their click actions; it simply defocuses any active entry. The `isinstance` check is exact because NumBox's Entry is the only `tk.Entry` in the app (verified: `grep -n "tk.Entry" afk_clicker.py` returns one hit).

### Global hotkey fires focus-drop (new)
In `start()`, add one line before status update:
```python
self._ui(self.root.focus_set)
```
This queues the defocus through the UI thread's queue (same latency as every other hotkey-triggered update), so a field edited mid-click-session is defocused within one `_drain_ui()` cycle (≤40 ms).

### No revert on Escape
Escape only blurs; it does not revert the field to its pre-edit value. The codebase has no per-field edit-state caching, and the validation model argues against inventing one here. The typed text is the live source of truth (continuously persisted on every keystroke and re-read every 200 ms), so there is nothing to "revert" from—what you typed is exactly what was already being clamped/validated.

## Resize behavior

### Window resizability
- `root.resizable(True, True)` replaces the current `root.resizable(False, False)`.
- Minimum size: `minsize(int((SIDEBAR_W + 1 + CONTENT_W) * s), int(690 * s))` — the exact size the layout ships at today (660 px wide, 690 * scale tall), tuned to the Minecraft profile's taller eating card, so nothing clips below this floor.
- Initial geometry: unchanged (geometry set to minsize at init).
- No window size/position persistence across restarts (non-goal per spec).

### Width distribution on resize
- **Sidebar**: Stays pinned at `SIDEBAR_W * s` (208 * scale ≈ 208 px at 96 dpi). Packed `side="left", fill="y"` without expand.
- **Content pane**: Absorbs 100% of extra width, via existing `pack(..., fill="both", expand=True)` at line 1044. No pack-option changes needed.
- **Concrete examples** (at DPI scale 1.0, which is 96 dpi):
  - Default (660 px window): sidebar 208 px, content 452 px.
  - 1000 px window: sidebar 208 px, content 791 px (175% of default content width).
  - 1600 px window: sidebar 208 px, content 1391 px (308% of default content width).

### Visual implications of width stretch
- **Row layout**: Each Row has a label side packed `side="left", fill="x", expand=True` (line 938), and control side (NumBox, Segmented, etc.) packed `side="right"` without expand/fill (line 945). Extra width flows to the label side; controls stay pinned to the right edge at their natural width.
  - At 1000 px: Label has ~340 px of extra space vs. the default layout.
  - At 1600 px: Label has ~940 px of extra space.
  - This is acceptable UX — the label side is commonly packed this way in settings-table layouts, and it gives label text breathing room.
  
- **Two-button rows** (e.g., Record/Apply in the hotkey card, packed left/right to opposite edges, line 1087–1089): The gap between them widens on wider windows.
  - At 1000 px: ~340 px gap between buttons (vs. ~80 px at default).
  - At 1600 px: ~940 px gap between buttons.
  - This is a pre-existing consequence of the anchor-to-opposite-edges layout, not new dead chrome. The ticket does not ask for centering or width-capping, so it is left as an expected cosmetic consequence of stretching the pane.

- **Fixed-size canvases**: Button, Segmented, StatusPill, and GameItem keep their configured pixel dimensions and existing pack sides. No changes.

### Height distribution on resize
- **Content pane**: Packed `fill="both", expand=True` but with `pack_propagate(False)` to hold children at their tuned height. Extra height creates blank space *below* the last card in the column. Cards themselves do not expand vertically.
- **Sidebar**: Packed `side="left", fill="y"` (no expand), but the list_frame inside it is packed `fill="both", expand=True`. Extra height expands the space in the games list; game-item rows get more vertical breathing room.
- **Sidebar buttons** ("Add current game", "Check for updates", version): Packed after the list_frame, so they stay pinned to the bottom of the sidebar, with expanded space above them.
- **Header**: No change; remains fixed at its declared height.

### No maximum width
Unlike the open question in the spec, this design does not cap content width and center it with padding frames. Capping would require adding pack structure (new filler frames or switching to `place` layout), which violates the "no redesign of card/row/canvas-widget layout" non-goal. The stretch-unbounded approach costs zero new code—it's already what `fill="both", expand=True` does—and is a reasonable UX choice for a settings/config window: more real estate means more legible labels and a familiar "stretch to fit" behavior.

## Interactive states

### NumBox focus transitions
1. **Click into an unfocused NumBox**: Wrap turns ACCENT (standard Entry focus behavior, unaffected by the new handler).
2. **Click elsewhere (non-Entry widget)**: Wrap turns LINE; focus leaves the entry. Existing click handlers on buttons/segments/game items still fire normally.
3. **Click another NumBox while one is focused**: Focus shifts to the new entry; the old one's wrap turns LINE. Entry's own class binding (processed before the `"all"` bindtag) keeps focus on Entry-to-Entry transitions.
4. **Press Enter/Escape while focused**: Wrap turns LINE; focus leaves the entry. Typed value unchanged (not reverted, not clamped in place).
5. **Global hotkey fires while field is focused**: Wrap turns LINE within one UI queue cycle (≤40 ms). Typed value unchanged.

### Tab/Shift-Tab traversal
Unaffected. No new bindings on Tab keys; `_maybe_drop_focus` only binds `<Button-1>`. Standard Tk focus traversal continues to work.

## Accessibility & platform notes

- **Touch targets**: NumBox entry width and padding are unchanged (existing `width=6` chars, `ipadx=5*s`, `ipady=4*s`). Wrap padding stays 1 px. No new touch-target concerns.
- **Color contrast**: 
  - ACCENT on BG in focused state: ACCENT #ffc542 on BG #0e0f13. Relative luminance: 0.734 and 0.010 → contrast ratio ≈ 73:1 (far exceeds AA 4.5:1).
  - LINE on BG in unfocused state: LINE #262a35 on BG #0e0f13. Relative luminance: 0.026 and 0.010 → contrast ratio ≈ 2.6:1 (does not meet AA). However, this is the existing border color and is already in use; the spec does not ask for a change. The wrap's visual function is to delineate the field, not to carry text, so the low contrast is cosmetic rather than functional. If contrast is a concern, it is a separate issue outside this ticket's scope.
- **Web vs. native**: This is a Tk desktop app (Windows/macOS/Linux), not a web app. All behavior is platform-uniform (bind_all, minsize, resizable are standard Tk/Tcl calls with no platform branches).
- **Hover**: No hover state is added to unfocused NumBox entries. The wrap stays LINE without visual change on hover. This is consistent with the rest of the UI and minimizes diff.

## Traceability to spec

| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| Click elsewhere defocuses entry and turns wrap LINE | Application-wide `bind_all("<Button-1>")` handler calls `root.focus_set()` on non-Entry clicks (see "Application-wide blur on non-Entry click") |
| Click another entry keeps it focused | `isinstance` check skips Entry widgets, letting Entry's own class binding keep focus on Entry clicks (see "Application-wide blur on non-Entry click") |
| Tab/Shift-Tab traversal unaffected | No new Tab bindings; standard Tk traversal continues (see "Tab/Shift-Tab traversal") |
| Enter/Escape blur the field | New `<Return>` and `<Escape>` bindings on each NumBox entry call `root.focus_set()` (see "NumBox bindings") |
| Enter/Escape do not revert value | Spec Decision 2: clamping happens at read time, not at blur; typed text is unchanged on blur (see "No revert on Escape") |
| Global hotkey fires focus-drop | New `self._ui(self.root.focus_set)` call in `start()` queues defocus through UI thread (see "Global hotkey fires focus-drop") |
| Window is resizable on both axes | `root.resizable(True, True)` replaces `resizable(False, False)` (see "Window resizability") |
| Minimum size is current default geometry | `minsize()` set to `(int((SIDEBAR_W + 1 + CONTENT_W) * s), int(690 * s))`, the exact current window size (see "Window resizability") |
| Extra width is used by content pane | Sidebar stays pinned at SIDEBAR_W; content expands via existing `pack(..., fill="both", expand=True)`. Examples at 1000 px and 1600 px provided (see "Width distribution on resize") |
| Extra width does not clip controls | Minsize enforced by Tk; setting `geometry("50x50")` against this minsize leaves window at exactly minsize (see "Window resizability") |
| Extra height creates space below last card (not clipping) | Content pane's `pack_propagate(False)` holds children at tuned height; extra height shows as blank space below cards (see "Height distribution on resize") |
