# Spec: Macro recording with real timings

## Summary
Add a "Record" mode to the existing macro editor dialog that listens to real keyboard/mouse input (reusing the app's existing pynput listener infrastructure) and appends the resulting key_down/key_up/click/wait steps — with real captured gaps as `wait` steps — to the macro's step list, as an alternative to building the list by hand.

## Goals
- A new control in `_open_macro_editor`'s Steps section lets the user start/stop a live recording.
- While recording, real key presses/releases and mouse clicks become `key_down`/`key_up`/`click` steps in the existing schema, each preceded by a `wait` step reflecting the real elapsed gap since the previous captured event.
- Recorded steps land in `ctx["steps"]` exactly like manually-added ones: visible immediately in the step list, reorderable/removable with the existing ↑/↓/✕ controls, validated through the existing `_validate_macro_step`/`_validate_macro` path at Save — no new step type, no schema change.
- Recording reuses `pynput.mouse.Listener`/`kb.Listener` (same library already imported for hotkeys and the clicker loop) — no new dependency.

## Non-goals
- No mouse-move/pointer-position capture or replay. `click` steps already carry no x/y (`MacroRunner`'s click fires wherever the pointer already is) — recording does not change that; clicks are captured and replayed positionless, same as today.
- No new step type and no `MacroRunner` changes — a recorded macro replays through the exact same runner as a hand-built one.
- No automatic merging/smoothing of consecutive short waits, no "humanizing"/jitter on recorded timings — ROADMAP's existing "no jitter, deterministic replay" rule applies to recorded macros exactly as to hand-built ones.
- No recording of scroll events or non-left/right/middle mouse buttons (matches `MACRO_BUTTONS`).
- No change to how an in-progress recording interacts with a concurrently running click loop or another macro — same already-documented open interleaving caveat in `docs/ROADMAP.md` (macros tab bullet) applies; not resolved here.
- No in-dialog playback/preview of a just-recorded sequence — the existing step-list display (`_describe_step`) is the only feedback.

## Background / current state
- `afk_clicker.py:5986` `_open_macro_editor` builds the add/edit dialog; its Steps card (`afk_clicker.py:6075-6192`) only supports adding one step at a time by hand (`_add_step`, `_capture_step_key` for a single key).
- `afk_clicker.py:734` `_validate_macro_step` / `afk_clicker.py:761` `_validate_macro` are the schema gate; steps are `{"type": "key_down"/"key_up", "key": [name, vk, char]}`, `{"type": "click", "button": "left"/"right"/"middle"}`, `{"type": "wait", "ms": 0..MACRO_MAX_WAIT_MS}`. `MACRO_MAX_STEPS = 200` (afk_clicker.py:696), `MACRO_MAX_WAIT_MS = 60_000` (afk_clicker.py:697).
- `afk_clicker.py:833` `MacroRunner.run()` replays the list deterministically, tracking held keys and releasing them in `finally` — unaffected by this feature.
- Existing single-key/hotkey capture pattern already in this dialog (`_record_macro_hotkey` at afk_clicker.py:6024, `_capture_step_key` at afk_clicker.py:6128) is the template to follow: a background `threading.Thread` guarded by `self._macro_capture_thread` (afk_clicker.py:2999, one shared field so only one capture — hotkey, single-key, or now recording — runs at a time), a `kb.Listener` run inside the worker, `macos_input_permitted()` checked first, results marshalled back to the UI thread via `self._ui(...)`.
- `_record`/`_same_key` (afk_clicker.py:448/463) convert a pynput key event to/from the stored `[name, vk, char]` record; `_key_from_record` (afk_clicker.py:817) is the inverse used by `MacroRunner`.
- `pynput.mouse` (already imported in part — `from pynput.mouse import Button as MouseButton, Controller` at afk_clicker.py:46) also exposes `Listener(on_click=...)`, not yet imported, needed for capturing real clicks the same way `kb.Listener` already captures keys.
- ROADMAP.md (lines 45-69) explicitly lists "Recording with real timings, not just an authored step list" as the open item this closes, and reaffirms the deterministic-replay, no-jitter rule that bounds it.

## Proposed approach
1. Import `from pynput import mouse as msq` is unnecessary; instead add `from pynput.mouse import Listener as MouseListener` alongside the existing `pynput.mouse` import at afk_clicker.py:46.
2. In the Steps card of `_open_macro_editor`, add a single toggle `Button` ("● Record" / "■ Stop") next to the existing "+ Add step" row (or its own row above it) and a status `Label` mirroring the hotkey-recording status label's styling (`ACCENT` while active, `BAD` on error, back to neutral when idle).
3. Starting recording (`_toggle_recording`), guarded by the existing `self._macro_capture_thread` busy-check (same as `_record_macro_hotkey`/`_capture_step_key`, so recording cannot start while a hotkey/single-key capture is mid-flight and vice versa):
   - Check `macos_input_permitted()` first; on failure, show the same "Accessibility permission not granted" message and do not start.
   - Worker thread starts both a `kb.Listener(on_press=..., on_release=...)` and a `MouseListener(on_click=...)` together (two listeners, one thread each is fine — pynput's own pattern — or run both `.join()`-ed via a shared `threading.Event` the Stop button sets; simplest: start both listeners, then `stop_event.wait()`, then `.stop()` both).
   - Record `t_prev = time.monotonic()` at start. On each key-down/key-up/click event: compute `gap_ms = (now - t_prev) * 1000`, clamp to `[0, MACRO_MAX_WAIT_MS]`, round to int; if `gap_ms > 0` append a `{"type": "wait", "ms": gap_ms}` step; then append the event's own step (`key_down`/`key_up` via `_record(key)`, or `click` via the pynput mouse-button → `"left"/"right"/"middle"` mapping, ignoring any button not in `MACRO_BUTTONS`, e.g. `Button.x1`); update `t_prev = now`. Run each append through `_validate_macro_step` before use, same reject-not-coerce discipline as `_add_step`.
   - Every appended step also checks the running total (existing list length + newly captured so far) against `MACRO_MAX_STEPS`; hitting the cap sets the stop event itself (auto-stop) rather than appending further, and the finishing status says why ("Stopped — 200-step limit reached").
   - Mouse-move (`on_move`) is not subscribed to at all — no pointer tracking.
4. Stopping recording (toggle clicked again, cap hit, or the dialog being cancelled/closed mid-recording) sets the stop event, joins the thread, and marshals the captured list onto `ctx["steps"]` via `self._ui(...)` in one batch, then calls the existing `_render_steps()`. If the dialog is destroyed before the thread finishes, the stop event is set from `_cancel()`/the window-close handler so the thread exits cleanly instead of writing to a dead dialog (mirrors how `_record_macro_hotkey` doesn't need this today only because it is a single blocking read-3-keys operation with no explicit stop; recording needs an explicit teardown hook, so `_cancel()` and the Toplevel's close protocol both call it).
5. No changes to `_validate_macro_step`, `_validate_macro`, `MacroRunner`, storage, or `MACRO_MAX_STEPS`/`MACRO_MAX_WAIT_MS` — the whole feature lives inside `_open_macro_editor` and feeds the exact same `ctx["steps"]` list the manual "+ Add step" flow already feeds, so Save/Cancel semantics are unchanged.

This is one architectural layer (one dialog's input-capture + UI, reusing an existing validation/schema/runner untouched) — no sub-spec split needed.

## Affected areas
- `afk_clicker.py`: new `MouseListener` import; `_open_macro_editor` gains the Record/Stop control, status label, and `_toggle_recording`/capture-worker logic; `_cancel()`/dialog close within that function gains a stop-recording-thread call. No other function changes.
- No data model / schema / persistence changes.
- No new public interfaces.

## Edge cases
- Recording started with zero events captured, then Stop clicked immediately: no steps appended, no error — same as Cancel with an empty list today.
- A gap longer than `MACRO_MAX_WAIT_MS` (user walks away mid-recording): clamp to the cap rather than reject, so a long real pause doesn't silently fail at Save.
- Hitting `MACRO_MAX_STEPS` mid-recording: auto-stop, keep everything captured so far (don't discard the whole recording), explain why in the status label.
- macOS without Accessibility permission: same existing error path as the other two capture flows in this dialog, no listener started.
- Recording across a key that's also this macro's own trigger hotkey, or the global clicker toggle hotkey: out of scope — recorded verbatim like any other key, since this dialog is not running the macro while recording, so no retrigger can occur from this path; a hotkey bound in *another* window firing during recording is the same already-documented cross-component interleaving this project leaves open elsewhere (ROADMAP).
- Dialog Cancel or window-close while recording is still active: listener thread is stopped and joined before the dialog is torn down; nothing captured is written back (matches Cancel's existing "discards it all" contract).
- Starting Record while a hotkey-record or single-key capture (the dialog's other two capture buttons) is mid-flight: blocked by the existing shared `self._macro_capture_thread` busy-check, same as those two block each other today.
- Platform: recording uses the same `kb.Listener`/mouse listener stack already gating hotkeys/macros on this platform — if the platform can't run those (macOS without permission, as above), recording can't either; no new platform-specific code path.

## Acceptance criteria
- [ ] Given the macro editor dialog (new or edit) on a platform where `macos_input_permitted()` passes, when the user clicks "Record", then a status label shows a recording-in-progress state and real key/mouse-click input while it's active is captured instead of operating the OS normally for any *other* window (note: focus-follows-input is outside this app's control — the acceptance is "input delivered to the app is captured", not "input is consumed/blocked").
- [ ] Given recording is active, when the user presses and releases a single key with a real pause before it, then after Stop, `ctx["steps"]` contains, in order, a `wait` step approximating that pause, a `key_down` step for that key, and a `key_up` step — each passing `_validate_macro_step`.
- [ ] Given recording is active, when the user left-clicks, then after Stop a `{"type": "click", "button": "left"}` step appears at the correct position, preceded by a `wait` step for the real gap since the prior event; right/middle clicks map to `"right"`/`"middle"` respectively.
- [ ] Given a real gap during recording exceeds `MACRO_MAX_WAIT_MS` (60000), when recording stops, then the resulting `wait` step's `ms` is clamped to 60000, not rejected and not silently dropped.
- [ ] Given the macro's existing step count plus captured steps reaches `MACRO_MAX_STEPS` (200) during an active recording, when the next event would exceed it, then recording stops automatically, the status explains the limit was hit, and every step captured up to that point is kept.
- [ ] Given recording has produced steps, when the user clicks Stop, then those steps appear in the dialog's step list (`_describe_step` rendering) and are reorderable/removable via the existing ↑/↓/✕ controls, identically to manually-added steps.
- [ ] Given macOS without Accessibility permission, when the user clicks Record, then the dialog shows "Accessibility permission not granted" (same message/style as the existing hotkey/step capture paths) and no listener starts.
- [ ] Given recording is active, when the user clicks Cancel or closes the dialog, then the capture thread stops (no lingering listener) and no steps are written to the macro being edited (existing Cancel contract preserved).
- [ ] Given recording is active, when a mouse-move with no click occurs, then no step is produced for it (no pointer-position capture at all).

## Open questions
- **Escape-to-stop:** should pressing Escape during recording also stop it (so the user isn't forced to click back into the dialog with the mouse)? Assumption: no special-casing — Escape is captured like any other key, and the only way to stop is clicking the same toggle button again, same explicit-action model `_record_macro_hotkey`'s own "press up to 3 keys" flow already uses for finishing a capture. If Leo wants an Escape-to-stop shortcut, flag it for a follow-up rather than blocking this cycle.
- **Leading wait before the first event:** should the delay between clicking Record and the user's first real action become a leading `wait` step? Assumption: no — only gaps *between* captured events become `wait` steps; the reaction time before the first action isn't part of "what I did," so it's dropped. This matches starting playback immediately.
- **Two simultaneous `pynput.Listener`s in one worker thread** (keyboard + mouse): confirmed this is pynput's own documented/common pattern (each `Listener` runs its own OS-level thread regardless of which Python thread constructs it), so no real concurrency concern beyond this dialog's existing single-worker-at-a-time guard.

## Risk / rollback notes
- Fully additive: no schema/runner/persistence change, so rollback is deleting the new UI control and its handler in `_open_macro_editor` — nothing else references it.
- Main runtime risk is a listener thread outliving the dialog (leak/zombie thread) if Stop/Cancel/close don't all route through the same teardown — mitigated by routing all three through one `_stop_recording()` helper, mirroring the existing `on_close()` cleanup discipline this codebase already uses for other pynput listeners.
- No new dependency, no CI/platform-matrix risk beyond what hotkey recording already carries (same macOS Accessibility-permission gate, already tested).
