# Design: Macro recording with real timings (G#65 / GH#115)

## Summary
A Record/Stop toggle and one status label sit in a new top row of the existing macro editor's Steps card, above the step list. Captured steps append live to that list, using the same rows and ↑/↓/✕ controls as hand-built steps. Two decisions drive the layout: the control sits above the list so it stays visible as the list grows downward, and Save is disabled while recording so the step list is complete before it is persisted.

## Environment note
This is a Tk desktop app (`afk_clicker.py`, Canvas-drawn `Button`/`Segmented`, theme globals `BG/CARD/INK/MUTED/ACCENT/ACCENT_INK/ACCENT_HI/BAD/LINE`). It is not Expo/NativeWind, so web-vs-native hover/touch notes do not apply. There is no Skill tool in this run, so `ui-ux-pro-max` and `design-is` could not be invoked. Palette and style decisions below come from the app's existing dark theme (`afk_clicker.py:84-85`) and the existing controls. Contrast ratios are computed by hand from the literal hex values using the WCAG sRGB linearisation (about ±0.05).

## ui-ux-pro-max choices
- Style: no new style. The feature uses the app's existing flat dark card UI, the same Canvas `Button` and the same `Label` status pattern used by the hotkey row and the capture flows.
- Palette: no new colors. The Record button uses the existing primary/secondary `Button` styles. Status text uses `ACCENT` (active), `BAD` (refusal/error), `INK` (finished), `MUTED` (idle hint). These are the same meanings the dialog already uses.
- Typography: `("Segoe UI", fs(9, s))` for the status label, matching `error_label` and the step rows. The Record button uses the Button's own bold 9.5pt.
- Relevant UX guidelines applied: visible state for every async action (recording, stopping, finished, refused); a status line that states what actually happened, including the reason for an auto-stop; no silent failure; the same controls and copy style as the neighbouring capture flows.

## Contrast (hand-computed, dark theme, the shipped default)
| Pairing | Use | Ratio | Result |
|---|---|---|---|
| INK `#e4e7ea` on CARD `#1c1f23` | finished status, step text | 13.3:1 | AA text pass |
| MUTED `#9299a3` on CARD `#1c1f23` | idle hint, disabled Stop/Save text | 5.8:1 | AA text pass |
| ACCENT `#e08a55` on CARD `#1c1f23` | "● Recording…" status | 6.3:1 | AA text pass |
| BAD `#f06262` on CARD `#1c1f23` | refusal / error status | 5.2:1 | AA text pass |
| ACCENT_INK `#1a0f08` on ACCENT `#e08a55` | "■ Stop" label (primary) | 7.1:1 | AA text pass |
| ACCENT_INK on ACCENT_HI `#e59f73` | "■ Stop" hover | 8.5:1 | AA text pass |
| LINE `#3a4048` on CARD | Button outline (existing, every Button) | 1.6:1 | Non-text, below 3:1, pre-existing. The label carries identity (13.3:1 INK text), so the outline is decoration. Not changed. |

Light theme (`set_active_theme("light")`, same code path):
| Pairing | Ratio | Result |
|---|---|---|
| ACCENT `#2b58cc` on `#ffffff` | 6.2:1 | pass |
| `#ffffff` on ACCENT | 6.2:1 | pass |
| BAD `#cc3527` on `#ffffff` | 5.1:1 | pass |
| MUTED `#596170` on `#ffffff` | 6.2:1 | pass |
| `#ffffff` on ACCENT_HI `#5176d5` (primary hover) | 4.3:1 | FAILS 4.5:1 for normal text. Pre-existing: the same hover is used by the Save button. Flagged for a theme follow-up, not changed here. |

## Component reuse
- Reused: `Button` (existing, `afk_clicker.py:2167`) for the toggle. Use `set_text("● Record" / "■ Stop")`, `set_primary(True/False)`, and `set_enabled(False)` for the Stopping state. No new widget class is needed.
- Reused: the `hotkey_row` precedent (`afk_clicker.py:6017-6062`): a row with a Button and a status label to its right, the Button's `width=` argument, and the `padx=(int(10*s),0)` spacing.
- Reused: `self._macro_capture_thread` busy-check and `self._ui(...)` marshalling, exactly as `_record_macro_hotkey` (`:6024`) and `_capture_step_key` (`:6128`) use them.
- Reused: `kb.Listener` (already imported), `macos_input_permitted()` (`:402`), `_validate_macro_step` (`:734`), `_render_steps()` (`:6081`), `_describe_step` (`:802`), `MACRO_MAX_STEPS` (`:696`), `MACRO_MAX_WAIT_MS` (`:697`).
- New: one `MouseListener` import (`from pynput.mouse import Listener as MouseListener`, beside the existing import at `:46`). One new `tk.Label` for status (same as `error_label`). The Record row Frame. Nothing else is new.

