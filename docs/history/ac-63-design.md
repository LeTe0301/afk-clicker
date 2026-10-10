# Design: Confirm before deleting a custom game profile or macro

Ticket: G#63 / GH#111. Spec: `docs/spec.md`.

## Summary
A single themed, non-blocking `tk.Toplevel` confirm dialog (same shape as `_show_update_log_dialog`, `afk_clicker.py:4981`) that names the item being deleted, with a neutral **Cancel** (safe default, Escape, Return, close box) and a red **Delete** that is the only path to the existing `_delete_game` / `_delete_macro`. Key decisions: one shared helper, a single open-slot so stacked dialogs can't pile up, and a re-validation step on confirm because the dialog is non-blocking.

## Platform reality (verified in code)
- The app is Tkinter/Canvas only (`afk_clicker.py`, no web or React Native target). The glassmorphism components named in the brief (`GradientBackground`, `GlassCard`, `SkeletonGlassCard`) do not exist in this codebase; the design system here is the module-level theme tokens plus the `Button` canvas helper.
- No `messagebox`/`askyesno` anywhere. Every dialog is a hand-painted Toplevel.
- Active theme is dark only: `_ACTIVE = THEMES["dark"]` (`afk_clicker.py:90`). Values used below:
  - `BG #15171a`, `CARD #1c1f23`, `CARD_HI #262a30`, `LINE #3a4048`
  - `INK #e4e7ea`, `MUTED #9299a3`, `ACCENT #e08a55`, `ACCENT_INK #1a0f08`
  - `BAD #f06262` (already used for the sidebar delete glyph hover, `afk_clicker.py:2633`)

## ui-ux-pro-max choices
- The search script needs Bash, which this agent does not have, so I grounded the choices in the skill's own priority table (`SKILL.md`, "Rule Categories by Priority") rather than running `--design-system`. Accessibility (4.5:1 text, keyboard reachability, no icon-only buttons), Forms & Feedback (explicit labels, no placeholder-only meaning), and "no emoji as icons" were the rules applied.
- Style: the app's existing flat dark theme. No new style, no new icon, no gradient.
- Palette: no new color. Destructive emphasis reuses the existing `BAD` token as a button fill. Its label uses `ACCENT_INK`, the same on-strong-fill ink `primary` buttons already use.
- Typography: `Segoe UI` only, same sizes as the update-log dialog (heading `fs(14, s)` bold, body `fs(9.5, s)`).
- UX guidelines applied: destructive action is never the default or the Return target; the consequence is named in copy; no hover-only meaning (the word "Delete" carries the meaning, red is reinforcement); the action is never instant; dismiss paths are equal to cancel.

## Component reuse
- Reused: `Button` (`afk_clicker.py:2148`) for both buttons. One additive kwarg is needed (see "Button change" below).
- Reused: `fs()` (`:169`), `CONTENT_PAD` (`:250`), theme tokens `BG`/`INK`/`MUTED` (`:91`), `BAD`/`ACCENT_INK` (`:94`), `_lighten()` (`:55`).
- Reused pattern: `top = tk.Toplevel(self.root, bg=BG)`, `top.title(...)`, `top.transient(self.root)`, `top.protocol("WM_DELETE_WINDOW", ...)`, `top.bind("<Escape>", ...)`, `_rebuild_ui()` closing the open dialog before teardown (same as `_close_log_dialog`, `:5130`).
- New: one helper `_open_confirm_dialog(self, title, heading, body, on_confirm)` (one place, both call sites), and two small call-site wrappers (`_confirm_delete_game`, `_confirm_delete_macro`). Nothing else new.

### Button change (the only shared-code edit)
Add `danger=False` next to `primary=False` in `Button.__init__` (`afk_clicker.py:2151`), and in `_colors` (`:2167`) add a branch before the `primary` branch: when `danger` and enabled, return fill and outline `BAD`, ink `ACCENT_INK`, and on hover `_lighten(BAD, 0.18)` (= `#f27e7e`, computed from the same helper `_theme` uses for `ACCENT_HI`). Default path (`danger=False`) is byte-for-byte unchanged, so every existing `Button` keeps its look.

## Modal layout and copy

Window title bar text: `Delete game` (profile) / `Delete macro` (macro).

Profile (base size 400 wide; height fits content):

```
+----------------------------------------------------+
| Delete game                                    [x] |  <- OS title bar
|                                                    |
|  Delete "Speedrun Quest"?                          |  INK, 14 bold
|                                                    |  8px gap
|  This removes its settings, macros, and hotkey.    |  MUTED, 9.5
|  It can't be undone.                               |
|                                                    |  16px gap
|                        [  Cancel  ]  [  Delete  ]  |  right-aligned row
|                                                    |
+----------------------------------------------------+
```

Macro:

