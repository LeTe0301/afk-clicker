# Implementation: Macro recording with real timings (G#65 / GH#115)

## Summary
Added a Record/Stop toggle to the macro editor's Steps card that captures real
keyboard and mouse input via `pynput` and live-appends it to the macro's step
list as `wait`/`key_down`/`key_up`/`click` steps, with the real gap between
events as a clamped `wait`. No schema, `MacroRunner`, or persistence changes —
recorded steps are ordinary steps in `ctx["steps"]`, validated and rendered
exactly like hand-built ones.

## Changes by file

- `afk_clicker.py`
  - Import: added `Listener as MouseListener` to the existing
    `from pynput.mouse import ...` line (line 46).
  - New `MacroRecorder` class (after `_key_from_record`, before
    `MacroRunner`): a pure state machine with no pynput/Tk dependency —
    `key_down(rec, now=None)` / `key_up(rec, now=None)` / `click(button,
    now=None)` each append a `[wait?, event]` pair, clamping the gap to
    `MACRO_MAX_WAIT_MS` and refusing (not coercing) anything
    `_validate_macro_step` would reject. The pair is dropped whole and
    `stopped_reason` is set to `"cap"` if it would exceed `MACRO_MAX_STEPS`
    (counting the macro's pre-existing steps too, via the constructor's
    `existing_step_count`). `_t_prev` starts `None` so the very first event
    of a session gets no leading wait (spec open question 2).
  - New `_recording_stopped_text(reason, captured_n)`: the exact stop-status
    copy ("Stopped · N step(s) added" / "Stopped · no input captured" /
    "Stopped · 200-step limit reached"), factored out as a pure function so
    its wording is covered by a test without an open dialog.
  - `_open_macro_editor`: new `record_row` (Button + status Label) created
    above `steps_list` inside `steps_card`. `_toggle_recording` starts a
    worker thread guarded by the existing `self._macro_capture_thread` busy
    check (so it can't run alongside the hotkey-record/single-key-capture
    flows, and vice versa — Stop is checked *before* the busy check, so Stop
    isn't blocked by its own thread being alive). The worker checks
    `macos_input_permitted()` first (same refusal copy/style as the other two
    capture flows), then starts a `kb.Listener` and a `MouseListener`
    together, feeding a `MacroRecorder`. Each captured step pair is handed to
    the UI thread via `self._ui(...)` and merged into `ctx["steps"][start_len:]`
    then re-rendered via the existing `_render_steps()`. A per-session
    `token` in the `recording` dict is bumped by `_stop_recording()` (called
    from `_cancel()` and the new `WM_DELETE_WINDOW` handler) so any
    already-queued worker callback becomes a no-op instead of touching a
    destroyed dialog's widgets. A 0.3s "stop-click suppression" window (one
    `# ponytail:` comment) drops a mouse click fired within 0.3s of a
    Record/Stop press, since that press is itself real input the same
    listener sees. `add_btn` and `save_btn` (previously anonymous `Button(...)`
    calls) are now named so they can be disabled while recording and
    re-enabled when it stops.
- `tests/test_ui.py`
  - `MacroRecorderLogic` / `RecordingStoppedStatusText` (after
    `MacroValidation`): pure unit tests of `MacroRecorder` and
    `_recording_stopped_text`, no Tk/pynput/listener involved — deterministic
    `now=` values drive the gap/clamp/cap math directly.
  - `_FakeListener` (module-level helper, next to `_find_button`): stands in
    for `kb.Listener`/`MouseListener`, capturing the real `on_press`/
    `on_release`/`on_click` callbacks so a test can fire a synthetic event by
    calling them directly — no real OS-level listener, no Xvfb/XTest
    dependency. Same "stub what would start a real listener" technique this
    suite already uses for `capture_hotkey()` in `PerGameHotkeys`.
  - `MacroRecording` (after `MacrosTab`, before `MacroIntervals`): opens the
    real dialog via `self.ui._open_macro_editor(...)`, patches
    `kb.Listener`/`app.MouseListener` to `_FakeListener` for the test's
    duration, and drives the real `_toggle_recording`/worker/`_apply_*` code
    path end-to-end.

## Key decisions / tradeoffs
- **Testing technique for the dialog wiring**: rather than driving real
  OS-level input under Xvfb (flaky, and no precedent anywhere in this suite —
  even the real-listener hotkey tests only ever assert a listener started,
  never that it reacted to a synthesized key), `kb.Listener`/`MouseListener`
  are monkeypatched to `_FakeListener` so the test can call the real
  `on_press`/`on_release`/`on_click` closures directly and deterministically.
  This exercises the actual production code path (worker thread, `_ui()`
  marshalling, `_apply_capture`/`_apply_done`, button/label state) with zero
  flake risk. The gap/clamp/cap *math* itself is covered separately and more
  thoroughly by the pure `MacroRecorderLogic` tests, which need no dialog or
  listener at all.
- **`MacroRecorder` extracted as a standalone class** rather than keeping the
  gap/clamp/cap logic as closures inside `_toggle_recording`'s worker. This
  is what makes the AC2–AC5 math testable without a listener or a dialog —
  matches the "actually try the cheapest mock" bar rather than declaring the
  worker untestable.
- **Status line reuses one pure formatter** (`_recording_stopped_text`) so
  the exact wording shown for the three stop reasons (cap / some steps /
  zero steps) is independently verified without needing to actually hit the
  cap through the dialog (though one dialog-level test does that too, for
  the end-to-end wiring).
