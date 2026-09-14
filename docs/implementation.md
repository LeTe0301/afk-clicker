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