```
+----------------------------------------------------+
| Delete macro                                   [x] |
|                                                    |
|  Delete macro "Auto-sell loop"?                    |
|                                                    |
|  This removes its steps and hotkey.                |
|  It can't be undone.                               |
|                                                    |
|                        [  Cancel  ]  [  Delete  ]  |
+----------------------------------------------------+
```

Copy rules:
- The name is inserted verbatim inside straight double quotes, so the user sees exactly which item. If the name is longer than 40 characters, show the first 39 plus `…`. If it is empty, use `Delete this game?` / `Delete this macro?`.
- Body copy deviates from the spec's draft in one place, deliberately: the macro line says "steps and hotkey", not "all its steps". The hotkey is also removed (the macro row and its hotkey arming both go away), and the spec's honesty goal (design-is principle 6) requires the copy to state everything that is lost. "It can't be undone." is true (non-goal: no undo) and is included so no one assumes a trash.
- Body line wraps at `int(368 * s)`; heading and body both use `wraplength=int(368 * s)`, so width stays bounded for long names.

Buttons (both `width=100`, `height=34`, scaled by `s`):
- **Cancel** (left, neutral): `Button(..., "Cancel", ..., width=100)`. Fill `CARD`, outline `LINE`, label `INK`. Hover `CARD_HI`.
- **Delete** (right, destructive): `Button(..., "Delete", ..., danger=True, width=100)`. Fill and outline `BAD`, label `ACCENT_INK`. Hover `#f27e7e`.
- Gap between buttons: `int(8 * s)`. Row packed `side="right"` so Cancel sits left of Delete (Windows convention: safe on the left, destructive on the right).
- Outer padding `int(CONTENT_PAD * s)` on all four sides, matching the update-log dialog's `body` frame.

