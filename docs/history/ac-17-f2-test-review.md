# Test & Review: OS light/dark detection (story #17, Feature 2)

## Scope
`detect_os_theme()` + its three seams (`_run_theme_command`,
`_read_windows_theme_registry`, `_detect_linux_theme`), `set_active_theme()`,
the `_lighten()` hardening, and the two new call sites (`__main__`,
`selftest()`) — all of `docs/spec.md`'s 19 acceptance-criteria checkboxes.
`docs/design.md` in this worktree is a Feature 1 leftover and was ignored;
this file replaces the Feature 1 `docs/test-review.md`.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Windows registry `0` → dark | automated | pass | `tests/test_ui.py::DetectOsTheme::test_windows_registry_value_0_is_dark` |
| 2 | Windows registry `1` → light | automated | pass | `test_windows_registry_value_1_is_light` |
| 3 | Windows registry `2` (garbage) → dark | automated | pass | `test_windows_registry_garbage_value_is_dark` |
| 4 | Windows registry `FileNotFoundError` → dark, no raise | automated | pass | `test_windows_registry_missing_key_is_dark` |
| 5 | Windows registry other exception → dark, no raise | automated | pass | `test_windows_registry_unexpected_oserror_is_dark`, `..._any_other_exception_is_dark` |
| 6 | macOS stdout `"Dark\n"` exit 0 → dark | automated | pass | `test_macos_key_present_exit_0_is_dark` |
| 7 | macOS `CalledProcessError` (key absent) → light | automated | pass | `test_macos_key_absent_nonzero_exit_is_light`; also reverted the branch in memory and watched it fail (Round 8 log below) |
| 8 | macOS `FileNotFoundError` → dark | automated | pass | `test_macos_defaults_binary_missing_is_dark` |
| 9 | macOS `TimeoutExpired` → dark | automated | pass | `test_macos_timeout_is_dark` |
| 10 | Linux `prefer-dark` short-circuits (gtk-theme not called) | automated | pass | `test_linux_prefer_dark_short_circuits_before_the_fallback` (asserts call count == 1) |
| 11 | Linux `prefer-light` → light | automated | pass | `test_linux_prefer_light` |
| 12 | Linux `default` + `Yaru-dark` → dark | automated | pass | `test_linux_default_falls_through_to_dark_gtk_theme` |
| 13 | Linux `default` + `Adwaita` → light | automated | pass | `test_linux_default_falls_through_to_light_gtk_theme` |
| 14 | Linux first call raises, second names dark case-insensitively → dark | automated | pass | `test_linux_first_call_raises_second_call_names_dark_case_insensitive` (`"HighContrastDark"`) |
| 15 | Linux both calls raise → dark | automated | pass | `test_linux_both_calls_raise_is_dark` |
| 16 | Linux both calls empty output → dark | automated | pass | `test_linux_both_calls_empty_output_is_dark` |
| 17 | Unrecognized `sys.platform` → dark, no raise | automated | pass | `test_unrecognized_platform_is_dark` |
| 18 | `set_active_theme("light")` reaches every sampled widget | automated | pass | `SetActiveThemeWidgets::test_light_theme_reaches_every_sampled_widget` (root bg, card bg, primary button fill, NumBox wrap bg) |
| 19 | No `set_active_theme` call → widgets still `THEMES["dark"]` | automated | pass | `test_no_theme_call_at_all_still_defaults_to_dark` |
| 20 | `--selftest` completes, exit 0 | automated (Linux, locally) | pass | `Selftest::test_selftest_passes` returns 0; real (unfaked) `detect_os_theme()` invoked in-process, 0.065 s elapsed |
| 21 | `set_active_theme` unknown name → `ValueError` | automated | pass | `SetActiveThemeUnknownName::test_unknown_name_raises_value_error` |
| 22 | `_lighten` factor clamp (>1, <0) and hex validation | automated | pass | `Lighten::test_out_of_range_factor_*`, `test_non_hex_color_raises_value_error` |
| 23 | Real subprocess timeout enforced (not just the seam) | manual probe | pass | `_run_theme_command([sys.executable, "-c", "time.sleep(10)"])` raised `TimeoutExpired` at 2.00 s |
| 24 | No hang/crash on `TimeoutExpired`/`FileNotFoundError`/`PermissionError`/`OSError`/garbage/`None`/huge-string/non-int-registry inputs | manual probe (in-memory injection beyond the 28 written tests) | pass | 10/10 injected cases returned `"light"`/`"dark"`, none raised — see probe log below |
| 25 | Windows console-flash / `CREATE_NO_WINDOW` audit | manual code read | pass | `_run_theme_command` is only reachable from `darwin`/`linux` branches; Windows uses `_read_windows_theme_registry`/`winreg` directly, no subprocess at all — confirmed no other `creationflags` use in the file applies here |
| 26 | No stray hard-coded theme-breaking hex outside `THEMES` | `grep '#[0-9a-fA-F]\{6\}' afk_clicker.py` | pass | only hits are inside `THEMES`'s own tuple literals and a comment |
| 27 | Quartz light-mode render matches the mock's "Chosen" intent (white cards, grey ground, pill controls, readable ink) | manual, screenshot review | pass | `f2-quartz.png` vs. `theme-board.html`'s "Chosen: Deepslate and Quartz" section — matches |
| 28 | No theme-state leak between tests, forward and shuffled order | automated, run twice in different class orders | pass | `SetActiveThemeWidgets → Themes → PrimaryButtonTheme → CardShell` and a reversed grouping including `DetectOsTheme`; `Themes::test_module_globals_still_ship_dark_only` (the leak detector) passed both times |
| 29 | Round 8: revert macOS non-zero-exit→light rule, and separately the outer fail-safe `except`, confirm the *actual* tests fail | manual, in-memory monkeypatch of `app.detect_os_theme`, run via `unittest.TestResult()` | pass (tests correctly fail on revert) | see log below; `git status --short` shows zero extra diff afterward |

