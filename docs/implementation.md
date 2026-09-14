# Implementation: Windows in-app install never completes (G#35 / GH#63) — Phase A

## Summary
Phase A only, per dispatch: added a Windows-only CI reproduction of the
`_quit_for_update` install-swap bug to `tests/test_updater.py`. No production
code (`afk_clicker.py`) was touched. This phase's job is to make the bug
observable on `windows-latest` CI with enough captured evidence to attribute
it to one of the three suspects in `docs/spec.md` — the actual fix is phase B.

Revised once, after an orchestrator review caught two fidelity gaps in the
first draft's acceptance case before it was pushed — see "Deviations from
spec" and the second half of "Key decisions / tradeoffs" for what changed and
why. Both were real: they could have made the acceptance case pass on
unfixed code, which would have defeated the entire point of phase A.

## Root cause
Not yet determined — that is phase A's whole point. This phase adds the
reproduction and its diagnostics; the CI run this PR triggers is the evidence
phase B diagnoses from. See "Known limitations" for what could not be checked
without a Windows machine.

## Changes by file
- `tests/test_updater.py`
  - Added `ROOT` (module-level): the project root path, needed a second time
    because the new reproduction's launcher runs in a *separate* interpreter
    that does not inherit `tests/context.py`'s `sys.path` insert.
  - Added `_SwapScriptLauncher` — a plain mixin (deliberately **not** a
    `unittest.TestCase` subclass) holding the fixture builder, the GUI-
    interpreter picker, the launcher subprocess spawner, the poll helper,
    the mirrored-target check, the diagnostics formatter, and the
    `_LAUNCHER` inline script template shared by both test classes below.
    Kept as a non-`TestCase` mixin specifically so unittest's method
    discovery can't accidentally make one class inherit (and silently
    re-run) the other's `test_*` methods.
  - Added `WindowsLaunchReproduction` (`@unittest.skipUnless(sys.platform ==
    "win32", ...)`) — the acceptance case:
    `test_production_launch_replaces_the_install_and_relaunches`. Launches
    the swap script with `_quit_for_update`'s exact command, creationflags,
    *and stdio* (none at all — no `stdout`/`stderr`/`stdin` kwarg of any
    kind on the `Popen` call).
  - Added `WindowsFixSuspectDiagnostics` (same skip guard) —
    `test_diagnostic_variants`, three subTest variants, informational only,
    never fails the suite.
  - No other test in the file was touched.

## Key decisions / tradeoffs
- **Separate OS process for the launcher, not an in-process call.** Suspect 3
  (the process tree not surviving its parent exiting) can only be reproduced
  if `write_swap_script`'s `os.getpid()` belongs to a process that then
  itself exits — the test runner process does not exit after `Popen()`
  returns, so calling `write_swap_script` directly from the test method could
  never exercise that suspect. The launcher's inline code calls the real
  `app.write_swap_script(...)`, launches the result, and returns — standing
  in for `on_close()` tearing the app down right after `Popen()` returns.
- **Config crosses the process boundary via environment variables (JSON),
  not string-formatted into the launcher source.** `staged`/`target`/
  `relaunch` are temp paths that can contain quotes, backslashes or spaces;
  formatting them into a Python source string would either produce a syntax
  error or, worse, get treated as code. `AFK_TEST_CFG` carries
  `json.dumps(cfg)`, `AFK_TEST_ROOT` carries the project root, and
  `AFK_TEST_ERROR_LOG` carries the crash-report path as its *own* env var
  rather than a cfg key — so even a cfg parse failure still lands somewhere
  readable (see the fidelity fix below).
- **`_SwapScriptLauncher` is a plain mixin, not a `TestCase` subclass.**
  The first draft had `WindowsFixSuspectDiagnostics(WindowsLaunchReproduction)`
  to reuse fixture code; caught in local testing that this makes unittest
  discover and re-run `test_production_launch_replaces_the_install_and_relaunches`
  as part of the diagnostics class too, which would have made a class
  documented as "must never fail the suite" do exactly that. Fixed by
  extracting the shared methods into `_SwapScriptLauncher`, a class with no
  `unittest.TestCase` in its MRO, mixed into each concrete test class
  separately.
