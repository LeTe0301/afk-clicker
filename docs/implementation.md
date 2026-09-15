# Implementation: Review residue from the updater PRs (#19, #31) — G#21/GH#32

## Summary
Four independent review-residue items, all inside `afk_clicker.py` plus its own two test files: `fetch_checksums` now rejects a 64-character token that is not actually hex, closing the one-line parsing gap the ticket named; `_safe_names`'s docstring (and the matching stale comment at `tests/test_updater.py`) now states plainly that zipfile's own extraction has stripped `..`/drive/absolute-path components since Python 3.6.2, so the check is defense-in-depth for zip and the real guard for tar, with zero executable-line change; `check_update`/`_check_worker` gained a `_check_seq`/`_apply_check` sequence-stamp-and-drop-stale-results gate, mirroring `_poll_games`/`_apply_scan`'s existing idiom exactly, closing both the latent supersession race and the separate off-main-thread write of `self._pending`; and `Store.save()` (and `put_game()`) now return `True`/`False` instead of swallowing every `OSError` into an untraceable `None`, with a new `_note_save()`/`_paint_save_notice()` pair surfacing a single, non-repeating, non-blocking notice in Settings → Appearance the first time a save actually fails, clearing it the next time one succeeds, per `docs/design.md`'s exact wording.

## Changes by file

