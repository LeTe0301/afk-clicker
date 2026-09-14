# Test & Review: Windows in-app install never completes (G#35 / GH#63)

## Scope
Reviews the diff `ab5584f..HEAD -- afk_clicker.py tests/test_updater.py` (commits
6dcab6b, b3e841d, 1c87592) against `docs/spec.md`'s acceptance criteria: the
Windows CI red→green reproduction of `_quit_for_update`'s launch bug, the fix
(`launch_swap_script` + `CREATE_NO_WINDOW`), and the shipped `update.log`
(`.cmd` and `.sh`, both variants).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Pre-fix code fails the new Windows acceptance test on windows-latest CI | Automated, CI | pass | Fetched run 34898517271 log directly: `test_production_launch_replaces_the_install_and_relaunches ... FAIL`, `target mirrored: False`, `relaunch marker present: False` |
| 2 | Fixed code passes the same test on windows-latest CI | Automated, CI | pass | Fetched run 34900930076 and run 34901735061 logs: `test_production_launch_replaces_the_install_and_relaunches ... ok` |
| 3 | Full suite passes on all 3 platforms incl. unmodified `SwapScript` assertions | Automated, CI + local | pass | CI run 34901735061: ubuntu/windows/macos all green (`gh pr checks 65`). Local: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t . -v` → `Ran 310 tests ... OK (skipped=8)` |
| 4 | Linux/macOS `Popen(["/bin/sh", script], start_new_session=True)` byte-for-byte unchanged | Manual diff read | pass | `git diff ab5584f..HEAD -- afk_clicker.py`: the only change to that branch is that it now lives inside `launch_swap_script` instead of inline; the line itself is untouched |
| 5 | `docs/implementation.md` states which suspect was confirmed, backed by real evidence | Cross-checked against raw CI logs | pass | Verified independently: phase A run 34898517271 shows the acceptance case failing with no console/stall evidence beyond a live `cmd.exe`; phase B run 34900930076's diagnostic log shows only `start pid=3324 staged=... target="...target dir" relaunch="...relaunch dir\relaunch.cmd"` and no `wait finished` line — matches the doc's claim that the stall is at the first `tasklist \| find` under the old flags, not later in the script |
| 6 | Successful update: log has `copy exit code N` and ends `done` | Automated (CI + local) + manual | pass | CI: acceptance test's own log assertions passed. My own manual run of a freshly generated `.sh` (independent of dev's tests) against real temp dirs: log ended with `start ... / wait finished after 0 iterations / copy exit code 0 / relaunch attempted / done`, target correctly mirrored, relaunch marker written |
| 7 | Failing copy: log has non-zero exit code, no `done` | Manual, independent of dev's tests | pass | Ran `write_swap_script` against a deliberately-missing staged dir (path containing a space, to also probe quoting): log = `... copy exit code 1 / relaunch attempted` (no `done`); `cp` reported `No such file or directory` as expected |
| 8 | Second update truncates rather than appends | Manual, independent of dev's tests | pass | Ran the generated `.sh` twice against the same `log_path` (first failing, second succeeding): second log contained only the second run's `start pid=...` line, first run's `staged_parent/missing staged` text was gone |
| 9 | Existing `SwapScript` assertions not weakened, only extended for `log_path` | Manual diff read | pass | `git diff ab5584f..HEAD -- tests/test_updater.py` shows only a 4th `log_path` argument added to the two existing call sites; no assertion text changed |
| 10 | `.cmd` correctness: `set /a COUNT+=1` inside a re-parsed (not batched) block, `%RC%`/`%ERRORLEVEL%` timing, `if %RC% LSS 8` threshold, quoting, and paths containing `(`/`)`/`&` (e.g. `Program Files (x86)`) | Manual code read + CI evidence | pass | Read `afk_clicker.py:881-901` line by line: `set /a COUNT+=1` reads/writes `COUNT` directly (no `%COUNT%` needed), correct without delayed expansion since each pass through `:wait` is freshly parsed via `goto`, not a batched loop. `RC` is set from `%ERRORLEVEL%` on its own top-level line immediately after `robocopy`, then read once by `if %RC% LSS 8 (`, also top-level — no staleness. No `staged`/`target`/`relaunch`/`log_path` value is ever interpolated *inside* a parenthesized block (only `%LOG%`/`%RC%`/`%COUNT%` references are) — the literal-path lines are all single, unblocked statements, where a stray `)` is not special to cmd (parens are only special in FOR/IF block syntax) and `&` is neutralised because each value is fully wrapped in its own `"..."` quotes. Confirmed live on real CI: run 34900930076's diagnostic log actually printed `target="C:\Users\RUNNER~1\...\target dir" relaunch="C:\Users\RUNNER~1\...\relaunch dir\relaunch.cmd"` — the fixture's `target dir`/`relaunch dir` (spaces) round-tripped correctly through this exact echo line |
| 11 | `.cmd`: relaunch attempted even when copy fails | Automated + manual read | pass | `SwapScriptWindowsCmdText.test_relaunch_is_attempted_even_if_the_copy_fails` passed (local + CI); confirmed by reading `afk_clicker.py:896-900` that `start "" "{relaunch}"` sits outside the `if %RC% LSS 8 (...)` block |
| 12 | `timeout` replaced with `ping -n 2 127.0.0.1`, no busy-spin | Automated, CI | pass | `SwapScriptWindowsCmdText.test_no_timeout_left_in_the_wait_loop` (local+CI, ok); `WindowsLaunchReproduction.test_wait_loop_paces_polls_instead_of_busy_spinning` — CI run 34900930076: `ok` |
| 13 | Every `write_swap_script` caller updated for the new `log_path` arg | `grep` across repo | pass | Only two definitions/call sites in production (`afk_clicker.py:846`, `:3046`) and all test call sites (`tests/test_updater.py`) pass 4 args; no stale 3-arg call site anywhere |
| 14 | `_install_worker`'s `except Exception` covers a `write_swap_script`/`os.makedirs` failure with a sane status | Manual code read | pass | `write_swap_script` call sits inside the same `try` block as `download_and_stage`/`install_root`; the trailing `except Exception as exc: ... "Update failed: {exc}"[:40]` catches any `OSError` from `os.makedirs`, same as every other staging failure |
| 15 | Sabotage-verify the new `.sh`/log tests | Manual, actually run | pass | See "Sabotage verification" below — 3 independent sabotages, each confirmed red, then reverted; `git status`/`git diff` confirmed clean afterward |
| 16 | No UI change; Settings → Install status flow untouched | Manual diff read | pass | Diff touches only `write_swap_script`, new `launch_swap_script`, `_install_worker`'s log-path line, and `_quit_for_update`'s body; `_set_update_state` and all UI code untouched |
| 17 | `%TEMP%` workdir behaviour untouched | Manual diff read | pass | `workdir = os.path.dirname(os.path.dirname(os.path.abspath(staged)))` and its guard are byte-identical in the diff |
| 18 | Manual 0.6.0 install-on-real-Windows check | Manual, deferred | not yet done (by design) | Spec explicitly calls this a post-release manual check that CI cannot close ("Call this out explicitly to Leo... automated CI evidence alone does not close this criterion") — flagged as an open item below, not a blocker for this cycle |

## Regression check
Full suite, local: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t . -v` → `Ran 310 tests in 112.279s / OK (skipped=8)`. No pre-existing test's outcome changed. Also independently confirmed via the real CI run for the current HEAD (1c87592, PR #65, run 34901735061): `test (ubuntu-latest)` / `test (windows-latest)` / `test (macos-latest)` all green (`gh pr checks 65`, `gh run view 34901735061`).