## Layout
Current Steps card (`afk_clicker.py:6075-6192`): `steps_list` (rows) then `add_row` (Segmented + capture/click/wait control + "+ Add step" right). The new row goes **above** `steps_list`, inside `steps_card`, so `steps_list` and `add_row` keep their current positions and order.

```
Name        [________________________________________]
[No hotkey]  [Record] [Clear]
Auto-repeat every [ 0 ] ms (0 = off)

Steps
+------------------------------------------------------------------+
| [● Record]  ● Recording · 12 steps                                |  <- NEW record_row
|                                                                  |
| Key ↓ a                                          [✕] [↓] [↑]     |  <- steps_list (unchanged)
| Wait 200 ms                                      [✕] [↓] [↑]     |
| Key ↑ a                                          [✕] [↓] [↑]     |
|                                                                  |
| [Key↓|Key↑|Click|Wait]  (control)          [+ Add step]          |  <- add_row (unchanged)
+------------------------------------------------------------------+
error_label
[Cancel]                                                 [Save]
```

Packing order: `record_row` must be created and packed before `steps_list` (`:6078-6079`). `steps_list.pack(fill="x", pady=(int(10*s), 0))` gives the gap after it. Nothing else moves or resizes. The dialog width is already set by the wider `add_row` (Segmented 260 + Capture 80 + "+ Add step" 100 at `s=1`). The record row fits that width with the longest status copy below, so the dialog does not widen.

Inside `record_row`: `Button(width=100)` packed left, then the status `tk.Label(bg=CARD, anchor="w", font=("Segoe UI", fs(9, s)))` packed left with `padx=(int(10*s), 0)`. Create `record_btn`, `record_status`, `add_btn` and `save_btn` as named variables. The current code discards the `Button(...)` return values, and the new code needs to enable/disable them.

The status label is on top, so long steps lists do not hide it. The dialog has no scroll today, and a 200-step list makes it very tall. That is pre-existing for hand-built lists and is not changed here (see Accessibility and platform notes).

## States

Button and status copy per state. Button colours come from `Button._colors()` (`:2188`).

