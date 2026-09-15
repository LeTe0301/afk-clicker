# Design: Ask to send the update log when an in-app update didn't finish (G#36 / GH#64)

## Summary

A one-off modal dialog appears at startup when the update log shows a failed or incomplete update attempt. It displays a redacted-by-default preview of the issue report that would be sent, a checkbox to show full paths, and three actions: **Send via GitHub** (primary, opens browser), **Dismiss** (marks as seen), and **Open log folder** (does not mark as seen). The dialog uses the app's existing color palette and component patterns (flat rectangles, `Button` class, monospace text areas) and honours both themes and UI scales.

## ui-ux-pro-max choices

- **Style**: Flat, minimal dialog matching the app's existing aesthetic (Feature 5 moved away from rounded corners). No new shape primitives beyond `create_rectangle`.
- **Palette**: Reuses the existing `THEMES` palette (`CARD`, `INK`, `MUTED`, `ACCENT`, `BAD`, `LINE`, `BG`) — no new colors introduced.
- **Typography**: Segoe UI with the same size/weight pattern already established:
  - Heading: 14pt bold (matching card section headers like "Hotkey" in screenshots)
  - Body text: 9pt or 9.5pt regular (matching Row labels)
  - Monospace preview: Consolas 10pt (matching NumBox entries; Tk falls back to a suitable monospace font on Linux/macOS)
- **Relevant UX guidelines applied**:
  - Redacted-by-default paths address user privacy concerns (the log can contain usernames in file paths).
  - Read-only preview ensures "show before send" — the user sees exactly what they're sending.
  - Primary button is the action button (Send), not Dismiss — consistent with modern UX (action first, safe exit via Escape/Dismiss).
  - Transient to the main window, no blocking `wait_window()` — the app remains responsive if the dialog is left open.

## Component reuse