**Probe log (case 24), platform-branch garbage/failure injection:**
```
OK  darwin: run returns None-like (no .stdout attr)   -> dark
OK  darwin: run returns huge stdout                    -> dark
OK  linux: run returns None-like object                -> dark
OK  linux: run returns huge stdout both calls           -> light
OK  win32: registry returns string "1"                  -> dark
OK  win32: registry returns None                        -> dark
OK  win32: registry raises OSError                      -> dark
OK  darwin: run raises PermissionError                  -> dark
OK  darwin: run raises generic OSError                  -> dark
OK  linux: run raises TimeoutExpired both calls          -> dark
```

**Round 8 revert log:**
```
FAIL  REVERT 1 (macOS light rule removed): test_macos_key_absent_nonzero_exit_is_light
    + light
FAIL  REVERT 2 (outer except removed): test_windows_registry_missing_key_is_dark
    FileNotFoundError: key/value missing
FAIL  REVERT 2 (outer except removed): test_windows_registry_unexpected_oserror_is_dark
    PermissionError: access denied
FAIL  REVERT 2 (outer except removed): test_windows_registry_any_other_exception_is_dark
    RuntimeError: unexpected winreg failure
FAIL  REVERT 2 (outer except removed): test_macos_defaults_binary_missing_is_dark
    FileNotFoundError: no defaults binary
FAIL  REVERT 2 (outer except removed): test_macos_timeout_is_dark
    subprocess.TimeoutExpired: ...
FAIL  REVERT 2 (outer except removed): test_macos_non_utf8_output_is_dark
    UnicodeDecodeError: ...
restored: True
```
Done by monkeypatching `app.detect_os_theme` in a scratch script (never
touching the worktree file), per the "in-memory patching, not git" handling
of the tree — `git status --short` before and after this session shows only
the developer's original two modified files, nothing else.

