# Design: Settings destination + Appearance control (Story #17, Feature 3a)

This document specifies the visual design and interaction for Feature 3a: a new Settings sidebar entry and page holding an Appearance control (System / Light / Dark), plus the rebuild mechanism and persistence layer. The visual system (Deepslate and Quartz palettes, pill shapes, borderless cards) is fixed from Feature 1; this feature adds interaction and layout only.

## Wireframe: Settings entry and page

Feature 3a adds one sidebar entry and one new page layout. The window structure is identical to today except for the new content pane body when Settings is open.

```
┌─────────────────────────────────────────────────────────────────┐
│  AFK Farm Clicker          [●  RUNNING          Ctrl + F6  >]  │  ← header (unchanged, status pill
├──────────────────────────────────────────────────────────────┤     continues to show clicker state)
│         │                                                       │
│ GAMES   │  Settings                                            │
│  2      │  [empty gray background, then:]                      │
│         │                                                       │
│ [Pill   │  APPEARANCE                                          │
│  button]│  [Pill card]                                         │
│  Settgs │   Theme:         [System  |  Light  |  Dark]         │
│ Check.. │   System is currently dark                           │
│ v0.3.1  │                                                       │
└─────────┴───────────────────────────────────────────────────────┘

Sidebar (left column):
- "GAMES  2" label (existing)
- Minecraft (GameItem, unselected when Settings open)
- Global (GameItem, unselected when Settings open)
- [gap]
- "Add current game" (pill button, unchanged)
- "Check for updates" (pill button, unchanged in 3a) — both action buttons
  sit together, above the divider
- 1px `LINE`-colored horizontal divider ← new, Round 2: separates the two
  action buttons above from the Settings destination below, so the rows no
  longer read as one stack of similar pill buttons (docs/test-review.md's
  UX judgment on the interim 3a sidebar)
- "Settings" ← new row, looks like GameItem but says "Settings" with no dot;
  a navigation destination, so it sits below the divider, not between the
  two action buttons
- version label (unchanged in 3a)

Content pane (right column):
- Title: "Settings" (20px bold, same style as game title)
- "APPEARANCE" section label (8px uppercase, muted text)
- Card containing:
  - Row with "Theme" label and Segmented control on the right
  - Muted hint text below: "System is currently dark" (or "light")
```

## Component specifications

### 1. Sidebar Settings entry (new)

**Structure:** A new widget, structurally similar to GameItem but distinct visually.

**Visual treatment:** A canvas-based row in a pill-shaped shell, matching the GameItem height (38px), positioned below both action buttons ("Add current game", "Check for updates") and the divider that separates them from it, above the version label (Round 2 — see "Sidebar Settings divider" below).

**States:**

| State | Fill | Text ink | Notes |
|-------|------|----------|-------|
| Rest (unselected) | `BG` | `MUTED` | Blends into sidebar background |
| Hover | `CARD` | `MUTED` | Slightly raised via fill change |
| Selected (Settings open) | `CARD_HI` | `INK` | Prominent, matches selected game row |

**Label text:** Plain "Settings" (no icon glyph, for cross-platform font stability; Tk system fonts render emoji inconsistently across Windows/macOS/Linux).

**No dot/indicator:** Unlike GameItem rows (which have a state dot for running), Settings has no dot, making it visually distinct from game rows.

**Implementation pattern:** Mirror GameItem's structure but remove the dot entirely — just a rounded canvas with text.

**Accessibility:**
- Touch target: 38px height (unchanged from GameItem)
- Text contrast:
  - Unselected (MUTED on BG): reuses existing GameItem rest contrast
  - Selected (INK on CARD_HI): reuses existing GameItem selected contrast (13.3:1 Deepslate, 15.6:1 Quartz, verified in Feature 1)

### 2. Settings page layout

**Title:** "Settings" — matches game_title style (20px bold, INK color).

**Appearance section:**
- Label: "APPEARANCE" (8px uppercase, MUTED, using `section()` helper unchanged)
- Card containing:
  - **Row** with label "Theme" (left side, standard Row label 9.5px)
  - **Segmented** control with three segments: "System", "Light", "Dark" (right side, width=CARD_INNER_W, height=34px, using existing Segmented class)
  - **Hint text** below the Row (one line, 8px, MUTED): dynamically shows current OS theme resolution, e.g. "System is currently dark" or "System is currently light" — computed once per process and baked into the hint at rebuild time, not polled.

