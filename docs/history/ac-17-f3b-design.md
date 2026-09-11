# Design: Move Updates into Settings (Story #17, Feature 3b)

This document specifies the visual design and layout for Feature 3b: moving the "Check for updates" button and version label from the sidebar footer into a new "Updates" section on the Settings page, plus the off-screen offer signal on the Settings row itself.

---

## Summary of changes from 3a

**Sidebar footer (removed):**
- `self.update_button` ("Check for updates", dynamic status/install action)
- `self.version_label` (version string, dynamic offer/error text)

**Sidebar footer (unchanged):**
- "Add current game" button
- 1px `LINE` divider
- "Settings" entry (now with optional `has_update` indicator)

**Settings page (new section):**
- "Updates" section label (matching "Appearance" style)
- Card containing:
  - Version row (label "Version", version string right-aligned in mono)
  - Status button ("Check for updates" / status / offer / error)

**Settings row (new):**
- Plain text "Settings" when no update pending
- Text "Settings · Update" when `has_update` is True (via `SettingsItem.set_state(has_update=True)`)
- Color: ACCENT when has_update and selected (offers visual prominence without a separate dot)

---

## Wireframe: Settings page with Updates section

```
Settings                                          ← page title (unchanged from 3a)

APPEARANCE                                        ← section label (unchanged)
[Pill card]                                       ← Appearance card (unchanged)
 Theme:    [System  | Light | Dark]
 System is currently dark

UPDATES                                           ← new section label
[Pill card]                                       ← new card
 Version:                          v0.3.1        ← version row with mono text right-aligned
 [Check for updates]               ← status button, full width or close to it

```

**State examples:**
- Idle: "Check for updates" (enabled, normal button)
- Checking: "Checking…" (disabled)
- Up to date: "Up to date · v0.3.1" (enabled, MUTED version label text)
- Offer found: "Install v0.3.2" (enabled, primary styling, ACCENT version label)
- Downloading: "Downloading… 45%" (disabled)
- Error: "[error text]" truncated to 40 chars (enabled, BAD color on version label)

---

## Component specifications

### 1. Sidebar Settings row with update indicator

**Modification to SettingsItem class:**