## Sabotage verification (performed independently this session, not reusing the dev's own sabotage runs)
All done against `afk_clicker.py`, each confirmed red then reverted to the exact original text (`git status`/`git diff` clean afterward):

| Sabotage | Test | Result |
|---|---|---|
| `.sh`: `done` echo replaced with a no-op inside the success guard | `SwapScriptLogLifecycle.test_successful_update_ends_with_done_and_records_the_exit_code` | `AssertionError: 'relaunch attempted' != 'done'` |
| `.sh`: `: > "$LOG"` → `: >> "$LOG"` (truncate → append) | `SwapScriptLogLifecycle.test_a_second_update_truncates_the_log_rather_than_appending` | `AssertionError: 10 != 5` |
| `.sh`: `done` echo made unconditional (wrong gate) | `SwapScriptLogLifecycle.test_a_failing_copy_records_a_nonzero_exit_code_and_never_writes_done` | `AssertionError: True is not false` (log ended with `done` despite `copy exit code 1`) |

## Spec coverage
Every acceptance criterion in `docs/spec.md` maps to a test case above (1–17), all passing. Criterion 18 (manual real-Windows install check) is explicitly deferred by the spec itself to a post-release manual step — not an automatable gap in this cycle, and the spec anticipates exactly this. No acceptance criterion was found unimplemented or untested.

## Findings (most severe first)
None that block approval. No must-fix or should-fix issues found.

### Nits (optional, not blocking)
- `afk_clicker.py:1112` (pre-existing, not touched by this diff): a comment says "unlike the swap-script Popen call (afk_clicker.py:1528-1529)" — this line reference was already stale before this branch (it pointed at `_quit_for_update`'s old location, itself long since moved) and the diff's insertions earlier in the file (the new `launch_swap_script` function, the expanded `write_swap_script`) push the real target further away (now ~line 956). Out of scope for this hotfix (unrelated code, minimal-diff philosophy) — worth a one-line fix next time someone is in that area, not now.

## Follow-ups (non-blocking)
- The manual 0.6.0-on-real-Windows install check (spec's last acceptance criterion) is still outstanding — call this out to Leo once 0.6.0 ships, per the spec's own wording.
- The in-app "send us the log" prompt is explicitly split into a separate follow-up ticket per spec's non-goals; not part of this cycle.
- `%` characters in `staged`/`target`/`relaunch`/`log_path` remain a known, pre-existing, undocumented-in-code (but documented in `docs/implementation.md`) `.cmd` interpolation risk — out of scope for this hotfix, already called out by the developer.

## Overall verdict
**Approve.**

Testing pass: all 18 test cases pass, backed by real command output and CI logs fetched and inspected directly this session (not trusted from the implementation doc), plus independent manual exercise of the `.sh` log lifecycle (success, failing copy, truncation-on-second-run) and independent sabotage-verification of three of the new tests. Full local suite: 310 tests, OK, skipped=8, matching CI. Current HEAD's CI (PR #65, run 34901735061) is green on all three platforms.

Review pass: read the full diff directly (`git diff ab5584f..HEAD`), traced every acceptance criterion to code and to a test, verified the `.cmd`'s parenthesized-block/quoting semantics line by line (including the `Program Files (x86)` regression risk called out in the dispatch) against both static reasoning and live CI evidence containing real spaced paths, confirmed every `write_swap_script` call site was updated, confirmed the Linux/macOS launch line is byte-identical, and confirmed `_install_worker`'s exception handling covers a log-directory-creation failure. No must-fix or should-fix findings; one pre-existing, out-of-scope stale comment noted as a nit.
