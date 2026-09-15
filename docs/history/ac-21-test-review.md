# Test & Review: Review residue from the updater PRs (#19, #31) — G#21/GH#32

## Scope
Four independent items against `docs/spec.md`'s four Goals, all inside
`afk_clicker.py` plus its own two test files: hex check on `fetch_checksums`
(item 1); `_safe_names` docstring correction (item 2); `check_update`/
`_check_worker` sequence-stamp guard (item 3); `Store.save()` return value
plus a save-failure notice in Settings → Appearance (item 4). Design's own
"Orchestrator correction" wording ("Couldn't save settings — changes won't be
kept after closing") is treated as authoritative over the earlier draft text.

Env: pynput 1.7.7 venv at
`/tmp/claude-1000/-home-dev-projects-afk-clicker/31f5a905-5b3f-4e0f-95d5-176a1d0748c4/scratchpad/pv`,
Xvfb `:99` already running, confirmed no other `unittest` process active
before starting. All sabotage/probing this session used in-process
monkeypatch scripts run from the scratchpad directory only — no on-disk edit
to any repo file was made or left behind; `git status --short` before and
after this session is byte-identical (confirmed above and below).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC (item 1): a 64-char non-hex token is rejected, valid lower/upper-case digests unaffected | Ran `tests.test_updater.Checksums` | pass | `DISPLAY=:99 <venv>/bin/python -m unittest tests.test_updater.Checksums -v` → 4/4 `ok` |
| 2 | Item 1 sabotage-verify (independently, not trusting the developer's report) | Reverted the hex check in-process (`app.fetch_checksums` monkeypatched to the pre-fix body) and reran `test_parses_sha256sum_output` | pass (fails as expected) | `AssertionError: {...'garbage.zip': 'gggg...'} != {...}` — confirms the hex check is load-bearing |
| 3 | AC (item 2): `_safe_names` docstring states the zipfile-since-3.6.2/tarfile-is-the-real-guard split; zero executable line changed; `tests/test_updater.py:292` comment corrected | `git diff afk_clicker.py` / `git diff tests/test_updater.py` read directly | pass | Docstring rewritten verbatim per spec's proposed text; only `#`/docstring lines touched, `root = os.path.realpath(...)` and the loop body are unchanged context; test comment corrected, assertion unchanged |
| 4 | AC (item 3): overlapping `check_update()` calls — older worker's result dropped, `self._pending`/offer state reflect only the newer check | Ran `tests.test_ui.SettingsUpdates` + `AnOlderCheckResultDoesNotOverwriteANewerOne` | pass | `DISPLAY=:99 ... -m unittest tests.test_ui.SettingsUpdates tests.test_ui.AnOlderCheckResultDoesNotOverwriteANewerOne -v` → 9/9 `ok` |
| 5 | Item 3 sabotage-verify (independently) | Monkeypatched `AfkAutoclicker._apply_check` to drop the `seq != self._check_seq` guard, reran the new regression test | pass (fails as expected) | `AssertionError: 'v8.0.0' != 'v9.9.9'` — confirms the guard is load-bearing |
| 6 | AC (item 4): `Store.save()`/`put_game()` return `True`/`False` correctly | Ran `tests.test_ui.StoreSaveResult` | pass | 3/3 `ok`, via `app.os.replace` monkeypatch-and-restore (no real filesystem permission bits) |
| 7 | AC (item 4): notice appears on failure, doesn't repeat on repeated failure, clears on success, survives the rebuild the failure itself triggers, stays hidden on other tabs and appears on switching to Appearance, all five call sites can trigger it | Ran `tests.test_ui.SaveFailureNotice` | pass | 6/6 `ok` |
| 8 | Item 4 sabotage-verify (independently) | Monkeypatched `AfkAutoclicker._note_save` to always repaint (no change-detection), reran `test_no_repaint_on_a_second_consecutive_failure` | pass (fails as expected) | `AssertionError: 3 != 1 : a second/third consecutive failure repainted the notice` — confirms the change-detection guard is load-bearing |
| 9 | **Full suite regression** | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` | pass | `Ran 385 tests in 98.028s` / `OK (skipped=10)` |
| 10 | Baseline re-derivation (not trusting the developer's "375 baseline" claim) | Checked out `7d49f83` (pre-diff) into a scratch worktree, ran the same full suite | pass | `Ran 375 tests in 97.495s` / `OK (skipped=10)` — 385 = 375 + 10 new tests this cycle, confirmed independently, not assumed |
| 11 | (a) Threading: can any of the five `save()` call sites run off the Tk main thread? | Traced every caller by reading code, not assuming | pass (all main-thread) | `apply_hotkey` (`afk_clicker.py:4158`) is called only from `__init__` directly (`afk_clicker.py:2467`, synchronous, main thread) and the Apply Button's command (`afk_clicker.py:2899`, Tk callback). `_select`'s five callers (`afk_clicker.py:2696,3468,3474,4027`) are all reachable only via `__init__`'s synchronous flow, Button/trace callbacks, or `_mark_running()` — which itself is gated through `_apply_scan()`, documented and confirmed (`afk_clicker.py:3996-4006`) to run only via `_drain_ui()` on the main thread. `_persist()`'s trace-driven calls (`afk_clicker.py:2956`) fire only from Entry/StringVar `.set()` calls that themselves only ever originate from Tk widget input on the main thread — no background thread anywhere in this diff or its neighbourhood calls `.set()` on any of these vars. `_apply_appearance`/`_apply_ui_scale` fire only from `appearance_var`/`ui_scale_var` write-traces (`afk_clicker.py:3059-3077`), themselves only set by the Segmented control's own click handler (Tk, main thread). No violation found. |
| 12 | (b) Item 3: does `_apply_check` drop exactly the stale results, including non-offer outcomes ("Up to date", "GitHub unreachable")? | Read `_check_worker`'s four early-return branches (`afk_clicker.py:3497-3514`) | **gap found, not a blocker — see Findings #2** | Only the success path is seq-gated (`_apply_check`, `afk_clicker.py:3516-3528`). `NoReleases`/unreachable/not-newer/no-build-for-OS all call `self._ui(self._set_update_state, ...)` directly, unconditionally, with no `seq` check at all — an orphaned older worker's "Up to date"/"GitHub unreachable" message can still land after a newer worker's offer has already been applied, overwriting the "Install vX.X.X" button text. This matches `docs/spec.md`'s own proposed diff verbatim (the spec itself only gates the offer/`_pending` path), and the scenario needs two overlapping `check_update()` calls, unreachable in production today (single button, disabled during a check) — same reachability envelope as the bug the fix does close. Not a new regression, but a real, narrower gap the ticket's own scope left open; flagged for the record, not a blocker. |
| 13 | (c) Item 4 edge case: a failure during `_apply_appearance`, whose save triggers `_rebuild_ui()` | Covered by `tests.test_ui.SaveFailureNotice.test_notice_survives_a_rebuild_triggered_by_the_failing_save_itself` | pass | 1/1 `ok`, independently re-run above (test case 7) |
| 14 | (c) Item 4 edge case: does `save_failed_label` exist before `_note_save` can first run at startup (`__init__` restore → `apply_hotkey` → `save`)? | Constructed `AfkAutoclicker` directly with a pre-populated `hotkey` key and `app.os.replace` broken from before construction (scratchpad probe, in-process) | pass (safe) | `CONSTRUCTED OK`, `save_failed: True`, `has save_failed_label attr: False` — no crash, because `_paint_save_notice()`'s guard (`self._settings_open` is `False` at `afk_clicker.py:2367`, unconditionally, until a user ever opens Settings) short-circuits before touching the not-yet-created label. This specific startup path is safe. |
| 15 | (c) Item 4: does the notice survive being shown the first time Settings is opened after a startup failure? | Same probe, then called `ui._show_settings()` | **FAIL — see Findings #1** | `AttributeError: 'AfkAutoclicker' object has no attribute 'save_failed_label'`, raised inside `_paint_save_notice()` (`afk_clicker.py:3135`), called from `_note_save()` (`afk_clicker.py:3121`), called from `_persist()` (`afk_clicker.py:3453`), called from `_rebuild_ui()`'s own leading `self._persist()` (`afk_clicker.py:2783`), called from `_show_settings()` (`afk_clicker.py:3201-3205`) |
| 16 | (c) Minimal repro of the same crash, no hotkey/startup path needed at all | Fresh `Store`, no prior save ever attempted, `app.os.replace` broken, then `ui._show_settings()` called directly — the single most ordinary first-open case | **FAIL — see Findings #1** | Identical `AttributeError` traceback, from the exact same call chain, on the very first-ever `_show_settings()` call with a broken save. `self._settings_tab` defaults to `"appearance"` (`afk_clicker.py:2384`), so this is not a corner case — it is the default tab. |
| 17 | (d) Does any test depend on the live latest GitHub release, or on `__version__` in a way that breaks after a future merge bumps it from `"0.6.0"` to `"0.7.0"`? | `grep` for every `"0.6.0"`/`__version__` occurrence in both test files | pass (no fragile literal found) | Every assertion comparing against the running app's version does so via `app.__version__` interpolation (`tests/test_ui.py:3435,3457,3501,3512,3518,3545,3635,3657,3681,3754`; `tests/test_updater.py:1403`), not a hardcoded `"0.6.0"`/`"0.7.0"` literal — safe across a version bump. The two literal `"0.6.0"` strings (`tests/test_updater.py:1455,1465`) are arbitrary `build_issue_report(...)` fixture inputs, unrelated to the installed `app.__version__`. `LiveRepository.test_resolves_the_highest_version` (`tests/test_updater.py:1499-1529`) is a live, two-separate-GitHub-request test (`setUp`'s own `releases` fetch vs. the test's own `app.latest_release()` fetch) — a release published on GitHub between the two requests produces exactly the `'v0.6.0' != 'v0.7.0'`-shaped flake the developer reported; this is pre-existing, network-inherent flakiness (`docs/CODING-GUIDELINES.md`: "Network tests skip cleanly when offline" — this one doesn't fail offline, it races between two live calls), untouched by this diff, and not blocking. |
| 18 | (e) No file beyond `afk_clicker.py`/`tests/test_updater.py`/`tests/test_ui.py`/`docs/design.md` touched; no scope creep | `git status --short`, `git diff --stat` | pass | Exactly those three code files modified plus the three untracked `docs/*.md` pipeline artifacts; nothing else |

## Regression check
Full suite run 385/385, `OK (skipped=10)`, matching the developer's own
report exactly, and independently re-derived against a `7d49f83` baseline
worktree (375/375, `OK (skipped=10)`) rather than trusted at face value. The
pre-existing, unrelated `invalid command name "..._poll_games"/"..._drain_ui"
(after script)` noise and `ResourceWarning`s were confirmed present at the
same baseline commit too (cross-checked against `docs/history/ac-33-test-
review.md`'s own prior note on the same noise) — not a regression introduced
by this diff.

## Defects (blocking)

### Defect 1 — `_paint_save_notice()` crashes on the first-ever Settings open after (or during) a save failure

**Location:** `afk_clicker.py:3123-3135` (`_paint_save_notice`), reached from
`afk_clicker.py:3104-3121` (`_note_save`), reached from `afk_clicker.py:3437-
3453` (`_persist`), reached from `_rebuild_ui()`'s own leading
`self._persist()` call at `afk_clicker.py:2783`, reached from
`_show_settings()` at `afk_clicker.py:3201-3205`.

**Root cause:** `self.save_failed_label` is created only inside
`_build_settings()` (`afk_clicker.py:3040`), which itself only ever runs
*inside* `_build_ui()` when `self._settings_open` is already `True`
(`afk_clicker.py:2658-2659`). `_show_settings()` sets `self._settings_open =
True` (`afk_clicker.py:3203`) **before** calling `_rebuild_ui()`
(`afk_clicker.py:3204`), and `_rebuild_ui()`'s very first action is
`self._persist()` (`afk_clicker.py:2783`, "flush any in-progress field edit
before its widget is destroyed") — i.e. a `Store.put_game()` call that,
through the new `_note_save()`/`_paint_save_notice()` chain, can try to
show/hide `self.save_failed_label` *before that label has ever been created*,
because the teardown-and-rebuild of the settings pane (which is what would
create it) hasn't happened yet at that point in `_rebuild_ui()`'s body.
`_paint_save_notice()`'s own guard (`if not (self._settings_open and
self._settings_tab == "appearance"): return`) does not protect against this,
because by the time `_persist()` runs inside `_rebuild_ui()`,
`self._settings_open` is already `True` and `self._settings_tab` already
defaults to `"appearance"` (`afk_clicker.py:2384`) — the exact condition the
guard is supposed to let through.

**Exact repro (minimal, no hotkey/startup state needed):**
```python
import tkinter as tk, afk_clicker as app, tempfile, os
path = os.path.join(tempfile.mkdtemp(), "settings.json")
root = tk.Tk()
ui = app.AfkAutoclicker(root, store=app.Store(path))
root.update()

original_replace = app.os.replace
app.os.replace = lambda *a, **kw: (_ for _ in ()).throw(OSError("read-only filesystem"))
ui._show_settings()   # AttributeError: 'AfkAutoclicker' object has no attribute 'save_failed_label'
```
Observed output (this session, `DISPLAY=:99`, scratchpad-only script, never
written into the repo):
```
Traceback (most recent call last):
  ...
  File "afk_clicker.py", line 3205, in _show_settings
    self._rebuild_ui()
  File "afk_clicker.py", line 2783, in _rebuild_ui
    self._persist()                    # flush any in-progress field edit
  File "afk_clicker.py", line 3453, in _persist
    self._note_save(self.store.put_game(self.current, values))
  File "afk_clicker.py", line 3121, in _note_save
    self._paint_save_notice()
  File "afk_clicker.py", line 3135, in _paint_save_notice
    self.save_failed_label.pack_forget()
AttributeError: 'AfkAutoclicker' object has no attribute 'save_failed_label'
```

**Why this matters:** this is not an obscure corner case — it is the
single most ordinary trigger the whole feature exists for: a user with a
read-only/unwritable config directory (the scenario named in `docs/spec.md`'s
own Summary and in `docs/CODING-GUIDELINES.md`'s "Failure behaviour") clicking
"Settings" for the first time in a session. Per this repo's own Tk-callback
convention, this exception surfaces via `report_callback_exception` (a
traceback to stderr, the click silently doing nothing useful) rather than a
hard process crash, but `self._settings_open` has already been set `True`
(`afk_clicker.py:3203`) before the exception aborts the rest of
`_rebuild_ui()`, leaving the app's `_settings_open` flag out of sync with
reality (no settings pane was actually built) — a corrupted, not just failed,
UI state. It directly violates this cycle's own acceptance criterion: "Given
a simulated save failure while Settings → Appearance is open (or the next
time it is opened after one), a single, non-blocking notice is visible in the
Appearance pane" — instead of a notice, the user gets a crash and Settings
never opens.

**Why the developer's own test suite didn't catch it:** every test in
`tests.test_ui.SaveFailureNotice` calls `self.ui._show_settings()` (which
creates `self.save_failed_label`) **before** breaking `app.os.replace` — so
`self.save_failed_label` already exists in every one of the six new tests by
the time any save is made to fail. None of them exercises "Settings has never
been opened this session, and the very first `_persist()`-flush inside that
first `_show_settings()` call is what fails (or transitions)." That is
exactly the gap this defect lives in.

**Verdict on this criterion: FAIL.** Blocks approval.

## Spec coverage
- Item 1 (hex check) — covered, pass (test cases 1-2).
- Item 2 (docstring/comment) — covered, pass (test case 3).
- Item 3 (sequence guard, offer path) — covered, pass (test cases 4-5); a
  narrower, spec-scoped-out gap noted for the record (test case 12,
  Findings #2), not a criterion violation.
- Item 4 (`Store.save()` return value) — covered, pass (test case 6).
- Item 4 (save-failure notice, five call sites, no-repeat, clears-on-success,
  survives-a-triggered-rebuild, per-tab visibility) — covered by the
  developer's own six tests (test case 7), **but the acceptance criterion's
  own "or the next time it is opened after one" clause is not covered by any
  existing test, and fails when exercised** (test cases 15-16, Defect 1).
  This is exactly the highest-value kind of gap this role exists to catch: an
  acceptance criterion with a passing-looking test suite that does not
  actually reach the failing case.
- Threading (a) — no violation found, all five call sites confirmed
  main-thread-only by tracing every caller (test case 11).
- Version-pin risk (d) — no fragile test found; the one live-network flake is
  pre-existing and unrelated (test case 17).
- Scope (e) — no file outside the declared four touched (test case 18).

## Findings

1. **Must-fix (blocking)** — `afk_clicker.py:3123-3135`/`3437-3453`/`2783`/
   `3201-3205`: `_paint_save_notice()` raises `AttributeError` the first time
   Settings is ever opened in a session during which a save fails (or has
   already failed) at or before that opening's leading `_persist()` flush,
   because `self.save_failed_label` does not exist until `_build_settings()`
   runs, which happens *after* `_persist()` in `_rebuild_ui()`'s own body.
   See Defect 1 above for the full trace and minimal repro. This must be
   fixed (e.g. create `self.save_failed_label` — or at least reserve the
   attribute with a safe default — before the leading `_persist()` call can
   ever reach `_paint_save_notice()`, or guard `_paint_save_notice()` itself
   on `hasattr(self, "save_failed_label")`) before this can be re-tested.

2. **Should-fix (non-blocking, worth folding into the same round)** —
   `afk_clicker.py:3497-3514` (`_check_worker`'s four early-return branches):
   none of "No releases published yet" / "GitHub unreachable" / "Up to date"
   / "{tag}: no build for this OS" is gated by `seq`, unlike the offer path in
   `_apply_check`. An orphaned older worker's non-offer message can still
   overwrite a newer worker's already-applied offer button text. This exactly
   matches `docs/spec.md`'s own proposed diff (the spec itself only scoped
   the fix to `self._pending`/the offer state) and needs the same
   today-unreachable two-overlapping-`check_update()`-calls trigger as the
   bug the fix does close, so it is not a regression and not a blocker — but
   worth closing at the same time, with the same idiom, since the developer
   will already be in this method.

3. **Nit** — `docs/implementation.md`'s "Key decisions" section states all
   five `save()` call sites were "verified by reading each call site's caller
   chain, not assumed" — independently re-traced here (test case 11) and
   confirmed accurate. No issue, noted only because it was a claim worth
   re-deriving rather than trusting, per this role's own standard, and it
   held up.

## Overall verdict
**Blocked.**

Items 1, 2, 3 (offer path), and the core of item 4 (`Store.save()`'s return
value, and the notice's appear/no-repeat/clear/tab-visibility behavior for an
*already-open* Settings pane) are all independently verified, including
sabotage-verified guards for items 1, 3, and 4 re-run in this session rather
than taken on the developer's word, and a from-scratch re-derivation of the
375-test baseline against `7d49f83`. That part of the testing pass is clean.

But the testing pass as a whole is not clean: exercising the exact edge case
this cycle's own spec calls out by name — "a read-only install directory" —
against the ordinary first-time "click Settings" action crashes the app with
an `AttributeError`, via a call chain (`_show_settings` → `_rebuild_ui` →
`_persist` → `_note_save` → `_paint_save_notice`) that the developer's own
six new tests never exercise, because every one of them opens Settings
before breaking saves rather than after. Per this role's own process, a
blocked testing pass does not proceed to the independent code-review pass —
no correctness/security/simplicity review was performed beyond what surfaced
naturally while tracing this defect and the two scrutiny points above it.

Must-fix for the next developer round:
- `afk_clicker.py:3135` (and the `_note_save`/`_persist`/`_rebuild_ui`/
  `_show_settings` chain feeding it) — Defect 1. Fix the ordering (or guard
  the attribute access) so a save failure/transition during the very first
  `_show_settings()` call of a session cannot reach `self.save_failed_label`
  before it exists. Add a regression test that opens Settings for the first
  time *while* `app.os.replace` is already broken (mirroring this review's
  minimal repro) to close the gap the existing `SaveFailureNotice` suite
  left open.

Should-fix (does not block, worth folding into the same round):
- `afk_clicker.py:3497-3514` — gate `_check_worker`'s four non-offer
  `_set_update_state` calls the same way `_apply_check` gates the offer path,
  closing the narrower stale-message-overwrite gap noted in Finding 2.

---

## Round 2

Scope: the developer's round-2 fixes for round 1's Defect 1 (must-fix) and
Finding 2 (should-fix), per `docs/implementation.md`'s "Round 2" section.
`git diff --stat` confirms the same three files as round 1
(`afk_clicker.py` +157/-23, `tests/test_ui.py` +432, `tests/test_updater.py`
+13, unchanged from round 1 — `test_updater.py`'s diff is untouched this
round) — no new file added, no file outside the four already declared
touched. This round performs both the testing pass and, since testing came
back clean, the review pass, in full.

### Testing pass

| # | Case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Full suite regression | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` | pass | `Ran 388 tests in 99.029s` / `OK (skipped=10)` — 388 = round 1's 385 + 3 new tests this round, matching the developer's own report exactly |
| 2 | New/updated test classes run in isolation | `unittest tests.test_ui.SaveFailureNotice tests.test_ui.AnOlderCheckResultDoesNotOverwriteANewerOne tests.test_ui.AnOlderNonOfferCheckResultDoesNotOverwriteANewerOffer tests.test_ui.StoreSaveResult -v` | pass | 13/13 `ok` (8 `SaveFailureNotice`, 1 offer-path supersession, 1 new non-offer supersession, 3 `StoreSaveResult`) — one pre-existing, unrelated `invalid command name "..._drain_ui" (after script)` warning fired during the new non-offer test, same class of harmless post-`root.destroy()` noise already documented in round 1, not a failure |
| 3 | Round-1 repro, Path A (no Settings ever opened, save fails, then `_show_settings()`) — must now NOT crash | Minimal in-process script: fresh `AfkAutoclicker`, break `app.os.replace`, call `ui._show_settings()` | pass (fixed) | `PATH A: no crash. settings_open= True save_failed= True label mapped= 1` |
| 4 | Path B (Settings opened once — creating the label — closed — destroying it — save fails while closed, Settings reopened) — must now NOT crash | In-process script: open, capture `old_label`, close via `_select(persist=False)`, confirm `old_label.winfo_exists()` is `False`, break saves, reopen | pass (fixed) | `old label destroyed: True` / `save_failed after break (settings closed): True` / `PATH B: no crash. label mapped= 1 is new object: True` |
| 5 | Sabotage-verify Defect 1's fix independently (not trusting the developer's own sabotage report) | Monkeypatched `AfkAutoclicker._note_save` to the round-1 buggy shape (repaint unconditionally, no `_rebuilding` gate), reran Path A's repro against the patched class | pass (fails as expected) | `SABOTAGE REPRODUCED CRASH AS EXPECTED: AttributeError("'AfkAutoclicker' object has no attribute 'save_failed_label'")` — confirms the `_rebuilding` gate is load-bearing, not incidental |
| 6 | Sabotage-verify Finding 2's fix independently | Monkeypatched `AfkAutoclicker._apply_check_state` to call `_set_update_state` unconditionally (no `seq` guard), reran `AnOlderNonOfferCheckResultDoesNotOverwriteANewerOffer` against the patched class | pass (fails as expected) | `AssertionError: False is not true : an orphaned older check's stale 'Up to date' message must not overwrite a newer, already-applied offer's button text` — confirms the guard is load-bearing |
| 7 | Additional ordering probe: `_apply_appearance` and `_apply_ui_scale` fired back-to-back while Settings is open and saves are broken, exercising `_request_rebuild()`'s own coalescing (two rebuild requests collapsing into one `_rebuild_ui()` call, itself running `_persist()` first) | In-process script, Settings open, `app.os.replace` broken, `_apply_appearance("dark")` then `_apply_ui_scale("115")` called back-to-back, then `root.update()` to run the coalesced idle rebuild | pass | `COALESCED: no crash. save_failed= True label mapped= 1` |
| 8 | Ordering probe: `_set_settings_tab` while a deferred `_request_rebuild()` is pending, `_apply_ui_scale`'s own coalesced rebuild, a theme change triggered by an OS-level poll | Read `afk_clicker.py` directly: `grep -n "after(" ` for any recurring theme-poll timer, and traced `detect_os_theme()`'s own call sites | pass (not applicable) | No such poll exists in this codebase — `detect_os_theme()` is called at most once per process (`afk_clicker.py:3049`, `self._os_theme is None` guard) and is never re-invoked from a timer; `self._timers` holds only `poll_games`/`drain`/`sync_settings` (`afk_clicker.py:4024,4105,4141`). This scenario the round-1 dispatch prompt asked to probe does not exist as a reachable code path in this app — confirmed by reading the code, not assumed |
| 9 | Is `self._rebuilding` reset in a `finally`? | Read `_rebuild_ui()` directly | pass | `afk_clicker.py:2781` sets `self._rebuilding = True`; the `finally` block at `afk_clicker.py:2827` unconditionally resets it to `False` (and re-arms exactly one follow-up rebuild if one was requested mid-body) — confirmed by reading the source, matching the implementation doc's own claim |
| 10 | Reentrancy check: could `card()`'s `_redraw()` — which calls `inner.update_idletasks()`, itself capable of reentrantly servicing another already-queued Tk idle callback — reach `_note_save()`/`_paint_save_notice()` from a *different* door than `_persist()`'s leading flush, before `self.save_failed_label` exists? | Grepped every `after_idle(...)` call site (`afk_clicker.py`) and traced whether any of them can call `_note_save`/`_paint_save_notice` | pass (no other door found) | The only `after_idle` jobs in this file are `_rebuild_ui` (already covered by Defect 1's fix and by `_rebuild_after_id`/`self._rebuilding` bookkeeping), `_run_pane_fill` (unrelated to save state), and `_maybe_offer_log_report` (unrelated). None of these calls `_note_save`/`_paint_save_notice`. `_apply_check`/`_apply_check_state` are queued via `self._ui()`'s own `SimpleQueue`, drained only by the recurring `_drain_ui()` `after()` job (cancelled during `_rebuild_ui()`'s teardown, `afk_clicker.py`'s `self._timers` loop) — not serviceable via `update_idletasks()`'s idle-queue reentrancy at all |
| 11 | Is `self._pending` still written from exactly one place, always main-thread? | `grep -n "self\._pending\s*="` | pass | Exactly two `None` assignments (`afk_clicker.py:2292` `__init__`, `:3504` `check_update()`, both main-thread) and exactly one real-tuple assignment (`:3557`, inside `_apply_check`, reached only via `self._ui()`/`_drain_ui()` on the main thread) — no regression from round 1's fix |
| 12 | Threading re-confirmation (b): do the five `save()` call sites still run only on the main thread after round 2's changes? | Re-read each call site's caller chain directly (not re-trusting round 1's trace, since `_note_save`'s own body changed) | pass | `_note_save`'s new `_rebuilding` check reads `self._rebuilding`, a plain bool set/cleared only inside `_rebuild_ui()`'s own body — no new thread boundary introduced. The five call sites themselves (`_apply_appearance`, `_apply_ui_scale`, `_select`'s persist branch, `_persist()`, `apply_hotkey`) are textually unchanged from round 1 (only the body of `_note_save`/`_paint_save_notice` changed) — round 1's trace still holds |
| 13 | Live-network flake (`test_resolves_the_highest_version`), noted in round 1 as pre-existing | `unittest tests.test_updater.LiveRepository -v` | pass (did not flake this run) | 2/2 `ok` — consistent with round 1's own note that it passed on every run but the session's very first baseline |

### Regression check

Full suite: 388/388, `OK (skipped=10)` — independently run, not taken on the
developer's word. 388 = round 1's own independently-confirmed 385 + 3 new
tests this round (2 for Defect 1's `SaveFailureNotice` additions, 1 for
Finding 2's `AnOlderNonOfferCheckResultDoesNotOverwriteANewerOffer`), matching
`docs/implementation.md`'s own accounting exactly. Same skip count as round 1
and the original `7d49f83` baseline. No regression introduced.

### Review pass

**Defect 1 fix — correctness.** `_note_save()` (`afk_clicker.py:3104-3134`)
now gates its repaint on `self._rebuilding`, recording `self._save_failed`
unconditionally but skipping `_paint_save_notice()` while a rebuild's own
leading `_persist()` flush is what triggered the call. `_build_ui()`'s tail
(`afk_clicker.py:2693`, inside the `if self._settings_open:` branch) still
calls `_paint_save_notice()` directly and unconditionally, and — critically —
only after `_build_settings(s)` has already (re)created `self.save_failed_label`
earlier in the same call. Traced every path that could reach `_note_save()`/
`_paint_save_notice()` while `self._rebuilding` is `True` but the label is
missing/destroyed: only `_persist()`'s leading flush inside `_rebuild_ui()`
does; nothing else (see testing pass #7-10 above) calls either method from
inside that window. Both round-1 repro paths (A: never-opened; B: opened,
closed, destroyed, reopened) are independently confirmed fixed (#3, #4), and
sabotage-reverting the guard reproduces the exact round-1 crash (#5) — the
fix is load-bearing, not coincidentally passing.

One `hasattr`-only guard (the must-fix's own suggested fallback) would not
have closed Path B, since `self.save_failed_label` still resolves to a real
(if destroyed) Tk object there — the developer's choice of gating on
`self._rebuilding` instead, which closes both paths with one condition, is
the more correct fix, not just the cheaper one.

**Finding 2 fix — correctness.** `_apply_check_state(seq, text, enabled,
colour)` (`afk_clicker.py:3527-3538`) mirrors `_apply_check()`'s existing
`if seq != self._check_seq: return` gate exactly, and `_check_worker`'s four
early-return branches now route through it instead of calling
`_set_update_state` directly. `check_update()`'s own synchronous "Checking…"
call is correctly left untouched (it isn't a worker-thread result, so there
is nothing stale for it to guard against). Sabotage-verified independently
(#6) — the guard is load-bearing.

**Spec-to-code traceability (round 2 delta).** Both fixes address exactly
the two items round 1 raised — no new acceptance criterion is introduced by
this round, so the check here is narrower: does the fix actually close the
gap, and does a regression test exist that would fail without it. Both hold,
confirmed independently (testing pass #3-#6), not solely on the developer's
own sabotage report.

**The `_set_settings_tab` deviation (carried from round 1, re-examined here
since round 1 never reached its review pass).** `afk_clicker.py:3369-3377`
adds one call, `self._paint_save_notice()`, at `_set_settings_tab()`'s own
tail — flagged by the developer as beyond `docs/spec.md`'s/`docs/design.md`'s
literal "Affected areas"/"Placement in the code structure." Judged here:
this is a genuine, narrow gap the ticket's own acceptance criteria imply but
don't spell out verbatim (a save failure while on the Updates tab must
become visible "the next time it is opened" — `docs/design.md`'s own
"Failure while Appearance pane is closed" scenario says "opens Settings and
navigates to (or is already on) Appearance," which a tab switch without a
full close/reopen satisfies under a literal reading) — not scope creep. It
mirrors the existing `self._request_pane_fill(value)` call at the exact same
tail, for the identical reason (react to whichever tab just became active),
and is covered by the developer's own
`test_notice_is_not_shown_while_a_different_settings_tab_is_active`
(independently rerun, testing pass #2). Accepted as in-scope, correctly
flagged rather than silently added, per this pipeline's own "faithful scope
adherence" standard.

**Comment/docstring accuracy against `docs/CODING-GUIDELINES.md`.**
`_note_save()`'s docstring (`afk_clicker.py:3105-3130`) was re-read in full
against the current code: it accurately describes the round-2 gate (the
`self._rebuilding` check, why it's needed, both paths it closes, and why
`_build_ui()`'s own unconditional tail call is what actually paints the
notice once the tree exists) — no stale claim found. `_apply_check_state`'s
comment (`afk_clicker.py:3528-3536`) and `_apply_check`'s (`afk_clicker.py
:3540-3546`) both correctly describe the current gating behavior. Both
match this repo's own "comment the why" convention
(`docs/CODING-GUIDELINES.md` "Comments").

One pre-existing, out-of-scope inaccuracy noted for the record, not part of
this round's diff: `docs/design.md`'s own "Placement in code" / "Behavior"
prose (e.g. "`_build_settings()`'s tail calls `_paint_save_notice()` again")
says the notice is repainted from `_build_settings()`'s own tail, but the
actual call is at `_build_ui()`'s tail (`afk_clicker.py:2693`), one level up
— `_build_settings()` itself has no such call. This is a design-doc wording
imprecision that predates round 2 (design.md is untouched in this round's
diff) and does not affect behavior, since the actual call site is correct
and tested; noted as a nit, not attributed to the developer's round-2 work.

**Color-contrast recomputation (item 4's notice, independent, not trusting
`docs/design.md`'s stated luminance figures).** Computed WCAG relative
luminance and contrast directly from the literal hex values in
`afk_clicker.py`'s `THEMES` dict (`afk_clicker.py:81-85`): dark theme
`CARD` `#1c1f23` vs `BAD` `#f06262` → contrast ≈ **5.22:1**; light theme
`CARD` `#ffffff` vs `BAD` `#cc3527` → contrast ≈ **5.11:1**. Both clear the
4.5:1 text threshold (9.5pt is small text, so 4.5:1, not 3:1, is the
correct bar) with margin. `docs/design.md`'s own stated luminance figures
(~0.310/~0.153) are close to, but not identical to, my own recomputed
values (0.281/0.155) — the difference doesn't change the pass/fail
conclusion, but the design doc's numbers were not re-derived by copying its
claim; they were computed independently from the hex values themselves.

**Simplicity / minimal diff.** Both fixes are the smallest change that
closes each gap: Defect 1 is a two-line addition to an existing method
(`if self._rebuilding: return`, plus recording the outcome first) — no new
attribute, no new widget, no restructuring of `_paint_save_notice()` itself.
Finding 2 is one new 8-line gate method reusing `_set_update_state`'s
existing signature, plus four one-line call-site changes — the same idiom
`_apply_check` already established, not a novel abstraction. No dead code,
no speculative generality, nothing beyond what round 1's own findings asked
for.

**Test volume/duplication (~432 lines total in `tests/test_ui.py` across
both rounds; round 2 itself added 3 tests — 2 in `SaveFailureNotice`, 1 new
class).** Read all 8 `SaveFailureNotice` tests and the new
`AnOlderNonOfferCheckResultDoesNotOverwriteANewerOffer` test directly
(`tests/test_ui.py:3126-3164`, `:3838-3922`). Each of the 8
`SaveFailureNotice` tests targets a genuinely distinct scenario (appears,
no-repeat, clears, survives-a-self-triggered-rebuild, hidden-on-other-tab,
Path A, Path B, all-five-call-sites) with no copy-pasted assertion set
between them; the two round-2 additions are minimal (single `_show_settings()`
call plus a targeted crash assertion) and could not be collapsed into the
existing six without losing the specific ordering each repros. The new
`AnOlderNonOfferCheckResultDoesNotOverwriteANewerOffer` test reuses the
`AnOlderCheckResultDoesNotOverwriteANewerOne` class's already-proven
deterministic-ordering technique (a blocked-until-released `latest_release`,
a `_TrackingThread` wrapper for joinable handles) verbatim rather than
re-deriving it — appropriate reuse of an already-validated technique
(per this role's "proportional verification depth" standard), not
duplication needing a should-fix. **Verdict: proportionate, no collapsing
needed.**

**Security.** No new external input parsing in this round (both fixes are
internal ordering/gating changes); no injection surface, no secrets, no
authz boundary touched. Nothing to flag.

### Findings (round 2)

No must-fix. No should-fix. One nit:

1. **Nit** — `docs/design.md`'s "Placement in code"/"Behavior" prose
   (multiple places) states the notice is repainted from
   `_build_settings()`'s own tail; the actual call is at `_build_ui()`'s
   tail (`afk_clicker.py:2693`). Pre-existing since round 1, not part of
   this round's diff, does not affect behavior (verified correct and
   tested) — worth a one-line correction in `docs/design.md` next time that
   file is touched, not worth a dedicated round.

### Overall verdict (round 2)

**Approve.**

Both round-1 defects are fixed, independently verified (not taken on the
developer's word): Defect 1's crash is reproducibly gone on both Path A and
Path B, and reproducibly returns when the `_rebuilding` gate is sabotaged
out; Finding 2's stale-message gap is closed and reproducibly returns when
`_apply_check_state`'s `seq` gate is sabotaged out. The full suite passes at
388/388 (`OK (skipped=10)`), matching the developer's own report exactly.
Additional orderings this round was asked to probe (`_set_settings_tab` with
a pending rebuild, `_apply_ui_scale`'s coalesced rebuild, an OS-triggered
theme-poll rebuild, `_rebuilding`'s own `finally`-reset, and a second
`update_idletasks()`-reentrancy door into `_paint_save_notice()`) were all
checked and found either safe or (for the theme-poll scenario) not a
reachable code path in this app at all. The review pass found no must-fix,
no should-fix, and one nit (a pre-existing, out-of-scope design-doc wording
inaccuracy). This build cycle is done — hands back to product-manager for
the next iteration.

## Round 3

Scope: `git diff f04fc60 91f410d` — a test-only change to
`tests/test_ui.py`'s `SaveFailureNotice.test_every_save_call_site_can_trigger_the_notice`
(`via_apply_hotkey` subtest only) plus a new "Round 3" section in
`docs/implementation.md`, in response to CI run 35013166754 aborting
(`Trace/BPT trap: 5`) on macOS only. This dispatch does the testing pass and
the review pass together, since PR #78's substantive diff (`f04fc60`) already
carries a round-2 approval above plus a posted PR review verdict of `MERGE` —
not repeated here.

### Testing pass (round 3)

1. **Does the stub fully prevent any real listener start on every path
   `apply_hotkey()` takes in this subtest, and does anything downstream read
   an attribute the stub lacks?**
   Traced `apply_hotkey()` (`afk_clicker.py:4188-4218`): the only places
   anything in this codebase touches `self.hk_listener` after `apply_hotkey()`
   sets it are `.stop()` at `afk_clicker.py:4193` (the "clear a leftover
   listener" guard at the top of `apply_hotkey()` itself) and `.stop()` at
   `afk_clicker.py:4418-4419` (`on_close()`, which `UITestCase.tearDown()`
   calls unconditionally — `tests/test_ui.py:85-97`). `_StubHotkeyWatcher`
   (`tests/test_ui.py:3195-3204`) implements both `start()` and `stop()` as
   no-ops, and its `__init__(self, hotkey, callback)` matches the real
   `HotkeyWatcher.__init__` signature (`afk_clicker.py:568`) that
   `apply_hotkey()` calls it with. Since `via_apply_hotkey` is the *last*
   trigger in the `triggers` list (`tests/test_ui.py:3216-3217`) and its own
   `finally` restores `app.HotkeyWatcher` before the subTest loop's
   `self.root.update()`/`_fix_saves()` even run, no other subtest or
   `tearDown()` call can ever see the patched *class* — only the already-live
   stub *instance* sitting in `self.ui.hk_listener`, and that instance's
   `.stop()` is exactly what `on_close()` calls. Confirmed no other
   `hk_listener.` read exists anywhere in `afk_clicker.py` (`grep -n
   hk_listener afk_clicker.py` → lines 2281, 2454 (comment), 4192-4194,
   4200 (comment), 4207-4210, 4418-4419 — only `.stop()`/`is None`/
   assignment, nothing else). **No gap. Confirmed independently, not taken
   on the developer's word.**

2. **Does anything else changed in this cycle's tests start a real listener,
   call `capture_hotkey`, or touch `HotkeyWatcher`/`kb.Listener`/`mouse` on
   darwin?**
   `git diff 7d49f83 -- tests/` touches only `tests/test_ui.py` (this one
   subtest) and `tests/test_updater.py` (two unrelated additions: a
   non-hex-digit checksum-rejection case at `tests/test_updater.py:173-186`,
   and a doc-comment clarifying an existing zip-traversal test at
   `tests/test_updater.py:289-293` — no listener, no thread, no new
   behavior). `grep -n "Listener\|capture_hotkey\|HotkeyWatcher\|mouse\." `
   against that diff hits only the six lines inside `via_apply_hotkey`
   itself. Confirmed independently — the developer's claim holds.

3. **Does the stub still exercise the save?**
   Proved this via an in-process monkeypatch from a scratchpad script
   (`prove_stub_r3.py`, run from `DISPLAY=:99`, deleted immediately after —
   never touched a repo file):
   - Positive: poisoned the *real* `afk_clicker.HotkeyWatcher.start` to raise
     `AssertionError("real HotkeyWatcher.start() was called")`, then ran
     `test_every_save_call_site_can_trigger_the_notice` directly via
     `unittest.TestLoader().loadTestsFromName(...)`. **Result: `OK`** — the
     poisoned real `start()` was never reached, because `via_apply_hotkey`'s
     stub replaces the class `apply_hotkey()` looks up before it ever
     constructs one.
   - Negative control: same poison, but called `apply_hotkey()` directly on a
     freshly-built `AfkAutoclicker` with *no* stub in place. Result:
     `apply_hotkey()` returned normally with `_save_failed=False` and
     `hk_listener=None` — the poison fired and was swallowed by
     `apply_hotkey()`'s own `except Exception` clause
     (`afk_clicker.py:4209-4212`), confirming `_note_save()` is never reached
     down that path and thus that patching `macos_input_permitted` alone (the
     initially-considered alternative) could never have exercised the save
     either — and confirming this proof harness is measuring something real,
     not a tautology.

4. **Full suite**, pynput 1.7.7 venv, `DISPLAY=:99 <venv>/bin/python -m
   unittest discover -s tests -t .`:
   ```
   Ran 388 tests in 101.165s
   OK (skipped=10)
   ```
   Matches the developer's reported 388/skipped=10 exactly, and matches
   round 2's own count — this round changes how one existing subtest is
   exercised, adding no new test. (Pre-existing `ResourceWarning`s from
   `tests/test_updater.py` for a handful of unclosed temp-file handles are
   unrelated to this diff — present before this cycle, not touched by it —
   and do not affect the `OK` result.)

No test failures, no regressions. Proceeding to the review pass.

### Review pass (round 3)

Per `docs/REVIEW-PROTOCOL.md`, only three of the ten lenses apply to a
test-only diff this narrow; the rest are **N/A — no production code, no
new dependency, no new untrusted input, no naming/shadowing, no roadmap
item touched by this diff.**

- **Ticket fidelity — PASS.** The diff does exactly what the CI failure
  demanded: stub `HotkeyWatcher` for the one subtest that reaches it,
  restore in `finally`, touch nothing else. `docs/implementation.md`'s
  Round 3 section accurately describes the diff; no scope creep (verified
  via `git status --short` → only `tests/test_ui.py` modified, per
  `docs/implementation.md`'s own "Scope check").

- **Tests — PASS.** Verified point 3 above satisfies the protocol's "does
  the test actually fail if you revert the fix" bar via the poison/negative-
  control pair rather than a literal repo revert (a literal revert would
  reproduce the macOS-only `SIGTRAP`, which cannot be reproduced on this
  Linux runner at all — the poison technique is the available substitute and
  demonstrates the same causal fact: the real `start()` is unreached with the
  stub, reached-and-swallowed without it). The stub also correctly keeps
  `_note_save()`'s call reachable on every platform rather than skipping the
  whole subtest on darwin, preserving coverage of the spec's "all five call
  sites" acceptance criterion (`docs/test-review.md` round 1's own note,
  restated in `docs/implementation.md`'s Round 3 rationale) instead of
  trading it away for CI stability.

- **Cross-platform behaviour — PASS, with the caveat the developer already
  states.** The fix cannot be exercised on the actual failing platform in
  this environment (no macOS runner available here) — `docs/implementation.md`
  says so plainly rather than implying coverage that doesn't exist. What
  *can* be confirmed statically holds: the stub's `start()`/`stop()` are
  no-ops regardless of OS, so no platform-specific branch inside
  `HotkeyWatcher.__init__`/`start()` (which constructs a real `kb.Listener`,
  `afk_clicker.py:576`) is ever reached from this subtest on any platform,
  which is precisely the mechanism that was aborting the process on macOS.
  Linux CI (this run) and the developer's prior windows/ubuntu-green runs
  give no reason to doubt the same holds on macOS CI; it is not independently
  provable in this environment, and calling it fully verified would overstate
  what was actually checked.

Everything else — Correctness (no production logic changed), Threading/Tk
safety (no off-main-thread Tk access introduced or moved), Naming/shadowing
(no new names outside the local `_StubHotkeyWatcher`, which does not
shadow anything), Untrusted input (none), Tech stack conformance (no new
dependency), Comments/documentation (the `via_apply_hotkey` comment states
the *why* — cross-references `HotkeyPersistence`'s own class comment rather
than restating the code — consistent with `CODING-GUIDELINES.md`), Roadmap
(nothing on `ROADMAP.md` touched by a CI-only fix) — **N/A, nothing in this
diff to examine under that lens.**

### Findings (round 3)

No must-fix. No should-fix. No nit.

### Overall verdict (round 3)

**Approve.**

The stub closes the macOS abort at its actual mechanism (a real
`kb.Listener` construction/start inside `apply_hotkey()`), independently
re-derived rather than taken on the developer's word: every `hk_listener.`
read after this subtest runs is `.stop()`, which the stub implements;
no other test in this cycle touches `HotkeyWatcher`/`Listener`/
`capture_hotkey`; and an in-process poison-and-negative-control pair proves
both that the stub is genuinely load-bearing (test still passes with the
real `start()` poisoned) and that the alternative the developer considered
and rejected (patching `macos_input_permitted` alone) would not have worked
either (the poison fires and is silently swallowed without the stub, before
ever reaching `_note_save()`). Full suite: 388/388, `OK (skipped=10)`,
matching round 2 exactly with no new test and no regression. No scratch
file was left in the repo (`git status --short` clean before and after this
pass). This build cycle is done — hands back to product-manager for the
next iteration.