Add two new pieces of state (constructor default, method parameter):
- Constructor parameter: `has_update=False` (bool, stored on `self`)
- Method parameter in `set_state()`: `has_update=None` (None means unchanged, following GameItem's pattern)

**Visual rendering in `_paint()`:**

Text changes from always "Settings" to:
- "Settings" (no symbol/dot) when `self.has_update is False`
- "Settings · Update" when `self.has_update is True`

The text uses the same 9.5px font as today; the separator `·` is a literal middle-dot character (Unicode U+00B7).

**Color for selected + has_update:**

When `selected=True` and `has_update=True` (Settings row is highlighted AND an update is available):
- Fill: `CARD_HI` (unchanged)
- Text: `ACCENT` (orange/blue depending on theme)
- Contrast: 5.18:1 (Deepslate), 4.94:1 (Quartz) — both ≥4.5:1 AA ✓

**When indicator clears:**

The text and `has_update` flag persist until a successful install (which restarts the process and clears `self._pending`). Once Settings is opened and dismissed, the indicator does NOT automatically clear — it remains as a persistent signal to return to Settings and act on the pending update. User must either install or close/restart the app.

**Touch target:**

38px height (unchanged), full sidebar width (unchanged).

---

### 2. Settings page — Updates section (new)

**Section label:**
- Text: "UPDATES" (uppercase, 8px, MUTED)
- Uses existing `section(body, "Updates", s)` helper with default top margin (14px)

**Card:**
- Uses existing `card(body, s)` helper (borderless, radius 12, CARD fill)
- Contains two main elements: version row + button

**Version row:**
- Label "Version" (left, INK, 9.5px, using standard Row label style)
- Version string (right, MUTED, 9px mono font — Consolas on Windows, `TkFixedFont` fallback)
- Example: "v0.3.1"
- Rendering: Use a `Row(card_inner, "Version", s)` with a `tk.Label` in `row.control` showing the version

**Status button:**
- Text varies by update state (see State coverage below)
- Full width inside card minus standard padding (close to CARD_INNER_W)
- Height: 34px (same as Segmented control, standard button height)
- Primary styling when offer is found (ACCENT background, light text)
- Normal styling when idle or checking
- BAD color on version_label (not button text) when errors occur
- Disabled state: button shows as greyed-out when checks in progress
- Enabled when idle, offering, or errored (user can retry or click normally)

**Spacing within card:**
- Version row: packed with fill="x"
- Status button: packed below with `pady=(int(8 * s), 0)` — standard card-internal spacing
- No hint text below button (errors are shown via color on version_label, truncated to 40 chars per spec)

---

## State coverage — all update states

| State | Button text | Button enabled | Version label text | Version label color | Notes |
|-------|-------------|----------------|--------------------|---------------------|-------|
| **Idle** (initial) | "Check for updates" | Yes | "v{version}" | MUTED | Normal resting state |
| **Checking** | "Checking…" | No | "v{version}" | MUTED | Background thread running |
| **No releases** | "No releases published yet" | Yes | "v{version}" | MUTED | Rare; repo has no releases tag |
| **GitHub unreachable** | "GitHub unreachable" | Yes | "v{version}" | BAD | Network or GH down |
| **Up to date** | "Up to date · v{current}" | Yes | "v{current}" | MUTED | Latest installed |
| **No build for OS** | "{tag}: no build for this OS" | Yes | "v{version}" | BAD | Platform binary missing |
| **Offer found** | "Install {tag}" | Yes | "v{current} → {tag}" | ACCENT | New version available; button is primary |
| **Downloading 0%** | "Downloading… 0%" | No | "v{current} → {tag}" | ACCENT | Initial progress; still shows offer text in label |
| **Downloading 50%** | "Downloading… 50%" | No | "v{current} → {tag}" | ACCENT | Mid-progress (example 50%) |
| **Downloading 100%** | "Downloading… 100%" | No | "v{current} → {tag}" | ACCENT | Nearly done, before swap |
| **Restarting** | "Restarting…" | No | "v{current} → {tag}" | ACCENT | Swap script started; process about to exit |
| **Checksum mismatch** | "checksum: not in SHA256SUMS: …" (≤40 chars) | Yes | Truncated error text | BAD | Asset not in checksum file; re-enable for retry |
| **Checksum mismatch — generic** | "checksum mismatch: …" (≤40 chars) | Yes | Truncated error text | BAD | Digest doesn't match; re-enable for retry |
| **Install folder read-only** | "Install folder is read-only" | Yes | "Install folder is read-only" | BAD | Permission denied; user can't retry here |
| **Install error (generic)** | "Update failed: {error}" (≤40 chars) | Yes | Truncated error text | BAD | Other exception; user can retry |
| **Not a build (dev/source)** | "Run \`git pull\` — not a build" | Yes | "Run \`git pull\` — not a build" | BAD | Running from source, not a frozen binary |

**Key behaviors:**

- **Truncation rule:** Error messages (checksum, generic install failures) are truncated to 40 characters, applied at the `_install_worker` call sites (no change from today).
- **Colour on version_label, not button:** Errors and offers use colour on the version label, not the button text itself. This keeps the button's text readable and reserves colour for "state context" rather than "action prompt".
- **Button state after error:** Re-enabled (user can click again to retry or start a new check).
- **During mid-download rebuild (special):** If a rebuild occurs while downloading (e.g., Appearance change), the button shows "Downloading… N%" again (not reset to "Install {tag}") — this is handled by the two-step replay in `_build_ui()`'s tail (per spec §3).

---

## Sidebar footer layout change

**Current (3a):**
```
[Add current game] (button, 4px gap below)
[Check for updates] (button, 4px gap below)
1px divider (4px gap above, 8px below)
[Settings] (entry, 7px gap below)
v0.3.1 (label)
```

**After 3b (no button/version_label in sidebar):**
```
[Add current game] (button, 4px gap below)
1px divider (4px gap above, 8px below) ← now separates just one button
[Settings] (entry)
```

The divider's spacing (4px above the button, 8px below the divider) remains unchanged — it already closes off the single button above and leaves space before the navigation row below, which is the right visual logic regardless of how many buttons sit above it.

No version label appears anywhere in the sidebar; the version is shown only on the Settings page in the Updates section.

---

## Sidebar offer indicator — color and contrast

**When to show "Settings · Update":**
- Condition: `self._pending is not None` (an offer has been found and Settings has not yet been closed and reopened for next check)
- Set via: `self.settings_item.set_state(has_update=True)` in `_offer_update()`
- Clear via: a fresh app or after a successful install (which restarts the process)

**When Settings row is unselected (has_update=True):**
- Fill: `BG` (blends into background, no fill)
- Text "Settings · Update": `ACCENT` (orange in Deepslate, blue in Quartz)
- Contrast on BG:
  - Deepslate: ACCENT (#e08a55) on BG (#15171a) = 6.8:1 ✓
  - Quartz: ACCENT (#2b58cc) on BG (#e8ebf0) = 5.2:1 ✓
  - Both ≥4.5:1 AA for text ✓

**When Settings row is selected (has_update=True):**
- Fill: `CARD_HI` (highlighted, pill-shaped)
- Text "Settings · Update": `ACCENT` (same orange/blue)
- Contrast on CARD_HI:
  - Deepslate: ACCENT (#e08a55) on CARD_HI (#262a30) = 5.18:1 ✓
  - Quartz: ACCENT (#2b58cc) on CARD_HI (#eff2f7) = 4.94:1 ✓
  - Both ≥4.5:1 AA ✓

All pairs meet or exceed WCAG AA text contrast (4.5:1).

---

## Component reuse

### Unchanged (3a already built these)
- `section()` function: used for "UPDATES" label
- `card()` function: borderless rounded card
- `Row` class: "Version" label + version display
- `Button` class: status button (reused from sidebar, now in Settings page)
- `SettingsItem` class: base class exists; feature 3b adds `has_update` parameter/state

### Modified (3b changes)
- `SettingsItem`: add `has_update=False` kwarg to `__init__`, add `has_update=None` kwarg to `set_state()`, modify `_paint()` to render "Settings" or "Settings · Update" based on `self.has_update`
- Sidebar footer in `_build_ui()`: remove `self.update_button` and `self.version_label` construction lines and preceding comments
- `_build_settings()`: add new "Updates" section/card with version row and button

### State management (3b new)
- `self._update_text`: tuple `(text, enabled, colour)` tracking the most recent `_set_update_state()` call, persisted across rebuilds
- `_set_update_state()`: now records to `self._update_text` and only touches widgets if `self._settings_open`
- `_offer_update()`: now calls `self.settings_item.set_state(has_update=True)` and also only touches widgets if `self._settings_open`
- `_build_ui()` tail: after building Settings page, replays pending state via two-step process (offer first, then text overlay)

---

## Platform notes

### Windows
- Version label uses Consolas font (10px, already used for NumBox entries)
- DPI scaling via `self.s` applied uniformly
- No platform-specific behavior in the layout or state handling

### macOS
- Version label falls back to `TkFixedFont` if Consolas unavailable
- No platform-specific behavior

### Linux
- Version label falls back to `TkFixedFont` if Consolas unavailable
- No platform-specific behavior

---

## Sizing and spacing (in code units: `px * s`)

### Sidebar Settings row — when has_update=True
- Width: unchanged, `SIDEBAR_W - 16` (192 px at s=1.0)
- Height: unchanged, 38 px
- Radius: unchanged, `CARD_R * s`
- Text: "Settings · Update" (instead of "Settings")
- Text color when unselected: ACCENT (#e08a55 dark, #2b58cc light)
- Text color when selected: ACCENT (same, inherits from parent's text rendering logic)

### Updates section
- Label: `section(body, "Updates", s)` with default top margin (14px)
- Card: standard `card(body, s)` with borderless radius-12 appearance

### Updates card contents
- Version row:
  - Label "Version" (left, 9.5px INK)
  - Version string (right, 9px mono MUTED) — example "v0.3.1"
  - Row packed with fill="x"
- Status button:
  - Width: approximately `CARD_INNER_W - 2 * pad` (fits inside card with inset)
  - Height: 34px (standard button height)
  - Packed with pady=(8px, 0) below the version row

### Sidebar footer (no version_label)
- "Add current game" button: packed as before
- 1px divider: `pady=(4*s, 8*s)` unchanged
- Settings entry: packed below divider as before

---

## State coverage — interaction flow

### Idle (no activity)
- Sidebar Settings row: "Settings" (no update indicator unless pending from earlier)
- Settings page Updates section (if open): "v0.3.1" + "Check for updates" button, enabled
- User action: click button → triggers check

### During check (Checking…)
- Sidebar: no change (Settings row remains as is; no indicator if check started on game page with Settings closed)
- Settings page (if open): button shows "Checking…", disabled; version label unchanged
- Background thread: `_check_worker` running

### Check completes — no new release
- Sidebar: no indicator
- Settings page: button shows "Up to date · v0.3.1", enabled; version label shows "v0.3.1", MUTED

### Check completes — new release found
- Sidebar: Settings row changes to show "Settings · Update", ACCENT color (if unselected)
- Settings page (if open): button shows "Install v0.3.2", enabled + primary styling; version label shows "v0.3.1 → v0.3.2", ACCENT color
- If Settings is not open: sidebar indicator persists until user clicks Settings, then page shows the offer

### User clicks Install (while downloading)
- Sidebar: indicator persists
- Settings page (if open): button shows "Downloading… 0%" → "Downloading… 50%" → "Downloading… 100%", disabled; version label remains "v0.3.1 → v0.3.2", ACCENT
- Background thread: `_install_worker` running, posting progress updates

### Download completes — swap and restart
- Sidebar: indicator persists (Settings still open or still showing the pending state)
- Settings page: button shows "Restarting…", disabled; process exits via `_quit_for_update()`

### Install error (e.g., checksum mismatch)
- Sidebar: indicator persists
- Settings page: button shows truncated error (e.g., "checksum: not in SHA256SUMS: abc…" up to 40 chars), enabled; version label shows same truncated error, BAD color (red)
- User can click button again to retry

### Rebuild while offer pending (Settings was closed)
- Sidebar: fresh `SettingsItem` built with `has_update=(self._pending is not None)`, so "Settings · Update" appears
- Settings page: not built (not opened); no state to replay
- Next time Settings is opened: full offer state replayed, page shows "Install v0.3.2" + "v0.3.1 → v0.3.2"

### Rebuild while downloading (Settings was open, Appearance changed)
- Sidebar: Settings row updated with fresh `has_update=(self._pending is not None)`, still True
- Settings page: rebuilt; `_build_ui()` tail's two-step replay runs:
  - Step 1: `_offer_update(tag)` restores primary styling + arrow text
  - Step 2: `_update_text` overlay applies "Downloading… 45%", disabled state
  - Final rendered state: "Downloading… 45%", disabled, still ACCENT-coloured underneath (from primary styling)

---

## Testing notes for developer

**States to verify:**

1. Sidebar footer no longer has `update_button` or `version_label` as direct children (only "Add current game", divider, Settings entry)

2. Settings page has "UPDATES" section below "APPEARANCE" with a card containing:
   - "Version" row showing current version in mono font, right-aligned, MUTED
   - Status button showing "Check for updates" initially, enabled

3. Sidebar Settings row shows "Settings · Update" when `_pending is not None` (offer found):
   - Unselected: "Settings · Update" in ACCENT on BG
   - Selected: "Settings · Update" in ACCENT on CARD_HI

4. Every update state (checking, up to date, offer, downloading %, errors) renders correctly when Settings is open

5. Offer signal on sidebar persists even if Settings is closed after an update is found; disappears after restart

6. Rebuild mid-download preserves "Downloading… N%" state, not reset to "Install v{tag}"

7. Error messages truncated to 40 chars, still contain keyword (e.g., "checksum" for checksum errors), and button re-enabled for retry

---

## Key design decisions

1. **Version display as a separate row, not part of the button:** Keeps the button's text focused on actionable status (Check / Checking / Install / Download / Error), while the version label provides context (which versions are involved). Mirrors the current sidebar behavior.

2. **Status colour on version_label, not button:** Errors and offers change the version_label's colour (BAD for errors, ACCENT for offers) while the button text remains readable (no light text on light background). This visual separation helps the user parse "I found a new version" (colour on label) vs. "click this to install" (button text).

3. **No separate error hint below button:** Error messages fit in the truncated 40-character button/label text; a second line below would require dynamic height and add complexity. The 40-char budget is deliberate per spec §2.

4. **Sidebar indicator uses text, not a dot:** Reuses SettingsItem's existing structure (no dot, per 3a's decision) but adds the "· Update" suffix to signal an action is needed without a visual dot.

5. **Indicator persists until install or restart:** Matches `self._pending`'s own lifetime; no separate "seen" flag to keep in sync.

6. **Two-step state replay during rebuild:** When Settings is open and a rebuild occurs mid-flight, replaying `_offer_update()` first (to restore styling) then `_update_text` (to overlay the current progress text) reproduces the exact layering the original widgets built up live — not a guess at the final state.

7. **All reused components:** No new widget classes, no new helpers — every piece is an existing function or a modification to SettingsItem's state/render logic.

---

## Contrast verification (WCAG 2.1, sRGB linearization)

**Deepslate palette:**
- ACCENT on BG (unselected Settings row): 6.8:1 ✓
- ACCENT on CARD_HI (selected Settings row): 5.18:1 ✓
- INK on CARD (Version label): 13.3:1 ✓ (reused from Row)
- MUTED on CARD (Version label): 5.8:1 ✓ (reused from hints)
- INK on CARD (button text): 13.3:1 ✓
- BAD on CARD (error version label): 4.30:1 (marginal, verify in implementation and darken if needed for full AA)

**Quartz palette:**
- ACCENT on BG (unselected Settings row): 5.2:1 ✓
- ACCENT on CARD_HI (selected Settings row): 4.94:1 ✓
- INK on CARD (Version label): 17.4:1 ✓ (reused)
- MUTED on CARD (Version label): 6.2:1 ✓ (reused)
- BAD on CARD (error version label): 4.93:1 ✓

All pairs meet or exceed 4.5:1 (AA text) or 3:1 (AAA graphical). Deepslate BAD on CARD is at 4.30:1; if this marginality is unacceptable in review, darken BAD (#f06262 → #e84242) or use a different color.

---

## Acceptance criteria (from spec)

From `docs/spec.md` §8:
- [ ] Sidebar footer no longer builds `update_button`/`version_label`; only "Add current game", divider, Settings entry remain
- [ ] Settings page has "UPDATES" section/card below Appearance, building the same widgets (`self.update_button`, `self.version_label`) with identical constructor shapes
- [ ] Update state set while Settings is open renders immediately
- [ ] Update state set while Settings is closed is remembered and replayed when Settings is opened
- [ ] Pending offer is signalled on sidebar Settings row ("Settings · Update" or similar, ACCENT colour, no separate dot)
- [ ] Settings row's offer indicator clears on install/restart, persists otherwise
- [ ] All existing `_drain_ui`/`_ui()` contract preserved (only main thread touches widgets, workers call `self._ui()`)
- [ ] All update states (checking, offers, errors, progress, etc.) render identically to today's sidebar when Settings is open
- [ ] Offer signal works even if Settings never opened this session (off-screen offer test)
- [ ] State survives rebuild mid-flight (e.g., Downloading… 45% stays at 45%, not reset to Install offer)
- [ ] Error messages truncated to 40 chars, re-enabled for retry, contain keywords (checksum, etc.)
- [ ] Hotkey card on game pages unchanged
- [ ] README.md updated (no longer claims "Check for updates" is at sidebar bottom)

---

## Summary

**Feature 3b is a pure relocation of two widgets (update_button, version_label) from the sidebar footer into a new Settings page section, plus a sidebar-level offer indicator to notify the user when an update is available even if Settings is never opened.** The update logic remains unchanged; only the UI location and the state-replay mechanism to handle rebuilds change. All components are reused from the existing library; SettingsItem gains one boolean flag for the offer state. The layout is compact and mirrors 3a's own Appearance section pattern.