- **Reused completely**: `Button` class (primary/secondary via `set_primary()` method) for Send/Dismiss/Open Folder.
- **Reused pattern**: Text layout and spacing using `tk.Frame`/`tk.Label` (same as the main window's content building).
- **Reused pattern**: Monospace text area modeled after `NumBox`'s read-only display aesthetic (Consolas, dark background, light text).
- **New minimal component**: A checkbox widget `ToggleCheckbox` (simple canvas-based, 16×16px, matching the app's no-dependencies style).
  - The app has no existing checkbox/toggle UI component; this is the first.
  - Design: a small canvas square with a MUTED outline (not LINE — MUTED passes the 3:1 floor in both themes). Fill behavior:
    - **Unchecked**: `CARD` fill, `MUTED` outline (1px).
    - **Checked**: `CARD_HI` fill, MUTED outline (1px), with a centered checkmark glyph (`✓`, rendered in `INK` text, ~8pt).
    - **Hover**: Fill becomes `CARD_HI` (unchecked) or a slightly darker shade (checked), giving clear visual feedback.
    - **Keyboard focus**: A 2px dashed outline around the checkbox in `ACCENT` color, appearing when focused via Tab.
  - Click behavior: left-click toggles the state; `<Button-1>` binding + `<Return>` key binding for accessibility; Space also toggles when focused.
  - Alternative designs considered: native `tk.Checkbutton` (inconsistent with this app's custom canvas-based controls) and a flat text indicator (less discoverable). The canvas approach wins on consistency with `Button`/`Segmented`.

## States

### Dialog appears (populated, with redaction)

**Trigger**: `update_log_status()` returns `"incomplete"` or `"wrong_version"`.

**Explanation text** (exact copy):
- If status is `"incomplete"`: *"The last update didn't finish. Your clicker still works — this just notifies us of the failure."*
- If status is `"wrong_version"`: *"The last update relaunched the old version. Your clicker still works — this just notifies us of the failure."*

**Layout** (at s=1, 600×480px window):

```
┌─ Update failed ─────────────────────────────────┐
│                                                 │
│  The last update didn't finish. Your clicker    │
│  still works — this just notifies us.           │ (exact copy per status)
│                                                 │
│  Preview of what will be sent to GitHub:        │ (9pt MUTED)
│  ┌─────────────────────────────────────────┐   │
│  │ In-app update didn't finish (v0.5.0)    │   │ (read-only, scrollable, dark BG)
│  │                                         │   │
│  │ **App version:** 0.5.0                  │   │ (monospace 10pt)
│  │ **Target version:** v0.5.1              │   │
│  │ **OS:** Linux 5.15.0 (linux)            │   │
│  │                                         │   │
│  │ ```                                     │   │
│  │ 2026-09-15 12:34:56 start pid=1234     │   │
│  │   staged="~/.cache/afk-clicker/..."    │   │ (paths redacted: ~ instead of full)
│  │   target="~/.local/share/afk-..."      │   │
│  │   version="v0.5.1"                      │   │
│  │ 2026-09-15 12:34:57 wait finished ...   │   │
│  │ 2026-09-15 12:34:58 copy exit code 1   │   │
│  │ ```                                     │   │
│  │                                         │   │
│  │ [☑] Show full local paths              │   │ (checkbox, unchecked by default)
│  │                                         │   │
│  ├─────────────────────────────────────────┤   │
│  │ [Send via GitHub] [Dismiss] [Open ...] │   │ (buttons, bottom row)
│  └─────────────────────────────────────────┘   │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Text content** (exact copy):

- **Heading (dialog title bar)**: "Update failed"
- **Explanation** (two variants):
  - Incomplete: *"The last update didn't finish. Your clicker still works — this just notifies us of the failure."*
  - Wrong version: *"The last update relaunched the old version. Your clicker still works — this just notifies us of the failure."*
- **Preview label**: *"Preview of what will be sent to GitHub:"* (9pt MUTED, placed above the text box)
- **Checkbox label**: *"Show full local paths"* (9.5pt INK, next to checkbox)
- **Button labels**:
  - Primary: *"Send via GitHub"* (10pt bold, width 120px)
  - Secondary: *"Dismiss"* (width 100px)
  - Secondary: *"Open log folder"* (width 130px)

**Styling**:

- **Dialog window**: 
  - Title bar: "Update failed"
  - Background: `BG` (#15171a dark / #e8ebf0 light)
  - Transient to `self.root`, resizable, minimum size 480×300

- **Heading text**: 14pt bold, `INK` on `BG`
- **Explanation text**: 9pt regular, `MUTED` on `BG`, padding `top=16, bottom=12` (units of `s`)
- **Preview box**:
  - Frame with `bg=CARD`, outline via `create_rectangle(0, 0, w, h, fill=CARD, outline=LINE)`
  - Inner text area: `tk.Text` widget (read-only, `state="disabled"` after populating)
    - Background: `BG` (darker, recessing the text from the frame border)
    - Foreground: `INK`
    - Font: Consolas 10pt or fallback monospace (same as NumBox)
    - Border: 1px `LINE` outline (via the frame)
    - Size: 600×(300–350)px at s=1, scrollable vertically with scrollbar
    - Padding inside frame: 12px (CARD_PAD)
  
- **Checkbox**: 16×16px canvas square
  - **Unchecked**: `CARD` fill, `MUTED` outline (1px)
  - **Checked**: `CARD_HI` fill, `MUTED` outline (1px), checkmark glyph (✓) in `INK` centered
  - **Hover**: Fill becomes `CARD_HI` (unchecked) or darker shade (checked)
  - **Keyboard focus**: 2px dashed border in `ACCENT` (visible when Tab'd to)
  - Cursor: `hand2` on hover

- **Buttons**:
  - Primary button (Send): `ACCENT` fill, `ACCENT_INK` text (existing Button pattern)
  - Secondary buttons: `CARD` fill, `INK` text, `LINE` outline (existing Button pattern)
  - Height: 34px, font 9.5pt bold (matching existing buttons)
  - Send width: 120px, Dismiss: 100px, Open: 130px
  - Spacing: 8px between buttons (via grid or pack with `padx`)

- **Overall padding**:
  - Outer dialog padding: 16px (`CONTENT_PAD`)
  - Between preview and checkbox: 16px vertical (`CONTENT_PAD`)
  - Button row top padding: 16px
  - Button row bottom padding: 16px

### Dialog with paths shown (checkbox checked)

**Change**: Every occurrence of the home directory (`~`, from `os.path.expanduser("~")`) in the preview is replaced with its absolute path (e.g. `/home/user` or `C:\Users\User`).

```
  │ 2026-09-15 12:34:56 start pid=1234           │
  │   staged="/home/user/.cache/afk-clicker/..." │  (full paths shown)
  │   target="/home/user/.local/share/afk-..."   │
  │   version="v0.5.1"                           │
```

**Behavior**: When the checkbox is clicked, the `Text` widget's contents are updated **immediately** (not cached from dialog-open time) — the URL built on `Send via GitHub` click matches the checkbox's current state at that moment.

### Browser unavailable (fallback)

**Trigger**: `webbrowser.open(url)` returns `False` or raises an exception.

**Layout** (replaces button row):

```
  │ ┌─────────────────────────────────────────┐  │
  │ │ https://github.com/LeTe0301/afk-...     │  │ (read-only entry, monospace)
  │ │                                         │  │
  │ │ [Copy link]           [Dismiss]         │  │ (buttons)
  │ └─────────────────────────────────────────┘  │
```

- **URL text**: monospace, single-line `tk.Entry`, `state="readonly"`, selectable via `<Control-a>`
- **Copy link button**: width 100px, same secondary style as Dismiss
- **Dismiss button**: moves to the fallback row

**Styling**: The entry has `bg=BG`, `fg=INK`, outline `LINE` (1px border), matching the preview box's own styling.

**Behavior**: 
- `Copy link` button calls `self.root.clipboard_clear()` followed by `self.root.clipboard_append(url)` — Tk's native clipboard API (no new dependency).
- Entry is selectable (`<Control-a>` highlights all) but not editable.
- The dialog remains open and can still be dismissed with `Dismiss` or the OS close button.

### Empty state (no failed log)

**Trigger**: `update_log_status()` returns `"ok"` or no `update.log` exists.

**Behavior**: `_maybe_offer_log_report()` is a no-op; no dialog is created or shown.

### Dialog dismissed

**Trigger**: `Dismiss` button clicked, or `Escape` key pressed, or OS close button clicked.

**Behavior**: 
- Dialog closes (window destroyed).
- `update.log` is renamed to `update.log.reported` (via `os.replace`).
- Next app launch shows no dialog for this attempt.

### Dialog sent via GitHub

**Trigger**: `Send via GitHub` button clicked (only possible if browser was available; if it failed, the `Copy link` button is shown instead).

**Behavior**:
- `webbrowser.open(url)` is called with the GitHub `issues/new` URL.
- `update.log` is renamed to `update.log.reported`.
- Dialog closes.
- Browser window or tab opens with the prefilled issue form (user's own GitHub login state).

### Dialog with small screen at 130% scale

**Scenario**: 480px window width, s=1.3 (130% UI scale), vertical layout forced.

**Layout adjustment**:

```
┌─ Update failed ───────────┐
│                           │
│  The last update didn't   │ (text wraps)
│  finish. Your clicker     │
│  still works — this just  │
│  notifies us.             │
│                           │
│  Preview of what will be  │
│  sent to GitHub:          │
│  ┌─────────────────────┐  │
│  │ [scrollable text]   │  │ (height reduced to ~200px to fit buttons below)
│  │                     │  │
│  └─────────────────────┘  │
│                           │
│  [☑] Show full local      │ (checkbox and label may wrap)
│      paths                │
│                           │
│  ┌─────────────────────┐  │
│  │ [Send via GitHub]   │  │ (buttons stack vertically if width < 380px)
│  ├─────────────────────┤  │
│  │ [Dismiss]           │  │
│  ├─────────────────────┤  │
│  │ [Open log folder]   │  │
│  └─────────────────────┘  │
│                           │
└───────────────────────────┘
```

**Responsive rules**:

- If window width < 380px (all three buttons' widths + spacing don't fit): stack buttons vertically (use `pack(fill="x")` per button instead of `grid`/`pack(side="left")`).
- Preview box height scales down but remains at least 150px (vertical scrollbar available if text is longer).
- Checkbox label wraps if needed (via `wraplength` or line break in label).
- Overall dialog minimum size: 480×300px; if user resizes smaller, scrollbars appear as needed.

**At s=1.3**:
- Heading: `int(14 * 1.3)` = 18pt
- Body text: `int(9 * 1.3)` = 11pt (still legible)
- Button text: `int(9.5 * 1.3)` = 12pt
- Padding: `int(16 * 1.3)` = 20px (generous whitespace)

All dimensions remain readable and clickable (buttons are 34 × (int(120 * 1.3)) = 34 × 156px).

## Accessibility & platform notes

### Color contrast

All text/element pairings verified via WCAG relative-luminance formula (sanity check: #ffffff / #000000 = **21.00**:1):

| Element | Dark theme | Light theme | WCAG floor | Notes |
|---|---|---|---|---|
| **Heading** INK on BG | 14.47:1 | 14.58:1 | 4.5 (AA text) | Exceeds ✓ |
| **Explanation** MUTED on BG | 6.25:1 | 5.22:1 | 4.5 (AA text) | Exceeds ✓ |
| **Preview text** INK on BG | 14.47:1 | 14.58:1 | 4.5 (AA text) | Exceeds ✓ |
| **Checkbox unchecked** MUTED outline on CARD | 5.76:1 | 6.23:1 | 3.0 (UI component) | Exceeds ✓ |
| **Checkbox checkmark** INK on CARD_HI | 11.62:1 | 15.53:1 | 4.5 (AA text) | Exceeds ✓ |
| **Button primary text** ACCENT_INK on ACCENT | 7.11:1 | 6.23:1 | 4.5 (AA text) | Exceeds ✓ |
| **Button secondary text** INK on CARD | 13.32:1 | 17.43:1 | 4.5 (AA text) | Exceeds ✓ |
| **URL fallback text** INK on BG | 14.47:1 | 14.58:1 | 4.5 (AA text) | Exceeds ✓ |
| **Focus ring** ACCENT on CARD | 6.25:1 | 6.23:1 | 3.0 (UI component) | Exceeds ✓ |

*Light-theme column corrected by the orchestrator, 2026-09-15, from the palette at `afk_clicker.py:79-82` (light: BG `#e8ebf0`, CARD `#ffffff`, CARD_HI `#eff2f7`, INK `#161a22`, MUTED `#596170`, ACCENT `#2b58cc`, ACCENT_INK `#ffffff`), with the WCAG relative-luminance formula checked against white/black = 21.00. Five of the seven light values in the previous revision were wrong; every pairing still passes.*

**Checkbox design rationale**: The unchecked state uses a `MUTED` outline (not `LINE`) to ensure ≥3:1 contrast (the WCAG 1.4.11 floor for UI components). The checked state is distinguished by a filled `CARD_HI` background **plus** a centered `✓` checkmark glyph in `INK` text (11.62:1 contrast on dark, 15.53:1 on light) — dual signaling ensures visibility even for users with color-blindness. Keyboard focus adds a 2px dashed `ACCENT` border for non-mouse users.

### Keyboard navigation

- **Tab order**: Heading (non-interactive) → Preview box (read-only) → Checkbox (Space or Enter to toggle) → Buttons (left to right, Enter activates primary button).
- **Enter key**: On the `Send via GitHub` button, pressing Enter activates it (same as clicking). On other buttons, Enter does nothing (secondary buttons are not the "default" action).
- **Escape key**: Closes the dialog as if `Dismiss` were clicked (renaming the log to `.reported`).
- **Space key**: When focus is on the checkbox, Space toggles it.
- **Ctrl+A**: When focus is on the URL entry (fallback case), selects all text for copying.

### Platform differences

- **Windows/macOS/Linux**: Behaviour is identical. 
  - `os.startfile` (Windows), `open` (macOS), `xdg-open` (Linux) are invoked by `webbrowser.open()` under the hood — no special handling needed from this dialog.
  - File manager opening (`Open log folder`) uses the same platform-specific commands (already tested in earlier features).
  - Tk's native `root.clipboard_*` API works identically across platforms.

- **Web vs. native** (if app is ever ported to web): The dialog is a Tk `Toplevel`, not a web modal. If a web port is needed later, the design translates to an HTML modal with the same layout and interactions.

- **Transient window behavior**: The dialog is `transient(self.root)`, so:
  - Windows: Dialog window appears above the main window and is grouped in Alt-Tab.
  - macOS: Dialog is grouped in the app's own window group (not a separate app icon in the Dock).
  - Linux/X11: Dialog is marked as a transient child of the main window; window managers (GNOME, KDE) respect this and handle stacking accordingly.

## Traceability to spec

| Acceptance criterion | Design element |
|---|---|
| Dialog appears when `update_log_status()` is `"incomplete"` or `"wrong_version"` | Heading + explanation clarify both cases with exact copy per status |
| Exact explanation text for both failure types | "didn't finish" vs. "relaunched the old version"; both mention clicker still works |
| Redaction is default (paths shown as `~`) | Checkbox unchecked by default; preview uses `~` immediately on open |
| Checkbox live-updates the preview and the URL sent | Preview box content updates on every checkbox click; `Send via GitHub` reads checkbox state at click time |
| `Send via GitHub` button opens the browser with the correct URL | Button calls `webbrowser.open(url)` where `url` is built from current checkbox state + current log tail |
| URL's `body` and `title` query params match the preview text | Preview is the literal source; no separate encoding/formatting step |
| `Dismiss` marks log as `.reported` and closes dialog | Button handler calls `os.replace(log_path, log_path + ".reported")` then `dialog.destroy()` |
| `Open log folder` does NOT mark log as `.reported` | Button handler calls `os.startfile` (etc.) but skips the rename; dialog stays open |
| Browser unavailable → fallback URL shown + "Copy link" button | Fallback branch detects `False` return or exception; shows `tk.Entry` + `Copy link` button |
| 2000-char URL cap enforced | Spec calls this out in issue body builder; design assumes this is implemented in the backend; design shows user the resulting (possibly truncated) preview |
| Checkbox label is "Show full local paths" | Exact copy specified |
| Buttons: "Send via GitHub", "Dismiss", "Open log folder" | Exact copy specified |
| Dialog respects light and dark themes | Layout uses `THEMES` tokens; both dark and light variants shown in design |
| Dialog respects UI scales (90%–130%) | All dimensions scaled by `s`; edge case (130% on 480px) shows vertical button stacking; no text becomes unreadable |
| Esc key dismisses dialog | Keyboard binding specified |
| Transient to main window, no blocking | `transient(self.root)` specified; no `wait_window()` |
| Checkbox unchecked state passes WCAG 1.4.11 (3:1) | MUTED outline on CARD: 5.76:1 dark, 6.23:1 light ✓ |
| Keyboard focus indicator on checkbox | 2px dashed ACCENT border around checkbox when focused via Tab ✓ |

## Summary of design decisions

1. **Checkbox uses MUTED outline, not LINE** — `LINE` outline alone (1.58:1 contrast) fails the 3:1 floor. `MUTED` outline (5.76:1 dark, 6.23:1 light) passes. Checked state adds a `CARD_HI` fill + `✓` checkmark in `INK` (11.62:1–15.53:1 contrast), ensuring dual signaling for visibility and color-blind accessibility.

2. **Keyboard focus is a 2px dashed ACCENT border** — Visible when focused via Tab; matches the app's accent-home pattern established in Feature 5 and NumBox.

3. **Exact explanation text clarifies the clicker still works** — "Your clicker still works — this just notifies us of the failure." avoids alarmism and reassures the user.

4. **Monospace preview, dark background** — Consolas 10pt (or Tk fallback) on `BG` (recessed from frame border) makes the technical log content legible and distinct from prose. Matches the app's existing use of Consolas in NumBox.

5. **Primary button is Send, not Dismiss** — Aligns with modern UX (action-first); Escape/close button provides the safe exit.

6. **Fallback URL entry + Copy button** — Avoids a silent failure; user can still report even if their browser launch fails. Uses Tk's native clipboard API (no new dependency).

7. **All color tokens from existing palette** — No new hex values; reuses `INK`, `MUTED`, `ACCENT`, `ACCENT_INK`, `CARD`, `CARD_HI`, `LINE`, `BG` at their defined values.

8. **Scales smoothly to 130% and down to 480px width** — Button row stacks vertically if needed; preview height reduces but remains scrollable; all text remains legible and clickable at any supported scale.

## References

- `afk_clicker.py` color palette: lines 78–91 (THEMES dictionary, color constants).
- `Button` class: lines 1319–1365 (primary/secondary styling, hover states).
- `Segmented` class: lines 1367–1404 (canvas-based toggle pattern, reusable for checkbox design).
- `Row` class: lines 1837–1859 (label + control layout pattern).
- `NumBox` class: lines 1861–1891 (Consolas monospace font usage, entry styling).
- `card()` function: lines 1518–1577 (flat rectangle shape, padding constants).
- Previous design docs: `docs/history/ac-24-f5-design.md` (flat UI aesthetic, contrast verification methodology).