## Sizing
- Width: content-driven, bounded by the 368 * s wraplength (about 400 * s with padding). Do not set a fixed size.
- Height: content-driven. Do NOT call `top.geometry("WxH")`. The update-log dialog's own comment (`afk_clicker.py:5084-5096`) records that an explicit size switches Tk to fixed size and clips rows. If the dialog must be centered over the main window, set position only (`top.geometry(f"+{x}+{y}")`) and verify on Windows that the size stays auto. If it does not, use the `_fit_log_dialog_to_content` pattern.
- `top.resizable(False, False)`. No minsize.
- Center over `self.root` after `update_idletasks()` (`root.winfo_rootx()/winfo_rooty()` plus half the root size minus half the dialog's `winfo_reqwidth()/reqheight()`).
- Touch targets: N/A (desktop pointer app). Buttons are 100 x 34 base px, the same size as the existing "Dismiss" button (`afk_clicker.py:5064`).

## Triggers

Profile (sidebar delete glyph):
1. `GameItem` glyph click (`afk_clicker.py:2636-2637`) still calls `on_delete(profile_id)` and returns `"break"`, so the row's select handler (`:2640`) does not fire. Unchanged.
2. `_rebuild_list()` (`:4403-4404`) passes `on_delete=self._confirm_delete_game` instead of `self._delete_game`.
3. `_confirm_delete_game(game_id)`: look up `self.by_id.get(game_id)`. If missing or not `custom`, return without opening anything. Otherwise `_open_confirm_dialog(title="Delete game", heading=<name>, body="This removes its settings, macros, and hotkey. It can't be undone.", on_confirm=<closure>)`. The closure calls `self._delete_game(game_id)`.

Macro (row Delete button, `afk_clicker.py:5718-5719`):
1. `Button(row, "Delete", lambda m=macro: self._confirm_delete_macro(m), s, width=70)`. Layout (width 70) is unchanged.
2. `_confirm_delete_macro(macro)`: capture `game_id = self.current` at open time. Open the dialog with title `Delete macro`, heading from `macro["name"]`, body "This removes its steps and hotkey. It can't be undone." The closure calls `self._delete_macro(macro)` only after the re-check below.

Important: `_delete_macro` works on `self.current` (`afk_clicker.py:5734`), not on the game the macro belongs to. Because the dialog is non-blocking, the user can switch games while it is open, so the closure must re-check.

## Confirm / cancel / Escape / close behavior

Single open slot: `self._confirm_dialog` holds the open Toplevel or `None`. Opening a new confirm first destroys any existing one. This stops a double-click on the glyph (or the row's Delete) from stacking two dialogs. Destroy uses the same try/except `TclError` pattern as `_close_log_dialog` (`:5148-5152`).

Confirm (Delete button):
1. Destroy the dialog first, then run the closure. A failure in the delete never leaves the dialog up.
2. Profile closure: if `game_id` is no longer in `self.by_id` or no longer `custom`, do nothing (no error UI). Else `self._delete_game(game_id)`. The rest of `_delete_game` (fallback to `"global"`, `_rebuild_list`, `_select`) is untouched.
3. Macro closure: if `self.current != game_id`, or no macro with `macro["id"]` exists in `self.store.game(game_id).get("macros", [])`, do nothing. Else `self._delete_macro(macro)` (unchanged, re-arms hotkeys/intervals and refreshes the pane).

Cancel, Escape, Return, and close box (`WM_DELETE_WINDOW`) all do the same thing: destroy the dialog and nothing else. No state, no save, no re-arm.
- Cancel button: `command` destroys the dialog.
- `top.bind("<Escape>", ...)` destroys the dialog.
- `top.bind("<Return>", ...)` destroys the dialog. Return is the safe default, so a reflexive Enter never deletes. This intentionally differs from the update-log dialog, where Return sends. Delete is never bound to a key.
- `top.protocol("WM_DELETE_WINDOW", ...)` destroys the dialog.

Keyboard focus: the Canvas `Button` helper cannot take keyboard focus (no tab stop, no focus ring), so Escape and Return work only if the Toplevel has focus. After building, call `top.focus_force()` (or `focus_set()`). Pre-existing helper gap, not changed here.

Rebuild: `_rebuild_ui()` must close the confirm dialog before teardown, the same way it closes the log dialog (`_close_log_dialog` precedent). Otherwise a UI-scale rebuild leaves an orphan dialog whose closure still points at the old game or macro.

Re-entry: the Delete click destroys the dialog before the closure runs, so a second rapid click has no dialog to hit. A second click on the sidebar glyph or a Delete button after that opens a new confirm; it cannot delete anything.

## States

| State | What the user sees |
|---|---|
| Closed (default) | Sidebar glyph `✕` in `MUTED` (existing, `:2631`) or macro row "Delete" (existing). Nothing else. |
| Glyph / Delete hover | Existing behavior: glyph turns `BAD` (`:2633`). Button uses `Button`'s existing hover (`CARD_HI`). |
| Confirm dialog open | Single state: heading naming the item, body, Cancel + Delete. The main window stays visible behind it. |
| Delete hover | Delete fill lightens to `#f27e7e`. |
| Cancel hover | `CARD_HI`, same as every other neutral `Button`. |
| Long name | Heading truncated at 39 chars + `…`; body wraps at `368 * s`. |
| Empty name | Fallback heading `Delete this game?` / `Delete this macro?`. |
| Target gone or changed while open | Confirm closes the dialog silently and deletes nothing (stale-target guard). |
| Loading / empty / error | N/A. The dialog is synchronous and has no data fetch. The project's skeleton convention (`SkeletonGlassCard`) does not exist here and would not apply to a two-line confirm. The only failure path (stale target) closes silently, not with an error. |

Disabled state: none needed. The Delete button is never disabled; the stale-target guard covers the only reason it would be.

## Styling tokens (dark theme, active)

| Element | Token / value |
|---|---|
| Toplevel and body background | `BG` `#15171a` |
| Heading | `INK` `#e4e7ea`, `Segoe UI` 14 bold |
| Body | `MUTED` `#9299a3`, `Segoe UI` 9.5 |
| Cancel fill / outline / label | `CARD` `#1c1f23` / `LINE` `#3a4048` / `INK` |
| Cancel hover | `CARD_HI` `#262a30` |
| Delete fill / outline | `BAD` `#f06262` |
| Delete label | `ACCENT_INK` `#1a0f08` |
| Delete hover | `_lighten(BAD, 0.18)` = `#f27e7e` |

Light theme (`THEMES["light"]`, not active): would also work through the same tokens. Delete label `ACCENT_INK` is `#ffffff` there, on `BAD #cc3527`, measured 5.11:1 (see below).

## Contrast (WCAG 2.x relative luminance, computed from the literal hex values)

Relative luminance L: `#15171a` (BG) 0.00826; `#1c1f23` (CARD) 0.01348; `#262a30` (CARD_HI) 0.02277; `#3a4048` (LINE) 0.05030; `#e4e7ea` (INK) 0.79595; `#9299a3` (MUTED) 0.31553; `#f06262` (BAD) 0.28142; `#f27e7e` (BAD hover) 0.35307; `#1a0f08` (ACCENT_INK) 0.00578; `#cc3527` (light BAD) 0.15531.

| Pairing | Use | Ratio | Result |
|---|---|---|---|
| INK on BG | Heading | 14.52:1 | AA text pass (4.5) |
| INK on CARD | Cancel label | 13.33:1 | AA pass |
| MUTED on BG | Body text | 6.27:1 | AA pass |
| MUTED on CARD | Body text, if rendered on a card | 5.76:1 | AA pass |
| ACCENT_INK on BAD | Delete label, rest | 5.94:1 | AA pass |
| ACCENT_INK on `#f27e7e` | Delete label, hover | 7.22:1 | AA pass |
| White on light BAD `#cc3527` | Light theme only | 5.11:1 | AA pass |
| BAD on BG | Glyph hover (existing) | 5.69:1 | AA pass |
| LINE on CARD | Cancel outline (non-text) | 1.58:1 | Below 3:1 |
| BAD on CARD | Delete outline (non-text) | 5.22:1 | Pass |

Note on the Cancel outline: `LINE` on `CARD` is 1.58:1, below the 3:1 non-text guideline if the outline were the only boundary. This is the same `LINE` outline every existing `Button` uses (update-log dialog, macro editor). Changing `LINE` would restyle the whole app, which is out of scope. The Cancel label is text and identifies the control on its own, and the Delete button's fill is 5.22:1 against the dialog. Flagged as a pre-existing app-wide gap, not fixed here.

Nothing here required darkening or lightening a token to clear 4.5:1, so no palette values were changed.

## Accessibility and platform notes
- Touch target: desktop pointer app; buttons match the existing 100 x 34 dialog buttons. The 44 px touch rule is not applicable.
- Color: the word "Delete" and the heading naming the item carry the meaning; red is reinforcement only.
- Keyboard: Escape and Return cancel, close box cancels. There is no keyboard path to Delete (intentional, safer). Canvas buttons have no tab focus; pre-existing `Button` gap.
- Focus: `top.focus_force()` after build. No-WM Xvfb can't prove real window-manager focus behavior, so this is verified by code inspection/manual check rather than an automated test.
- Motion: none. Dialog appears instantly, same as the update-log dialog.
- Web vs native: no web target. Windows/Linux/macOS Tk behave the same for Escape/Return. The Cancel-left/Delete-right order follows the Windows convention; macOS users see the same order, which is acceptable here.

## Design-is pass (Dieter Rams, applied as a sanity check; no artifacts written)
1. Innovative: N/A, reuses existing Toplevel/Button pattern. Good.
2. Useful: names the item and the loss before the click. Good.
3. Aesthetic: flat, theme-consistent, no added decoration. Good.
4. Understandable: heading names the item, red only on the destructive action. Good.
5. Unobtrusive: non-blocking, no grab, no icon, no checkbox. Good.
6. Honest: macro copy now lists the hotkey too (spec draft omitted it); "can't be undone" stated because there is no undo. Changed from the draft.
7. Long-lasting: tokens only, no hard-coded new colors. Good.
8. Thorough: long/empty names, stale targets, double-open slot, rebuild closure, current-game check for macros, focus. Folded in (was missing from the spec's draft: single open slot, stale-target guard, Return=cancel, rebuild close).
9. Environmentally friendly: one helper, one additive kwarg, no dependency, no new settings key. Good.
10. As little design as possible: no "don't ask again", no icon, no third button, no grab. Good.

## Traceability to spec

| Acceptance criterion / edge case (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| AC1: sidebar glyph opens themed modal naming profile; profile not yet deleted | "Triggers / Profile" steps 2-3; heading = profile name; `_confirm_delete_game` only opens the dialog |
| AC2: Delete removes profile exactly as `_delete_game` does today | "Confirm (Delete button)" step 1-2; `_delete_game` unchanged; closure calls it |
| AC3: Cancel / Escape / window close leave profile intact | "Cancel, Escape, Return, and close box" bullets; no save, no re-arm |
| AC4: macro Delete opens themed modal naming macro; macro not yet deleted | "Triggers / Macro" steps 1-2; heading = macro name |
| AC5: macro Delete removes it exactly as `_delete_macro` does today | "Confirm" step 3; `_delete_macro` unchanged, closure calls it after current-game check |
| AC6: Cancel / Escape / window close leave macro intact | Same contract as AC3 |
| AC7: themed, uses `BG/CARD/INK/MUTED/BAD/ACCENT_INK`, `Button`; no `messagebox` | "Styling tokens"; "Component reuse"; only `Button` gets one additive `danger` kwarg |
| AC8: built-in profiles still show no glyph | Unchanged: `GameItem` guard at `afk_clicker.py:2628` untouched; `_confirm_delete_game` also returns for non-custom |
| Edge: cancel must leave every piece of state untouched | Cancel/Escape/close only destroy the dialog |
| Edge: confirm while deleted game is selected | Unchanged; `_delete_game`'s fallback to `"global"` untouched |
| Edge: rapid double-click on Delete | Single open slot; dialog destroyed before closure runs |
| Edge: confirming an armed macro | Unchanged; `_delete_macro` re-arms as today |
| Added (not in spec): target changed while non-blocking dialog open | Stale-target guard in both closures; current-game check for macros |
| Added: UI rebuild while dialog open | Close in `_rebuild_ui()` before teardown |
