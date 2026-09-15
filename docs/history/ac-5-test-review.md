# Test & Review: macOS Accessibility-permission guard — G#5 / G#8 / G#9

## Scope
Three tickets, one diff: G#5/GH#7 (verify already-fixed claim, no code change),
G#8/GH#10 (`registered_hotkey` must not claim a listener that isn't running),
G#9/GH#11 (5 small residue items: `selftest()`'s dead `if`, redundant call,
`restype` comment, `HOTKEY_HELP` string, self-skipping darwin test). Covers
`docs/spec.md`'s Acceptance criteria section in full, plus the specific
multi-attempt edge case called out in "Edge cases".

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | G#5: `c798cdd` introduced `macos_input_permitted()` + both guards in one patch | `git show c798cdd -- afk_clicker.py` | pass | Diff shows `macos_input_permitted()` added alongside `if not macos_input_permitted():` in both `capture_hotkey()` and `apply_hotkey()`, same commit |
| 2 | G#5: no 5th unguarded listener call site in current tree | `grep -n "kb.Listener(\|HotkeyWatcher(" afk_clicker.py` | pass | 4 sites found: `selftest()` (unconditional, construction-only), `HotkeyWatcher.__init__:544` (construction-only, only ever reached from `apply_hotkey()`'s guarded branch), `capture_hotkey():3996` (guarded at 3991), `apply_hotkey():4041` (guarded at 4032) |
| 3 | G#8: `registered_hotkey` is `None` after a first, never-permitted Apply | `tests/test_ui.py::HotkeyPersistence::test_no_listener_is_started_without_permission` | pass | `assertIsNone(self.ui.registered_hotkey, ...)` passes |
| 4 | G#8: `self.hotkey` survives the not-permitted branch (second-Apply contract) | same test, `assertEqual(self.ui.hotkey.label(), "Ctrl + F6", ...)` | pass | passes |
| 5 | G#8: `self.hk_listener` is `None` afterward | same test, `assertIsNone(self.ui.hk_listener, ...)` | pass | passes (pre-existing assertion, unchanged) |
| 6 | G#8: `test_capture_refuses_without_permission` unaffected | full-suite run | pass | unmodified, still green |
| 7 | **G#8 edge case (spec's own "Re-Apply while still not permitted, with a previously-registered hotkey"): `registered_hotkey` degrades to `None` on a *second* Apply attempt too, after a real listener had been running** | targeted scratch script: real Apply (permitted) → real listener starts, `registered_hotkey` set → monkeypatch `macos_input_permitted` to `False` → Apply again | **FAIL** | See Defect 1 below |
| 8 | G#9 item 1+2: `selftest()` calls `macos_input_permitted()` exactly once, constructs `kb.Listener(...)` unconditionally | `grep -c` inside function body + read | pass | one call at line 249, unconditional `kb.Listener(...)` at line 255 |
| 9 | G#9 item 1: `selftest()` still returns 0 under Xvfb | `tests/test_ui.py::Selftest::test_selftest_passes` | pass | part of full-suite green run |
| 10 | G#9 item 3: `restype` comment present, `InputPermission` tests pass | read + `tests/test_hotkey.py::InputPermission` | pass | comment present at line 341-343; `test_true_off_darwin` and rewritten `test_false_on_darwin_when_the_question_cannot_be_answered` both pass |
| 11 | G#9 item 4: `HOTKEY_HELP` darwin string exact text; no test pins old text | read + `grep -rn "HOTKEY_HELP\|Grant Accessibility" tests/` | pass | string is exactly `"Grant Accessibility permission, then press Apply again"`; grep empty (confirmed non-blocking coverage gap, see Follow-ups) |
| 12 | G#9 item 5: rewritten test no longer self-skips, imports `unittest.mock`, patches `find_library`, asserts `False` | read + run | pass | no `skipTest`; passes locally via the off-darwin fake-platform path |
| 13 | G#9 item 5: rewritten test's mock actually reaches the darwin branch (not vacuous) | read `macos_input_permitted()`'s branch order | pass | first line is `if sys.platform != "darwin": return True`; test sets `sys.platform = "darwin"` before entering the `with patch(...)` block, so `find_library` genuinely gets called and mocked in both the off-Mac (faked) and on-Mac (already-darwin, no fake needed) paths — not vacuous |
| 14 | Deviation: `import ctypes.util` is genuinely required, not masking prod code | revert just that import line, run `InputPermission.test_false_on_darwin_when_the_question_cannot_be_answered` | pass (reproduced developer's claim) | Exact `AttributeError: module 'ctypes' has no attribute 'util'` at `unittest.mock.patch(...).__enter__` → `pkgutil.resolve_name`, matching implementation.md's account verbatim; restored, green again |
| 15 | Sabotage: dead `hotkey_label.config(...)` line, restored, is genuinely unreachable-effect | reintroduced the line, ran `HotkeyPersistence` | pass (confirms dead) | all 5 tests in the class still green — nothing catches it; correctly a should-fix-only (nothing *could* catch it, not "nothing does") |
| 16 | Sabotage: `HOTKEY_HELP` string flipped back to old text | reverted string, ran full suite | pass (confirms gap) | 369 tests still green — no test pins the literal string; non-blocking, already noted in spec |
| 17 | Sabotage: reintroduce `if macos_input_permitted():` guard around `selftest()`'s `kb.Listener(...)` | reintroduced guard, ran full suite | pass (confirms gap) | 369 tests still green — `selftest()` **is** called from `tests/test_ui.py:1898` (`Selftest` class), but on Linux `macos_input_permitted()` unconditionally returns `True`, so the guard is unobservable there either way; this item's regression-safety rests entirely on a real macOS CI run (`--selftest` in `release.yml`), not the PR-time unit suite |
| 18 | Full existing suite unaffected elsewhere | full discover run, before and after every sabotage/restore cycle | pass | `Ran 369 tests ... OK (skipped=10)`, identical count throughout |

## Regression check
Full suite: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .`
Result: **`Ran 369 tests in ~68s — OK (skipped=10)`**, run repeatedly (baseline, after each sabotage, after final restore) — identical count every time, matching implementation.md's stated baseline. Working tree verified byte-identical to the pre-review diff after every sabotage/restore round (`diff` against a saved copy of `git diff -- afk_clicker.py`, exit 0).

## Defects found

### Defect 1: `registered_hotkey` still claims a listener after it was stopped, on a second Apply while not permitted
- **File**: `afk_clicker.py:4025-4041` (`apply_hotkey()`)
- **Repro** (exact steps run this session):
  1. On Linux/Xvfb, `macos_input_permitted()` is real (unconditionally `True`, non-darwin), so a first `apply_hotkey()` call succeeds normally: `self.hk_listener` becomes a real running `HotkeyWatcher`, `self.registered_hotkey = self.hotkey` (line 4047).
  2. Monkeypatch `app.macos_input_permitted = lambda: False` (the same technique the existing test suite already uses).
  3. Call `apply_hotkey()` again with the same `self.hotkey`.
  4. Observed: `self.hk_listener.stop()` runs unconditionally at the top (lines 4028-4030) and correctly sets `self.hk_listener = None`. But the not-permitted branch (lines 4032-4038) no longer assigns `self.registered_hotkey` at all — it is simply left at its prior value, which is still the `Hotkey` object from step 1.
  5. **Expected** (per the ticket's own invariant, restated in the diff's new comment at line 4033-4037: *"registered_hotkey means a listener is running for this, and none is, so it stays None"*, and per spec.md's Edge cases section, which explicitly claims `registered_hotkey = None is correct in both the first-ever-Apply and the re-Apply-while-still-blocked cases"*): `self.registered_hotkey` should be `None` after step 3.
  6. **Actual**: `self.registered_hotkey` is still the non-`None` `Hotkey` object from step 1 — printed directly in this session: `after second apply (not permitted): hk_listener= None registered= <afk_clicker.Hotkey object at 0x...>`.
- **Root cause**: the fix only removes the wrong *assignment* (`self.registered_hotkey = self.hotkey`); it does not add the assignment the invariant actually requires (`self.registered_hotkey = None`) for the case where a *prior* successful Apply had already set it non-`None`. "Simply not assigning it" is correct only when it was already `None` (the untested first-Apply case that the one new test covers) — it is provably wrong on any subsequent Apply after a previously-successful one, which is exactly the scenario a permission revoked mid-session (or a transient exception from `macos_input_permitted()`'s own `except Exception: return False` fail-closed path, which can fire even after a prior success) would trigger in the field.
- **Impact**: with `hk_listener is None` but `registered_hotkey` non-`None`, every one of the five `registered_hotkey`-reading UI sites (`afk_clicker.py:2637,2640,4082,4089,4147` in the current tree) renders a hotkey label/status implying a working global hotkey ("Ctrl + F6 toggles") that will never fire again, because the actual listener was stopped in the very same call. This is the precise class of bug G#8 was filed against, just in the one path the new test doesn't reach.
- **Severity**: must-fix — an acceptance-criteria-adjacent edge case (spec.md's own "Edge cases" section describes the expected outcome, and gets it wrong) is not tested and does not hold.
- **Suggested fix direction** (for the developer, not prescribing the exact diff): explicitly set `self.registered_hotkey = None` in the not-permitted branch, rather than relying on "leave it alone," and add a test that Applies once while permitted (or fakes a prior running state), then Applies again while not permitted, asserting `registered_hotkey is None` afterward.

## Overall verdict
**Blocked.** Per process, the testing pass stops here — no independent review pass performed on top of this blocking defect. Route back to developer with Defect 1 as the must-fix; re-run the full suite plus a new regression test for the multi-Apply case once fixed.

---

## Appendix: review-lens spot-checks already performed (informational, not a substitute for the post-fix review pass)
These were verified as part of grounding the testing pass and are provided so the next cycle doesn't have to re-derive them:
- **Vacuous-test check (G#9 item 5)**: not vacuous. `macos_input_permitted()`'s first line is `if sys.platform != "darwin": return True`; the rewritten test sets `sys.platform = "darwin"` (when not already) *before* entering the `find_library` patch context, so the darwin branch — and therefore the mock — is genuinely exercised on both the faked-Linux and real-darwin paths.
- **Comment/string accuracy**: `HOTKEY_HELP`'s new text and the `restype` comment both read as accurate against the surrounding code; no test pins either exact string (confirmed by grep + sabotage), which is a pre-existing, non-blocking coverage gap already called out in spec.md, not something this diff need fix.
- **Minimal diff / scope**: the diff touches exactly what spec.md's "Affected areas" lists — one file (`afk_clicker.py`) plus the two named test files — no drive-by changes observed.
- **Commit-message-worthiness**: no attribution, AI mentions, or trailers present in the working-tree diff (nothing has been committed yet).
- **G#5 independent conclusion**: confirmed via `git show c798cdd` and a fresh grep of the current tree — no code change is needed for G#5, it is fully closed by `c798cdd`'s existing guards. This finding stands independent of Defect 1 (Defect 1 is a residual G#8 gap, not a G#5 regression — `capture_hotkey()`'s and `apply_hotkey()`'s guards themselves are both intact and still correctly prevent any listener from starting/`.start()`ing without permission).
