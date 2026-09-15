# Implementation: Ask to send the update log when an in-app update didn't finish (G#36 / GH#64)

## Summary
At startup, if the previous in-app update's `update.log` shows it died
part-way or silently relaunched the old build, a one-off `tk.Toplevel`
dialog now offers a redacted preview of what would be reported and lets the
person open a prefilled GitHub issue, dismiss, or open the log's folder —
never sending or contacting anything on its own. Detection, redaction and
the issue-report/URL builder are pure, Tk-free functions; the dialog itself
is new `AfkAutoclicker` methods plus one new reusable canvas checkbox.

## Changes by file

- `afk_clicker.py`
  - New imports: `platform`, `urllib.parse`, `webbrowser`.
  - `write_swap_script(staged, target, relaunch, log_path, target_version=None)`
    — new keyword-only, default-`None` parameter. When given, the `start`
    line gains a trailing ` version="{target_version}"` on both the `.cmd`
    and `.sh` variants; omitted, the line is byte-identical to before (all
    5 pre-existing test call sites needed no change). The `.sh` branch's
    echo line is itself one big double-quoted shell string, so its version
    suffix uses escaped `\"` (a separate `sh_version_suffix`) — an
    unescaped `"` there closed the string early and silently dropped the
    quotes from the logged value; caught by
    `SwapScriptLogLifecycle.test_target_version_recorded_on_the_start_line_when_given`
    during TDD, see "Key decisions" below.
  - `_install_worker` (the `write_swap_script` call) — now passes
    `target_version=tag`.
  - New module-level functions, placed directly after `write_swap_script`
    (before `launch_swap_script`): `read_update_log`, `_extract_target_version`,
    `update_log_status`, `_redact_home`, `build_issue_url`,
    `build_issue_report`. All pure / file-I/O only, no Tk, no network.
  - New `ToggleCheckbox(tk.Canvas)` class (placed after `Segmented`, before
    `TabBar`) — this file's first checkbox, canvas-drawn to match
    `Button`/`Segmented`'s existing style rather than the native
    `tk.Checkbutton`.
  - `AfkAutoclicker.__init__` — three new instance attributes
    (`self._log_dialog`, `self._log_dialog_ctx`, `self._log_dialog_show_paths_var`,
    all `None`) and, at the very tail,
    `self.root.after_idle(self._maybe_offer_log_report)`.
  - New `AfkAutoclicker` methods: `_maybe_offer_log_report`,
    `_show_update_log_dialog`, `_fit_log_dialog_to_content` (round 2),
    `_current_log_report`, `_refresh_log_preview`, `_mark_log_reported`,
    `_close_log_dialog`, `_on_log_dismiss`, `_on_log_open_folder`,
    `_on_log_send`, `_show_log_fallback`, `_on_log_copy_link`,
    `_capture_log_dialog_restore_state` (round 2), `_restore_log_dialog`
    (round 2).
  - `on_close()` — calls `_close_log_dialog()` if the dialog is still open,
    before the existing teardown sequence; round 3: also cancels
    `self._log_report_after_id` the same way `_rebuild_after_id`/
    `_pane_fill_after_id` are.
  - `_rebuild_ui()` — round 2: captures the update-log dialog's restorable
    state and closes it *before* its own teardown loop runs (which would
    otherwise destroy it as a byproduct, leaving dangling references), then
    rebuilds it, in the new theme/scale, at its own tail. See "Round 2"
    below for the full story.
  - Round 3: `AfkAutoclicker.__init__` — new `self._log_report_after_id`
    instance attribute; the startup `after_idle(self._maybe_offer_log_report)`
    call now stores its id there instead of discarding it.
    `_maybe_offer_log_report()` — its one widget-touching call
    (`_show_update_log_dialog(...)`) is now wrapped in `try/except
    tk.TclError: pass`, belt-and-braces against a stray fire post-teardown.
    See "Round 3" below.
  - Round 4 (security): `_is_safe_version_tag(tag)` (new, placed directly
    after `is_newer`) — validates a tag against this project's own
    `vX.Y.Z` release shape. `_install_worker` now computes
    `safe_target_version = tag if _is_safe_version_tag(tag) else None`
    and passes *that* to `write_swap_script`, never the raw `tag`. See
    "Round 4" below.

