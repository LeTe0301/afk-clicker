# Spec: Windows in-app Install never completes (G#35 / GH#63)

Branch: `hotfix/ac-35/windows-install-never-updates`

## Summary
Fix how `_quit_for_update()` launches `apply-update.cmd` on Windows so the
swap script actually runs to completion (mirrors the install folder and
relaunches the app) instead of being cut short right after a console flashes,
by first building a Windows-CI reproduction that fails on today's code and
confirms which of the three suspected causes is real, then applying the
targeted fix.

## Goals
- Confirm, with evidence captured on the `windows-latest` GitHub Actions
  runner (the only place Windows behaviour is observable — the local box is
  Linux-only), which of the three suspects in the ticket actually causes the
  failure:
  1. `DETACHED_PROCESS` gives `cmd` no console, so `cmd` and/or its
     console-subsystem children (`tasklist`, `find`, `timeout`, `robocopy`)
     each try to allocate their own — the visible flash.
  2. `timeout /t 1 /nobreak` fails outright ("ERROR: Input redirection is not
     supported") when it has no real console to read from, corrupting the
     wait loop.
  3. The spawned process tree does not survive `_quit_for_update`'s parent
     process exiting shortly after `Popen()` returns.
- Fix `_quit_for_update`'s Windows branch so that, end to end: the app window
  closes, no console window is visible, the install folder is fully replaced
  with the staged build's contents, and the relaunched build starts.
- Land a regression test that fails on the current code and passes on the
  fixed code, running automatically in CI (no manual `workflow_dispatch`,
  which this token cannot trigger anyway).
- **Shipped update log** (added by Leo, 2026-09-14 — replaces the earlier
  "diagnostic-only logging" assumption). The swap script that ships writes
  a step log on every update, so the next failure in the field leaves
  evidence instead of a vanished console:
  - **Location:** `update.log` in the settings directory, i.e.
    `os.path.join(os.path.dirname(config_path()), "update.log")` — stable
    across updates and findable by the app at its next launch (the
    follow-up prompt depends on this). Not `%TEMP%`, which is shared and
    cleaned by the OS. Create the directory if missing.
  - **Lifecycle:** truncated/started fresh by each update, not appended
    forever — one log per update attempt, bounded size.
  - **Content, per line:** a timestamp and a step name. At minimum: script
    start (pid being waited on, staged, target, relaunch), wait finished,
    the copy step's exit code (`robocopy` ≥ 8 is failure; `cp -a` non-zero),
    relaunch attempted, and a final `done` line. A log without `done` is how
    the follow-up will recognise an update that died part-way.
  - **Both script variants** (`.cmd` and `.sh`) write it, same path and same
    step names, so the follow-up prompt is not Windows-only. The
    Linux/macOS *launch line* in `_quit_for_update` stays byte-for-byte
    unchanged; only the script text gains logging.
  - `write_swap_script` takes the log path as an argument (caller passes
    the settings-dir path) rather than computing it, so tests never write
    into the real `%APPDATA%`/`~/.config`.
  - **Fidelity warning:** redirecting the script's console children into a
    file changes which std handles they have — the very thing suspects 1/2
    are about. So the Windows acceptance test must exercise the real,
    logging script as `write_swap_script` produces it, launched exactly as
    production launches it; never a hand-simplified copy.

## Non-goals
- **No UI/UX change.** `_set_update_state("Restarting…", enabled=False)` and
  the rest of the Settings → Install status flow are untouched — this is a
  pure launch-mechanism fix inside `_quit_for_update`. **ux-designer should be
  skipped for this cycle.**
- **No fix for already-installed 0.3.1/0.5.0 Windows clients.** Every
  installed copy runs its own already-shipped swap script; this fix only
  helps from the *next* successful update onward. Existing Windows users
  install the fixed release by hand once. This goes in the 0.6.0 release
  notes, not in code (per `backlog.md`'s "Release blocker" note).
- **Not moving the swap script out of `%TEMP%`.** `write_swap_script`'s
  `workdir = dirname(dirname(staged))` resolving to `%TEMP%` itself (because
  the Windows zip isn't flattened, unlike the single-top-level-dir Linux/macOS
  case) is real, but Leo's own manual repro — running the exact leftover
  `%TEMP%\apply-update.cmd` by hand from an interactive `cmd` — updated to
  0.5.0 correctly *from that exact location*. That rules the script's
  location out as a contributor to this bug. Changing it now would be
  unrelated scope creep against a code path that already has passing,
  deliberate tests (`tests/test_updater.py:357-383`, the filesystem-root
  guard). Leave it alone unless the CI repro below proves otherwise.
- **No change to the Linux/macOS launch** (`_quit_for_update`'s
  `subprocess.Popen(["/bin/sh", script], start_new_session=True)`), which
  already works end to end per the ticket. The `.sh` script text changes only
  by gaining the shipped update log (Goals); its wait/copy/relaunch
  behaviour stays as it is.
- **No new CI job or workflow file.** `ci.yml` already runs the full unit
  test suite on `windows-latest` for every PR — reuse that leg (see
  "Proposed approach").
- **No renaming of the packaged executable or settings directory** — see
  `docs/history/ac-33-spec.md`, still binding.
- **No work on the unrelated updater residue items** (G#21 / GH#32).
- **No in-app "update didn't finish — send us the log" prompt.** Leo
  (2026-09-14) wants the app to ask the person to send the log via a
  prefilled GitHub issue, but split it out: that is a follow-up ticket with
  its own design pass, so this release blocker is not held up by UI work.
  This cycle only makes the log exist, in a stable place the follow-up can
  find (see Goals, "Shipped update log").

## Background / current state
- `write_swap_script(staged, target, relaunch)` — `afk_clicker.py:846-885`.
  Windows branch writes `apply-update.cmd`: a `tasklist`/`find` wait loop with
  `timeout /t 1 /nobreak >nul` between polls, then `robocopy "{staged}"
  "{target}" /MIR /NFL /NDL /NJH /NJS /NC /NS >nul`, then `start ""
  "{relaunch}"`. Confirmed correct by Leo running it by hand.
- `_install_worker` (`afk_clicker.py:2949-2977`) stages the update, then calls
  `write_swap_script`, then hands the resulting path to `_quit_for_update`.
- `_quit_for_update(script)` (`afk_clicker.py:2979-2986`) is the actual bug
  site:
  ```python
  def _quit_for_update(self, script):
      self._set_update_state("Restarting…", enabled=False)
      if sys.platform == "win32":
          subprocess.Popen(["cmd", "/c", script],
                           creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_GROUP
      else:
          subprocess.Popen(["/bin/sh", script], start_new_session=True)
      self.on_close()
  ```
  `0x00000008` is `DETACHED_PROCESS`, `0x00000200` is
  `CREATE_NEW_PROCESS_GROUP`. No `stdin`/`stdout`/`stderr` are passed, so
  Python's default (non-inherited, since `close_fds` defaults to `True` on
  Windows too) leaves the child with no standard handles at all. `on_close()`
  runs immediately after, which tears down the Tk app and ends the process —
  so in production the "parent" that suspect 3 is about really does exit
  within roughly one mainloop iteration of the `Popen()` call.
- `tests/test_updater.py:345-429`'s `SwapScript` class already tests the
  *contents* written by `write_swap_script` (pid presence, wait-not-kill,
  copy direction, no destructive path crossing). None of it exercises how the
  script is actually *launched* — that gap is exactly what let this ship.
- `tests/context.py:93`: `needs_display = unittest.skipIf(HEADLESS, ...)`
  where `HEADLESS = sys.platform.startswith("linux") and not
  os.environ.get("DISPLAY")` — irrelevant to Windows, which always has a
  window server in CI. No existing Windows-only test gate exists yet in this
  file; this fix introduces the first one.
- `.github/workflows/ci.yml` already runs `python -m unittest discover -s
  tests -t . -v` on `windows-latest` for every PR and every push to `main`
  (no Xvfb needed on Windows/macOS — see the "Run the test suite (Windows /
  macOS)" step). This is the only Windows execution environment available to
  us: `release.yml`'s Windows build+smoke-test leg is not reachable without
  `actions: write` (no `workflow_dispatch`), and pushing a `release/**`
  branch is gated on a human approval before publish — not a test vehicle.

## Proposed approach

### 1. Reproduction, on `windows-latest` CI, before touching the fix
Add a Windows-only test class to `tests/test_updater.py`, gated with
`@unittest.skipUnless(sys.platform == "win32", "Windows launch reproduction")`
(no `@needs_display` — this exercises `subprocess`/`write_swap_script`, not
Tk). It must reproduce the bug exactly as `_quit_for_update` triggers it,
including the part of suspect 3 that requires the *caller* to actually exit:

1. Build a dummy install layout under a temp dir: `staged/new.txt` (content
   `"new"`), `target/old.txt` (content `"old"`, so a successful `/MIR` proves
   itself by making this file disappear), and `relaunch.cmd` — a `.cmd` file
   (not a Python script; `start "" "{relaunch}"` needs something `cmd`'s
   `start` can associate directly) whose body is `@echo off` +
   `echo relaunched> "{marker_path}"`. Give the target path a space in it
   (e.g. `target dir`) to catch a regression in the existing quoting.
2. Spawn a short-lived **launcher** subprocess —
   `subprocess.Popen([sys.executable, "-c", <inline code>], ...)` — whose
   inline code, running as its own OS process (so `os.getpid()` inside
   `write_swap_script` is *that* process's pid, not the test runner's):
   - imports `app` (via the same `tests.context` path-setup the rest of the
     suite uses),
   - calls `app.write_swap_script(staged, target, relaunch)`,
   - calls the **exact same** launch line as `_quit_for_update`:
     `subprocess.Popen(["cmd", "/c", script], creationflags=0x00000008 |
     0x00000200)`, redirecting `stdout`/`stderr` to a log file path passed
     in (this differs from production only in *where the output goes*, not
     in the creationflags/command — needed so a human can inspect what, if
     anything, the console commands emitted, e.g. `timeout`'s "Input
     redirection is not supported"),
   - then exits immediately (falls off the end of the `-c` script) — the
     stand-in for `on_close()` tearing the real app down right after
     `Popen()` returns. This is what actually puts suspect 3 under test;
     a launcher that stays alive for the rest of the test would not.
3. The outer test polls (bounded, e.g. 20s timeout, short sleep interval)
   for both `target/new.txt` to exist and `target/old.txt` to be gone (proof
   `/MIR` ran) and for the relaunch marker file to exist. On timeout, fail
   with an assertion message that includes the captured log file's contents
   (if any) — that's the diagnostic evidence for which suspect was real.
4. This test must fail on current `main` (sabotage-verify: run it on the PR's
   `windows-latest` CI leg before writing the fix and confirm red) and pass
   once the fix lands.

**Recommendation: this lives in `tests/test_updater.py`, running through
`ci.yml`'s existing Windows leg — not a dedicated CI job.** `ci.yml` already
executes the full suite on `windows-latest` for every push/PR; a new job
would duplicate an already-available runner for no reproducibility benefit,
and (per the hard constraint) we cannot `workflow_dispatch` a bespoke job
anyway. Keeping it next to `SwapScript` also matches this file's existing
layout — one test class per concern, same module.

### 2. Diagnose from the repro's evidence, then fix
Use whatever the reproduction's captured log and pass/fail pattern show to
attribute the failure to one or more of the three suspects (see "Open
questions" #1 for the leading hypothesis and the fallback if it's wrong), then
change `_quit_for_update`'s Windows branch (`afk_clicker.py:2979-2986`)
accordingly. Re-run the same test on the PR's `windows-latest` leg (push a
commit; there is no rerun-without-a-push available) until it's green.

### 3. Confirm no collateral change
- The existing `SwapScript` tests (`tests/test_updater.py:345-429`) keep
  every assertion they make today; they may only be extended for the new
  log-path argument.
- The Linux/macOS launch line in `_quit_for_update` is not touched.
- `write_swap_script`'s `%TEMP%` workdir behaviour is not touched (see
  "Non-goals").

## Affected areas
- `afk_clicker.py:2979-2986` (`_quit_for_update`, Windows branch only) —
  single function, single platform branch. This is a small, single-layer
  change; no sub-spec split needed (skill 11 doesn't apply here).
- `afk_clicker.py:846-885` (`write_swap_script`, both branches) — gains
  the log-path argument and the logging lines; `_install_worker`
  (`afk_clicker.py:2946-2977`) passes the settings-dir log path.
- `tests/test_updater.py` — new Windows-only test class (additive), plus
  log tests for the `.sh` path that run locally.
- `docs/implementation.md` (developer's own output) should record which
  suspect(s) the CI evidence actually confirmed — Leo will want that on
  record given three unconfirmed suspects were named going in.
- No changes to `.github/workflows/ci.yml` or `release.yml`.
- No data model / schema / API changes.

## Edge cases
- **Relaunch path containing spaces** (real installs land in `Program
  Files`) — covered by giving the dummy `target`/`relaunch` fixture paths a
  space (see step 1 above); `start "" "{relaunch}"` is already quoted
  correctly today, this just guards the fix from regressing it.
- **Target directory has stale files not present in the staged build** —
  already exercised by the `old.txt` disappearing assertion; `/MIR`'s pruning
  behavior is unchanged by this fix.
- **CI runner job-object cleanup**: GitHub Actions Windows runners sometimes
  assign spawned process trees to a job object that gets torn down (and kills
  children) at the end of a workflow step, independent of whether the actual
  parent process (our short-lived launcher) exited on purpose. If the repro
  is still red after the real fix specifically on the "process outlives its
  immediate parent" axis, that's a CI-environment artifact, not evidence the
  production fix is wrong — flagged under "Open questions" #2, not a blocker
  to starting.
- **Antivirus/Defender briefly locking or scanning a freshly-written
  `apply-update.cmd`/relaunch exe** — out of scope; not something a
  `creationflags` change can control, and not what Leo observed (his manual
  run of the identical script worked).
- **Empty staged directory / zero-byte update** — pre-existing behavior
  (`robocopy /MIR` against an empty source deletes everything from target),
  unaffected by and out of scope for this fix.
- **Concurrent double-click of "Install"** — prevented UI-side today by
  `enabled=False` during the worker; unrelated to this fix.

## Acceptance criteria
- [ ] Given the current (pre-fix) code, when the new Windows-only test runs
      on the PR's `windows-latest` CI leg, then it fails (target not fully
      mirrored and/or relaunch marker missing within the timeout) —
      confirmed by actually observing this red run before implementing the
      fix, not assumed.
- [ ] Given the fixed `_quit_for_update`, when the same test runs on
      `windows-latest` CI, then it passes: `target/new.txt` exists,
      `target/old.txt` is gone, and the relaunch marker file exists, all
      within the timeout.
- [ ] Given the fix, when the full suite runs via `ci.yml` on all three
      platforms (`ubuntu-latest`, `windows-latest`, `macos-latest`), then
      every previously-passing test — including `SwapScript`
      (`tests/test_updater.py:345-429`) — still passes unmodified.
- [ ] Given the fix, when `_quit_for_update` runs on Linux/macOS, then its
      `subprocess.Popen(["/bin/sh", script], start_new_session=True)` line is
      byte-for-byte unchanged.
- [ ] Given 0.6.0 built and installed by hand once on a real Windows machine
      (manual verification — CI cannot fully simulate a double-clicked
      `--windowed` frozen exe), when Settings → Install is used to update to
      a later release, then: no console window is visibly flashed, the
      install folder is fully replaced, and the relaunched instance reports
      the new version. Call this out explicitly to Leo as a manual check
      once 0.6.0 ships — automated CI evidence alone does not close this
      criterion.
- [ ] `docs/implementation.md` states, with the CI run's actual evidence,
      which of the three named suspects was confirmed (not asserted).
- [ ] Given a successful update (the Windows acceptance test on CI, and the
      `.sh` path on Linux locally), then the log path passed to
      `write_swap_script` holds one fresh log for that attempt whose steps
      include the copy step's exit code and end with `done`.
- [ ] Given a script whose copy step fails (e.g. an unreadable/missing
      staged dir), then the log records the failing exit code and has **no**
      `done` line.
- [ ] Given a second update after a first, the log holds only the second
      attempt (truncated, not appended).
- [ ] Existing `SwapScript` tests may be extended for the new argument but
      not weakened — every assertion they make today still holds.

## Open questions
1. **Leading fix hypothesis, to be confirmed empirically by the repro's
   captured evidence, not decided here.** `DETACHED_PROCESS` is meant for a
   process that will never need a console of its own; `cmd.exe` running
   `tasklist`/`find`/`timeout`/`robocopy` very much does. The standard fix
   for "launch a console-subsystem command with no visible window" is
   `CREATE_NO_WINDOW` (`0x08000000`) instead of `DETACHED_PROCESS`, which
   still gives the process tree a real (hidden) console — avoiding both the
   flash (suspect 1) and `timeout` having no console to read from (suspect
   2) — combined with explicit `stdin=subprocess.DEVNULL,
   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL` so no handle is left
   ambiguous. **Proceeding under the assumption this is the fix the repro
   will confirm.** If instead the captured log/behavior points at suspect 3
   (process tree dying with the parent), the remedy is different
   (`CREATE_BREAKAWAY_FROM_JOB` and/or an explicit Job Object exempting the
   child) and the developer should apply that instead — this is a technical
   branch resolved by the CI evidence during implementation, not something
   that needs Leo's input before starting.
2. **CI job-object risk, informational, not blocking.** Noted under "Edge
   cases" — if the repro is flaky specifically on outliving its parent when
   run under GitHub's Windows runner, that may be a CI-runner artifact rather
   than the real-world bug. Worth Leo knowing about if the repro proves hard
   to get stable, but not a reason to hold off starting.
3. **Permanent step-logging — resolved by Leo, 2026-09-14: yes, ship it**,
   and the app should ask the person to send it. Split: the log ships in
   this cycle (Goals, "Shipped update log"); the in-app prompt that opens a
   prefilled GitHub issue with the log is a separate follow-up ticket. Note
   for that follow-up, not this cycle: the log contains local paths (user
   name in `C:\Users\…`), so the prompt should show the person what gets
   sent before opening the issue.

## Risk / rollback notes
- Blast radius of the fix itself is one function, one platform branch,
  additive test only — a `git revert` of the single commit fully undoes it.
- If `CREATE_NO_WINDOW` (or whatever the confirmed fix turns out to be)
  changes process-exit-code visibility or buffering in some Windows
  configuration not exercised by `windows-latest`, that would only surface on
  a real user's machine, not in CI — this is the same class of gap the
  ticket already accepts (CI is the only Windows evidence we have; a manual
  check on 0.6.0 is called out explicitly in "Acceptance criteria").
- The fix does not change on-disk script contents or the `%TEMP%` workdir,
  so it carries no risk to the filesystem-root guard tests already covering
  that path.
- Existing installed clients (0.3.1, 0.5.0) are unaffected either way — they
  run their own already-shipped, unfixed script regardless of what ships in
  0.6.0 (see "Non-goals").