| # | State | Record button | Status label (fg) | Other controls |
|---|---|---|---|---|
| S0 | Idle, not yet recorded this open | "● Record", secondary | "Record real keys and clicks" (MUTED) | "+ Add step" and Save enabled |
| S1 | Starting (transient, until the worker confirms or refuses) | "■ Stop", primary | "● Recording · waiting for input" (ACCENT) | "+ Add step" and Save disabled |
| S2 | Recording, zero captured | "■ Stop", primary | "● Recording · waiting for input" (ACCENT) | "+ Add step" and Save disabled |
| S3 | Recording, n captured (n ≥ 1) | "■ Stop", primary | "● Recording · 12 steps" (ACCENT), updated per captured step | "+ Add step" and Save disabled. ↑/↓/✕ stay enabled |
| S4 | Stopping (after Stop click or cap hit, until the worker's done marker is applied) | "■ Stop", disabled (MUTED text) | "Stopping…" (MUTED) | Save disabled. Cancel enabled |
| S5 | Stopped by user | "● Record", secondary | "Stopped · 12 steps added" (INK), or "Stopped · no input captured" when n = 0 | Restored (Save enabled, "+ Add step" enabled) |
| S6 | Stopped by cap (auto) | "● Record", secondary | "Stopped · 200-step limit reached" (INK). Persists until the next Record click or until the dialog closes. | Restored, as S5 |
| S7 | Refused: list already full at Record click | unchanged, "● Record" | "Step list is full (200 of 200)" (BAD). No listener starts. | unchanged |
| S8 | Refused: no Accessibility permission (macOS) | "● Record", secondary (reverted from S1) | "Accessibility permission not granted" (BAD) | unchanged |
| S9 | Listener failed (other exception, e.g. no X11/Wayland) | "● Record", secondary (reverted) | `str(exc)` (BAD), same as the other capture flows | unchanged |
| S10 | Another capture busy (hotkey or single-key capture mid-flight) | unchanged | unchanged. Silent no-op, same as the existing busy-check | unchanged |

### Empty
The dialog opened with no steps. S0 hint, and `steps_list` shows the existing "No steps yet." label. Nothing else changes.

### Loading
There is no loading state. Starting is instant (a thread start). The S1 "waiting for input" copy covers the window between Record and the worker confirming the listeners are up.

### Populated
A macro with steps, not recording. S0 or S5/S6 on the record row, steps listed below, as today.

### Error
S7, S8, S9. Each keeps the Record button in the idle "● Record" style. The refused message replaces the status copy in BAD. Nothing is written to `ctx["steps"]`.

**Permission-denied (S8) matches the existing flows.** The worker checks `macos_input_permitted()` first, as `_capture_step_key` does (`:6134-6136`). On failure it calls `self._ui(lambda: record_status.config(text="Accessibility permission not granted", fg=BAD))` and returns. No `print`, no modal, no listener. The copy and BAD colour are the same as hotkey and single-key capture. The Record button is reverted to idle because the Starting state was optimistic. This is the only place the optimistic S1 state can be seen, and it reverts within one UI tick.

### Interactive / expanded states
- **Live append:** each captured step (wait and event as a pair, or the event alone when the gap is 0) is applied on the UI thread via `self._ui(...)`, then `_render_steps()` and the count in the status label update. The worker never writes `ctx["steps"]` directly, so ↑/↓/✕ and the appends cannot interleave badly.
- **Pair-atomic cap check:** before a captured event is appended, the UI-thread handler checks `len(ctx["steps"]) + pair_size <= MACRO_MAX_STEPS`, where `pair_size` is 2 when a wait is needed and 1 otherwise. If it does not fit, the pair is dropped whole and recording moves to S4 with reason "cap". No half-pair is ever appended.
- **Stop-click suppression:** the Stop press is itself a real mouse press that the global listener sees. The UI thread records `toggle_pressed_at = time.monotonic()` on every Record or Stop press. The worker drops any mouse press within 0.3 s of that timestamp. Keys are never dropped. The 0.3 s is a ceiling: a click within 0.3 s before a Stop press is also dropped. A human rarely does this, so accept it, and leave a `# ponytail:` comment naming this ceiling.
- **Done marker:** on Stop (or cap, or Cancel), the UI thread sets the stop event and sets S4. The worker stops both listeners, joins, then posts a final "done" callback after all of its event callbacks. Queued events apply before the done marker because the UI queue is FIFO. The done handler sets S5 or S6 from the stop reason. The done handler also re-enables Save and "+ Add step". This ordering is why Save can be disabled while recording: by the time Save is re-enabled, `ctx["steps"]` is complete.
- **Session guard:** every worker-to-UI callback checks a per-open session token first. Cancel and window close bump the token. Late events and the done marker from a closed dialog are then no-ops and never touch dead widgets.
- **Busy-check vs Stop:** `_toggle_recording` checks "am I recording?" before the `self._macro_capture_thread.is_alive()` busy check. Otherwise the busy check would block Stop itself, because the recording thread is alive.
- **Save and Cancel:** Save is disabled while recording (S1–S4), so the user must Stop first. Cancel stays enabled. Cancel calls `_stop_recording()` (set stop, join with a 1.0 s timeout, bump the session token), then `dialog.destroy()`. Cancel discards `ctx`, so nothing reaches the store (the existing contract).
- **Close via window X:** the dialog currently has no `WM_DELETE_WINDOW` handler, so the X destroys it with no hook. Add `dialog.protocol("WM_DELETE_WINDOW", _cancel)`. For the user this is identical to today (it destroys), and it routes through `_stop_recording()`.
- **Timing:** the gap for each event is `int(round((now - t_prev) * 1000))`, clamped to `[0, MACRO_MAX_WAIT_MS]`. `t_prev` is set at the first event, not at Record, so the reaction time before the first action is dropped (spec open question 2). Dropped clicks do not advance `t_prev`.

## Deliberate deviations from the spec (and why)
1. **Placement above the step list, not beside "+ Add step".** The spec allowed "or its own row above it". Above the list is better because the list grows downward. A control at the bottom would scroll out of view on a long recording, and the auto-stop message would be out of view too.
2. **Live append, not one batch at Stop.** The spec's approach step 4 batches at Stop. The requested behaviour is live. Live append is also consistent with the Cancel contract because `ctx` is still local until Save.
3. **Save disabled while recording, plus a done-marker ordering.** The spec did not cover Save mid-recording. Without this, Save could read `ctx["steps"]` before queued events apply.
4. **Stop-click suppression added.** The spec did not mention that the Stop press is itself captured as a click step.

## Accessibility & platform notes
- Touch targets: the Record and Stop buttons are the existing 34 px-high Canvas `Button` (`s`-scaled), the same height as the hotkey Record button and "+ Add step". This is a desktop app with a mouse, so no 44 pt touch target applies.
- Color contrast: every new text pairing passes AA (table above). The one fail is a pre-existing light-theme primary hover (4.3:1), which this feature reuses via the Save button and does not change.
- Non-text contrast: the recording state is shown by fill (primary ACCENT fill, ACCENT on CARD at 6.3:1, well above 3:1) and the ● glyph, not by the outline. The outline is the pre-existing 1.6:1 border and is not relied on.
- State is not colour-only: the copy changes ("Recording" / "Stopped" / "Stopping…") and the button label flips ("● Record" / "■ Stop").
- Keyboard: the Canvas `Button` has only a mouse binding, so the toggle is mouse-only. This is pre-existing for every `Button` in the app and is not changed here. Recording is inherently mouse-driven because it is started and stopped from the dialog.
- Screen readers: canvas-drawn text is not exposed to assistive tech. Pre-existing for every `Button`.
- Long lists: the dialog has no scrolling. A 200-step list makes it taller than most screens, so Save can end up off-screen. Pre-existing for hand-built lists. The record row at the top stays visible. Out of scope.
- Platform: macOS is the only platform with a permission gate, and S8 covers it. On Linux (X11) and Windows, the `kb.Listener` and `MouseListener` start without a gate. Wayland cannot see global keys, so its listener fails and S9 shows the message, the same as hotkey capture. No platform-specific code path is added.
- Web vs native: not applicable (Tk desktop).

## design-is self-check (principles applied manually)
- Honest: the status says what happened ("Stopped · 200-step limit reached") rather than a generic "Done". This drove S5/S6 and the done-marker reason.
- As little design as possible: no new widget, no elapsed-time timer, no extra dialog. Reuses the hotkey row. This drove the step-count status and the decision not to add a timer tick.
- Thorough to the last detail: Stop-click suppression, the pair-atomic cap, Save disabled until the done marker, and the window-X hook. These were all found by tracing the real event flow, not by the spec.
- Understandable: verb labels plus a glyph ("● Record" / "■ Stop"). Status copy uses one vocabulary across states.
- Unobtrusive: the new row is the same height as the hotkey row, and it does not change any existing row.

## Traceability to spec
| Acceptance criterion / edge case (docs/spec.md) | Where it's addressed in this design |
|---|---|
| AC1: Record shows a recording-in-progress state and captures input | Record button S1–S3; status "● Recording · …" (ACCENT); worker `kb.Listener` + `MouseListener` |
| AC2: key press/release with a pause gives wait, key_down, key_up | Timing bullet (gap from `t_prev`, clamp, round); Live append bullet |
| AC3: left click gives click step preceded by wait; right/middle map | Live append; Stop-click suppression; button mapping stays as spec |
| AC4: wait clamped to 60000 | Timing bullet (clamp to `MACRO_MAX_WAIT_MS`) |
| AC5: cap reached auto-stops, status explains, all kept | Pair-atomic cap bullet; S6 "Stopped · 200-step limit reached" |
| AC6: Stop puts steps in the list, reorderable with ↑/↓/✕ | Live append (rows rendered via `_render_steps`); ↑/↓/✕ stay enabled (S3) |
| AC7: no permission shows "Accessibility permission not granted", no listener | S8; Error section (same copy, BAD, same worker check) |
| AC8: Cancel or close stops the thread, nothing written | Save and Cancel bullet; Close via window X bullet; session guard |
| AC9: mouse-move produces no step | No `on_move` subscription; only `on_click` (press) is used |
| Edge: Stop with zero events | S5 "Stopped · no input captured" |
| Edge: long real gap | Timing bullet (clamp) |
| Edge: start while another capture is mid-flight | S10 silent no-op; Busy-check vs Stop bullet |
| Edge: list already full at start | S7 "Step list is full (200 of 200)" |
| Non-goal: no in-dialog playback | No playback control added |
| Open question 1: Escape to stop | Not special-cased. Stop is the toggle only, as the spec assumed |
| Open question 2: leading wait | Timing bullet (`t_prev` set at first event) |
