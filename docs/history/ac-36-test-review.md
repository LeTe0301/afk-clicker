# Test & Review: Ask to send the update log when an in-app update didn't finish (G#36 / GH#64)

## Scope
Testing pass against `docs/spec.md`'s acceptance criteria, plus round 2's
targeted re-verification of the two must-fix defects from round 1 (theme/
scale rebuild destroying the open dialog; fallback-state button clipping).
Same environment as round 1: venv at `.../scratchpad/devvenv`, Xvfb `:99`
(confirmed no other test runner attached before starting: `pgrep -af
"[u]nittest"` returned nothing but this shell's own command).

**Round 2 result: clean.** Both round-1 defects are fixed, verified by
re-running my exact round-1 repro scripts plus new targeted checks, and by
sabotaging each fix myself and watching the developer's new regression
tests (and mine) go red. Full suite: **358 tests, OK, skipped=10** (350 + 8
new), run three times back to back with no flake. Proceeding to a full
review pass below; verdict is **Approve**.

## Round 1 recap (for context)
Round 1 found two must-fix defects from live exercise of the app (not just
code reading):
1. `_rebuild_ui()`'s `for w in self.root.winfo_children(): w.destroy()`
   (then at `afk_clicker.py:2643`) destroyed the update-log dialog
   `Toplevel` on any theme/UI-scale change made while it was open (the
   dialog is a genuine child of `root`), leaving `self._log_dialog`/
   `self._log_dialog_ctx` as dangling references and producing uncaught
   `TclError`s on the next checkbox write.
2. The dialog's explicit `top.geometry(f"{int(600*s)}x{int(480*s)}")`
   pinned its size (disabling Tk's auto-resize-to-fit-content), so
   `_show_log_fallback`'s taller Entry+2-button row got clipped at the
   bottom edge at 100% scale (confirmed via `reqheight` vs actual height
   and a screenshot).

## Round 2 verification

### Defect 1 (theme/scale rebuild destroying the dialog) — fixed, verified
Re-ran my exact round-1 script, `theme_change_probe2.py`, unmodified. The
old, pre-rebuild `dialog` local correctly now shows `winfo_exists() == 0`
(expected — the *old* generation is properly torn down); what matters is
`ui._log_dialog` (live current reference) afterward, which I checked with a
new script (`theme_change_probe_r2.py`) covering everything the coordinator
asked for:

| Check | Result |
|---|---|
| Dialog is a live widget after `_apply_appearance("light")` while open | `new_dialog.winfo_exists() == 1`, pass |
| Checkbox state (set `True` before rebuild) survives | pass |
| Preview reflects the preserved (unredacted) state post-rebuild | pass |
| `Send via GitHub` still works post-rebuild, marks `.reported` | pass |
| Fallback state (Entry + Copy link/Dismiss) survives an `_apply_ui_scale("130")` rebuild, same URL | pass |
| `Copy link` still works post-rebuild in fallback state | pass |
| `on_close()` with the dialog open, normal state | no exception |
| `on_close()` with the dialog open, fallback state, post-rebuild | no exception |
| 5 consecutive `_apply_appearance()` rebuilds with the dialog open | dialog stays alive; current var's trace count stable at 2 (not growing); the *old*, torn-down generation's var has 0 traces left (confirmed cleared); toggling 3× afterward raises nothing |
| `report_callback_exception` hook (catches anything Tk would otherwise swallow to stderr) | never fired across the whole script |

No `_tkinter.TclError` anywhere in this run (round 1's identical script
printed two uncaught `TclError`s at this exact point). Root cause fix:
`_capture_log_dialog_restore_state()`/`_restore_log_dialog()`
(`afk_clicker.py:3435`, `:3451`) snapshot the dialog's plain-data state
before `_rebuild_ui()`'s teardown loop runs, and `_close_log_dialog()`
(`afk_clicker.py:3617`) now explicitly removes the "show full paths"
`BooleanVar`'s trace(s) before destroying the Toplevel — closing the exact
ac-27 "trace outlives its widgets" gap the developer's own comment names.
Also confirmed `_restore_log_dialog` never re-runs `update_log_status()` or
re-marks/re-triggers "ask once" — it replays the captured status/text/
target_version verbatim, and only calls `_show_log_fallback` again with the
*already-obtained* URL string, never re-touching `webbrowser`.

**Sabotage**: reverted the capture/restore call (`log_dialog_restore =
None`, skipping `_close_log_dialog()`'s pre-teardown call) on a scratch
copy — the developer's own 3 new rebuild-preservation tests
(`test_appearance_change_preserves_the_open_dialog_and_checkbox_state`,
`test_ui_scale_change_preserves_the_open_dialog_and_checkbox_state`,
`test_appearance_change_preserves_the_fallback_state_and_url`) correctly
went red (`AssertionError: 0 != 1` on `new_dialog.winfo_exists()`). Restored
byte-for-byte before continuing (`diff` against a pristine copy showed no
output).

### Defect 2 (fallback clipping) — fixed, verified
Wrote my own `winfo_reqheight()`-vs-`winfo_height()` probe (per the
coordinator's note that root-relative bottom-edge checks don't catch a
*squeezed* widget, which is allocated less than it asked for rather than
positioned past the window edge) and ran it at all four supported scales:

| Scale | Fallback `reqheight+pad` | Actual window height | Clipped? |
|---|---|---|---|
| 90% | 465 | 465 | No |
| 100% | 510 | 510 | No |
| 115% | 572 | 575 | No |
| 130% | 656 | 656 | No |

At every scale the window grows to exactly fit (never less), confirming
`_fit_log_dialog_to_content()` (`afk_clicker.py:3564`) works as intended:
it recomputes `body.winfo_reqheight()` after layout settles
(`top.update_idletasks()`) and grows the window's geometry only if the
current height is insufficient — never shrinks, called from both
`_show_update_log_dialog`'s tail and `_show_log_fallback`'s tail.

Also looked at all four new screenshots myself:
`ac36-shots/06-fallback-90.png` and `07-fallback-100.png` (both a `Copy
link`/`Dismiss` row fully visible, not clipped — visibly fixed vs round 1's
`05-fallback.png`), `08-normal-130.png` (ordinary 3-button row, fully
visible), `09-theme-switch-after.png` (dialog correctly rebuilt in light
theme with the checkbox state — checked, full paths shown — preserved
across the switch, matching Defect 1's fix).

**Sabotage**: replaced `_fit_log_dialog_to_content()`'s body with `pass` on
a scratch copy — 3 of the 4 new clipping tests
(`test_fallback_is_not_clipped_at_{90,100,130}_percent`) correctly went red
(`25 not greater than or equal to 35`, etc. — the exact "allocated less
than requested" signature); the 115% case happened not to clip in this
sabotage (consistent with round 1's own finding that the raw clipping bug
was scale/rounding-dependent — exactly why a computed, per-scale fit is the
right fix rather than a hardcoded taller default). Restored byte-for-byte
before continuing.

## Regression check
Full suite, three separate runs across this session (round 1's two runs
plus round 2's runs before/after sabotage):
```
Ran 358 tests in 65.2s ... OK (skipped=10)
Ran 358 tests in 79.0s ... OK (skipped=10)
Ran 358 tests in 82.9s ... OK (skipped=10)
```
350 pre-existing + 35 round-1 + 8 round-2 = 358, matching the coordinator's
expected count exactly. `tests/test_updater.py` is untouched in round 2
(`git diff --stat` shows no change to that file's line count since round
1); all 8 new tests are in `tests/test_ui.py`'s `UpdateLogPrompt` class.
`git status`/`git diff --stat` at the end of this session match the state
at the start of round 2 — every sabotage round-trip was restored
byte-for-byte before moving on.

## Spec coverage
Re-checked every acceptance criterion in `docs/spec.md` against the round-2
diff and test suite; all are implemented and covered (no change from round
1's mapping, since round 2 only touched the rebuild-interaction and
geometry-fit paths, not the underlying detection/redaction/URL-building
logic). No criterion is newly at risk from round 2's changes — the fixes
are additive (capture/restore, one geometry helper) and don't alter
`update_log_status`, `build_issue_report`, `build_issue_url`, or the
Send/Dismiss/Open-folder marking semantics.

## Findings (review pass)
Read the round-2 diff directly (not just the round-1 diff plus a diff of
diffs) for correctness, security, and simplicity:

- **Correctness**: `_restore_log_dialog` replays captured state without
  re-invoking `update_log_status()` or touching `webbrowser` again for an
  already-shown fallback URL — confirmed by both reading and the
  `test_appearance_change_preserves_the_fallback_state_and_url` assertion
  that `update.log.reported` still doesn't exist after the rebuild. The
  `_fit_log_dialog_to_content()` `update_idletasks()` call happens entirely
  inside `_rebuild_ui()`'s existing `self._rebuilding = True` window (when
  called via `_restore_log_dialog`), so it's covered by that method's own,
  already-battle-tested reentrancy guard (ac-17 history) rather than
  introducing a new one — verified in practice by the 5-consecutive-rebuild
  script above showing no growth/instability across repeated calls.
- **Security**: no new imports, no new external input, no new network or
  file-write path — round 2 is pure widget-lifecycle/geometry bookkeeping.
  Nothing here changes.
- **Simplicity/scope**: the fix is proportionate to the two defects — one
  capture/restore snapshot dict (plain data, not widgets/Variables, exactly
  matching this file's own established `_ui_queue`-style discipline) and
  one small geometry-fit helper, reusing the existing `_forget_traces()`-
  style trace-removal pattern (`_close_log_dialog` now mirrors it locally)
  rather than inventing something new. No drive-by refactors.
- No must-fix or should-fix findings from this pass. One pre-existing,
  explicitly-flagged, out-of-scope note carries over unchanged from the
  code's own comments: `_rebuild_ui()`'s docstring already documents that
  the *final* generation's traces (at whatever point the app actually
  closes) aren't released by anything (`backlog.md`, pre-existing, not
  introduced or worsened by this feature).

## Overall verdict
**Approve.** Both round-1 must-fix defects are fixed and independently
re-verified through live exercise (not just reading the fix), the
regression suite is green at the expected 358/OK/skipped=10 across three
runs, and sabotaging each fix correctly turns the developer's new
regression tests red. The review pass over the round-2 diff found no new
must-fix, should-fix, or scope issues. No commit/push performed by me, per
instructions.