- **Fixture spaces:** both `target dir` and `relaunch dir` (the directories
  holding the target install root and the relaunch `.cmd`) contain a space,
  per `docs/spec.md`'s "Edge cases" — real installs land under `Program
  Files`, and this guards `start "" "{relaunch}"`'s existing quoting from a
  regression, not just the happy path.
- **Straggler cleanup uses a PowerShell one-liner matching the `afk-repro`
  temp-dir prefix**, not a bare `taskkill /IM cmd.exe`. The bug under test is
  exactly a process tree that might outlive the timeout, and a blanket
  `cmd.exe` kill would also kill unrelated `cmd.exe` processes a CI step
  might have running. Matching on the command line for the shared
  `afk-repro`/`afk-repro-diag` prefix scopes the kill to processes this test
  file itself spawned. Wrapped in `try/except`, printed not raised — it's
  best-effort cleanup, not an assertion.

### Round-2 fidelity fixes (post orchestrator-review, pre-push)
Two problems in the first draft's acceptance case, both catchable only by
reasoning about what a Windows process actually inherits — neither would
have shown up in the Linux-only local run, since both are specifically about
Windows stdio/handle semantics:

1. **The acceptance case had stopped being byte-identical to production.**
   The first draft passed `stdout=log, stderr=log` to the acceptance case's
   `Popen()` call "for diagnostics." But suspects 1/2 are specifically about
   console/handle availability for `tasklist`/`timeout`/`robocopy` — handing
   `cmd.exe` real, usable stdio handles when production hands it none at all
   is plausibly the exact thing that would make those suspects' failure mode
   disappear, which could turn the acceptance case green *on unfixed code*
   and defeat the whole point of phase A. Fixed: the acceptance case's
   `Popen(["cmd", "/c", script], creationflags=...)` now carries no other
   kwarg at all — `stdio_mode == "none"` in `_LAUNCHER`. The captured-stdio
   variant moved to `WindowsFixSuspectDiagnostics` as
   `production_flags+captured_stdio`, which only ever prints what it saw.
2. **How the launcher itself was spawned leaked into the result.**
   `_spawn_launcher` used `subprocess.run(..., capture_output=True)` — pipes.
   If the grandchild `cmd.exe` ended up inheriting a pipe write handle,
   `subprocess.run()` would block waiting for that handle to close (i.e.
   until `cmd.exe` exits), which would silently defeat the "parent exits
   immediately" premise the whole suspect-3 reproduction depends on — and
   pipes are also handles production's actual launch (a frozen `--windowed`
   PyInstaller exe, no console, no std pipes) never has. Fixed:
   `_spawn_launcher` now starves the launcher's stdin (`subprocess.DEVNULL`)
   and redirects its stdout/stderr to a real file
   (`<workdir>/launcher-output.log`) instead of a pipe, and prefers
   `pythonw.exe` next to `sys.executable` (GUI subsystem, no console — the
   same shape as the frozen app) over `python.exe`, falling back to
   `sys.executable` if no `pythonw.exe` exists alongside it. Because
   `pythonw.exe` cannot be assumed to have a working `sys.stdout`/`stderr`
   to print to at all, `_LAUNCHER`'s body no longer prints anything; instead
   it wraps everything after reading `AFK_TEST_ERROR_LOG` in a
   `try/except Exception` that writes `traceback.format_exc()` to that path
   on any failure, so a launcher-side crash is still visible on disk
   regardless of what stdio the chosen interpreter actually has. Both the
   acceptance case and every diagnostic variant now assert/report the
   interpreter used, the launcher's own captured output, and this error-log
   content.

## Deviations from spec
- None from `docs/spec.md`'s "Proposed approach §1" beyond what's already
  covered above (the round-2 fixes tighten fidelity to the spec's own "exact
  same launch line" requirement — they do not relax it).
- One extra beyond §1's own wording: an explicit `tearDown`/`_kill_stragglers`
  straggler-process cleanup — the dispatch instructions asked for it
  directly ("kill any leftover cmd/relaunch processes in tearDown"), and it
  does not change what's under test.
- Per the dispatch instructions, nothing in `afk_clicker.py` was touched, and
  no extraction of a shared `launch_swap_script(script)` helper was done —
  that refactor is explicitly deferred to phase B so this phase's red run is
  against unmodified production code (`_LAUNCHER`'s Popen line is a
  hand-mirrored copy of `afk_clicker.py:2982-2983`, called out by comment so
  it can't silently drift).

## Known limitations
- **Not run against real Windows.** This box is Linux-only; the test classes
  skip (`unittest.skipUnless(sys.platform == "win32", ...)`) rather than
  running here. Both compile clean (`python -m py_compile`), the embedded
  `_LAUNCHER` string was verified separately to `compile()` without a syntax
  error, and I read through the Popen/env/JSON round-trip and the
  `pythonw.exe`-selection logic by hand, but none of it has executed —
  including whether `pythonw.exe` actually sits next to `python.exe` on
  GitHub's `windows-latest` runner image (expected for a standard CPython
  install via `actions/setup-python`, but unconfirmed). That only happens
  once this PR's `windows-latest` CI leg runs.
- **Whether the red run actually reproduces the bug is unconfirmed until CI
  runs.** The reproduction is built exactly to the spec's step-by-step
  design, mirroring the real launch line and stdio shape as closely as a
  test process can, but "does it actually go red on `windows-latest`" is the
  thing this dispatch exists to find out — that's the evidence phase B needs
  before touching `_quit_for_update`.
- **CI job-object risk** (`docs/spec.md` "Edge cases"/"Open questions" #2):
  if GitHub's Windows runner tears down a job object that kills the spawned
  `cmd`/`robocopy` tree independent of whether the launcher process exited on
  purpose, the repro could stay red even under a scenario where a real user's
  machine would have succeeded. Flagged, not solved, in this phase.
- **`WindowsFixSuspectDiagnostics`'s PowerShell straggler-kill and `tasklist`
  diagnostics have not been exercised on a live Windows box** for the same
  reason as above — read carefully for correctness (parameter names,
  `Get-CimInstance`/`Stop-Process` cmdlet syntax) but not run.

## How to verify locally
This machine is Linux, so the new classes can only be checked for "skip
cleanly, don't break anything else":

```
python3 -m py_compile tests/test_updater.py

