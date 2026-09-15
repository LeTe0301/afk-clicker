# Spec: macOS Accessibility-permission guard — combined fix for G#5, G#8, G#9

## Summary
Three related tickets against the same `macos_input_permitted()` guard machinery added by PR #4 (commit `c798cdd`): G#5/GH#7 ("crashes without Accessibility permission") turns out to already be fixed by that same commit and just needs confirming/closing; G#8/GH#10 ("`registered_hotkey` claims a listener that is not running") is a real bug in the not-permitted branch of `apply_hotkey()`; G#9/GH#11 is five small residue items (dead `if` in `selftest()`, a redundant call, an uncommented load-bearing line, a stale help string, and a self-skipping test) from the same PR #4 review that were deferred rather than fixed.

## Goals
- Confirm and document that G#5's crash-reachable path is already closed (evidence below), so the ticket can be closed without a code change for it specifically.
- Fix G#8: `registered_hotkey` must mean "a listener is running for this," so it must stay `None` (not become `self.hotkey`) when `apply_hotkey()` takes the not-permitted branch. Remove the resulting dead line. Fix the one test that currently pins the wrong behavior.
- Fix all five G#9 items in `macos_input_permitted()` and its two callers.

## Non-goals
- `Hotkey.from_json`'s vocabulary checking (G#7/GH#9) — separate, already-tracked ticket, untouched here.
- Any change to the Linux (`HOTKEY_HELP` Wayland string) or generic-platform help text, or any other hotkey-recording/matching logic (`HotkeyRecorder`, `_mod_base`, chord matching) — out of scope, not implicated by any of the three tickets.
- No UI/visual redesign. The only user-visible text change is the one-word correction to the darwin `HOTKEY_HELP` string (G#9 item 4), which is already fully specified by the ticket — **ux-designer is skipped for this cycle**, there is no layout/visual decision to make.
- Not re-opening G#27's macOS interpreter-abort investigation (`Tcl_FindHashEntry on deleted table`) — unrelated abort, different code path, tracked separately.

## Background / current state

All three tickets trace to one commit: `c798cdd` ("Two of the rejection cases were caught by the wrong guard", part of PR #4 `feature/ac-2/hotkey-lost-on-restart`, merged `19ce2a1`/`1283b57`). That commit introduced `macos_input_permitted()` and guarded the two places that start a pynput listener. All three Gitea tickets (#5 at `2026-09-10T00:04:02Z`, #8 and #9 both at `2026-09-10T09:47:1{5,23}Z`) were filed *before* PR #4's merge commit (`2026-09-10T10:34:32Z`) — i.e. during that PR's own review rounds — and #9's title is literally "residue from review of PR #4." G#8 and G#9 describe bugs/rough edges *introduced by* `c798cdd`'s own fix for G#5.

Current relevant code (`afk_clicker.py`, line numbers verified against the branch tip today):

- `macos_input_permitted()` — lines 311-338. Returns `True` on non-darwin. On darwin, resolves `AXIsProcessTrusted` via `ctypes` and returns its answer; returns `False` (fail-closed) if the library/symbol can't be resolved. Docstring already explains the SIGTRAP mechanism (`.start()`ing a listener creates the CoreGraphics event tap; that's what traps, not construction).
- `selftest()` — lines 240-268. Lines 248 and 255-256:
  ```python
  macos_input_permitted()                       # the guard itself must load
  detect_os_theme()                             # ...
  if macos_input_permitted():
      kb.Listener(on_press=lambda k: False)     # pynput keyboard backend
  ```
- `capture_hotkey()` — lines 3983-4000. Guards its `kb.Listener` at the top (lines 3984-3986):
  ```python
  if not macos_input_permitted():
      self._ui(self._hotkey_error, "Accessibility permission not granted")
      return
  ```
- `apply_hotkey()` — lines 4018-4045. Guards its `HotkeyWatcher` construction/`.start()` (lines 4025-4032):
  ```python
  if not macos_input_permitted():
      # Starting the listener here would trap, not raise. Show the label
      # and keep the recorded combination so applying it again after the
      # permission is granted just works.
      self.registered_hotkey = self.hotkey          # <-- G#8 bug
      self.hotkey_label.config(text=self.hotkey.label(), fg=INK)   # <-- dead, next line overwrites it
      self._hotkey_error("Accessibility permission not granted")
      return
  ```
- `_hotkey_error(self, detail)` — lines 4011-4016. Its own body ends with `self.hotkey_label.config(text=HOTKEY_HELP, fg=BAD)`, which is what actually wins in the sequence above.
- `registered_hotkey` reads, all already null-safe (`if self.registered_hotkey else ""`/similar) — confirmed at lines 2630, 2633, 4068, 4075, 4140, plus the `_rebuild_ui` docstring's own note at line 2644 that a rebuild must never reset it. None of these five reads need a code change; they're listed here to confirm the `None` fix from G#8 is safe everywhere it's read.
- `HOTKEY_HELP` — lines 156-162, three per-platform strings; darwin's is line 158.
- Tests: `tests/test_ui.py:2017` `test_no_listener_is_started_without_permission`, `tests/test_ui.py:2032` `test_capture_refuses_without_permission` (both in `HotkeyPersistence`), `tests/test_hotkey.py:291-315` `InputPermission` (`test_true_off_darwin`, `test_false_on_darwin_when_the_question_cannot_be_answered`).

### G#5 — already fixed, evidence

G#5 asked for exactly one thing: "Check `AXIsProcessTrusted` before touching a listener." Both places in the codebase that ever touch a listener already do this — `capture_hotkey()` (line 3984) and `apply_hotkey()` (line 4025) — and this guard was added by `c798cdd`, the same commit whose diff is quoted above (`git show c798cdd -- afk_clicker.py` shows `macos_input_permitted()` being introduced alongside both guards in the same patch). `grep -n "kb.Listener(\|HotkeyWatcher(" afk_clicker.py` finds exactly four listener-touching sites in the whole file: `selftest()` (already conditionally guarded, see G#9 item 1 below), `HotkeyWatcher.__init__` (construction only — per the function's own docstring and PR #3's macOS leg, construction doesn't trap, only `.start()` does, and `HotkeyWatcher(...)` is only ever constructed from inside `apply_hotkey()`'s already-guarded branch), `capture_hotkey()`, and `apply_hotkey()`. There is no fifth, unguarded call site.

**Conclusion: G#5 has no residual gap. It is fully fixed by the guards already in `apply_hotkey()` and `capture_hotkey()`. This cycle makes no code change for G#5 itself** — the developer should note this finding in `docs/implementation.md` and the ticket should be closed on that basis (referencing `c798cdd`) rather than reopened with new work.

## Proposed approach

### G#8 fix — `apply_hotkey()`, lines 4029-4030
Remove the two lines that set `registered_hotkey` to a combination with no listener behind it and then immediately get overwritten:
```python
        if not macos_input_permitted():
            # Starting the listener here would trap, not raise. Keep the
            # recorded combination (self.hotkey) so applying it again after
            # the permission is granted works without re-recording — but
            # registered_hotkey means a listener is running for this, and
            # none is, so it stays None.
            self._hotkey_error("Accessibility permission not granted")
            return
```
`self.registered_hotkey` is only ever initialized to `None` (line 2227) and otherwise only ever assigned `self.hotkey` in the permitted branch further down (line 4040) — so simply not assigning it here leaves it at whatever it already was (`None` on first run through this path, or the previous *running* combination on a re-Apply while permission is still missing, which is also correct: a previously-started listener was already `.stop()`ped a few lines above at 4020-4022, so there is genuinely no listener running for it any more either way). `self.hotkey` is untouched by this branch already (nothing here clears it), so a second `Apply` after the user grants permission still works exactly as the removed comment described — this is a comment-preservation/rewording, not a behavior change to that path.

`_hotkey_error("Accessibility permission not granted")` still runs and still sets `hotkey_label` to `HOTKEY_HELP` via `BAD` styling — that is unchanged.

**Correction (round 2, post-review): the code block and reasoning above are superseded.** The claim that "simply not assigning it here leaves it at whatever it already was... which is also correct" is wrong for the re-Apply-while-still-blocked case with a *previously-registered* hotkey — see the corrected Edge cases entry below for the actual bug and fix (`self.registered_hotkey = None` must be assigned explicitly in this branch, not omitted).

### G#9 fixes

**Item 1 + 2 (selftest's dead `if`, and the double call) — `selftest()`, lines 248-256.** Ticket #9's claim that bare `kb.Listener.__init__` does not trap (citing PR #3's macOS leg) is corroborated by `macos_input_permitted()`'s own docstring, which attributes the SIGTRAP specifically to "`HotkeyWatcher.start` creating the event tap" — not to `Listener()` construction. `selftest()` never calls `.start()` on the listener it builds; it only constructs one. So the `if` buys no real-Mac safety and, per the ticket, actively costs coverage: `AXIsProcessTrusted` reports trusted on `macos-latest` (`.github/workflows/ci.yml` runs the full suite there as a required, non-continue-on-error leg; `.github/workflows/release.yml:209` runs `--selftest` there too), so on every CI run the `if` branch is always taken anyway and the `False` branch — the one case this line exists to guard — is never exercised anywhere in CI. Fix: drop the `if`, construct unconditionally, and doing so naturally also fixes item 2 (the redundant call) since there is now only one call to `macos_input_permitted()` left in the function:
```python
    Controller()                                  # pynput mouse backend
    macos_input_permitted()                       # the guard itself must load
    detect_os_theme()                             # ...
    kb.Listener(on_press=lambda k: False)         # pynput keyboard backend --
                                                   # __init__ only, never
                                                   # started here, so this is
                                                   # safe even without
                                                   # Accessibility permission
                                                   # (see macos_input_permitted's
                                                   # docstring)
```

**Item 3 (uncommented `restype`) — line 336.** Add the one-line comment the ticket specifies:
```python
        lib.AXIsProcessTrusted.restype = ctypes.c_bool   # without this ctypes reads an
                                                          # int; non-zero garbage in the
                                                          # upper bytes reads as trusted
        return bool(lib.AXIsProcessTrusted())
```

**Item 4 (stale `HOTKEY_HELP` darwin string) — line 158.** The guard is re-asked on every `Apply` (there is no "only checked once at launch" behavior — `apply_hotkey()` calls `macos_input_permitted()` fresh every time), so "reopen" is misleading; nothing needs to relaunch. Change:
```python
    HOTKEY_HELP = "Grant Accessibility permission, then press Apply again"
```
No test asserts this string's literal text (`grep -rn "HOTKEY_HELP\|Grant Accessibility" tests/` is empty), so this is a pure string change with no test fallout.

**Item 5 (`test_false_on_darwin_when_the_question_cannot_be_answered` self-skips on darwin) — `tests/test_hotkey.py:305-315`.** Today:
```python
    def test_false_on_darwin_when_the_question_cannot_be_answered(self):
        if app.sys.platform == "darwin":
            self.skipTest("only meaningful where the framework is absent")
        original = app.sys.platform
        app.sys.platform = "darwin"
        try:
            self.assertIs(app.macos_input_permitted(), False)
        finally:
            app.sys.platform = original
```
On a real Mac, `sys.platform` is already `"darwin"`, so `find_library("ApplicationServices")` would actually find the real framework and the function would return the real, ambient `AXIsProcessTrusted()` answer — not necessarily `False` — so the test self-skips there instead of asserting something that could legitimately vary. Fix per the ticket: patch `ctypes.util.find_library` to return `None` (forcing the fail-closed branch deterministically regardless of the machine's actual trust state), and only fake `sys.platform` when it isn't already `"darwin"` (still needed on Linux/Windows CI to reach the darwin-only branch at all — `macos_input_permitted()`'s very first line is `if sys.platform != "darwin": return True`). This removes the skip entirely, so the real darwin branch gets exercised for real on the real platform (`macos-latest` in CI):
```python
    def test_false_on_darwin_when_the_question_cannot_be_answered(self):
        # The two mistakes do not cost the same: a wrong True is an
        # uncatchable SIGTRAP that takes the window with it, a wrong False is
        # a message. Patch find_library rather than sys.platform to force the
        # unanswerable-question branch, so this asserts something real on a
        # genuine Mac too instead of skipping there.
        original_platform = app.sys.platform
        if original_platform != "darwin":
            app.sys.platform = "darwin"     # still needed off-Mac to reach the branch at all
        try:
            with unittest.mock.patch("ctypes.util.find_library", return_value=None):
                self.assertIs(app.macos_input_permitted(), False)
        finally:
            app.sys.platform = original_platform
```
Requires adding `import unittest.mock` to `tests/test_hotkey.py` (not currently imported there).

## Affected areas
- `afk_clicker.py`: `selftest()` (lines ~248-256), `macos_input_permitted()` (line ~336, comment only), `HOTKEY_HELP` (line 158), `apply_hotkey()` (lines ~4029-4030 removed). All in one file, one architectural layer (application logic) — no schema/API/multi-layer split needed, this stays one dispatch.
- `tests/test_ui.py`: `test_no_listener_is_started_without_permission` (line ~2028) assertion changed.
- `tests/test_hotkey.py`: `test_false_on_darwin_when_the_question_cannot_be_answered` (lines 305-315) rewritten; add `import unittest.mock`.
- No data model, schema, or public API changes. No `docs/design.md` needed (see Non-goals).

## Edge cases
- **Re-Apply after granting permission mid-session**: `self.hotkey` must survive the not-permitted branch untouched so a second `Apply` (now permitted) works without re-recording — explicitly preserved by the G#8 fix; add an assertion for it in the updated test (see Acceptance criteria).
- **Re-Apply while still not permitted, with a previously-registered hotkey**: `apply_hotkey()` already `.stop()`s and clears `self.hk_listener` unconditionally near the top (lines 4020-4022) before the permission check, so there is genuinely no listener running once the not-permitted branch is reached, regardless of whether one was running before — `registered_hotkey` must read `None` in both the first-ever-Apply and the re-Apply-while-still-blocked cases. **Correction (round 2, post-review): this edge case was originally mis-specified.** The proposed approach's "simply not assigning it here leaves it at whatever it already was (`None` on first run through this path...)" is only true for a *first-ever* Apply, where `registered_hotkey`'s only prior value could be its `None` default. On a *second* Apply while not permitted — after an *earlier successful* Apply had set `registered_hotkey` to a real `Hotkey` and started a listener — merely not assigning it leaves the stale non-`None` value in place even though `hk_listener` was just correctly stopped/cleared a few lines above. That is G#8's exact bug, reproduced live by the reviewer in round 2. The fix must explicitly set `self.registered_hotkey = None` in the not-permitted branch (not just omit the old assignment), so both cases land on the same correct state.
- **`selftest()` on a real permission-less Mac**: after the item-1 fix, `kb.Listener(...)` now constructs unconditionally there too. Per `macos_input_permitted()`'s own docstring and the PR #3 evidence cited in G#9, construction alone does not touch the event tap and is safe; this is the one part of this cycle only a real macOS CI run (not local Xvfb) can actually confirm — see Acceptance criteria's CI-only note.
- **Status pill / hotkey-label rendering with `registered_hotkey is None`**: already null-safe at every one of the five read sites (`if self.registered_hotkey else ""` or equivalent) — confirmed by reading each site; no site needs a code change, only the assignment does.
- **CI vs. real Mac for G#9 item 1**: on `macos-latest` CI, `AXIsProcessTrusted` already reports trusted, so removing the `if` changes CI behavior not at all in terms of what gets skipped (the branch was already always taken there) — the only behavioral difference is deterministic construction on a genuinely permission-less machine, which per the docstring is safe.

## Acceptance criteria
- [ ] `git show c798cdd -- afk_clicker.py` (cited above) plus the current guards at `capture_hotkey()`/`apply_hotkey()` are documented in `docs/implementation.md` as the evidence that **G#5/GH#7 requires no code change** and can be closed.
- [ ] Given `macos_input_permitted()` is monkeypatched to return `False`, when `apply_hotkey()` is called with `self.hotkey` set, then `self.registered_hotkey` is `None` afterward (not `self.hotkey`).
- [ ] Given the same setup, `self.hotkey` still equals the pre-call combination afterward (second-Apply contract preserved).
- [ ] Given the same setup, `self.hk_listener` is `None` afterward (unchanged, already covered).
- [ ] `tests/test_ui.py::HotkeyPersistence::test_no_listener_is_started_without_permission` asserts `self.assertIsNone(self.ui.registered_hotkey)` (replacing the old `assertEqual(..., "Ctrl + F6")`), plus a new assertion that `self.ui.hotkey.label() == "Ctrl + F6"` survives.
- [ ] `tests/test_ui.py::HotkeyPersistence::test_capture_refuses_without_permission` passes unmodified (not touched by this change; confirms no regression to the capture path).
- [ ] `selftest()` calls `macos_input_permitted()` exactly once (`grep -c "macos_input_permitted()" ` inside the function body) and constructs `kb.Listener(...)` with no surrounding `if`.
- [ ] `selftest()` still returns `0` under Xvfb on this Linux sandbox (existing `Selftest` test class in `tests/test_ui.py`, unmodified, must still pass) — proves the item-1/2 change doesn't break the one platform this session can verify directly.
- [ ] `macos_input_permitted()`'s `restype` line carries the one-line comment specified above; `tests/test_hotkey.py::InputPermission` (`test_true_off_darwin`, and the rewritten `test_false_on_darwin_when_the_question_cannot_be_answered`) both pass — comment-only change, no behavior change expected.
- [ ] `HOTKEY_HELP` on darwin reads exactly `"Grant Accessibility permission, then press Apply again"`; no test currently asserts the old text (confirmed empty grep), so none needs updating for this alone.
- [ ] `tests/test_hotkey.py::InputPermission::test_false_on_darwin_when_the_question_cannot_be_answered` no longer contains a `skipTest` call, imports `unittest.mock`, patches `ctypes.util.find_library` to return `None`, and asserts `macos_input_permitted() is False` — verified to actually pass when run locally (Linux, via the `sys.platform` fake path) in this session, and structurally correct for the real-darwin path per the reasoning above (only a `macos-latest` CI run can confirm that leg directly — see Risk/rollback notes).
- [ ] Full existing suite (`python -m pytest tests/` or the project's existing runner) still passes locally after all changes, with no test other than the two explicitly listed above modified.
- [ ] Sabotage-verify per this repo's convention: for each changed/added assertion above, temporarily revert the corresponding production fix and confirm the test fails for the right reason, then restore.

## Open questions
- **None blocking.** One assumption stated for the record: G#8's ticket text says "three call sites" read `registered_hotkey`; the actual count in the file is five (2630, 2633, 4068, 4075, 4140), all following the same null-safe pattern — assuming the ticket meant the three inside `AfkAutoclicker`'s run-control methods (`start`/`stop`/the eating-status line in `loop()`) specifically, since the other two (`_rebuild_ui`'s resync) are a status-pill resync of the exact same pattern rather than a distinct "call site" in the ticket's sense. No behavior differs either way — all five are already null-safe and none needs a code change.

## Risk / rollback notes
- All three fixes are small, localized diffs in `afk_clicker.py` plus two test edits — low blast radius, no data/schema/API surface.
- The one part of this cycle that cannot be verified in this Linux/Xvfb sandbox is whether `selftest()`'s now-unconditional `kb.Listener(...)` construction is genuinely safe on a real, permission-less Mac (G#9 item 1) and whether the rewritten darwin-branch test in item 5 actually passes on real `macos-latest` CI rather than just the Linux-side platform-faked path exercised locally. Both rest on `macos_input_permitted()`'s own docstring and the PR #3 precedent cited in the ticket, not on a fresh macOS run in this session — call this out explicitly in `docs/implementation.md`/`docs/test-review.md`, and treat the next green `macos-latest` CI run on this branch as the actual confirmation, not a local guarantee.
- Rollback is a single revert of this cycle's commit(s); no migrations, no persisted-state format changes (`self.hotkey`/`self.registered_hotkey` stay in-memory Python objects; `Hotkey.to_json()`/`from_json()` are untouched).