- **Tests never call `self.ui._drain_ui()` directly**, only `pump_until`.
  `_drain_ui()` unconditionally reschedules its own `self.root.after(40,
  ...)` job on every call (afk_clicker.py's own real, production behaviour
  — a live app always has a `mainloop()` to land in). An extra manual call
  in a *test* overwrites `self._timers["drain"]` with a second, untracked
  job; if the test ends before that orphaned job's 40ms elapse, it fires
  into a Tcl interpreter `tearDown()`'s `root.destroy()` already tore down
  — `"invalid command name ..._drain_ui"`, printed to stderr but not caught
  by `CapturesCallbackExceptions` (it's a Tcl-level `after`-script error
  against a dead interpreter, not a Python-level callback dispatch).
  Reproduced directly while writing these tests (synthetic, fast — unlike
  most of this suite's existing double-`_drain_ui()` call sites, which
  happen to have a real thread-join or sleep between calls, giving the
  orphaned job enough wall-clock time to fire harmlessly first). Fixed at
  the test level only (`pump_until` on the expected rendered text), since
  `_drain_ui()`'s self-rescheduling is correct, pre-existing production
  behaviour outside this feature's scope.

## Fix pass (post-review, G#65/GH#115)
Reviewer's testing pass (`docs/test-review.md`) found one must-fix and two
should-fix items, addressed here before re-review:

- **Defect #1 (must-fix) — `MacroRecorder._append_pair` could leave a lone
  `wait` with its event silently dropped.** `afk_clicker.py` (`_append_pair`):
  it validated each half of `[gap_step, event_step]` independently in a loop
  and appended whichever half passed, so a `key_up`/`key_down`/`click` that
  failed `_validate_macro_step` (e.g. `_record()` returning `(None, None,
  None)` for a key pynput can't identify at all) still left its otherwise-valid
  `wait` appended alone — contradicting both the spec's "whole pair dropped"
  language and the method's own docstring. Fixed by validating both halves
  first and only extending `self.steps` if none are `None`; a validation
  failure is treated as a silent drop (not a stop condition, unlike the cap
  check two lines above). Regression test:
  `MacroRecorderLogic::test_an_event_record_too_broken_to_validate_drops_its_wait_too`,
  using exactly the reviewer's repro shape (a valid `key_down` followed by a
  `key_up` with an all-`None` record).
- **Should-fix N2 — no lock around `MacroRecorder`'s mutating methods**,
  despite `kb.Listener` and `MouseListener` calling in from two separate OS
  threads. Added `self._lock = threading.Lock()` in `__init__`, and wrapped
  `_append_pair`'s whole check-then-append body (cap check, validation,
  `self.steps`/`self._t_prev`/`self.stopped_reason` mutation) in `with
  self._lock:`. No test added for the race itself (same reviewer note: "low
  likelihood... worth a one-line fix as a follow-up" — not asked for a
  concurrency test, and the existing `_FakeListener` tests already fire
  events sequentially from one thread, so a real race test would need actual
  threads and a timing window, disproportionate to this fix's size).
- **Should-fix N4 — S7 (Record clicked when the step list is already at
  `MACRO_MAX_STEPS`) had no test coverage.** Added
  `MacroRecording::test_record_is_refused_when_the_step_list_is_already_full`,
  driving the real dialog with a macro pre-filled to 200 steps: clicking
  Record starts no `_FakeListener`, shows "Step list is full (200 of 200)",
  and leaves the Record button enabled (refused, not disabled-forever).

N1 (stop-click-suppression false negative) and N3 (AC9 mouse-move has no
explicit assertion) were both marked non-blocking/nit by the reviewer with no
action requested — left as-is.

## Deviations from spec
Following docs/design.md's own already-declared deviations from docs/spec.md
(live append instead of batch-at-Stop, Save disabled while recording,
stop-click suppression, record row above the list) — no further deviations
introduced during implementation.

## Known limitations
- Stop-click suppression is a 0.3s ceiling, not a precise fix: a genuine
  click thrown within 0.3s of pressing Record or Stop is also dropped. Noted
  in-code with a `# ponytail:`-style comment; a click-origin check would be
  the upgrade if that ever matters in practice.
- No automated test exercises a *real* `pynput` Listener receiving a
  synthesized OS-level key/click event during recording (only the permission
  gate and busy-check paths, which never construct a real listener, are
  exercised without the `_FakeListener` patch). This matches the rest of the
  suite's existing precedent for every other real-listener capture flow in
  this dialog (hotkey record, single-key capture) — none of them are driven
  with synthetic OS input either, only checked for "a listener started."

## How to verify locally
```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python3 -m unittest \
  tests.test_ui.MacroRecorderLogic tests.test_ui.RecordingStoppedStatusText \
  tests.test_ui.MacroRecording -v
```
Actually run in this session (Xvfb :99, the project's own
`/home/dev/.venvs/afk-clicker-test` venv):
- The three new test classes above: 21 tests (19 + the 2 added in the fix
  pass), all passing, no stderr noise.
- `python -m unittest discover -s tests -t .` (the exact invocation
  `.github/workflows/ci.yml` uses on Linux, run here with `DISPLAY=:99` in
  place of `xvfb-run` per this box's own test-environment notes): 600
  tests, `OK (skipped=10)`, re-run after the fix pass above.
- The same full `tests/test_ui.py` run twice under `pytest` for a second,
  independent confirmation (pre-fix-pass): 476 passed, 11 failed both times —
  the 11 failures are a pre-existing `Themes.test_module_globals_still_ship_dark_only`
  test-order leak (confirmed present identically with this diff fully
  reverted via `git stash`), unrelated to this feature.

Manually: Settings → a game → Macros tab → New macro (or Edit an existing
one) → the Steps card now shows "● Record" above the step list. Click it,
press some keys and click the mouse inside the app window, click "■ Stop" —
the captured steps appear in the list immediately and are reorderable with
the existing ↑/↓/✕ controls.
