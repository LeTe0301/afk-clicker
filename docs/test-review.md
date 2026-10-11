# Test & Review: Macro recording with real timings (G#65/GH#115)

## Scope
Second pass, after the first round's BLOCKED verdict (must-fix Defect #1, should-fix N2/N4).
This pass re-verifies the whole feature from scratch per dispatch instructions: full suite
re-run, the original repro re-checked against the fixed code, the lock's coverage of every
mutation path, the new refusal-path test's fidelity to the real guard, then an independent
review of the diff as a whole.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1: Record shows in-progress state, captures real input | automated | pass | `MacroRecording::test_a_key_press_and_release_with_a_pause_live_appends_wait_key_down_key_up` |
| 2 | AC2: key down+up with real pause → wait, key_down, key_up, in order, each valid | automated | pass | `MacroRecorderLogic::test_a_key_press_and_release_with_a_pause_produces_wait_key_down_key_up` |
| 3 | AC3: left/right/middle click → `click` step preceded by its own `wait` | automated | pass | `MacroRecorderLogic::test_a_click_is_preceded_by_its_own_wait_and_every_button_maps`; `MacroRecording::test_a_left_click_appends_its_own_wait_and_click_step`, `::test_right_and_middle_clicks_map_to_their_own_names` |
| 4 | AC4: gap > `MACRO_MAX_WAIT_MS` clamps, not reject | automated | pass | `MacroRecorderLogic::test_a_gap_longer_than_the_cap_is_clamped_not_rejected` |
| 5 | AC5: hitting `MACRO_MAX_STEPS` mid-recording auto-stops, explains why, keeps all captured so far | automated | **pass (now including the validation-drop boundary)** | `MacroRecorderLogic::test_hitting_the_cap_auto_stops_and_keeps_everything_captured_so_far`, `MacroRecording::test_hitting_the_cap_mid_recording_auto_stops_with_visible_feedback`, plus new `MacroRecorderLogic::test_an_event_record_too_broken_to_validate_drops_its_wait_too` |
| 6 | AC6: recorded steps render via `_describe_step` and are reorderable/removable like manual ones | automated | pass | unchanged from round 1 |
| 7 | AC7: macOS no permission → message, no listener starts | automated | pass | `MacroRecording::test_permission_denied_shows_the_message_and_starts_no_listener` |
| 8 | AC8: Cancel / window-close mid-recording stops the thread, nothing written | automated | pass | `MacroRecording::test_cancel_mid_recording_stops_the_thread_and_discards_nothing_yet_saved`, `::test_closing_the_window_mid_recording_stops_the_thread` |
| 9 | AC9: mouse-move produces no step | static + inspection | pass | unchanged, `on_move=` still never passed |
| 10 | Concurrent-capture guard, both directions | automated | pass | `MacroRecording::test_recording_is_blocked_while_another_capture_is_mid_flight`, `::test_other_capture_flows_are_blocked_while_recording_is_active` |
| 11 | **Defect #1 fix: cap boundary, whole pair dropped including a validation failure on the event half** | automated + manual repro (this pass) | **pass** | `MacroRecorderLogic::test_an_event_record_too_broken_to_validate_drops_its_wait_too`; independently re-ran the original repro shape directly against the fixed `MacroRecorder` — see "Defect #1 re-verification" below |
| 12 | Stop-click suppression (true positive + non-swallowing of a later real click) | automated | pass | unchanged from round 1 |
| 13 | **N2 fix: lock wraps every `MacroRecorder` mutation path** | code trace (this pass) | **pass** | `key_down`, `key_up`, `click` all route through `_append_pair`, and `_append_pair`'s entire check-then-append body (gap computation, cap check, validation, `self.steps`/`self._t_prev`/`self.stopped_reason` mutation) is inside `with self._lock:` (afk_clicker.py:876-887) — no other method touches those fields outside the lock |
| 14 | **N4 fix: S7 (Record clicked when list already at 200) now has coverage** | automated | pass | `MacroRecording::test_record_is_refused_when_the_step_list_is_already_full` — verified it drives the real `_toggle_recording` button handler (not a mock of the guard), asserts `_FakeListener.instances == []`, the exact status text, and Record staying enabled |

