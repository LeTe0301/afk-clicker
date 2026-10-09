# Design: Import/export of a game profile (G#60)

## Summary
Two buttons, "Export" and "Import", sit as a side-by-side pair directly under "Add current game" in the sidebar footer (collapsed rail: stacked icon-only "↑" and "↓" under "+"). Success and failure are reported in one sticky status strip under that pair, in the sidebar, styled like the Appearance pane's "Couldn't save settings" notice. No popup, no new screen.

Key deviation from the spec, decided here: the spec's status mechanism (`self.game_state`, `afk_clicker.py:3629`) does not work and is replaced by a sidebar status strip. Reasons, verified in code:
1. `_mark_running()` (`:5046-5060`) rewrites `game_state` every 5 s from `_poll_games()` (`:5022`), so a flash would be overwritten within 5 seconds.
2. `game_state` belongs to the game-page header built only in the non-Settings branch of `_build_ui()` (`:3419-3420`, `:3619-3631`). While Settings is open it is not a live widget, so a `.config()` on it can raise `TclError`. The sidebar, by contrast, is always built and is rebuilt on every `_rebuild_ui()`, so it is always visible.

The spec's Background also says Export/Import failure feedback should use "this existing label"; the spec itself leaves wording and placement to this doc, so this is within scope. The product-manager should be told about the override in the handoff.

## ui-ux-pro-max choices
Note: the `ui-ux-pro-max` skill could not be invoked in this run (no Skill tool available to this agent). The choices below are grounded in the app's own design system (`THEMES`, `Button`, the G#21 save notice, the G#22 sweep band, the G#38 Auto scaling) and in the WCAG arithmetic in section "Accessibility" rather than in the skill's generic palette and style output. If the skill is run later for this feature, its output should be checked against these choices, not used to override them.

- Style: no new style. Existing flat Tk look: `Button` pill (CARD fill, LINE outline, INK label, hover CARD_HI), sidebar on BG.
- Palette: no new colours. Existing tokens only: `CARD` (button and status-strip fill), `INK` (button labels), `OK` (success text), `BAD` (failure text), `LINE` (button outline, unchanged). No new THEMES entry.
- Typography: button labels `fs(9.5, s)` bold, exactly as the Add button. Status text `fs(9, s)` regular, which is the sidebar's secondary size (between the 8 pt section caption and the 9.5 pt save notice).
- Relevant UX guidelines applied:
  - Feedback says what happened, not just "Success". Examples: `Exported "Minecraft"`, `Imported as "Foo (2)"`, `Import failed: not a valid game profile file`.
  - Colour is never the only carrier. The strip text names the outcome; the collapsed rail uses a glyph ("OK" / "!") plus colour.
  - Feedback sits next to the control that caused it (sidebar, under the buttons), not in a modal, which matches the app's non-blocking precedents.
  - Sticky until the next Export/Import attempt, so a failure cannot be missed by a slower glance. No auto-hide timer, which keeps the code smaller and avoids a message vanishing while the user is still reading it.

## Component reuse
- Reused: `Button` (existing, `afk_clicker.py:2067-2112`) for both Export and Import, with the same `width=`, `s`, and default `height=34` as the Add button. Canvas-based, so hover and pointer behaviour come for free.
- Reused: sidebar footer structure (`afk_clicker.py:3386-3398`): the Add button's `pack(pady=(int(12*s), int(4*s)))`, the divider and the Settings entry below stay as they are.
- Reused: the "record on `self`, paint on build" pattern from the G#21 save notice (`self._save_failed`, `_note_save()` `:3970-3980`, `_paint_save_notice()` `:3982-3994`) and from the G#22 sweep hint (`self._sweep_hint_pending`, `:4333-4371`). The status is stored as `self._profile_io_status` and painted from the sidebar build block, so it survives `_rebuild_ui()` (Settings toggle, rail toggle, UI-scale change).
- Reused: `fs()` (`:168`), `SIDEBAR_RAIL_W` (`:278`), `RAIL_COLLAPSE_THRESHOLD` (`:284`), and the `rail_w - 28` width rule from the Add button (`:3388`).
- Reused: `OK`, `BAD`, `CARD`, `INK` and `MUTED` palette globals.
- New, and why nothing existing fits:
  - The two-button row. The Add button is one full-width control, so a row frame holding two `Button`s is the smallest new layout.
  - One sidebar status `tk.Label` with `bg=CARD` (see the Accessibility section for why not `BG`). Nothing existing lives in the sidebar with a message slot, and `game_state` is ruled out above.
  - `tkinter.filedialog` (stdlib). Not a widget to build; no existing file picker exists, so this is the one new stdlib import the spec already planned.