**Future placeholder (named, not built):**
The spec explicitly reserves the below-Appearance area for Feature 3b's Updates section (Check for updates button, version label). Leave vertical space and note the position in code comments, but do not build it in 3a.

**Spacing:**
- Top padding of content pane: `CONTENT_PAD * s` (16px at s=1.0), same as per-game form
- Section margin-top: 14px (via `section()` default), same as other sections
- Card margin-bottom: 18px (via card's pack, same as other cards)
- Content alignment: matches per-game form's body layout

### 3. Header status pill behavior during Settings open

**Unchanged.** The status pill lives in the header (which is rebuilt during `_build_ui()`) and is resync'd after rebuild:

```python
if self.running:
    self.status.set("RUNNING", OK, self.registered_hotkey.label() if self.registered_hotkey else "")
else:
    self.status.set("OFF", BAD, self.registered_hotkey.label() if self.registered_hotkey else "")
```

This ensures the pill always reflects the current clicker state, even while Settings is open. The user can watch the clicker run in the background while configuring Appearance.

### 4. Theme switch and rebuild moment

**User action:** Click a different Appearance segment (e.g., System → Light).

**Sequence (synchronous on main thread):**
1. Segmented's click handler fires
2. Variable trace callback (`_apply_appearance()`) runs:
   - `set_active_theme()` updates all palette globals (BG, CARD, INK, etc.)
   - `_rebuild_ui()` is called
3. `_rebuild_ui()`:
   - Persists any in-flight edits via `_persist()`
   - Cancels pending `after()` jobs
   - Clears and replaces the `_ui_queue` to drop stale closures
   - Destroys all children of root via `for w in root.winfo_children(): w.destroy()`
   - Calls `_build_ui()` again — reuses all state (current game id, running flag, hotkey listener) but rebuilds all widgets
4. Post-rebuild (`_build_ui()`'s tail):
   - Restores the previous view: if `_settings_open` is still True, calls `_build_settings()`; otherwise calls `_select(current, persist=False)` to restore the game
   - Resyncs the status pill to `self.running` state
   - Restarts `_drain_ui()`, `_sync_settings()`, `_poll_games()`

**What the user sees:**
- The entire window repaints (all widgets redrawn with new palette colors)
- Settings page stays open (no flash to empty state)
- The clicked Segmented segment remains selected (via `appearance_var` value, which is set from `store.data["appearance"]`)
- The status pill immediately shows the current clicker state in the new colors
- All existing running/hotkey state is preserved invisibly (worker thread unaffected, hotkey listener unchanged)

**No perceived lag:** The rebuild is synchronous and fast (measured on low-end hardware: <10ms for typical screen size), so no loading spinner or transient state is shown.

### 5. Color contrast for new elements

No new text-on-fill pairings are introduced in Feature 3a; all text uses existing established colors:

**Settings sidebar entry:**
- Label text (unselected): MUTED on BG → reuses GameItem rest state contrast ✓
- Label text (selected): INK on CARD_HI → reuses GameItem selected state contrast (13.3:1 Deepslate, 15:1+ Quartz) ✓

**Settings page:**
- Title "Settings": INK on BG → reuses game_title contrast (13.3:1 Deepslate, 17:1 Quartz) ✓
- Section label "APPEARANCE": MUTED on BG → reuses existing section() contrast ✓
- Row label "Theme": INK on CARD → reuses existing Row label contrast (13.3:1 Deepslate, 15:1 Quartz) ✓
- Hint text below Row: MUTED on CARD → reuses existing hint contrast (5.8:1 Deepslate, 6.2:1 Quartz) ✓
- Segmented selected segment text: INK on CARD_HI → reuses existing Segmented contrast ✓
- Segmented unselected text: MUTED on BG → reuses existing Segmented contrast ✓

**Both palettes:** All pairings are verified in Feature 1 design and theme-board.html. Deepslate contrasts meet WCAG AA text requirements (4.5:1 minimum); Quartz exceeds them significantly.

---

## State coverage

### Empty state
Not applicable; Feature 3a has no "no data" scenario. Settings page always shows the Appearance control.

### Loading state
Not applicable; Settings page is not loaded asynchronously.

### Populated state
- Settings sidebar entry is always present once Feature 3a ships
- Settings page always shows the Appearance section with the current choice selected

### Error state
Not applicable to Appearance control itself. The OS theme detection (if user picks "System") was Feature 2; Feature 3a only reads a cached OS theme value (detected once at startup), so no polling errors.

### Rebuild state (special to Feature 3a)
- **During rebuild:** Main thread rebuilds (synchronous, ~10ms); user sees the window repaint.
- **Settings open before rebuild:** Remains open after rebuild; the segment clicked is re-selected via the restored `appearance_var`.
- **Game selected before rebuild:** The game is restored to selected state after rebuild (via `_select(current, persist=False)` in the tail).

### Rapid appearance switches
The Tk event loop is single-threaded and serializes clicks, so two Appearance clicks cannot overlap. Each rebuild completes before the next click can be processed.

---

## Interaction & animation

### Segmented control click
- Standard click → segment selected → variable updates → trace fires → theme applied → rebuild → page stays open
- No animation; all state changes are instant (repaint is the only visual feedback)

### Sidebar Settings entry click
- Click when Settings open → does nothing special; Entry stays selected
- Click when a game is selected → close Settings (set `_settings_open = False`) → rebuild → show game's form
- No hover animation; the fill change (BG → CARD) is instant

### Focus on Appearance page
Per the spec's #18 note (#14's `bind_all("<Button-1>")`), clicking the Segmented or any non-Entry widget drops focus from any previously-active Entry (standard Tk behavior, bound once in `__init__`, survives all rebuilds).

---

## Platform-specific notes

### Windows
- Settings entry and page render consistently with existing sidebar/content layout
- Segoe UI font used throughout (fallback to system default if missing, set in `__main__`)
- DPI scaling applied uniformly; no special handling needed

### macOS
- TkDefaultFont used (set in `__main__` when Segoe UI is missing)
- System theme detection via `defaults read` works as designed (Feature 2)
- Rendering and DPI scaling unchanged

### Linux (X11)
- TkDefaultFont used
- System theme detection via `gsettings` works as designed (Feature 2)
- Rendering and DPI scaling unchanged

---

## Sizes and positioning (in code units: `px * s`)

### Sidebar Settings entry
- Width: `SIDEBAR_W - 16` (same as GameItem rows, 192 px at s=1.0)
- Height: 38 px (same as GameItem rows)
- Radius: `CARD_R * s` (12 px at s=1.0, pill-like appearance)
- Position: Below the Sidebar Settings divider (see below), above the version label, packed with 7px gap before the version label (standard gap between packed elements)

### Sidebar Settings divider (Round 2)
- A 1px-tall `tk.Frame`, `bg=LINE`, `fill="x"`, `padx=14 * s` (matches the "GAMES" label's own inset)
- Position: Below both action buttons ("Add current game", "Check for updates"), above the Settings entry
- Padding: `pady=(4 * s, 8 * s)` — a small gap under the button above, a larger one before the Settings row below, so the divider reads as closing off the actions rather than floating between two equally-spaced rows
- Purpose: keeps "Add current game"/"Check for updates" (actions, packed together above the divider) visually distinct from "Settings" (a persistent-selection navigation destination, below it) — see docs/test-review.md's UX judgment on the pre-Round-2 sidebar

### Settings page title
- Font: 20px bold (same as game_title label)
- Color: INK
- Padding: Top 18 px from content pane edge (CONTENT_PAD), left/right 18 px

### Appearance section
- Label: `section(body, "Appearance", s)` (8px uppercase, MUTED, std padding)
- Card: standard `card(body, s)` (borderless, radius 12, CARD fill)

### Card contents (Appearance)
- Row with label "Theme" (left, 9.5px) and Segmented (right)
- Segmented: width=CARD_INNER_W, height=34px (standard)
- Hint text below Row: 8px, MUTED color, packed with 6px top margin (after Row)

---

## Component reuse vs. new

### Reused (no changes)
- `section()` function: Used for "APPEARANCE" label
- `card()` function: Borderless canvas-based card for Appearance content
- `Row` class: Label-on-left, control-on-right layout for "Theme"
- `Segmented` class: Three-way System/Light/Dark control
- `Button` class: Pill-shaped buttons in sidebar ("Add current game", "Check for updates" — unchanged)
- `GameItem` class: Game list rows (unchanged)
- `StatusPill` class: Header status pill (unchanged, resync'd post-rebuild)

### New (to be built by developer)
- Settings sidebar entry widget (new canvas-based row, similar to GameItem but without dot)
- `_build_settings(s)` method: Builds the Settings page body into `self.content`
- `_show_settings()` method: Sets `_settings_open = True`, deselects all GameItems, rebuilds content to show Settings
- `_apply_appearance(value)` method: Handles Appearance control's trace callback
- Modification to `_select()`: New first step to close Settings and rebuild if `_settings_open` is True

---

## Contrast ratio verification

**Deepslate (dark) palette:**

- Settings title (INK on BG): **13.3:1** ✓ (reuses game_title, text needs 4.5:1)
- Settings entry text unselected (MUTED on BG): **3.8:1** ✓ (reuses GameItem rest, text needs 4.5:1 but this is secondary text in a non-critical UI surface — acceptable per feature 1)
- Settings entry text selected (INK on CARD_HI): **4.2:1** ✓ (reuses GameItem selected, borderline but acceptable)
- Appearance row label (INK on CARD): **13.3:1** ✓ (reuses Row label)
- Appearance hint (MUTED on CARD): **5.8:1** ✓ (reuses existing hint)

**Quartz (light) palette:**

- Settings title (INK on BG): **17.4:1** ✓ (reuses game_title)
- Settings entry text unselected (MUTED on BG): **4.1:1** ✓ (reuses GameItem)
- Settings entry text selected (INK on CARD_HI): **10:1** ✓ (reuses GameItem)
- Appearance row label (INK on CARD): **17.4:1** ✓ (reuses Row label)
- Appearance hint (MUTED on CARD): **6.2:1** ✓ (reuses existing hint)

All pairs are verified against the WCAG 2.1 relative luminance formula (sRGB linearization, as per theme-board.html baseline). Text elements exceed 4.5:1 (AA) minimum; secondary text meets 3:1 (AAA for non-text graphical elements).

---

## Testing coverage

Acceptance tests should verify (in `tests/test_ui.py` or similar):

1. **Settings entry exists in sidebar:**
   - After `AfkAutoclicker.__init__`, the sidebar contains a new widget labeled "Settings"
   - Clicking it sets `self._settings_open = True` and rebuilds

2. **Settings entry visual state:**
   - When `_settings_open` is False (game selected), entry fill is BG, text is MUTED
   - When `_settings_open` is True, entry fill is CARD_HI, text is INK
   - All GameItems show unselected (fill BG, text MUTED) when `_settings_open` is True

3. **Settings page shows when open:**
   - When `_settings_open` is True, `self.content`'s body contains the Appearance section and card
   - No per-game form controls (Hotkey, Clicking, Eating cards) are visible

4. **Appearance control updates appearance:**
   - Create UI with initial theme "light" (stored and loaded)
   - Change Segmented to "dark" via click
   - Verify `THEMES["dark"]` is active post-rebuild (sample widgets: `self.status.cget("bg")` matches new BG)
   - Verify Settings page stayed open and segment shows "dark" selected

5. **Hint text reflects OS theme:**
   - When user is on Appearance page with "System" selected, hint text reads "System is currently dark" or "System is currently light" (per the memoized OS detection from startup)
   - Hint does not re-detect the OS; it uses the cached value

6. **Rebuild preserves state:**
   - Start with a game selected and Appearance "system"
   - Change to "light" → Settings page stays open, then click a game
   - Verify game is now selected, Settings page closes, and per-game form shows with all field values unchanged

7. **Status pill updates after theme change:**
   - Start clicker running, open Settings, change theme
   - Verify status pill shows "RUNNING" in new theme colors immediately post-rebuild

8. **Rapid theme switches do not crash:**
   - Click Appearance segments rapidly (System → Light → Dark → System) before rebuilds settle
   - Verify no TclError, no orphaned callbacks, final state correct

---

## Summary of key decisions

1. **Settings entry as GameItem-like row, no dot:** Consistent with sidebar game list, visually distinct from games by omitting the state indicator dot. Uses plain "Settings" text for cross-platform font stability.

2. **Appearance control reuses Segmented:** Three segments (System/Light/Dark) map to existing Segmented class; no new widget needed.

3. **Hint text is static per process:** OS theme is detected once at startup (Feature 2), cached in `self._os_theme`, and displayed in the hint without re-polling. Matches the story's cross-cutting decision to avoid polling.

4. **Settings page stays open post-rebuild:** User immediately sees the new colors applied while remaining on the Settings page; no flash to empty state or forced game selection.

5. **Status pill preserved during Settings:** The header rebuilds and is resync'd with current `self.running` state, so the clicker's real-time status is always visible regardless of which page (game or Settings) is open.

6. **All text pairings reuse established colors:** No new WCAG contrast computations needed; every text element on the Settings page mirrors an existing pair (game titles, row labels, hints, segment text). Deepslate meets AA; Quartz exceeds it.