## Defect #1 re-verification
Ran the fixed code directly, using a realistic `_record()`-shaped record (name=None for a
character key, matching `_record()`'s actual return shape — the original round-1 repro's
`("a", 30, "a")` was illustrative only and would itself fail `_validate_key_record` on the name
field; the regression test's `(None, None, "a")` / `(None, None, None)` shape is the real one):

```
r = MacroRecorder(0)
r.key_down((None, None, "a"), now=0.0)        # -> True, appends key_down (first event, no wait)
r.key_up((None, None, None), now=1.0)         # -> True, but drops silently
r.steps  # -> [{'type': 'key_down', 'key': [None, None, 'a']}]
```
The wait+key_up pair is dropped as a whole; no lone wait is left behind. Confirmed by reading
`_append_pair` (afk_clicker.py:872-887): `validated = [_validate_macro_step(step) for step in
pair]; if any(v is None for v in validated): return True` — drops before any `self.steps.extend`.

I also traced (not executed, see note below) what the old per-step-validate loop would have done
against this same input: the `wait` step validates standalone and would append; the `key_up` step
fails and would not — reproducing exactly the round-1 defect. Did not execute this trace: a
sandbox policy classifier blocked the Edit that would have temporarily reverted `_append_pair` to
the old loop ("Security Test Removal", since the edit removed the lock along with the loop). I
restored the file to the fixed version immediately and re-ran the 21 targeted tests to confirm no
corruption (still 21/21 OK) before proceeding. The manual trace above plus the new regression
test (which is a direct TDD red→green per the developer's own report, and whose assertion would
fail against the literal old code shown in round 1's Defect #1 writeup) is sufficient evidence
here without re-executing the revert.

## Regression check
- Targeted: `DISPLAY=:99 python -m unittest tests.test_ui.MacroRecorderLogic
  tests.test_ui.RecordingStoppedStatusText tests.test_ui.MacroRecording -v` → **21/21 pass**, no
  stderr noise. (2 more than round 1's 19, matching the 2 new tests added in the fix pass.)
- CI's exact invocation: `DISPLAY=:99 python -m unittest discover -s tests -t .` → **600 tests,
  OK (skipped=10)**. Ran this myself this session.
- Independent cross-check via pytest: `DISPLAY=:99 python -m pytest tests/test_ui.py -q` →
  **11 failed, 478 passed** (478 = round 1's 476 + the 2 new tests). All 11 failures are the same
  `Themes::test_module_globals_still_ship_dark_only` subtests as round 1; re-ran
  `tests/test_ui.py::Themes` alone → 6 passed, 31 subtests passed, confirming it's the same
  pre-existing test-order leak, not a regression from the fix pass.
- `py_compile afk_clicker.py tests/test_ui.py` → clean.

## Review pass

### Spec coverage
All 9 acceptance criteria implemented and covered by a passing automated test (table above).
AC5's previously-uncovered boundary (validation failure on the event half of a pair) is now
covered by `MacroRecorderLogic::test_an_event_record_too_broken_to_validate_drops_its_wait_too`.
No criterion is implemented without a corresponding test.

### Correctness
- `_append_pair`'s fix is minimal and correct: build the full pair, check the cap, validate both
  halves *before* mutating `self.steps`, extend only if both validate. This is the smallest
  change that restores "whole pair or nothing" and doesn't touch the cap-check branch, which was
  already correct. No new edge case introduced (e.g. a pair where only the gap half is invalid —
  impossible by construction, since `_gap_step` always produces a schema-valid `wait` or `None`).
- `click()`'s early-return for an unrecognized button (`Button.x1`) still bypasses `_append_pair`
  entirely and does not touch `self._t_prev` — unchanged from round 1, still correct per spec's
  "ignored" language, and outside the lock since it never reaches shared mutable state.
- `_toggle_recording`'s S7 guard (`len(ctx["steps"]) >= MACRO_MAX_STEPS`) reads `ctx["steps"]` on
  the main/Tk thread only, before any worker thread exists — no race with the lock-protected
  `MacroRecorder` (which is a separate, not-yet-constructed object at that point).

### Thread-safety
- `threading.Lock()` wraps the entire check-then-append sequence in `_append_pair`, the sole
  mutator of `self.steps`/`self._t_prev`/`self.stopped_reason`. `key_down`/`key_up`/`click` all
  funnel through it (confirmed by grep: these are the only three public methods, and all three
  call `_append_pair`). `total_count` is only read inside the lock. This closes N2 as described.
- No deadlock risk: the lock is only ever held within one method, non-reentrant calls, no nested
  acquisition, no lock held across a UI callback (`self._ui(...)` is called outside the `with`
  block, after `_append_pair` returns).

### Simplicity / scope
- The fix is a true minimal diff: the loop-based validate was replaced with a list-comprehension
  check, no new abstractions, no new fields beyond the one `threading.Lock()` the should-fix
  explicitly asked for. The new tests target exactly the two gaps named in round 1, nothing more.
- No scope creep: N1 (stop-click suppression false negative) and N3 (AC9 missing explicit
  assertion) were both nits/non-blocking in round 1 and were correctly left untouched, as stated
  in `docs/implementation.md`'s "Fix pass" section — not re-litigated here either, since neither
  is a must-fix and the dispatch asked for a fresh full pass, not new scope.

### Security
No new trust boundary: input still comes from the local OS input stack via the same pynput
listener pattern already used elsewhere in this dialog; no new file/network/subprocess surface.
Nothing to flag.

## Findings
No must-fix or should-fix findings remain open. Round 1's Defect #1, N2, and N4 are all verified
fixed and tested against real production code paths, not mocks of the guard being tested. N1 and
N3 remain as previously-accepted nits (no action requested, already documented in
`docs/implementation.md`'s "Known limitations").

## Overall verdict
**Approve.** All 9 acceptance criteria are implemented and automatically tested. Round 1's
must-fix (Defect #1) is fixed correctly and covered by a regression test that exercises the real
`MacroRecorder._append_pair` code path (re-verified independently with a realistic record shape,
not just re-reading the developer's own test). Both should-fix items (N2 lock, N4 S7 coverage) are
addressed and verified: the lock covers every mutation path through all three public methods, and
the new refusal test drives the real dialog button handler, not a stand-in for the guard. Full
regression suite (600 tests) and the project's own CI invocation both pass clean; the only test
failures seen (pytest's `Themes` subtests) are a pre-existing, confirmed test-order flake,
unrelated to this diff. No new must-fix, should-fix, or scope-creep findings surfaced in this
pass's independent review of the diff.