- `tests/test_updater.py`
  - `import urllib.parse` added.
  - `SwapScriptWindowsCmdText` — 2 new tests: no `version=` suffix by
    default; `version="v0.7.0"` present when `target_version` is passed.
  - `SwapScriptLogLifecycle` — `_write_script_in_subprocess` gained an
    optional `target_version` parameter; 2 new tests mirroring the above
    for the `.sh` script, run end-to-end via `/bin/sh`.
  - New `UpdateLogDetection` class (9 tests) — `read_update_log`/
    `update_log_status` for all three states (`ok`/`incomplete`/
    `wrong_version`), the 1 MiB tail cap, and non-UTF-8 byte handling.
  - New `IssueReportBuilder` class (9 tests) — title/body shape, the
    "unknown (older log format)" fallback, default redaction and
    `redact=False`, the URL round-trip, and the 2000-char cap with
    oldest-line-first truncation.
  - Round 4 (security): new `SafeVersionTag` class (6 tests) —
    `_is_safe_version_tag` accepts this project's own tag shape, rejects
    shell metacharacters, an oversized tag, the wrong number of
    dot-separated parts, non-digit parts, and non-string/empty input.

- `tests/test_ui.py`
  - `import urllib.parse` added.
  - New `UpdateLogPrompt` class (13 tests, `@needs_display`) — not built on
    `UITestCase` (that class's own `setUp()` already constructs the UI
    before a test can write `update.log`). Covers: no dialog for no
    log/`done`-matching-version logs; dialog for `incomplete`/
    `wrong_version`; Escape dismisses and marks `.reported`; a dismissed
    log stays dismissed on a fresh `AfkAutoclicker` against the same
    settings dir; the checkbox live-updates the preview; `Send via GitHub`
    calls a stubbed `webbrowser.open` with a URL ≤ 2000 chars whose
    decoded title+body exactly reconstruct the visible preview, and marks
    the log reported; the fallback (stubbed `webbrowser.open` returning
    `False` or raising) leaves the dialog open with a copyable URL; `Copy
    link` populates the clipboard; `Open log folder` does not mark the log
    reported and Dismiss still works afterward in the same session.
  - Round 2: 8 more tests in the same class —
    `test_appearance_change_preserves_the_open_dialog_and_checkbox_state`,
    `test_a_stray_reference_to_the_pre_rebuild_ctx_does_not_raise`,
    `test_ui_scale_change_preserves_the_open_dialog_and_checkbox_state`,
    `test_appearance_change_preserves_the_fallback_state_and_url`, and
    `test_fallback_is_not_clipped_at_{90,100,115,130}_percent` (via a
    shared `_assert_fallback_not_clipped` helper). See "Round 2" below.
  - Round 3: 2 more tests in the same class —
    `test_on_close_before_the_startup_idle_job_ever_ran_cancels_it`
    (mirrors `OverlappingAppearanceChanges`'s own `after info` technique
    for `_rebuild_after_id`) and
    `test_maybe_offer_log_report_swallows_a_tclerror_from_a_torn_down_root`.
  - Round 4 (security): 3 new tests in the existing `InstallWorker` class
    — `test_a_shell_metacharacter_tag_never_reaches_write_swap_script`,
    `test_an_oversized_tag_never_reaches_write_swap_script`,
    `test_a_normal_release_tag_still_reaches_write_swap_script_unchanged`
    (via a shared `_install_worker_with_tag(tag)` helper that fakes
    `fetch_checksums`/`download_and_stage`/`write_swap_script` and drives
    `_install_worker()` directly, the same technique the class's two
    existing tests already use).

## Key decisions / tradeoffs

- **Log path uses `self.store.path`, not the bare `config_path()`
  `_install_worker` calls.** Identical value in production (`Store()` with
  no override *is* `config_path()`), but it is the only way a whole
  `AfkAutoclicker` can be pointed at a temp settings directory in tests
  (`app.Store(self.config)`, the same isolation `UITestCase` already uses)
  without this feature ever touching a real machine's actual settings
  directory. Documented inline at `_maybe_offer_log_report`.
- **Theme-change handling — CORRECTED in round 2 (see "Round 2" section
  below).** This bullet originally claimed *"the dialog is left in its
  build-time colours, not rebuilt or closed on a theme change"* and that
  this was a deliberate, verified-safe design decision. That claim was
  never actually tested and was false: the dialog is a genuine child of
  `root` (`tk.Toplevel(self.root, ...)`), so `_rebuild_ui()`'s teardown
  loop destroys it like every other child, and the app follows the
  *system* theme, so this isn't even a narrow window gated behind
  Settings — an OS dark/light switch can trigger it with nobody touching
  the app. The reviewer's testing pass caught this live (test-review.md
  round 2 Defect 1); it is now rebuilt with its state preserved. Left here
  rather than deleted so the mistake (asserting a behavior without
  exercising it) is visible, not quietly erased.