### `afk_clicker.py`
- **Item 1** (~line 794-800), `fetch_checksums`: the `len(parts[0]) == 64` length check is now followed by an all-hex check on the lowered digest before it's accepted into `sums`. No signature change, no caller change, no new import (inline literal `"0123456789abcdef"`, per the spec's own "either is one line of real cost" note).
- **Item 2** (~line 816-830), `_safe_names`'s docstring: rewritten to state the zipfile-since-3.6.2/tarfile-is-the-real-guard split verbatim from `docs/spec.md`'s proposed diff. No executable line touched — `git diff` confirms only docstring lines changed.
- **Item 3** (~lines 2287-2288, 3486-3527): `self._check_seq = 0` added next to `self._poll_seq`/`self._poll_applied_seq`. `check_update()` now bumps `self._check_seq` and passes the captured `seq` into `_check_worker(seq)`; every one of `_check_worker`'s early-return branches (`NoReleases`, unreachable GitHub, not-newer, no-build-for-OS) is unchanged. Its success path now calls a new `_apply_check(seq, tag, asset, release)` via `self._ui(...)` instead of writing `self._pending`/calling `_offer_update` directly — `_apply_check` is the only place `self._pending` is ever written now, always on the main thread, gated by `if seq != self._check_seq: return`.
- **Item 4**:
  - `Store.save()` (~line 1338-1345): returns `True` on a successful `os.replace`, `False` on a caught `OSError` (was `pass`/implicit `None` either way).
  - `Store.put_game()` (~line 1350): returns `self.save()`'s result instead of discarding it.
  - `AfkAutoclicker.__init__` (~line 2291): new `self._save_failed = False`.
  - `_build_settings()` (~line 3034-3041): new `self.save_failed_label` (`tk.Label`, `fg=BAD`, Segoe UI 9.5pt scaled, `wraplength=int(CARD_INNER_W * s)`), created (not packed) right after the UI-scale Row's Segmented, before the existing "System is currently…" label — per `docs/design.md`'s "packed below the UI scale Row" placement.
  - Two new methods, `_note_save(ok)` and `_paint_save_notice()` (~line 3104-3135), placed immediately before `_apply_appearance` — `_note_save` only acts on a change in outcome (docstring states why); `_paint_save_notice` only paints while Settings is open on the Appearance tab, mirroring `_set_update_state`'s own if-not-open-remember-and-return shape.
  - All five existing `self.store.save()`/`self.store.put_game(...)` call sites (`_apply_appearance`, `_apply_ui_scale`, `_select`'s persist branch, `_persist()`, `apply_hotkey`) now route their result through `self._note_save(...)`.
  - `_build_ui()`'s tail, inside the `if self._settings_open:` branch (~line 2688-2694): one new call, `self._paint_save_notice()`, right after the existing `_set_update_state(*overlay)` replay — this is what makes the notice survive a rebuild, including the rebuild a failed `_apply_appearance` save itself triggers.
  - `_set_settings_tab()`'s tail (~line 3349-3358): one new call, `self._paint_save_notice()`, after the existing `_request_pane_fill(value)` — see "Deviations from spec / design" below for why this was added.

### `tests/test_updater.py`
- `Checksums.test_parses_sha256sum_output` (item 1): extended with a `"g" * 64 + "  garbage.zip"` line; asserts `"garbage.zip"` is absent from the returned dict, alongside the existing lowercase/uppercase/too-short assertions (all unchanged).
- `StagingSafety.test_an_entry_escaping_the_directory_is_refused`'s comment (item 2): corrected to match `_safe_names`'s new docstring wording. No assertion changed.

### `tests/test_ui.py`
- Item 3: the two direct `_check_worker` call sites (`SettingsUpdates.test_offer_lands_through_a_real_worker_thread_with_settings_closed`/`_open`) now pass `args=(self.ui._check_seq,)` explicitly. New class `AnOlderCheckResultDoesNotOverwriteANewerOne` (one test), mirroring `AnOlderScanResultDoesNotOverwriteANewerOne`'s deterministic-ordering technique via `threading.Event`, with a controllable `latest_release` that blocks the first (older) check and a `threading.Thread` tracking wrapper (`app.threading.Thread` monkeypatched, restored in `finally`) to get joinable handles for both checks, since `check_update()` — unlike `_poll_games()` — does not stash its own worker thread anywhere.
- Item 4: new class `StoreSaveResult` (3 tests, plain `unittest.TestCase`, no Tk fixture — Store has no UI knowledge) covering `save()`'s True/False return and `put_game()` forwarding it, via the same `app.os.replace` monkeypatch-and-restore seam `DetectOsTheme` already uses. New class `SaveFailureNotice` (6 tests, `UITestCase`): notice appears on a failed `_apply_appearance`; no repaint on a second/third consecutive failure (spies on `_paint_save_notice` directly, per "test the property, not the plumbing"); notice clears on a subsequent real save; notice survives the rebuild the failing save itself triggers; notice stays hidden while a different Settings tab is active and appears once switched to Appearance; and all five save call sites (`_apply_appearance`, `_apply_ui_scale`, `_select(persist=True)`, `_persist()`, `apply_hotkey`) independently set `self._save_failed` when their save fails.

## Key decisions / tradeoffs
- Items 1–3 matched `docs/spec.md`'s proposed diff essentially verbatim — the sequence-stamp idiom for item 3 is copied from `_poll_games`/`_apply_scan` with only the renamed counter/method, exactly as the spec's own judgment call argued for.
- Item 4's `_note_save`/`_paint_save_notice` split, the notice's exact wording/styling, and its Appearance-pane-only scope all came from `docs/design.md` (including its own "Orchestrator correction" wording override, used verbatim: "Couldn't save settings — changes won't be kept after closing").
- All five `Store.save()`/`put_game()` call sites run on the main thread already (`_apply_appearance`/`_apply_ui_scale` are Segmented/trace callbacks; `_select`/`_persist` run from Tk callbacks or `_rebuild_ui()`'s own synchronous teardown; `apply_hotkey` is a Button callback) — verified by reading each call site's caller chain, not assumed. `_note_save`/`_paint_save_notice` therefore touch `self.save_failed_label` directly rather than routing through `self._ui()`/`_drain_ui()`, and this is stated explicitly in `_note_save`'s own docstring so a future caller from a background thread doesn't silently inherit an unsafe assumption.
- The notice label is created inside the `ap` card right after the UI-scale Row's Segmented, ahead of the existing "System is currently…" label — `docs/design.md`'s own placement instruction ("packed below the UI scale Row") didn't account for that pre-existing label, so this keeps the notice adjacent to the control it's about (UI scale/Theme) rather than after an unrelated status line.

## Deviations from spec / design
- **One addition beyond the literal proposed diff**: `_set_settings_tab()` now also calls `self._paint_save_notice()` at its own tail. Neither `docs/spec.md`'s "Affected areas" nor `docs/design.md`'s "Placement in the code structure" names this call site. It was added after a test (`SaveFailureNotice.test_notice_is_not_shown_while_a_different_settings_tab_is_active`) found a real gap: a save failure that happens while Settings is open on the *Updates* tab sets `self._save_failed = True`, but `_paint_save_notice()` returns early (Appearance isn't active) and never packs the label — and switching to the Appearance tab afterward via `_set_settings_tab()` (which only toggles `pack`/`pack_forget` on the two already-built, already-existing panes, not a rebuild) never re-checked the flag, so the notice stayed invisible until the next full rebuild. `docs/design.md`'s own "Failure while Appearance pane is closed" scenario states the notice must appear "the next time the user opens Settings and navigates to (or is already on) Appearance" — read literally, "navigates to" covers a tab switch while Settings stays open, not only a fresh open-from-closed. The fix is one line, mirrors the existing `self._request_pane_fill(value)` call already at that exact tail for the identical reason (react to whichever tab just became active), and stays inside the one file both `docs/spec.md` and `docs/design.md` already scope this item to. Flagged here rather than silently added, per "faithful scope adherence."
- No other deviation. Items 1–3 and the rest of item 4 match `docs/spec.md`'s "Proposed approach" and `docs/design.md`'s code samples line for line, including the design doc's own "Orchestrator correction" section overriding the notice's wording.

## Known limitations
- `_note_save`/`_paint_save_notice` assume every call site runs on the main thread, stated as a design constraint in `_note_save`'s own docstring rather than enforced by an assertion — if a future save call site is added from a background thread, this would need routing through `self._ui()`/`_drain_ui()` first, the same way `_apply_check` now is for item 3's `self._pending` write.
- Item 3's fix narrows an already-unreachable-in-production race (no call site bypasses the button today) rather than adding a new capability; `install_update`/`_install_worker`, which read `self._pending` directly, are unchanged and untested further here, per the spec's own edge cases.
- The pre-existing `ResourceWarning`s emitted by `tests/test_updater.py` (unclosed files at lines 454/693/711/730/747/760/771/775, and inside `Checksums`'s own two tests) are unrelated to this diff — `git diff` confirms none of those lines changed — and were already present on `main`.

## Pre-existing, unrelated flake observed
- `test_resolves_the_highest_version` (a live-network test comparing `app.latest_release()` against the real GitHub API's `/releases/latest`) failed once, at this session's very first baseline run before any change was made (`'v0.6.0' != 'v0.7.0'` — a real release published on GitHub between whenever the documented 375-test baseline was captured and this session), and passed on every later run in this session, including the final full-suite run below. Confirmed pre-existing/environmental drift in the live repository state, not caused by anything in this diff — no file this test touches is part of this cycle's changes.

## How to verify locally
Environment (this repo's convention: venv + Xvfb `:99`, confirm nothing else is running first):
```
pgrep -a Xvfb            # :99 should already be up
pgrep -af "[u]nittest"   # nothing else running
cd /home/dev/projects/afk-clicker
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```

### Per-item test runs (this session)
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_updater.Checksums -v
# 4 tests, OK

DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.SettingsUpdates tests.test_ui.AnOlderCheckResultDoesNotOverwriteANewerOne -v
# 9 tests, OK

DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.StoreSaveResult tests.test_ui.StoreMigration tests.test_ui.SaveFailureNotice -v
# 22 tests, OK
```

### Sabotage-verify performed this session

**Item 3** — an in-process monkeypatch script (scratchpad-only, never written to `afk_clicker.py` on disk, per this repo's "prefer an in-process monkeypatch over editing the file" convention) replaced `AfkAutoclicker._apply_check` with a version that drops the `seq != self._check_seq` guard entirely, then re-ran the new regression test against the patched class:
```
FAIL: test_an_orphaned_older_check_landing_later_is_dropped
AssertionError: 'v8.0.0' != 'v9.9.9'
```
Confirms the guard is load-bearing. `git diff afk_clicker.py` after this session shows only the intended changes — the sabotage never touched the file.

**Item 4** — same technique, replacing `AfkAutoclicker._note_save` with a version that always calls `_paint_save_notice()` (no change-detection), then re-ran `test_no_repaint_on_a_second_consecutive_failure`:
```
FAIL: test_no_repaint_on_a_second_consecutive_failure
AssertionError: 3 != 1 : a second/third consecutive failure repainted the notice
```
Confirms the change-detection guard is load-bearing. `git diff afk_clicker.py` unaffected.

### Full suite result (this session, final state)
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 385 tests in 99.791s

OK (skipped=10)
```
385 = the documented 375-test baseline + 10 new tests this cycle (1 for item 3, 3 + 6 = 9 for item 4's `StoreSaveResult`/`SaveFailureNotice`). Same skip count as the baseline.

### Verification of scope
```
git status --short
 M afk_clicker.py
 M tests/test_ui.py
 M tests/test_updater.py
?? docs/design.md
?? docs/spec.md
```
No file outside `afk_clicker.py`, `tests/test_updater.py`, `tests/test_ui.py` was touched (`docs/implementation.md` itself is this document); no scratch file was left in the repo tree — the two sabotage scripts used above lived only in the session's own scratchpad directory and were deleted immediately after use.

## Round 2

`docs/test-review.md`'s testing pass came back **Blocked** on one must-fix (Defect 1) and one should-fix (Finding 2). Both are addressed in this round.

### Defect 1 — `_paint_save_notice()` touching a widget that isn't part of the live tree

**Root cause, restated precisely:** `_note_save()`'s repaint call and `_rebuild_ui()`'s own leading `self._persist()` flush share the same window — the moment between "the old widget tree is being (or is about to be) torn down" and "the new tree, including a fresh `self.save_failed_label` if `self._settings_open`, exists." `_persist()` runs inside that window on every rebuild (`afk_clicker.py:2783`, before `_build_ui()` runs at `afk_clicker.py:2823`), and if the save it triggers changes `self._save_failed`'s value, `_note_save()` used to repaint immediately — reaching `self.save_failed_label` either before it has ever been created (Path A: first-ever `_show_settings()` this session) or after the previous generation's widget was already destroyed by this same rebuild's teardown loop (Path B: Settings opened once, closed — which itself rebuilds and destroys the label — then reopened after a save failed while it was closed). A bare `hasattr(self, "save_failed_label")` guard would only catch Path A: the attribute exists and points at a real (if dead) Tk object in Path B, so `hasattr` is `True` and the call still reaches `.pack()`/`.pack_forget()` on a destroyed widget, raising `TclError`.

**Fix:** `_note_save()` (`afk_clicker.py:3104-3129`) now records `self._save_failed`'s new value unconditionally (as before), but skips the immediate repaint whenever `self._rebuilding` is `True`:
```python
if ok == (not self._save_failed):
    return
self._save_failed = not ok
if self._rebuilding:
    return
self._paint_save_notice()
```
`self._rebuilding` (already existing, set for the duration of `_rebuild_ui()`'s own body, `afk_clicker.py:2781/2827`) is exactly the flag that is `True` throughout the leading `_persist()` flush and `False` everywhere else `_note_save()` is ever called from (every one of the five call sites' *other* triggers — a live Segmented click, a hotkey Button click, a keystroke trace outside of a rebuild — runs with `_rebuilding` already `False`). `_build_ui()`'s own tail (`afk_clicker.py:2693`) still calls `self._paint_save_notice()` directly, not through `_note_save()`, and unconditionally — it runs *inside* `_rebuild_ui()`'s body too (so `self._rebuilding` is still `True` there), but by that point `_build_ui()` has already (re)built the tree, including a fresh `self.save_failed_label` if `self._settings_open`, so painting there is always safe. This is why the fix lives in `_note_save()`'s gate, not in `_paint_save_notice()` itself — `_paint_save_notice()` stays exactly as before, and the one caller that must always run (the tail) is untouched.

**Why this closes both paths:**
- **Path A** (no Settings ever opened, save fails, `_show_settings()` called): `_show_settings()` sets `self._settings_open = True` then calls `_rebuild_ui()`; the leading `_persist()` fails, `_note_save(False)` records the flag but returns early (`self._rebuilding` is `True`) instead of touching `self.save_failed_label`, which doesn't exist yet. `_build_ui()` then runs (still inside `_rebuild_ui()`), builds `_build_settings()` (creating the label fresh), and its own tail calls `_paint_save_notice()` unconditionally — which now finds a real widget and paints the notice.
- **Path B** (Settings opened once, closed, save fails while closed, Settings reopened): the close (`_select(..., persist=False)`, which itself rebuilds without a Settings pane) destroys the old label; `self.save_failed_label` is left pointing at a destroyed widget. Reopening via `_show_settings()` runs the identical leading-`_persist()`-inside-`_rebuild_ui()` sequence as Path A — `_note_save()`'s `_rebuilding` guard means the destroyed widget is never touched at all, regardless of whether the attribute still resolves to a (dead) Tk object. `_build_ui()`'s tail then builds a fresh label and paints it, same as Path A.

Both paths funnel through the exact same `_rebuilding`-gated code path, so one guard closes both without needing to distinguish "doesn't exist" from "exists but destroyed" — the two failure modes the two paths produce.

**Checked, per the reviewer's own list:**
- The first `_build_ui()` call from `__init__`: `self._rebuilding` is `False` there (`__init__` calls `_build_ui(s)` directly, never through `_rebuild_ui()`), and `self._settings_open` is `False` by default, so `_build_ui()` takes the `_build_content()` branch and never reaches `_paint_save_notice()`/`_build_settings()` at all — no `save_failed_label` exists yet, and nothing tries to touch it.
- The startup `apply_hotkey` → `save` path (`__init__`, after the first `_build_ui()` call returns): `self._rebuilding` is `False` here too (the first rebuild, if any, hasn't started), so if this save fails, `_note_save()` calls `_paint_save_notice()` directly — which returns early via its own existing `self._settings_open` guard (still `False` at this point in `__init__`) before ever touching the label. Confirmed safe, matching the reviewer's own test case 14.

### Regression tests added (`tests/test_ui.py`, `SaveFailureNotice`)

- `test_no_crash_the_first_time_settings_is_ever_opened_after_a_save_already_failed` — breaks `app.os.replace` before Settings has ever been opened this session, then calls `self.ui._show_settings()` directly (Path A). Asserts no exception and `self.ui.save_failed_label.winfo_ismapped()` is `True` afterward.
- `test_no_crash_reopening_settings_after_a_save_fails_while_settings_is_closed` — opens Settings (creating the label), closes it via `self.ui._select(self.ui.current, persist=False)` (asserts the old label is actually destroyed, confirming the test exercises the intended precondition), breaks saves, then reopens Settings (Path B). Asserts no exception and the (freshly created) label is mapped afterward.

**Confirmed failing against the round-1 code, before this round's fix** (ran both directly, this session):
```
ERROR: test_no_crash_the_first_time_settings_is_ever_opened_after_a_save_already_failed
AttributeError: 'AfkAutoclicker' object has no attribute 'save_failed_label'
  (raised from afk_clicker.py:3133, _paint_save_notice, via _note_save via
  _persist via _rebuild_ui via _show_settings — exact match to Defect 1's
  own repro)

ERROR: test_no_crash_reopening_settings_after_a_save_fails_while_settings_is_closed
_tkinter.TclError: bad window path name ".!frame4.!frame3.!frame.!frame2.!canvas.!frame.!label"
  (raised from the same call chain, on the second _show_settings() call --
  the destroyed-widget case Defect 1's Path B describes)
```
Both pass after the fix (`DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.SaveFailureNotice -v` → 8/8 `ok`).

### Finding 2 — `_check_worker`'s non-offer branches weren't seq-gated

**Fix:** a new gate method, `_apply_check_state(seq, text, enabled=True, colour=None)` (`afk_clicker.py:3516-3527`), mirrors `_apply_check()`'s existing `if seq != self._check_seq: return` guard and then delegates to the unchanged `_set_update_state(text, enabled, colour)`. `_check_worker`'s four early-return branches (`NoReleases`, unreachable GitHub, not-newer, no-build-for-OS) now route through `self._ui(self._apply_check_state, seq, ...)` instead of `self._ui(self._set_update_state, ...)` directly — one gate method, one changed call per branch, matching the spec's own "keep the diff small" instruction. `check_update()`'s own synchronous `self._set_update_state("Checking…", enabled=False)` call (main thread, before the worker even starts) is untouched — it isn't a worker-thread result, so there's nothing stale for it to guard against.

### Regression test added (`tests/test_ui.py`, new class `AnOlderNonOfferCheckResultDoesNotOverwriteANewerOffer`)

`test_an_orphaned_older_up_to_date_result_landing_after_a_newer_offer_is_dropped` — mirrors `AnOlderCheckResultDoesNotOverwriteANewerOne`'s deterministic-ordering technique (a blocked-until-released older worker, a `_TrackingThread` wrapper for joinable handles): the older check's `latest_release()` blocks, then resolves to a release `is_newer` says is *not* newer (drives the "Up to date" branch); the newer check resolves immediately to a release that *is* newer (drives a real offer, landing and being applied first). Once the older worker is released and lands last, asserts `self.ui._pending[0]` is still `"v9.9.9"` and `self.ui._update_text[0]` still starts with `"Install"` — the orphaned older "Up to date" message must not have overwritten either.

**Sabotage-verify performed this session** (in-process monkeypatch, scratchpad-only, never written to `afk_clicker.py` on disk): replaced `AfkAutoclicker._apply_check_state` with a version that calls `_set_update_state` unconditionally, dropping the `seq` guard, then re-ran the new test against the patched class:
```
FAIL: test_an_orphaned_older_up_to_date_result_landing_after_a_newer_offer_is_dropped
AssertionError: False is not true : an orphaned older check's stale 'Up to
date' message must not overwrite a newer, already-applied offer's button
text
```
Confirms the guard is load-bearing. `git status --short`/`git diff` after this session show only the intended changes to `afk_clicker.py`/`tests/test_ui.py` — the sabotage script never touched a repo file and was deleted from the scratchpad immediately after use.

### Full suite result (this round, final state)
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 388 tests in 99.146s

OK (skipped=10)
```
388 = round 1's own 385 + 3 new tests this round (2 for Defect 1, 1 for Finding 2). Same skip count as round 1 and the original baseline. The pre-existing `ResourceWarning`/`invalid command name "..._drain_ui" (after script)` noise, already documented as unrelated in round 1, is unchanged. The one pre-existing live-network flake (`test_resolves_the_highest_version`) did not flake this run.

### Scope check (this round)
```
git status --short
 M afk_clicker.py
 M tests/test_ui.py
 M tests/test_updater.py
```
(`tests/test_updater.py`'s diff is unchanged from round 1 — nothing in this round touches it.) No file outside the four already declared in round 1 (`afk_clicker.py`, `tests/test_updater.py`, `tests/test_ui.py`, `docs/design.md`) was touched; no scratch file was left in the repo tree.

### Deviations from spec / design (round 2)
None. Both fixes are exactly what `docs/test-review.md` asked for: Defect 1's must-fix (an ordering fix, chosen over a bare `hasattr` guard because the reviewer's own Path B shows `hasattr` alone doesn't close it) and Finding 2's should-fix (one gate method, following the `_apply_scan`/`_apply_check` precedent, exactly as suggested).