## Regression check
Full suite: `DISPLAY=:99 .../venv/bin/python -m unittest discover -s tests -t .`
Result: **183 tests, OK, skipped=5** — run twice (once at the start of this
pass, once after all probing), identical result both times, matching the
developer's reported baseline (155 → 183, 28 new). Also ran targeted
re-orderings (`SetActiveThemeWidgets`, `Themes`, `PrimaryButtonTheme`,
`CardShell`, `DetectOsTheme` in two different groupings) specifically to
shake out theme-global leaks between tests — clean both times.

## Defects found
None — testing pass is clean. Proceeded to the review pass.

---

## Spec coverage
All 19 checkboxes in `docs/spec.md`'s "Acceptance criteria" section map to a
named test above (rows 1–19, 21) or to the existing `Selftest` test (row 20,
unmodified but now exercising the new `detect_os_theme()` call inside
`selftest()`). No criterion is untested. The two things `docs/spec.md`
itself states are "not provable on CI" (a specific human-chosen OS setting;
Gatekeeper/notarization subprocess restrictions on a real Mac) are correctly
left unverified — that's the spec's own explicit scope boundary, not a gap
in this pass.

## Findings (most severe first)

### 1. macOS: a `defaults` crash for any reason is read as "light", not just "key absent" — should-fix (non-blocking)
- File: `afk_clicker.py:965-983` (`detect_os_theme`'s darwin branch)
- Issue: `except subprocess.CalledProcessError: return "light"` treats *any*
  non-zero exit from `defaults read -g AppleInterfaceStyle` as "the key is
  absent, so we're in light mode" — true for the documented case
  (`AppleInterfaceStyle` unset in light mode), but the same exception also
  fires for e.g. a corrupted preferences domain or a `defaults` binary that
  fails for a reason unrelated to light/dark.
- Failure scenario: a Mac in dark mode, but with a transiently corrupted
  preferences cache that makes `defaults read -g AppleInterfaceStyle` fail
  for an unrelated reason, would show Quartz (light) instead of the
  intended fail-safe Dark.
- This is a **documented, deliberate trade-off**, not an oversight —
  `docs/spec.md` lines 165-175 name this exact ambiguity and justify it via
  Apple's own convention. Worst-case impact is purely cosmetic (wrong theme
  shown once at startup, no crash, no data loss), and distinguishing "key
  genuinely absent" from "some other failure" would require parsing
  `defaults`'s stderr text, which is fragile across macOS versions and adds
  complexity the spec's Non-goals/minimal-diff framing argues against. Not
  a blocker; recorded so it isn't rediscovered as a "bug" later.

### 2. Windows/macOS real (non-monkeypatched) branches are only locally exercised via `--selftest` on this Linux sandbox — should-fix (non-blocking), already disclosed
- File: `docs/implementation.md` "Known limitations"
- The developer's own doc already states this plainly: no gated
  `if sys.platform == "win32"`/`"darwin"` real-detection test was added
  (`docs/spec.md`'s own "Provable on CI" section names this as something
  CI's `windows-latest`/`macos-latest` legs can do, not something achievable
  in a Linux-only dev sandbox). `RunThemeCommandSeam` and the existing
  `Selftest` test do give *some* real, ungated exercise (real subprocess
  spawn via `sys.executable`; real `detect_os_theme()` call inside
  `selftest()` on whatever platform CI runs on) — but nothing in this repo
  asserts a real `winreg`/`defaults` read against an actual Windows/macOS
  box, and this review session had no such box either. Confirmed
  `release.yml:150,157,161` runs `--selftest` on the frozen build on all
  three OSes, and `ci.yml`'s unit-test matrix includes
  `windows-latest`/`macos-latest`, so this gap closes automatically once
  the PR's own CI matrix runs. Not a blocker; not closeable from this
  review pass either.

No must-fix findings.

## Follow-ups (non-blocking)
- If macOS detection is ever reported unreliable in practice, consider
  distinguishing "key absent" (light) from "other failure" (dark) by
  checking `defaults`'s stderr for the specific "does not exist" text —
  not needed now; flagged only so Finding 1's trade-off isn't relitigated
  from scratch later.