- **Version-field extraction uses plain string search
  (`_extract_target_version`), not `re`.** `_version_tuple` a few lines
  above already sets this file's own precedent for hand-parsing an ad hoc
  field rather than reaching for a new regex dependency; `_redact_home`
  follows the same style for the same reason.
- **`build_issue_report` returns `(title, body)`; a separate
  `build_issue_url(title, body)` builds the URL.** The 2000-char cap
  applies to the *encoded URL*, so the truncation loop inside
  `build_issue_report` calls `build_issue_url` to measure candidate
  lengths, but the public two-value return matches the spec's own
  signature and lets the dialog/tests build the exact same URL from the
  exact same (title, body) shown on screen.
- **`ToggleCheckbox` hover, checked state:** stays `CARD_HI` (no separate
  darker shade) instead of design's suggested "slightly darker" checked
  hover — this file has no existing color-darkening helper (only
  `_lighten`), and inventing one for a single hover microstate seemed like
  more new surface than the visual gain justified. Both states still pass
  every contrast pairing in the design doc's table; only the extra hover
  affordance on an already-checked box is reduced.
- **A genuine bug caught by TDD:** the `.sh` script's `version=` suffix
  originally used unescaped `"` inside an already-double-quoted shell
  string; the shell silently ate the quotes (`version="v0.7.0"` came out
  as `version=v0.7.0`). Caught red by
  `SwapScriptLogLifecycle.test_target_version_recorded_on_the_start_line_when_given`
  before the code was "fixed" to pass — see that test and the
  `sh_version_suffix` comment in `write_swap_script`.
- **A genuine layout bug caught by TDD:** the preview `tk.Text` had no
  explicit `height`, so its default 24-row request ate the entire
  dialog's vertical budget, silently squeezing the checkbox/button rows to
  0px — still packed, never mapped, so no click could ever reach them.
  Caught by the first UI test that tried to click a button
  (`event_generate` landed on an unmapped widget and did nothing). Fixed
  with an explicit `height=12`.
- **A Tk flake found only deep in the full suite, not in isolation:** the
  fallback URL `Entry` was originally built with `textvariable=` (a
  `tk.StringVar`). Its initial sync from the variable was reliably correct
  when the test ran alone, but reliably blank when run after ~300 other
  tests in the same process (reproduced repeatedly; root cause not
  conclusively pinned down — plausibly some Tcl-interpreter-scale
  behaviour change after thousands of widgets/variables have been created
  and destroyed across the suite, since `tests/context.py` already
  documents this suite's own GC-disabled-for-Tk-safety posture). Fixed by
  inserting the URL text directly and then setting `state="readonly"`,
  which needs no variable, no trace and no sync step at all — verified
  green across two consecutive full `test_ui.py` runs (238/238) after the
  change. Noted here rather than filed as a mystery: the fix removes the
  entire class of failure regardless of its exact mechanism, and the
  simpler, variable-free technique is arguably the more idiomatic choice
  for a static read-only field anyway.

## Deviations from spec

- None substantive. `build_issue_report`'s two-value return plus a
  separate `build_issue_url` (rather than the URL living inside
  `build_issue_report` itself) is an implementation-detail split, not a
  behavioral deviation — spec section 6 describes both the (title, body)
  shape and the URL's construction/cap without mandating they be the same
  function.
- The `ToggleCheckbox` checked-hover shade (see "Key decisions") is a
  minor, called-out simplification versus design.md's "slightly darker
  shade" suggestion, not a spec deviation — design.md itself lists this as
  one of two "alternative designs considered" trade-offs already.

## Known limitations

- **Windows OEM code page.** `read_update_log` decodes as UTF-8 with
  `errors="replace"`, so a non-ASCII username in a Windows-written log can
  render as `�` in the preview/report. This is the explicitly
  accepted trade-off from spec's "Edge cases" (no `ctypes`/`win32api`
  dependency for code-page detection) — confirmed only by unit test
  (`UpdateLogDetection.test_read_update_log_replaces_invalid_utf8_bytes_instead_of_raising`)
  with synthetic bytes, not against a real `cmd`-written OEM-code-page log,
  since this sandbox has no Windows `cmd.exe` to produce one.
