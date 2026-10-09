# Design: Per-game hotkeys (G#57)

## Summary
The Hotkey tab keeps its exact place and its Record-then-Apply card; only the data under it becomes per-game. The one copy change is the section subtitle: "Hotkey  ·  shared by every game" becomes "Hotkey  ·  this game only". Two behaviour decisions go beyond the spec's silent handling, because a silent "Not set" for a saved-but-unarmed chord and a Record button that silently does nothing after a game switch are both dishonest UI: (1) a switch-time arm failure reuses the existing error copy and re-enables Apply, and (2) a capture still in flight when the user switches games is dropped by a generation counter, and Record on the new game works immediately.

## ui-ux-pro-max choices
- Style: none new. Existing glass/flat-card Tk system (`card()`, `section()`, `Row`, `Button`) unchanged.
- Palette: none new. Every colour below is an existing `THEMES` token. Contrast is computed in "Accessibility" below for the pairings this pane actually uses.
- Typography: none new. Subtitle stays `section()`'s Segoe UI Bold `fs(10, s)`; chord/status text stays Consolas `fs(10, s)`.
- Relevant UX guidelines applied: state honesty (a control's label must say what is actually armed, not a default); no silent failure for an action the user just triggered by switching games; copy states scope in the same words the rest of the app uses ("this game", not a new term).
- Note: the `ui-ux-pro-max` and `design-is` skills are not callable tools in this run, so the palette/UX checks were done by hand against the project's own tokens. The `design-is` pass was done manually; its findings are folded into the decisions below (see "Rams pass").

## Component reuse
- Reused: `section()` (`afk_clicker.py:2254`), for the subtitle; text change only at `afk_clicker.py:3614`.
- Reused: `card()` (`:2274`), `Row(hk, "Toggle", s)` and `self.hotkey_label` (`:3615-3620`), `Button` Record/Apply (`:3623-3626`), unchanged.
- Reused: `_show_hotkey()` (`:5134`), `_hotkey_captured()` (`:5138`), `_hotkey_error()` with `HOTKEY_HELP` (`:5143`, `:213-219`), `self.apply_button.set_enabled()`, `self.status`. No new widget, no new string, no new colour.
- New: none. The only new slots are non-visual (`_capture_gen`, `_capture_thread_gen`, see "Interactive states").

## Subtitle wording (the spec's deferred copy decision)

Chosen: `"Hotkey  ·  this game only"` (25 characters, was 31).

Why this and not the alternatives:
- "Hotkey" alone: accurate, but the tab's whole point is scope, and Clicking/Macros show no subtitle, so the subtitle is the only place a user learns the chord is per-game.
- "Hotkey  ·  for this game": same meaning, longer, and "for" invites "for this game's clicks" reading. "this game only" mirrors the old string's shape (the old one was also a scope phrase), so the diff reads as a single-clause fix.
- Keep the existing "  ·  " separator (two spaces either side) so the subtitle matches the old string's rhythm exactly. No test asserts the old string (grep: only `afk_clicker.py:3614` contains it), so no test edit is needed.

Layout verification (not eyeballed):
- Geometry: `section()` packs a `tk.Label` (no `wraplength`) into a row that fills the pane. The pane sits in `body`, `padx = int(CONTENT_PAD * s)` (`:3558`), inside `self.content` of width `int(CONTENT_W * s)` (`:3353`). Available text width = `int(452*s) - 2*int(16*s)` = about 420*s px.
- Font: `fs(10, s)` = `max(6, int(10*s))` pt Segoe UI Bold. At 96 dpi a pt is 4/3 px, so em = 13.33 px at s=1 and scales with s.
- Estimate: Segoe UI Bold averages about 0.55-0.6 em per character for this text. Using a pessimistic 0.7 em/char: 25 chars x 0.7 x 13.33 px = about 233 px at s=1, against 420 px available = 56%. Realistic (0.46 em/char for this mix) is about 150 px = 36%.
- Across steps: both the text and the frame scale with `s`, so the ratio is scale-invariant. Checked at the four discrete steps and Auto's continuous range (`AUTO_SCALE_MIN..MAX`, `:142-143`, clamped to `dpi_s * [0.9, 1.3]`): at s=1.3 the font is `int(13)` = 13 pt (17.3 px em), so 25 x 0.7 x 17.3 = 303 px against 420 x 1.3 = 546 px = 56%. At s=0.9 the font is 9 pt (12 px em), 210 px against 378 px = 56%. The minimum window width (`_apply_minsize`, `:3083`) pins the frame at `CONTENT_W * s` even in the collapsed-sidebar rail, so there is no narrower case.
- Conclusion: it fits at every step with about 44% headroom. No wrap or clip, and no layout/height implication (one line, same `section()` row, same `pady`).
- Caveat: Segoe UI is not installed on this Linux sandbox, so these are metric estimates, not a render. The developer should confirm once on Windows. The old string is wider (31 chars), so the new one cannot regress.

## Wireframe (Hotkey tab, per game page)

```
  [Clicking]  [Hotkey]  [Macros]                       (existing TabBar)

  Hotkey  ·  this game only                            (section, MUTED bold)
  +----------------------------------------------------+
  |  Toggle                              Not set       |  (Row; label col 152*s,
  |                                                    |   control col right)
  |  [ Record ]                        [ Apply ]       |  (Buttons 124*s wide)
  +----------------------------------------------------+
```

## States

### Empty (game has no hotkey, the default for a new game)
- Label: `Not set`, MUTED. Record enabled. Apply disabled.
- This is also what a game shows after a v2->v3 migration carried no chord.

### Loading
- No async load. The chord is read synchronously in `_arm_toggle_hotkey()` from the store, so there is no skeleton and none is warranted.
- The closest analogue is the recording-in-flight state below.

### Populated: applied and armed
- Label: chord, INK, e.g. `Ctrl + Shift + F12`. Apply disabled. The existing status pill shows its usual `OFF` with `"<chord> toggles"` subtext (`apply_hotkey()`, unchanged).

### Populated: captured, not yet applied
- Label: `"<chord>   · not applied"`, ACCENT. Apply enabled. Unchanged from today.

### Recording in flight
- Label: `Press up to 3 keys, then let go…`, ACCENT. Record itself shows no change (existing). Esc with no keys cancels (`HotkeyRecorder.press`).

### Interactive: switching games while a capture is in flight (deviation from spec §4)
Problem with the spec as written: `register_hotkey()` (`afk_clicker.py:5108-5109`) returns early while `capture_thread.is_alive()`. A capture from game A stays alive until the user releases a chord or presses Esc. So after switching to B, a Record click on B is a silent no-op until the user presses a key somewhere. The spec's guard only drops the stale result; it does not unblock Record. Also, `capture_hotkey()` sets `self.hotkey = hotkey` on the worker thread at `:5129` before the `_ui` hop, so the spec's guard inside `_hotkey_captured()` would not cover that write.

Design:
- Replace the spec's `_hotkey_capture_game` with an integer generation counter `_capture_gen` (init 0, next to `capture_thread` at `:2783`), plus `_capture_thread_gen` for the thread last started.
- `_arm_toggle_hotkey()` increments `_capture_gen` after its same-game early return, so any capture in flight becomes stale on a real switch.
- `register_hotkey()` returns early only if the thread is alive AND `_capture_thread_gen == _capture_gen` (double-click on the same game still blocked, as today). Otherwise it increments the generation, records `_capture_thread_gen`, and starts a new `capture_hotkey(gen)`. Record on B therefore works immediately. The old thread finishes on its own, its result is dropped, and it lingers until the user's next keypress or Esc, same as a cancelled capture does today.
- `capture_hotkey(gen)` routes all four UI hand-offs (`_hotkey_captured`, `_show_hotkey`, `_hotkey_error` for the permission and exception paths) through one helper that runs the callback only if `gen == self._capture_gen`, checked on the UI thread at dispatch time. `self.hotkey = hotkey` moves into `_hotkey_captured(hotkey)`, so the worker thread no longer writes shared state.
- Result: a stale capture is never attributed to the wrong game, including A -> B -> A (the generation has moved twice, so the old capture still does not apply).

### Interactive: arm failure on game switch (deviation from spec §3)
Problem with the spec as written: `_arm_toggle_hotkey()` sets `self.hotkey = None` and ends with `self._show_hotkey(self.registered_hotkey)`. When a game has a saved chord but Accessibility is missing (macOS), or the listener fails (Wayland/X11), the user sees `Not set` with no reason and no way to retry. Today the same failure at startup shows `HOTKEY_HELP` in BAD via `_hotkey_error()`, and the user can press Apply again. The spec regresses that.

Design (only when a chord is stored and arming fails):
- Show `_hotkey_error(...)` exactly as `apply_hotkey()` does today (BAD, `HOTKEY_HELP`).
- Set `self.hotkey = stored` and enable Apply, so the `HOTKEY_HELP` copy ("...then press Apply again") is literally true.
- Do not call `_show_hotkey(None)` on this path (it would overwrite the error).
- When no chord is stored, or arming succeeds, behaviour is exactly the spec's.

### Error
- Arm failure on switch or on Apply: label `HOTKEY_HELP`, BAD. Apply enabled for retry. Stderr print unchanged.
- Known limit, pre-existing, not changed here: see "Known pre-existing copy limits" below.

### Same-game rebuild (theme/scale change)
- Unchanged from the spec: `_arm_toggle_hotkey()` returns early, `hk_listener` identity is preserved (`HotkeyListenerSurvivesRebuild`, `tests/test_ui.py:5851`). The label resets to `Not set` after a rebuild while the chord stays armed. That is pre-existing (no `_show_hotkey()` call in the `_build_ui()` tail) and explicitly out of scope per the spec, so it is not fixed here.

## Known pre-existing copy limits (not introduced by this ticket, flagged)
The `Row` control column is about `(CARD_INNER_W - (ROW_LABEL_W + ROW_LABEL_GAP)) * s` = `244 * s` px, minus 8*s right padding. With Consolas `fs(10, s)` (about 0.55 em per char, 7.3 px per char at s=1), that is about 32 characters at every scale step. Measured against that capacity:
- `"Press up to 3 keys, then let go…"` (32 chars): right at the limit.
- `"Ctrl + Shift + F12   · not applied"` (34 chars, a 3-key chord plus suffix): clips by about 2 characters. Pre-existing.
- `HOTKEY_HELP` on Windows, `"Could not register the hotkey"` (29): fits.
- `HOTKEY_HELP` on macOS, `"Grant Accessibility permission, then press Apply again"` (54), and on Linux, `"Needs an X11 session (Wayland blocks global keys)"` (49): clip badly. This matters more after this change, because the switch-time failure path (above) shows it on every switch without permission, not just at startup.
- Decision: do not change the copy in this ticket (spec scope). Record it as a follow-up: a `HOTKEY_HELP` of at most 32 characters, e.g. "Grant Accessibility, then Apply" (31). The developer should not expand the row or add wrapping, since that changes the card's height and the pane's fill maths (`pack_propagate(False)`, `:3602`).

## Contrast (WCAG 2.x, computed from literal THEMES hex values)
No new colour pairing is introduced. These are the existing pairings the subtitle and the hotkey label use, computed here so the numbers are on record. Relative luminance uses the sRGB linearisation (c/255 <= 0.03928 ? c/12.92 : ((c/255 + 0.055)/1.055)^2.4), L = 0.2126R + 0.7152G + 0.0722B.

| Pairing (theme) | Text / bg hex | L text | L bg | Ratio | Needed | Result |
|---|---|---|---|---|---|---|
| Subtitle, MUTED on BG (dark) | #9299a3 / #15171a | 0.3165 | 0.00847 | 6.27:1 | 4.5 | PASS AA |
| "Not set", MUTED on CARD (dark) | #9299a3 / #1c1f23 | 0.3165 | 0.01348 | 5.77:1 | 4.5 | PASS AA |
| Error `HOTKEY_HELP`, BAD on CARD (dark) | #f06262 / #1c1f23 | 0.2810 | 0.01348 | 5.21:1 | 4.5 | PASS AA |
| Subtitle, MUTED on BG (light) | #596170 / #e8ebf0 | 0.1184 | 0.8273 | 5.21:1 | 4.5 | PASS AA |
| "Not set", MUTED on CARD (light) | #596170 / #ffffff | 0.1184 | 1.0000 | 6.23:1 | 4.5 | PASS AA |

INK on CARD, ACCENT on CARD and the Record/Apply controls are unchanged from today and carry the same existing tokens. The only text colours used on the new paths are MUTED (`Not set`, subtitle) and BAD (error), both computed above.

## Accessibility & platform notes
- Touch target sizes: Record and Apply keep their existing `width=124*s` and height. No target is added, removed or resized. Apply's enabled state on the new arm-failure path is the same button, so it has the same target.
- Color contrast: see the table above; all pass AA. The state is never conveyed by colour alone: "Not set" vs chord vs error are different strings, and "not applied" is a text suffix, not just ACCENT.
- Keyboard: unchanged (Record, Apply are existing `Button` widgets). Esc still cancels a recording.
- Web vs. native: desktop Tk only, no web target. Platform differences are the existing `HOTKEY_HELP` split (darwin/linux/other), which this design does not change.
- Platform behaviour difference (not a UI change): on macOS without Accessibility, a switch to a game with a saved chord now shows the error and enables Apply, instead of a silent `Not set`. That is the intended change.

## Rams pass (design-is, by hand)
- Honest: the spec's silent `Not set` for a saved, unarmed chord was a lie in the UI. Fixed by the arm-failure decision.
- Understandable: the subtitle now states the scope the card depends on.
- Unobtrusive / as little design as possible: no new widget, string, colour or row. Only one new integer slot for the capture generation.
- Useful: Record must work when the user asks for it. Fixed by the generation counter, instead of a silent no-op.
- Thorough to the last detail: the `self.hotkey` write on the worker thread (`:5129`) was a leak the spec's guard missed. Moved into the UI-thread callback.

## Deviations from docs/spec.md (for product-manager to accept or reject)
1. Spec §4 guard keyed on `_hotkey_capture_game` is replaced by `_capture_gen` / `_capture_thread_gen`, with the stale check on the UI thread and `self.hotkey` assignment moved into `_hotkey_captured`. Reason: a game-id compare accepts A -> B -> A stale results, and the spec's guard missed the worker-thread write at `:5129`.
2. Spec §4 "register_hotkey returns early while a capture is alive" is changed: it now returns early only for the same generation. Reason: otherwise Record on B is a silent no-op until the user presses a key.
3. Spec §3 `_arm_toggle_hotkey()` on arm failure with a stored chord: shows `_hotkey_error` and enables Apply with `self.hotkey = stored`, instead of `Not set`. Reason: honest state, and the existing "press Apply again" copy becomes true.
Everything else in the spec is followed as written.

## Traceability to spec
| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| Fresh store: `version == 3`, no top-level `"hotkey"` written | No UI surface. Storage only (spec §1). Nothing in this doc changes it. |
| v2 with one game: old chord carried over, still armed when selected | Populated/applied state (chord label INK). Arm-failure path above applies if permission is missing. |
| v2 with several games: every game gets the chord | No UI surface beyond the same populated state per game. |
| v2 with zero games: nothing crashes | Empty state (`Not set`). |
| Corrupt blob on one game only | Empty state for that game (`Not set`); other games unaffected. |
| Game A's chord does not fire on game B; B shows "Not set" | Empty state (`Not set`, MUTED) on B; switch rearm in spec §3, unchanged UI. |
| Each game's own chord toggles only while selected | Populated/applied state; switch rearm (spec §3). |
| Same chord on two games: no rejection | No validation message anywhere. Populated state on both games; only the selected one is armed. |
| Record on A, switch to B before release: capture discarded | Interactive: switching games while a capture is in flight. B shows its own state; A's result is dropped by generation. Record on B works immediately. |
| Theme rebuild keeps `hk_listener` identity | Same-game rebuild state: `_arm_toggle_hotkey()` early return, unchanged. |
| `on_close()` stops the listener | No UI change. |
| Permission missing: no listener, `registered_hotkey` None, candidate survives | Arm-failure state: error shown, Apply enabled with the stored candidate, retry without re-recording. Apply-path behaviour unchanged. |
| Subtitle no longer says "shared by every game" | Subtitle wording section: "Hotkey  ·  this game only". |