## Layout

### Expanded sidebar (`self._rail_collapsed == False`, `rail_w = SIDEBAR_W = 208`)
Logical px, multiplied by `s` at build time. Footer order top to bottom:

```
 GAMES
 [ Minecraft ]
 [ Global    ]
 [ custom    ]
 ...
 ┌──────────────────────────────┐   Add current game   width 180 (= rail_w - 28)
 │      Add current game        │   pady (12s top, 4s bottom)
 └──────────────────────────────┘
 ┌──────────────┐ ┌──────────────┐  Export | Import     2 x width 87, gap 6 -> 180 total
 │    Export    │ │    Import    │  height 34, pady bottom 4s
 └──────────────┘ └──────────────┘
 ┌──────────────────────────────┐   status strip (ONLY when a status is set)
 │ Exported "Minecraft"         │   bg CARD, width 180, wraps to 2 lines max
 └──────────────────────────────┘
 ────────────────────────────────   divider (unchanged)
 Settings
```

Build rules for the developer:
- Row = `tk.Frame(side, bg=BG)`, packed with `pady=(0, int(4*s))`. Inside: Export `Button(row, "Export", ..., s, width=(rail_w-28-6)//2)` packed left; Import `Button(row, "Import", ..., s, width=(rail_w-28-6)//2)` packed left with `padx=(int(6*s), 0)`. Use `(rail_w-28-6)//2 = 87` in the expanded case.
- Status strip = one `tk.Label(side, bg=CARD, fg=<OK or BAD>, font=("Segoe UI", fs(9, s)), anchor="w", justify="left", wraplength=int((rail_w-28)*s), padx=int(8*s), pady=int(6*s))`. Packed `fill="x"` with `pady=(0, int(6*s))` only when `self._profile_io_status` is not None; otherwise `pack_forget()` (same pattern as `save_failed_label`).
- The status is set and repainted from the sidebar build block, not from its own timer.

### Collapsed rail (`self._rail_collapsed == True`, `rail_w = SIDEBAR_RAIL_W = 64`)
Mirrors how the Add button already collapses to `"+"` (`:3386`). A 36 px wide column of stacked icon-only buttons, since two side-by-side buttons would be about 16 px each:

```
   ┌────┐
   │ +  │   Add current game -> "+"          (unchanged, width 36)
   └────┘
   ┌────┐
   │ ↑  │   Export  -> "↑"   width 36, height 34, pady bottom 4s
   └────┘
   ┌────┐
   │ ↓  │   Import  -> "↓"   width 36, height 34, pady bottom 4s
   └────┘
   ┌────┐
   │ OK │   status: "OK" (OK colour) or "!" (BAD colour), bg CARD, width 36, centred
   └────┘   (only when a status is set; same show/hide rule as expanded)
   ───────   divider
   [Settings]
```

Glyph choices:
- Export "↑" (U+2191), Import "↓" (U+2193). Direction matches the data direction relative to the app: leaving versus entering. Both are in the Segoe UI glyph set (verify on Windows at the first render; if either is missing it renders as a box, so fall back to plain "E" / "I" in that case, not a new icon font).
- Status glyph "OK" (success) and "!" (failure), not a tick mark, because "✓" is not in Segoe UI and would fall back to a different font.
- The rail has no room for the full message. The full text is not available in the rail. Accepted trade-off: the rail is icon-only by design (`SIDEBAR_RAIL_W` comment, `:278-283`), and the user can widen the window to read the message. No tooltip (none exists in the app).

### UI-scale steps
Everything is `int(width * s)` / `fs(base, s)`, the same as the Add button, so no step needs special-casing.