# venv with pynput, needed for the whole suite to import afk_clicker at all
python3 -m venv <venv>
<venv>/bin/pip install pynput

# Xvfb only matters for the rest of the suite (pynput's X11 backend);
# WindowsLaunchReproduction/WindowsFixSuspectDiagnostics don't need a display
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &   # skip if already running
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t . -v
```

Actually run in this session, after the round-2 fixes:
- `python3 -m py_compile tests/test_updater.py` → compiled clean.
- `compile(_SwapScriptLauncher._LAUNCHER, "<launcher>", "exec")` → syntax OK.
- Full suite: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t . -v`
  → `Ran 300 tests ... OK (skipped=7)`, with
  `test_production_launch_replaces_the_install_and_relaunches` and
  `test_diagnostic_variants` both reporting `skipped 'Windows launch
  reproduction'` and every pre-existing test (including `SwapScript`)
  unaffected.

**To verify the actual reproduction**, this needs to go through
`windows-latest` CI: push this branch, open the PR, and read the "Run the
test suite (Windows / macOS)" step's log for `tests.test_updater`. Look for:
- `test_production_launch_replaces_the_install_and_relaunches ... FAIL` (the
  expected red result on today's code) with the assertion message's captured
  diagnostics — `launcher interpreter: ...` (confirm it's `pythonw.exe`),
  `target mirrored: ...`, `relaunch marker present: ...`, the `tasklist
  cmd.exe` output, `launcher stdout/stderr: ...`, and `launcher crash
  traceback: ...` (should read "none" — a non-empty traceback here means the
  launcher itself broke, not `_quit_for_update`).
- The three `[diagnostic:...]` lines printed by `test_diagnostic_variants` —
  `create_no_window+devnull_stdio`, `production_flags+captured_stdio`, and
  `production_flags+parent_stays_alive` — each reports `succeeded=True/False`
  plus `cmd_output` (only populated for `captured_stdio`). Whichever
  configuration flips to `succeeded=True` relative to the acceptance case,
  and whatever `production_flags+captured_stdio`'s `cmd_output` actually
  shows (e.g. `timeout`'s "Input redirection is not supported"), is the
  strongest signal for which of the three named suspects is real.

## Phase B — the fix

### Root cause, as evidenced by phase A's CI run (windows-latest, run
34898517271, commit 6dcab6b)
- **Acceptance case: FAIL**, as designed to. Target not mirrored, no
  relaunch marker, a `cmd.exe` (PID 9324, session 2) still alive after 45s.
  Launcher itself exited 0, no traceback — so the launcher process reached
  `Popen()` and returned cleanly; the *spawned tree* is what stalled.
- **`create_no_window+devnull_stdio`: succeeded=True.** Giving the tree a
  real hidden console instead of none fixes it outright.
- **`production_flags+parent_stays_alive` (5s): succeeded=False.** Keeping
  the launcher alive longer after `Popen()` did not help — **suspect 3
  (the tree dying with its parent) is ruled out.**
- **`production_flags+captured_stdio`: succeeded=False, cmd_output=''.**
  Completely empty — no `timeout` "Input redirection is not supported"
  message ever appeared, so **suspect 2 is not confirmed as the cause**;
  the script stalls with *no output at all* under a console-less `cmd`.
- Taken together, this is consistent with **suspect 1**: `DETACHED_PROCESS`
  gives `cmd.exe` no console, and `cmd` (or a console-subsystem child it
  starts — `tasklist`/`find`/`timeout`/`robocopy`) stalls trying to get one,
  rather than crashing or printing anything. I am not claiming stronger than
  that — the empty `cmd_output` rules suspect 2 out as *confirmed*, it does
  not prove suspect 1 beyond the `create_no_window` variant's own success.

### The fix
- **`launch_swap_script(script)`** (`afk_clicker.py:932-956`), a new
  module-level function holding all the platform `Popen` logic that used to
  live inline in `_quit_for_update`. Windows:
  `subprocess.Popen(["cmd", "/c", script], creationflags=CREATE_NO_WINDOW
  (0x08000000) | CREATE_NEW_PROCESS_GROUP (0x00000200), stdin=stdout=stderr
  =subprocess.DEVNULL)`. `CREATE_NEW_PROCESS_GROUP` is kept (spec: "unless
  you have a reason" — I don't have one to drop it, and it costs nothing).
  Linux/macOS: `subprocess.Popen(["/bin/sh", script],
  start_new_session=True)`, byte-for-byte identical to before — confirmed by
  diff, not just by eye (see "Verification" below).
- **`_quit_for_update`** (`afk_clicker.py:3050-3053`) now just calls
  `launch_swap_script(script)` then `self.on_close()`. This is also what the
  Windows acceptance test calls directly (`_LAUNCHER`'s `stdio_mode ==
  "production"` branch in `tests/test_updater.py`), so the test can never
  silently drift from what production actually runs.
- **`timeout` replaced with `ping -n 2 127.0.0.1 >nul`** in the `.cmd`'s wait
  loop. `timeout /t 1 /nobreak` refuses redirected stdin outright ("ERROR:
  Input redirection is not supported") when it has no real console to read
  from — under `stdin=subprocess.DEVNULL` (needed regardless, so no handle
  is left ambiguous) that failure is instant and silent, which would have
  turned the wait loop into a tight busy-loop of `tasklist` calls even after
  switching to `CREATE_NO_WINDOW`. `ping -n 2 127.0.0.1 >nul` is the
  conventional console-free ~1s delay and needs nothing from stdin.

### Shipped update log
- **`write_swap_script(staged, target, relaunch, log_path)`** — `log_path`
  is a new **required, positional** argument (not keyword-with-a-default).
  A default would create two code paths (logging vs. not), and every real
  caller must always pass one now — the only reason to omit it would be a
  test that doesn't care, and those are updated below anyway. Every existing
  caller was updated: `_install_worker` (`afk_clicker.py:3033-3034`) passes
  `os.path.join(os.path.dirname(config_path()), "update.log")`; every
  `SwapScript`/`WindowsLaunchReproduction`/`WindowsFixSuspectDiagnostics`
  call site in `tests/test_updater.py` was updated to pass one.
- **Directory creation is Python-side, inside `write_swap_script` itself**
  (`log_dir = os.path.dirname(os.path.abspath(log_path)); if log_dir:
  os.makedirs(log_dir, exist_ok=True)`), not left to the `.cmd`/`.sh` text.
  Simpler, cross-platform, directly unit-testable
  (`SwapScriptWindowsCmdText.test_the_log_directory_is_created`), and avoids
  `cmd`'s own `mkdir`/`if not exist` quoting quirks on a path that can
  contain spaces.
- **Lifecycle:** truncated at the top of every run (`> "%LOG%"` / `: >
  "$LOG"`), never appended — one log per update attempt. Verified by
  `SwapScriptLogLifecycle.test_a_second_update_truncates_the_log_rather_than_appending`.
- **Content, both `.cmd` and `.sh`, same step names:** `start pid=… staged=…
  target=… relaunch=…`, `wait finished after N iterations`, `copy exit code
  N`, `relaunch attempted`, and — only on success — `done`.
- **Robocopy ≥ 8 / `cp -a` non-zero = failure → no `done`, but relaunch is
  still attempted unconditionally.** Decision: relaunching the *old* build
  (whatever's left at `target`, which may be untouched or only partially
  mirrored) after a failed copy is better than leaving the user with
  nothing running at all — a stuck update is bad, a stuck update *and* no
  running app is worse. The `done` gate only ever wraps the log line, never
  the `start "" "{relaunch}"` / `"{relaunch}" &` line itself
  (`SwapScriptWindowsCmdText.test_relaunch_is_attempted_even_if_the_copy_fails`
  proves this for the `.cmd`; the `.sh` shares the same shape by
  inspection — its `"{relaunch}" &` line is likewise unconditional, above
  the `if [ "$RC" -eq 0 ]` guard).
- **Wait-loop pacing/no-busy-spin:** the log now counts wait-loop iterations
  (`COUNT`/`$COUNT`) and reports them in the `wait finished after N
  iterations` line. Proven two ways, deliberately not by parsing `%date%
  %time%` (locale-dependent on a Windows runner, so fragile): (1) statically
  — `SwapScriptWindowsCmdText.test_no_timeout_left_in_the_wait_loop` checks
  the word `timeout` is gone and `ping -n 2 127.0.0.1` is present; (2) at
  runtime on Windows CI —
  `WindowsLaunchReproduction.test_wait_loop_paces_polls_instead_of_busy_spinning`
  keeps the launcher (and therefore the waited-on pid) alive for a known 5s
  via `keep_alive_seconds`, then asserts the logged iteration count is
  `> 0` and `< keep_alive_seconds * 4` — a busy-spin (no sleep at all) would
  produce dozens-to-hundreds of iterations in the same 5s window, not a
  small number. The main acceptance test's own pid dies within roughly one
  mainloop iteration of `Popen()` (that's the point of it — see phase A), so
  its own iteration count is usually 0-1 and isn't a meaningful pacing
  signal by itself; the pacing proof deliberately lives in this second test.
- **Quoting:** `set "LOG={log_path}"` (not `set LOG=...`) survives a log
  path containing spaces (a Windows username with a space in it is common —
  `C:\Users\First Last\AppData\...`), verified by
  `SwapScriptWindowsCmdText.test_the_log_path_is_quoted`.
- **Known, pre-existing, not expanded:** a `%` character anywhere in
  `staged`/`target`/`relaunch`/`log_path` would still break the `.cmd`
  (batch expands `%...%` sequences inside the interpolated string) — this
  risk already existed for `staged`/`target`/`relaunch` before this change;
  `log_path` now shares it. Not fixed here: `write_swap_script`'s existing
  interpolation style already carries this risk and doing it properly (`%%`
  escaping, or moving values into env vars set with `set "VAR=%~1"` from
  script arguments) is a larger rewrite of the whole `.cmd` generation, out
  of scope for this hotfix.

### Tests (`tests/test_updater.py`)
- **`SwapScript`** (existing, `:355-462`): both `write_swap_script` call
  sites updated to pass a 4th `log_path` argument (a temp path). No
  assertion was weakened or removed.
- **`SwapScriptWindowsCmdText`** (new, cross-platform): monkeypatches
  `app.sys.platform = "win32"` and restores it via `addCleanup` — the same
  restore-in-a-cleanup style already used by
  `tests/test_hotkey.py:305-316`'s `InputPermission`
  (`test_false_on_darwin_when_the_question_cannot_be_answered`); this suite
  deliberately has no `unittest.mock` anywhere (`tests/test_ui.py:2119-2120`).
  Lets the `.cmd`'s *text* be checked on every platform, not just
  `windows-latest`. 6 tests: `.cmd` extension, log directory created, log
  path quoted, no `timeout` left (`ping -n 2` present instead), `done` after
  the copy-exit-code line, relaunch not gated behind the copy succeeding.
- **`SwapScriptLogLifecycle`** (new, local/Linux, actually executes the
  generated `.sh`): 3 tests. `write_swap_script` always waits on
  `os.getpid()` of whichever process calls it, so calling it directly from
  the test method would make the script wait on the *test runner's own*
  still-alive pid and hang until the subprocess timeout; instead, each test
  calls `write_swap_script` from a short-lived `python -c` subprocess (the
  same technique the Windows launcher reproduction already uses for the
  same reason) so that by the time the generated `.sh` actually runs, its
  waited-on pid has already exited and the wait ends at once.
  1. `test_successful_update_ends_with_done_and_records_the_exit_code` —
     real staged/target/relaunch fixtures, runs the script, asserts
     `new.txt` present/`old.txt` gone/relaunch marker written, log contains
     `copy exit code 0` and ends with `done`.
  2. `test_a_failing_copy_records_a_nonzero_exit_code_and_never_writes_done`
     — `staged` deliberately never created, so `cp -a` fails; asserts the
     log has a non-`0` `copy exit code` and does not end with `done`.
  3. `test_a_second_update_truncates_the_log_rather_than_appending` — runs
     the script twice against the same `log_path`, asserts the second run's
     log has exactly as many lines as the first (not double), and exactly
     one `start pid=` line.
- **`_SwapScriptLauncher`/`WindowsLaunchReproduction`
  (Windows-only, CI-only):**
  - `_LAUNCHER`'s inline script now takes a `stdio_mode: "production"`
    branch that calls `app.launch_swap_script(script)` directly (not a hand
    copy of flags) — used only by the acceptance test, so it can never
    silently drift from what `_quit_for_update` actually calls. Every
    `write_swap_script` call inside `_LAUNCHER` now also passes
    `cfg["log_path"]`.
  - `test_production_launch_replaces_the_install_and_relaunches` (renamed
    fixture setup unchanged) now additionally asserts `update.log` exists,
    contains `copy exit code`, and ends with `done`; on a timeout its
    failure message now appends the log's own contents — the best evidence
    left now that there's no console to flash and no captured `cmd_output`
    on this code path.
  - New `test_wait_loop_paces_polls_instead_of_busy_spinning` (see "Shipped
    update log" above for what it proves and why it's separate from the
    main acceptance test).
- **`WindowsFixSuspectDiagnostics`** (Windows-only, CI-only, informational,
  never fails the suite): reduced to one variant,
  `test_old_creationflags_still_stall_for_the_record`, using a renamed
  `OLD_CREATIONFLAGS` constant (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`
  — what shipped before this fix). Dropped the other three phase-A variants:
  `create_no_window+devnull_stdio` is now literally what `launch_swap_script`
  does, so it's covered by the acceptance case itself; `production_flags
  +captured_stdio` and `production_flags+parent_stays_alive` already
  answered their questions in phase A's CI run (empty output; suspect 3
  ruled out) and re-running them teaches nothing further. What replaced
  them: the *old* flags (no stdio kwargs at all, matching exactly what
  shipped) run through the *new* logging `write_swap_script`, printing
  `update.log`'s contents to the CI log — since the log write is a plain
  file redirect (not console I/O), it should land even if a later
  console-subsystem step is the one actually stuck, telling us *which*
  step for the record.

### Sabotage-verify results (all local, Linux, actually run and observed)
Every new local assertion below was broken, confirmed red, then restored —
not asserted from reading the code:
| Test | Sabotage | Result |
|---|---|---|
| `SwapScriptWindowsCmdText.test_the_log_directory_is_created` | commented out the `os.makedirs(log_dir, ...)` call | `AssertionError: False is not true` |
| `SwapScriptWindowsCmdText.test_the_log_path_is_quoted` | `set "LOG=..."` → `set LOG=...` | `AssertionError: ... not found in ...` |
| `SwapScriptWindowsCmdText.test_no_timeout_left_in_the_wait_loop` | `ping -n 2 ...` → `timeout /t 1 /nobreak ...` | `AssertionError: 'timeout' unexpectedly found` |
| `SwapScriptWindowsCmdText.test_done_is_written_after_the_copy_exit_code` | moved the `done` echo before the copy step | `407 not greater than 562` |
| `SwapScriptWindowsCmdText.test_relaunch_is_attempted_even_if_the_copy_fails` | moved `start "" "{relaunch}"` inside the `if %RC% LSS 8` guard | `579 not less than 561` |
| `SwapScriptLogLifecycle.test_successful_update_ends_with_done_and_records_the_exit_code` | dropped the `done` echo on success | `'relaunch attempted' != 'done'` |
| `SwapScriptLogLifecycle.test_a_failing_copy_records_a_nonzero_exit_code_and_never_writes_done` | made `done` unconditional | `True is not false` (log ended with `done` despite `copy exit code 1`) |
| `SwapScriptLogLifecycle.test_a_second_update_truncates_the_log_rather_than_appending` | `: > "$LOG"` → `: >> "$LOG"` | `10 != 5` |

After every sabotage above was reverted, the full local suite was re-run
clean (see "Verification" below).

### What only CI can confirm
- The Windows acceptance test, the new `test_wait_loop_paces_polls_instead_
  of_busy_spinning` test, and `WindowsFixSuspectDiagnostics`'s single
  remaining variant only run on `windows-latest` — this box is Linux-only,
  so none of the `.cmd`'s actual *execution* (as opposed to its generated
  *text*, which the new `SwapScriptWindowsCmdText` class does check
  everywhere) has been run in this session. `robocopy`/`tasklist`/`ping`
  cmdlet syntax and behavior, `CREATE_NO_WINDOW`'s actual effect on a
  console-subsystem child tree, and the pacing test's real-world iteration
  count under CI scheduling jitter are all unconfirmed until this PR's next
  `windows-latest` CI run.
- Whether `%LOG%`'s quoting survives a real Windows runner's actual
  `%TEMP%`/settings-dir paths (as opposed to the synthetic paths used in
  `SwapScriptWindowsCmdText`, which monkeypatches `sys.platform` on Linux)
  is likewise only provable there.

## Verification (this session)
- `python3 -m py_compile afk_clicker.py tests/test_updater.py` → clean.
- `DISPLAY=:99 <venv>/bin/python -m unittest tests.test_updater -v` →
  `Ran 46 tests ... OK (skipped=3)` — the 3 skips are the Windows-only tests
  (now 3, up from 2, after adding
  `test_wait_loop_paces_polls_instead_of_busy_spinning`).
- Full suite: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests
  -t .` → `Ran 310 tests ... OK (skipped=8)` (up from phase A's 300/7 —
  10 new local tests added, 1 new Windows-only skip).
- Every sabotage in the table above was actually applied to
  `afk_clicker.py`, run, observed red, then reverted to the exact original
  text before moving to the next one; the diff shown by `git diff
  afk_clicker.py` at the end of this session matches the intended change
  with no sabotage left in place.
- `_quit_for_update`'s Linux/macOS `Popen` line
  (`subprocess.Popen(["/bin/sh", script], start_new_session=True)`) is
  unchanged — confirmed by `git diff`, not just visual inspection: the only
  change to that branch is that it's now inside `launch_swap_script` rather
  than inline in `_quit_for_update`.