- **Window-manager behaviour (focus, stacking, `transient()` grouping) is
  Xvfb's known blind spot**, called out as a deliberate risk when Leo
  picked this design (spec's "Resolved 2026-09-15"). Everything or
  everything close to it that Xvfb *can* show was checked by hand:
  screenshots (below) at both themes and 90–130% scale, the fallback
  state, and redaction on/off. What only a real Windows/macOS CI runner
  can confirm: the dialog's actual stacking order and grouping in Alt-Tab/
  the Dock relative to the main window, and real window-manager-driven
  focus behaviour for Escape/Tab (Xvfb has no WM, so a freshly created
  Toplevel never organically owns X input focus — the UI tests use the
  same one-time `focus_force()` precedent `UITestCase.setUp()` already
  established for this exact reason, not something a real WM run would
  need).
- **The `.sh`-vs-`.cmd` `version=` quoting fix (see "Key decisions") is
  exercised end-to-end only on the `.sh` path** (this sandbox is Linux).
  The `.cmd` path's own text is checked by
  `SwapScriptWindowsCmdText.test_version_suffix_when_target_version_given`,
  but actually *running* the generated `.cmd` (as
  `WindowsLaunchReproduction`/`WindowsFixSuspectDiagnostics` already do for
  the pre-existing script body) only happens on windows-latest CI.

## Round 2 (test-review.md, blocked → this round's fixes)

Reviewer verdict: **blocked**, two must-fix defects, both found by driving
the live app (not from reading code). Both are now fixed and re-verified
live against the reviewer's own repro technique before writing any test.

### Defect 1 — a theme/UI-scale change while the dialog is open destroyed it

**Root cause**: the update-log dialog (`tk.Toplevel(self.root, ...)`) is a
genuine child of `root`. `_rebuild_ui()`'s teardown loop
(`for w in self.root.winfo_children(): w.destroy()`) destroys every child
of `root` on any Appearance or UI-scale change, so it destroyed the dialog
too — but `self._log_dialog`/`self._log_dialog_ctx` were never cleared,
leaving them as dangling references to destroyed widgets. A later write to
the "show full paths" `BooleanVar` (from either of its two live traces —
`ToggleCheckbox`'s own repaint trace, or the dialog's own preview-refresh
trace) then raised an uncaught `TclError` into a destroyed widget. The
`docs/implementation.md` "Key decisions" claim that this was a deliberate,
verified-safe choice was wrong — it had never actually been exercised.

**Fix, per the orchestrator's decided behaviour** ("rebuild in the new
theme/scale with state preserved, never re-run detection"):
- `_capture_log_dialog_restore_state()` (new) — a plain-data snapshot
  (status, log path/text, target version, the checkbox's boolean state,
  and the fallback URL if the dialog was already in that state) taken
  *before* `_rebuild_ui()`'s teardown loop runs.
- `_rebuild_ui()` — captures that snapshot, calls `_close_log_dialog()`
  (below) if one was open, runs its existing teardown/`_build_ui()`
  unchanged, then calls `_restore_log_dialog(state)` (new) at its own
  tail. `_restore_log_dialog` calls `_show_update_log_dialog()` with the
  *captured* status/log_path/log_text/target_version (never
  `update_log_status()` again — the log's own detection is never re-run,
  and "ask once" is never re-triggered), then replays the checkbox state
  and, if applicable, the fallback state (via `_show_log_fallback(url)`
  with the *same* previously-computed URL — `webbrowser.open` is not
  called again).
- `_close_log_dialog()` (new — the previous version's inline destroy logic
  in `on_close()`/`_on_log_dismiss` is now a named, reusable method) — also
  clears the trace(s) on the checkbox's `BooleanVar` before destroying the
  Toplevel, so nothing can fire into a destroyed widget afterward (the
  ac-27 "trace outlives its widgets" lesson, applied here). Used by
  Dismiss, a successful Send, and this rebuild path alike.
- `self._log_dialog_show_paths_var` (new instance attribute) — the *same*
  `BooleanVar` as `ctx["show_paths_var"]`, additionally stored as a direct
  attribute of `self` purely so the existing `_forget_traces()` sweep
  (which walks `vars(self)` directly, not two levels into a dict) also
  finds and clears it on every rebuild — a second, independent safety net
  for the same Variable, reusing this file's own established convention
  instead of inventing a new one.
- `on_close()` now calls `_close_log_dialog()` instead of duplicating its
  logic inline.

**Verified live**, before writing any test, against the reviewer's own
repro shape (`theme_change_probe2.py`) and a fuller version exercising
Send afterward: dialog survives, is a live widget (not a stale reference),
`self._log_dialog_ctx` is genuinely a *new* dict (not the destroyed one),
checkbox state and full-paths preview survive, toggling the checkbox
post-rebuild raises nothing, and Send still works and marks `.reported`.
Also verified that a stray reference kept to the *pre-rebuild* ctx (the
reviewer's exact technique — `ui._log_dialog_ctx` saved to a local before
the rebuild, then `.set()` called on its `show_paths_var` afterward) no
longer raises, now that its traces are cleared before the widgets they
touch are destroyed.

New regression tests (`tests/test_ui.py`, `UpdateLogPrompt`):
`test_appearance_change_preserves_the_open_dialog_and_checkbox_state`,
`test_a_stray_reference_to_the_pre_rebuild_ctx_does_not_raise`,
`test_ui_scale_change_preserves_the_open_dialog_and_checkbox_state`,
`test_appearance_change_preserves_the_fallback_state_and_url`.

**Sabotage-verified** (each applied, confirmed red, then reverted):
- Skipping the `_restore_log_dialog(state)` call at `_rebuild_ui()`'s tail
  → all 3 rebuild-preservation tests failed red (dialog `None` after the
  rebuild).
- Removing `self._log_dialog_show_paths_var = show_paths_var` (so neither
  `_forget_traces()` nor `_close_log_dialog()` can find the Variable to
  clear its traces) → `test_a_stray_reference_to_the_pre_rebuild_ctx_does_not_raise`
  failed red with the *exact* `TclError` from the reviewer's own repro
  (`invalid command name ".!toplevel...!togglecheckbox"`).
- Two narrower variants (skipping only `_close_log_dialog()`'s own
  pre-teardown call; skipping only its internal `.destroy()` sub-step)
  stayed green — `_forget_traces()`'s later, unconditional sweep and the
  generic teardown loop already cover those specific sub-steps
  independently. Left as genuine (documented) defense-in-depth, not
  removed for being "redundant": the redundancy is exactly what makes the
  fix robust against a future refactor to any *one* of these three
  mechanisms.

### Defect 2 — the fallback state's buttons were clipped at some scales

**Root cause**: `_show_update_log_dialog()` calls
`top.geometry(f"{600*s}x{480*s}")` — an explicit size, which per Tk's own
`wm geometry` semantics disables that toplevel's automatic
resize-to-fit-content for every geometry request after it. The fallback
layout (an `Entry` + 2 buttons) requests more height than the default
3-button row it replaces; with the toplevel's size pinned, `pack()` does
not let the extra content overflow past the container's edge — it
silently *shrinks* the affected widgets instead (confirmed live: the
`Dismiss` button was allocated 25px against Tk `Consolas`/`Segoe UI`'s own
computed 35px request at 100% scale on the un-fixed code). This matters
for testing too: measuring by root-relative bottom-edge coordinates
(`widget.winfo_rooty() + winfo_height()` vs. the window's own) does **not**
detect this failure mode, since a squeezed widget's own reported edge
never exceeds the window's — only its *content* renders truncated. The
correct check is requested vs. allocated size
(`winfo_reqheight() > winfo_height()`), which is what both the reviewer's
own measurement and this round's fix/tests use.

**Fix**: `_fit_log_dialog_to_content()` (new) — grows (never shrinks) the
dialog to `ctx["body"].winfo_reqheight() + 2*CONTENT_PAD*s` whenever that
exceeds the toplevel's current height. Called at the tail of
`_show_update_log_dialog()` (covers the ordinary case and a rebuild
landing at a different scale) and at the tail of `_show_log_fallback()`
(covers the layout swap itself, the scenario Defect 2 was about).
`ctx["body"]` (the dialog's outer content frame) and `ctx["status"]` are
now also stored on the ctx dict (the latter needed for Defect 1's replay).

**Verified live** at 90/100/115/130% scale, before writing any test: on
the un-fixed code, the fallback's `Dismiss`/`Copy link` buttons and their
row were measurably squeezed (allocated less than requested) at 90%, 100%
and 130% — not at 115%, a rounding coincidence at that specific scale,
consistent with the reviewer's own note that this is "scale/rounding-
dependent". On the fixed code, allocated height exactly matches requested
height at all four scales — no squeezing.

New regression tests (`tests/test_ui.py`, `UpdateLogPrompt`):
`test_fallback_is_not_clipped_at_90_percent`,
`_at_100_percent`, `_at_115_percent`, `_at_130_percent` (via a shared
`_assert_fallback_not_clipped(ui_scale)` helper) — each builds a fresh
`AfkAutoclicker` at that scale, triggers the fallback, and asserts
`winfo_height() >= winfo_reqheight()` for the Dismiss button, the Copy
link button, and the fallback row itself, after confirming the dialog is
genuinely mapped (`winfo_ismapped()`) — an unmapped window's geometry is
not reliable and differs across platforms, so this is checked explicitly
rather than assumed.

**Sabotage-verified**: skipping `_fit_log_dialog_to_content()` at
`_show_log_fallback()`'s tail (re-pinning the geometry, matching the
original bug) made the 90%, 100% and 130% tests fail red with the exact
squeeze pattern found live (e.g. "25 not greater than or equal to 35" at
100%); 115% stayed green, consistent with the same rounding coincidence
noted above — a real, expected, scale-dependent gap in that one sabotage
run, not a gap in the fix (the fix itself passes at all four scales).

### Regression check after round 2
Full suite, twice, under Xvfb `:99` (confirmed via `pgrep -af "[u]nittest"`
that nobody else was attached first): `Ran 358 tests ... OK (skipped=10)`
both times — 350 from round 1 plus 8 new (4 rebuild-preservation/stray-
reference tests, 4 fallback-fit tests).

### Screenshots (round 2)
Re-taken under `.../scratchpad/ac36-shots/`, all visually confirmed:
`06-fallback-90.png` (fallback, 90%, not clipped), `07-fallback-100.png`
(fallback, 100% — the exact case the reviewer's screenshot showed
clipped, now fully visible), `08-normal-130.png` (ordinary dialog, 130%,
re-confirmed still fine), `09-theme-switch-after.png` (dark→light switch
performed *while the dialog was open*, checkbox pre-ticked before the
switch — the "after" state: dialog alive, rebuilt in light theme, checkbox
still ticked, preview still showing full paths).

## Round 3 (macOS CI: PR #72 head 67516be, all 22 `UpdateLogPrompt` tests failing)

**Symptom**: every `UpdateLogPrompt` test failed on macOS CI (ubuntu/
windows stayed green) in `tearDown()`'s `_assert_no_callback_exceptions()`,
all the same shape: `TclError: bad window path name ".!toplevel.!frame"`
deep inside `_fit_log_dialog_to_content`, called from
`_show_update_log_dialog`, called from `_maybe_offer_log_report`, itself
called from Tk's `callit` — an `after`/`after_idle` callback firing.

**Root cause**: `self.root.after_idle(self._maybe_offer_log_report)`
(`__init__`'s own tail) was never tracked anywhere — unlike every other
scheduled job in this file (`self._timers`, `self._rebuild_after_id`,
`self._pane_fill_after_id`, all cancelled by `on_close()`). A test whose
own `tearDown()`/`on_close()` runs before this specific idle job gets a
turn leaves it queued; when it does eventually fire, it builds/measures
widgets against a root that's already torn down. This is the exact same
*class* of bug as G#39's history (an untracked, uncancelled `after`/
`after_idle` handle surviving teardown) — not the same bug, a different
untracked handle — invisible on Linux/Windows's idle-flush timing
(confirmed: 369/369 green under Xvfb across this whole implementation,
every round), reliably fatal on macOS's.

**Fix**:
- `self._log_report_after_id` (new `__init__` attribute) stores the id
  the startup `after_idle()` call returns.
- `on_close()` cancels it — guarded `after_cancel` + `except tk.TclError:
  pass`, the identical pattern already used for `_rebuild_after_id`/
  `_pane_fill_after_id`, placed right after them.
- `_maybe_offer_log_report()` additionally wraps its one widget-touching
  call (`_show_update_log_dialog(...)`) in `try/except tk.TclError: pass`
  — belt and braces, since a scheduled Tk callback's cancel guarantees
  around `root.destroy()` are apparently not airtight on every platform.
  Everything above that call in the method is pure file I/O, no Tk, so
  nothing else needed wrapping.

**Verified locally** (this sandbox has no macOS runner, so the exact
platform-specific teardown race — a live root's Tcl interpreter still
answering to a command while an individual child widget it just built is
already gone — could not be reproduced byte-for-byte; the hazard *class*
was, both ways):
- Constructed `AfkAutoclicker`, called `on_close()` immediately (no
  `root.update()`/idle flush at all — the job never got a turn), then
  forced Tk's idle queue to process. On the fixed code: `_log_report_after_id`
  goes from a real id to `None`, no callback exceptions, clean. With the
  fix monkeypatched out (`on_close()` forgets the id, simulating the
  original bug): the queued job fires anyway and raises "invalid command
  name" — reproducible, though the exact downstream error text
  necessarily differs from macOS's own async widget-teardown timing
  (Linux/Xvfb's X11 teardown is synchronous; this sandbox's raw repro hits
  "invalid command name" on the callback itself rather than macOS's
  "bad window path name" three calls deeper into widget construction —
  same hazard class, different platform-specific manifestation of it).
- The more portable, deterministic check: a direct regression test
  (`test_on_close_before_the_startup_idle_job_ever_ran_cancels_it`)
  mirroring `OverlappingAppearanceChanges`'s own established `after info`
  technique for `_rebuild_after_id` — captures the job's real id right
  after `__init__` (before any `update()`), hooks `_release_right()`
  (on_close()'s last call before `root.destroy()`) to snapshot `after
  info`'s output, and asserts the id is no longer in it. **Sabotage-
  verified**: commenting out the cancel makes this test fail red with the
  id still present in `after info`, confirming it actually exercises the
  cancel path (not just checking a flag).
- A second direct test
  (`test_maybe_offer_log_report_swallows_a_tclerror_from_a_torn_down_root`)
  exercises the belt-and-braces guard on its own terms: monkeypatches
  `_show_update_log_dialog` to raise `tk.TclError` directly and asserts
  `_maybe_offer_log_report()` doesn't propagate it. **Sabotage-verified**:
  removing the `try/except` makes this test error with the raised
  `TclError` uncaught.

## Round 4 (security review, PR #72 — BLOCKER)

**Finding**: command injection via `tag_name`. `_check_worker` reads
`tag = release.get("tag_name", "")` straight from the GitHub API with no
validation; it flows into `_install_worker`'s
`write_swap_script(..., target_version=tag)` call, which writes it
**verbatim** into the generated `.cmd`/`.sh` update script. The reviewer
proved live: a release tag of `'$(touch /tmp/.../PWNED)'`, through the
real `write_swap_script` → the real generated `.sh` → `/bin/sh`
execution, created the marker file. The `.sh` path's own single-`\"`-
escaping (added in round 1 for the legitimate `version="..."` case) does
not stop `$()`/backtick command substitution inside POSIX double quotes;
the `.cmd` path has zero escaping at all. This runs entirely outside the
asset's SHA256 verification — a tag name alone, never the downloaded
binary, is enough.

**Fix, at the source, not by escaping harder downstream** (this project's
own "root cause, not symptom" convention, `docs/CODING-GUIDELINES.md`'s
"Input validation" section — *"anything read from disk or typed by a user
is untrusted"*, extended here to anything read from the network — and
mirroring what `.github/workflows/release.yml`'s own version-input check
already does for the same shape of string):
- `_is_safe_version_tag(tag)` (new, placed directly after `is_newer`,
  same neighbourhood) — `True` only for a tag shaped exactly like this
  project's own release tags: an optional leading `v`/`V`, then exactly
  three dot-separated all-digit parts, 1–32 characters total (matching
  `release.yml`'s own `MAJOR.MINOR.PATCH` check, generalized to also
  accept the `v`-prefixed form the GitHub API's `tag_name` field actually
  carries — `release.yml` itself strips `v` before checking, the API
  keeps it).
- `_install_worker` computes `safe_target_version = tag if
  _is_safe_version_tag(tag) else None` and passes *that* to
  `write_swap_script` — never the raw `tag`. Fails safe, not closed:
  `target_version` is best-effort diagnostics for the log's own
  `"wrong_version"` detection, not load-bearing for the update itself, so
  an unexpectedly-shaped tag is treated exactly like "version unknown"
  (`write_swap_script`'s own pre-existing default), never a reason to
  abort the update. `tag` itself (used everywhere else — button labels,
  status text) is untouched; only the one call site that generates and
  executes a script is gated.

**The 2000-char title-cap concern the reviewer also raised is closed by
this same fix, confirmed by recomputation, not just assumed**:
`build_issue_report`'s title embeds `target_version` verbatim/unbounded
(the log tail is the only thing the truncation loop shrinks). Once
`_install_worker` only ever writes a *validated* tag (or `None`) into
`update.log`'s `version="..."` field, `target_version` reaching
`build_issue_report` at read time is always either `None` or ≤32
characters of digits and dots. Recomputed directly: a maximal validated
tag (`"v" + "9"*26 + ".0.0"`, 31 chars) produces a 67-character title and
a 357-character full URL — nowhere near the 2000-char cap. A tag that
could actually threaten the cap is, by construction, already rejected by
`_is_safe_version_tag` before it ever reaches the log file.

**Verified live, both directions**, before writing any test:
- Re-ran the reviewer's own repro technique (a malicious tag through the
  *real* `write_swap_script`, not a stub, then actually executing the
  generated `.sh` via `/bin/sh`) with `target_version` computed the
  **unfixed** way (`safe = tag`, bypassing validation): the generated
  script contained a `version="$(touch .../PWNED)"` line verbatim, and
  running it created the marker file — injection confirmed reproducible
  in this sandbox too, not just the reviewer's environment.
- Same repro with the **fixed** computation (`safe = tag if
  _is_safe_version_tag(tag) else None`): the generated script contains no
  `version=` line at all and no trace of the malicious text; running it
  does not create the marker file.

**New tests**:
- `tests/test_updater.py`'s new `SafeVersionTag` class (6 tests) — pure
  unit tests of `_is_safe_version_tag` itself: accepts this project's
  `vX.Y.Z` shape; rejects `$()`, backticks, `"`, `&&`, `|`, `;`, and an
  embedded newline; rejects an oversized tag; rejects the wrong number of
  dot-separated parts; rejects non-digit parts; rejects non-string/empty
  input.
- `tests/test_ui.py`'s existing `InstallWorker` class gains 3 tests driven
  through the real `_install_worker()` (checksums/staging/`write_swap_script`
  faked, matching the class's own existing technique) via a shared
  `_install_worker_with_tag(tag)` helper that captures the
  `target_version` `write_swap_script` was actually called with: 5 shell-
  metacharacter shapes and an oversized tag all come out as `None`; a
  normal `"v0.7.0"` tag still comes out unchanged (the fix must not turn
  every real release into "version unknown").

**Sabotage-verified**: replacing `_install_worker`'s
`safe_target_version = tag if _is_safe_version_tag(tag) else None` with
`safe_target_version = tag` (skip the validation) made both the
metacharacter test (all 5 subtests) and the oversized-tag test fail red,
each showing the raw dangerous tag reaching `write_swap_script` instead
of `None`.

### Non-blocking notes from the review (no code change, per the reviewer's own read)
- `docs/design.md`'s claim that "Open folder" cross-platform handling is
  "already tested in earlier features" is inaccurate — this feature is
  this codebase's *first* use of that `os.startfile`/`open`/`xdg-open`
  three-way branch; it's consistent in shape with other existing
  per-platform branches elsewhere in the file, but not itself reused code.
  Left as-is (a design-doc wording nit, not a functional issue); noted
  here for the record.
- `LiveRepository.test_resolves_the_highest_version` intermittently errors
  instead of skipping cleanly when offline — confirmed pre-existing on
  `main`, unrelated to this feature, out of scope for this PR.

## How to verify locally

1. Activate the project's existing test venv (pynput + Tk) and run the
   full suite under Xvfb, same as CI's Linux leg:
   ```
   xvfb-run -a python -m unittest discover -s tests -t . -v
   ```
   Expect `Ran 369 tests ... OK (skipped=10)` — 315 on `main` plus 54 new
   across all four rounds (28 in `tests/test_updater.py`, 26 in
   `tests/test_ui.py`).
2. To exercise just the new pieces:
   ```
   python -m unittest tests.test_updater.UpdateLogDetection \
       tests.test_updater.IssueReportBuilder \
       tests.test_updater.SwapScriptWindowsCmdText \
       tests.test_updater.SwapScriptLogLifecycle \
       tests.test_ui.UpdateLogPrompt -v
   ```
3. To see the dialog itself without a real update attempt, point a throwaway
   settings dir at a hand-written `update.log` (never the real settings
   directory) and run the app from source, e.g.:
   ```python
   import os, tkinter as tk, afk_clicker as app
   workdir = "/tmp/afk-log-demo"
   os.makedirs(workdir, exist_ok=True)
   with open(os.path.join(workdir, "update.log"), "w") as fh:
       fh.write('2026-01-01 00:00:00 start pid=1 staged="a" target="b" '
                'relaunch="c" version="v0.7.0"\n2026-01-01 00:00:01 wait finished after 1 iterations\n')
   store = app.Store(os.path.join(workdir, "settings.json"))
   root = tk.Tk()
   app.AfkAutoclicker(root, store=store)
   root.mainloop()
   ```
   The dialog appears once at startup; Dismiss/Send renames `update.log`
   to `update.log.reported` in the same directory, and relaunching against
   the same `workdir` shows no dialog.