| Step | s | Pair widths (px) | Button label 9.5pt bold | Status wrap width (px) |
|---|---|---|---|---|
| 90 | 0.9 | 78 + 5 + 78 | ok, font floor applies if needed | 162 |
| 100 | 1.0 | 87 + 6 + 87 | ok | 180 |
| 115 | 1.15 | 100 + 7 + 100 | ok | 207 |
| 130 | 1.3 | 113 + 8 + 113 | ok | 234 |
| Auto (G#38) | continuous, clamped to 0.9..1.3 | scales with s | same | same |

Auto mode (`self._auto_scale_factor()`, `:3249`) gives a continuous `s`, and the sidebar is rebuilt on each size change through the existing `_apply_ui_scale()` path. The new widgets need no special handling. The 1.3 wrap width is the widest the strip ever renders.

### Vertical budget (the one real risk)
The footer grows by one button row plus its 4 px gap (about 38 px at 100%, 49 px at 130%) at rest, and by up to about 36 px more (scaled) when the two-line status strip is set. The game list is a `pack(fill="both", expand=True)` frame packed before the footer, so the game list is what gets squeezed. At `WINDOW_MIN_H = 740` with many custom games, the Settings entry at the bottom could be clipped. The developer must check this at 130% with at least 8 games and with the status set, and report the result in `docs/implementation.md`. If it clips, the fix is to drop the 4 px gap and not to hide the buttons.

## States

### Empty
Fresh install, or a user with only Minecraft and Global. The footer shows Add, the Export/Import pair, no status strip, the divider and Settings. Export works on the selected built-in game (`self.current` is always set; there is no disabled state because a game is always selected). Import works with no custom games present.

### Loading
Not applicable. The file dialog is native and synchronous, and the read/write is a few KB of JSON. There is no list being fetched, so the app's skeleton convention (`SkeletonGlassCard` / the skeleton used for data-backed lists) does not apply. The app is Tkinter, not Expo/NativeWind, so the template's GlassCard/NativeWind references do not apply either.

### Populated (idle, no status)
Same as Empty: the pair, no strip. Hover on a button uses `CARD_HI` (existing `Button._colors()`).

### Success (sticky strip, OK colour)
```
 ┌──────────────────────────────┐
 │ Exported "Minecraft"         │   fg OK, bg CARD
 └──────────────────────────────┘
 ┌──────────────────────────────┐
 │ Imported as "Foo (2)"        │   fg OK, bg CARD; the new game is also selected in the list
 └──────────────────────────────┘
```
- The Import success strip is set after `self._select(game_id)`, so it is not overwritten by the selection.
- The name shown is the display name (`candidate` after disambiguation, or `self.by_id[self.current]["name"]` for export). Names are at most 28 characters, so the strip never needs truncation.

### Error (sticky strip, BAD colour)
```
 ┌──────────────────────────────┐
 │ Import failed: not a valid   │   fg BAD, bg CARD, wraps to 2 lines
 │ game profile file            │
 └──────────────────────────────┘
 ┌──────────────────────────────┐
 │ Export failed: couldn't      │   fg BAD, bg CARD
 │ write the file               │
 └──────────────────────────────┘
```
- One import failure message for every rejection path (not JSON, wrong `kind`/`profile_version`, missing `name`/`game`, unreadable file). The user does not need to know which check failed; the file is simply not usable. A split message would add a string table for no user benefit.
- A malformed macro or hotkey inside an otherwise valid file is NOT an error state. Per the spec it is dropped silently and the import succeeds, with the success strip. Nothing in the UI tells the user a macro was dropped; the spec explicitly accepts that partial-survival outcome, and a warning would add a state the spec does not ask for.
- No game is created on any error path, so the list does not change.

### Cancelled
Clicking Export or Import and cancelling the native dialog: no file is touched, no game is created, and the status strip is cleared (set to None and hidden). The spec says "no status is shown", so clearing a previous status is the only way to satisfy that when an older strip is still on screen. This is a deliberate small deviation from "silent no-op": a cancel clears, it does not add a message.

### Interactive / expanded states
- Native file dialog (`asksaveasfilename` / `askopenfilename`) is modal to the app and blocks until closed. No busy or disabled state is shown on the buttons. The dialog is opened from the button's own click, so there is no second click possible during it.
- Settings open: the sidebar is rebuilt around the Settings body, the status strip is repainted from `self._profile_io_status`, and Export/Import still work because they act on `self.current`, which is unchanged by opening Settings.
- Status persistence: the strip stays until the next Export or Import attempt (which replaces it or clears it on cancel). Switching game does not clear it. This is simpler than tying it to `_select()`, which runs during rebuilds and would wipe the message the user just read.
- Rail collapse or expand while a status is set: the strip is rebuilt in the other form (text in expanded, "OK"/"!" in rail), with the same `self._profile_io_status` value.

## Accessibility & platform notes

### Touch / pointer target sizes
- Buttons: 87 x 34 px expanded (100%), 36 x 34 px rail. Matches the existing Add button (180 x 34) and the rail "+" (36 x 34), so there is no new target size in the app. The app is a desktop pointer app, so the 44 px touch guideline does not apply; 34 px is the app's own floor.
- Status strip is not interactive, so it has no target size.
- Known gap, pre-existing: `Button` is a canvas with mouse bindings only and takes no keyboard focus. Export and Import inherit this. Adding keyboard focus to `Button` is a change to a shared widget and is out of scope for G#60; noted for a separate ticket.

### Color contrast (WCAG 2.x relative luminance, computed from the literal THEMES hex values)
Method: linearise each sRGB channel (`c/255`; if `<= 0.04045` then `/12.92`, else `((c+0.055)/1.055)^2.4`), then `L = 0.2126*R + 0.7152*G + 0.0722*B`, then `ratio = (L_lighter + 0.05) / (L_darker + 0.05)`. Text needs 4.5:1 (AA), non-text 3:1. The status is 9 pt regular text, so 4.5:1 applies.

Luminances computed for this doc:

| Colour | Hex | L |
|---|---|---|
| dark BG | #15171a | 0.00847 |
| dark CARD | #1c1f23 | 0.01348 |
| dark INK | #e4e7ea | 0.7960 |
| dark MUTED | #9299a3 | 0.3154 |
| dark BAD | #f06262 | 0.2816 |
| dark OK | #5cc9a4 | 0.4673 |
| light BG | #e8ebf0 | 0.8287 |
| light CARD | #ffffff | 1.0000 |
| light INK | #161a22 | not needed (existing, ~17:1 on white) |
| light MUTED | #596170 | 0.1184 |
| light BAD | #cc3527 | 0.1553 |
| light OK | #0f7f4c | 0.1580 |

Pairings used by this feature:

| Pairing | Use | Ratio | Result |
|---|---|---|---|
| dark INK #e4e7ea on CARD #1c1f23 | button labels | 13.33:1 | PASS AA |
| dark BAD #f06262 on CARD #1c1f23 | failure strip text | 5.22:1 | PASS AA |
| dark OK #5cc9a4 on CARD #1c1f23 | success strip text | 8.15:1 | PASS AA |
| light INK #161a22 on CARD #ffffff | button labels | ~17:1 (existing) | PASS AA |
| light BAD #cc3527 on CARD #ffffff | failure strip text | 5.11:1 | PASS AA |
| light OK #0f7f4c on CARD #ffffff | success strip text | 5.05:1 | PASS AA |

Pairings rejected, computed to show why the strip must be CARD and not BG:

| Pairing | Ratio | Result |
|---|---|---|
| light BAD #cc3527 on BG #e8ebf0 | 4.28:1 | FAIL AA (text) |
| light OK #0f7f4c on BG #e8ebf0 | 4.22:1 | FAIL AA (text) |
| dark BAD #f06262 on BG #15171a | 5.67:1 | PASS, but the strip is on CARD anyway |

Consequence: the status strip uses `bg=CARD`, not `BG`, so the existing `BAD` and `OK` tokens clear 4.5:1 in both themes with no value change. No THEMES value is darkened, so no existing error text (save notice, sweep band, hotkey error) changes colour. Darkening light BAD to #b82d20 would also clear 4.5:1 on BG (computed 5.12:1), but it would change every existing light-theme error text for a problem this feature can avoid, so it was rejected.

Note on prior arithmetic: several existing design docs in `docs/history/` carry luminance values that do not reproduce from the hex (for example MUTED dark L shown as 0.3399 in `ac-22-design.md:311`; this doc gets 0.3154). The ratios used for the pairings above are recomputed here, not copied from those tables. The pass/fail results for the pairings above match the earlier tables (5.76, 5.22, 5.11, 6.23 as checked) so no existing decision changes.

Non-text elements: the button outline is `LINE` (existing), not a new non-text state indicator, so the 3:1 non-text rule does not add a new requirement here. The rail glyphs are text, so 4.5:1 applies, and the same pairs above cover them.

### Web vs. native differences
- Tk desktop only (Windows and Linux, per the `platform` notes in the project). There is no web build for this screen, so no web-only hover or focus styles are needed.
- Hover (`CARD_HI`) is the existing pointer-hover behaviour of `Button`; it is not a touch concept and needs no change.
- File dialogs: `tkinter.filedialog` uses the native Windows dialog on Windows and the Tk/GTK dialog on Linux. The initial directory is `os.path.dirname(config_path())` (per-OS, existing), so no new platform branching in the UI.
- Under Xvfb (tests), `filedialog` must be patched (spec's test plan). No visual test of the rendered strip is possible there; verify rail and expanded visually on Windows.

## Design review pass (Rams)
Applied by hand against the draft (the claude-mem `design-is` skill was not invoked in this run, for the same reason as the Skill tool note above):
- Innovative: no. Kept as the existing button and the existing sticky-notice pattern.
- Useful: the strip says what happened, including the resulting game name, so the user can confirm an import without scanning the list.
- Unobtrusive: a strip, not a dialog; no animation, no timer.
- Honest: failure text names the outcome and the cause class ("not a valid game profile file"), not a generic "error". Success text does not claim anything the code did not do (a malformed macro silently dropped is not reported as success-with-warnings).
- Long-lasting: sticky messages, no timer, no new token; the same pattern as the G#21 notice.
- Thorough to the last detail: rail glyphs, the cancel-clears rule, the 130% vertical budget check, and the Settings-open repaint are all specified above.
- As little design as possible: one row, one strip, two glyph pairs. Nothing else was added.
Folded in from this pass: the rail status uses "OK" / "!" (a glyph plus colour, not colour alone), and the cancel-clears rule (no status shown on cancel).

## Traceability to spec
| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| Export on any selected game writes the envelope with `game` minus `_profile`, macros and hotkey included | Export button in the expanded row and the rail "↑" (Layout); success strip `Exported "<name>"` (States: Success). Export acts on `self.current`, so built-in and custom games are both covered. |
| Export save dialog cancelled: no file written, no status shown | States: Cancelled. The strip is cleared, so no status is visible. |
| Well-formed file imported: new custom game appears in the sidebar, selected, fields/macros/hotkey match | Import button (Layout); success strip `Imported as "<name>"` set after `_select()` (States: Success). |
| Name collision: new game disambiguated, existing game untouched | Success strip shows the disambiguated name `Foo (2)` (States: Success). Disambiguation logic itself is in the spec, not a visual. |
| One malformed macro or hotkey: field dropped, rest imports, no exception | Success state (no warning UI, by decision in States: Error). |
| Not valid JSON, or `kind`/`profile_version` mismatch: refused, no game, failure shown | Error state `Import failed: not a valid game profile file`, BAD on CARD (5.22:1 dark, 5.11:1 light). No game is added, so the list does not change. |
| Import open dialog cancelled: nothing changes | States: Cancelled. |
| Export of Minecraft imported: resulting custom game does not show Eating | Not a visual added by this design; the Eating panel rule is existing behaviour (`_select()` `:4279`). The imported game's success strip is the only new UI on that path. |
| Export write fails: no partial file, failure shown | Error state `Export failed: couldn't write the file`. The atomic write is in the spec. |
| `Store.__init__` sanitize behaviour unchanged after `_sanitize_game_entry()` extraction | No UI impact; not a design item. |
| Edge: built-in profile export allowed | Export is always enabled (there is always a `self.current`); no disabled state. |
| Edge: UI scale 90/100/115/130 and Auto (G#38) | UI-scale table in Layout; vertical budget check. |
| Edge: rail collapsed (`RAIL_COLLAPSE_THRESHOLD`) | Collapsed rail layout and glyphs (Layout). |
| Spec "UI surface": the two buttons sit below "Add current game" in the footer | Layout, expanded and rail diagrams. |
| Spec Background: failure/success feedback via `game_state` | Overridden in Summary and States: `game_state` is clobbered by `_mark_running()` every 5 s (`:5046-5060`) and is not a live widget while Settings is open (`:3419-3420`). The sidebar strip replaces it. |