## Additional review notes (ten-round protocol, condensed — no blockers surfaced)
- **Round 1 (ticket fidelity):** branch `feature/ac-17/themes-follow-system-settings-tab`
  matches the naming convention with a real ticket (#17); diff is scoped to
  exactly `docs/spec.md`'s "Affected areas" (one file, `afk_clicker.py`, plus
  its tests) — `_lighten`'s hardening is an explicit carried-over hard
  requirement from PR #28's review, not scope creep.
- **Round 2 (correctness):** no failing input found beyond Finding 1 above,
  which is a documented trade-off, not a bug. Windows registry comparison
  (`== 1`) fails safe on any non-int (`"1"`, `None`, `2`) — verified by
  probe, not just read.
- **Round 3 (threading/Tk):** `PASS — no threaded code touched.` Both call
  sites (`__main__` before `tk.Tk()`, `selftest()`) run on the main thread
  before any worker/listener exists; `set_active_theme` only reassigns bare
  module globals, no widget/Tk-variable access off-thread.
- **Round 4 (naming/shadowing):** `PASS`. Each new name (`detect_os_theme`,
  `_run_theme_command`, `_read_windows_theme_registry`, `_detect_linux_theme`,
  `_THEME_DETECT_TIMEOUT`, `set_active_theme`) defined exactly once, greps
  clean against the rest of the module namespace.
- **Round 5 (untrusted input):** `PASS`. Subprocess stdout is treated as
  untrusted throughout — stripped, quote-stripped, lowercased, substring-
  checked, never `eval`'d; `errors="replace"` prevents an invalid byte from
  becoming an uncaught `UnicodeDecodeError`; registry value is type/value
  compared, never assumed to be an `int`.
- **Round 6 (tech stack conformance):** `PASS`. No new third-party
  dependency — `winreg`/`subprocess` are stdlib. `winreg` is imported via a
  literal `import winreg` statement (same shape as the existing `ctypes`
  import in `_window_titles`'s win32 branch), which PyInstaller's static
  analysis resolves without a `--hidden-import` — that flag is specifically
  needed for pynput's string-resolved backends (`docs/TECHSTACK.md`), not
  for an ordinary lazy stdlib import. `--selftest` still exercised
  (`release.yml:150,157,161`), now also covering `detect_os_theme()`.
- **Round 7 (cross-platform):** stated per-OS, not implied: Linux is proven
  for real by CI (`ubuntu-latest`/Xvfb has no `gsettings` session — confirmed
  locally, returns `"dark"`); Windows/macOS real code paths are proven only
  by CI's `windows-latest`/`macos-latest` unit-test legs and `release.yml`'s
  frozen-build `--selftest`, not by anything run in this session (Finding 2).
  All three `if` branches funnel into the same outer fail-safe; the
  "platform not recognized" case has no `else`/crash, matching the project's
  fail-safe philosophy rather than being a missing `else`.
- **Round 8 (tests):** every one of the 28 new tests maps to a spec bullet;
  the two central fail-safes were reverted in memory and both watched to
  fail for real (Round 8 log above), not merely inspected.
- **Round 9 (comments/docs):** comments throughout explain *why* (timeout
  budget vs. `_window_titles`'s 5 s, Apple's key-presence convention, clamp-
  vs-reject rationale for `_lighten`), matching `CODING-GUIDELINES.md`; no
  restate-the-code noise found. `docs/implementation.md` documents both
  deviations from `docs/spec.md`'s illustrative code (`errors="replace"`,
  `ValueError` on unknown name) with reasoning.
- **Round 10 (roadmap/release readiness):** `docs/ROADMAP.md` has no theming
  entry to update (tracked in `docs/story.md` instead) and nothing here
  contradicts an "Explicitly not planned" item. No settings-format change,
  so no schema-version concern applies.

## Overall verdict
**Approve** (with two non-blocking follow-ups — the macOS non-zero-exit/
light conflation, and the CI-only verification of the real Windows/macOS
code paths — both already honestly disclosed by the developer in
`docs/implementation.md` rather than hidden).
