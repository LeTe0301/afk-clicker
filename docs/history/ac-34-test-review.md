# Test & Review: App icon — the Loop icon (part 2 of 2, Gitea #34 / GitHub #60)

## Scope

Covers `docs/spec.md`'s acceptance criteria for the Loop app icon: the
committed SVG source, runtime `iconphoto` wiring (load, GC-safety, survival
across `_rebuild_ui()`), the fail-loudly-on-missing-asset behaviour, and the
per-platform `--icon`/`--add-data` PyInstaller flags in
`.github/workflows/release.yml` and `build.bat`. Also covers the new
`assets/` binaries (`.svg`, `.ico`, `.icns`, four PNGs) against
`docs/design.md`'s size/variant table, and the four new tests in
`tests/test_ui.py`.

Environment: Linux only (Xvfb `:94`, scratch venv at
`/tmp/claude-1000/.../scratchpad/devvenv`). Windows `.ico`/macOS `.icns`
*embedding* (does Explorer/Finder actually show the icon) cannot be verified
here — this is explicitly accepted by `docs/spec.md`'s own acceptance
criteria as CI-build-only. What *can* be verified locally — that both files
parse as valid ICO/ICNS and contain the correct simplified/full artwork per
slot — was verified below.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | `assets/icon.svg` byte-for-byte matches spec's SVG block | automated diff | pass | `diff` against the literal spec block: no output, identical |
| 2 | `root.iconphoto` called with ≥1 non-empty `PhotoImage`, no exception (unfrozen, Xvfb) | automated (`tests.test_ui.AppIcon.test_icon_images_are_loaded_non_empty`) | pass | ran under `DISPLAY=:94`, `OK` |
| 3 | Icon reference held on `self`, survives `_rebuild_ui()` (theme/scale change) | automated (`tests.test_ui.AppIcon.test_icon_reference_survives_a_rebuild`) | pass | ran; **sabotage-checked** — reloading `self._icon_imgs` inside `_rebuild_ui()` makes this test fail with `AssertionError: [...] is not [...]` (see Findings/verification below), reverted, suite green again |
| 4 | Deleting a PNG raises visibly rather than starting with a blank icon | automated (`tests.test_ui.AppIconMissingAsset.test_missing_png_raises_instead_of_starting_blank`) | pass | ran; **sabotage-checked** — wrapping the load in `try/except tk.TclError: pass` makes this test fail with `AssertionError: TclError not raised`, reverted, suite green again |
| 5 | `release.yml` Build step per platform: `--name`, all 6 `--hidden-import`s, correct `--add-data` separator, `--icon` path | automated (PyYAML parse + printed `run:` strings) | pass | see "release.yml parse" below |
| 6 | `build.bat` carries the same `--add-data`/`--icon` flags as `release.yml`'s Windows job | manual diff | pass | `git diff` of both files against spec/implementation.md's stated changes matches exactly |
| 7 | `_asset_dir()` unfrozen resolution | automated (`tests.test_ui.AssetDir.test_unfrozen_resolves_next_to_the_module`) | pass | ran, `OK` |
| 8 | `.ico`/`.icns` per-slot artwork: simplified at 16/32(pt), full at 48+(pt) | manual (Pillow extraction + visual inspection via Read tool) | pass | see "Assets" below — every slot extracted and eyeballed |
| 9 | `icon.svg`/`icon-simplified.svg` render correct art per size class in the four runtime PNGs | manual (Read tool on the PNGs) | pass | `icon-16.png`/`icon-32.png` show loop-only; `icon-48.png`/`icon-256.png` show full mouse art |
| 10 | Windows `.exe`/macOS `.app` actually shows the icon in Explorer/Finder | not locally verifiable | n/a | per spec's own acceptance criteria — Linux-only local env, flagged explicitly, not a gap in this review |
| 11 | Frozen-build crash risk: does anything in CI actually exercise the new icon-loading code path once packaged? | automated (read `selftest()`, `__main__`, and `release.yml`'s Smoke test steps) | **fail** (see Findings #1) | `selftest()` (afk_clicker.py:228-254) never constructs `AfkAutoclicker`; `--selftest` short-circuits before it (afk_clicker.py:3400-3402); none of the three Smoke test steps in `release.yml` exercise a normal launch |

## Regression check

Full suite: `DISPLAY=:94 <devvenv>/bin/python -m unittest discover -s tests -t .`
— **297 tests, OK (skipped=5)**, run three times across this session (baseline,
post-sabotage-revert ×2). Matches the developer's reported count exactly; no
regressions. `python -m py_compile afk_clicker.py tests/test_ui.py` — clean.

## release.yml parse (PyYAML, scratch venv)

Printed each `Build (…)` step's resolved `run:` string:
- Windows: `--name "AFK Farm Clicker"`, all 6 `--hidden-import`s, `--add-data "assets;assets"`, `--icon assets\icon.ico` — present and correctly separated (`;`).
- Linux: same `--name`/6 imports, `--add-data "assets:assets"`, no `--icon` (correct — no Linux equivalent).
- macOS: same `--name`/6 imports, `--add-data "assets:assets"`, `--icon assets/icon.icns`.

`--add-data`'s destination (`assets`) matches `_asset_dir()`'s frozen branch
(`os.path.join(sys._MEIPASS, "assets")`, afk_clicker.py:636-645) exactly — the
bundled path and the runtime lookup agree.

`if:` conditions (`runner.os == 'Windows'/'Linux'/'macOS'`), Smoke test paths,
and Package steps all still line up per-OS; unchanged by this diff except for
the new flags, confirmed via `git diff`.

## Assets (Pillow, scratch venv — never added to repo/CI)

- `assets/icon.svg`: byte-identical to spec's block (`diff`, no output).
- `assets/icon-{16,32,48,256}.png`: exact pixel sizes, RGBA. 16/32 visually
  confirmed loop-only (simplified); 48/256 visually confirmed full mouse art
  (Read tool, direct visual inspection of all four).
- `assets/icon.ico`: `{(16,16),(32,32),(48,48),(256,256)}`. Extracted and
  viewed all four — 16/32 simplified, 48/256 full, matching `docs/design.md`'s
  cutoff table exactly.
- `assets/icon.icns`: slots `(16,16,@2x=32px), (32,32,@2x=64px), (128,128,@1x
  and @2x=256px), (256,256,@1x=256px and @2x=512px), (512,512,@1x=512px and
  @2x=1024px)` — matches implementation.md's stated Pillow-writer constraint
  exactly. Extracted and viewed the 32px and 64px slots (simplified, loop
  only) and the 128px slot (full, mouse present) — confirmed.
- `assets/icon-simplified.svg`: read directly, matches design.md's simplified
  block (tile + arc + arrowhead, no clipPath/mouse rects/line).
- `assets/README.md`: present, documents both SVGs as sources and the rest as
  regenerated outputs, per spec's requirement for such a note.

## Tk correctness

- `iconphoto` is called exactly once, in `AfkAutoclicker.__init__`
  (afk_clicker.py:1794-1799), outside `_build_ui()`/`_rebuild_ui()`'s scope.
  `_rebuild_ui()` (afk_clicker.py:2172 on) tears down only `root`'s children,
  never touches `self._icon_imgs` — confirmed by reading the method and by a
  sabotage check (see Test case 3): forcing a re-load inside `_rebuild_ui()`
  makes the survival test fail immediately, and removing the sabotage
  restores green. `_apply_appearance()` and `_apply_ui_scale()` both funnel
  through this same `_rebuild_ui()` tail, so both theme and UI-scale changes
  are covered by the same guarantee, not just the one path the test exercises
  directly.
- `PhotoImage` references are held on `self._icon_imgs`, a list that outlives
  `root`'s children-only teardown — confirmed non-GC'd across a real
  `_rebuild_ui()` call in the same test.
- `master=root` deviation: sabotage-reverted to the spec's literal
  `tk.PhotoImage(file=...)` (no `master=`) and reran
  `SetActiveThemeWidgets.test_dark_is_restored_after_light` — reproduced the
  developer's claimed failure exactly: `_tkinter.TclError: can't use
  "pyimage5" as iconphoto: not a photo image`. Reverted; suite green again.
  Confirmed this is a real, necessary correctness fix, not a style choice.
- All icon loading happens in `__init__`, on the thread that constructs
  `AfkAutoclicker` (main thread, per the `__main__` block) — no
  worker-thread Tk access introduced.

## Spec coverage

| Acceptance criterion | Status |
|---|---|
| `assets/icon.svg` byte-for-byte | met, verified |
| `iconphoto` called, non-empty `PhotoImage`, no exception (unfrozen) | met, verified |
| Icon reference survives rebuild, not GC'd | met, verified (incl. sabotage check) |
| Missing PNG raises visibly | met, verified (incl. sabotage check) |
| `release.yml` per-platform `--icon`/`--add-data` | met, verified |
| `build.bat` matches `release.yml`'s Windows flags | met, verified |
| CI build shows the icon in Explorer/Finder | not locally verifiable — correctly flagged by spec itself as CI-build-only |

All seven written acceptance criteria are implemented and covered by a real
test or direct inspection. The gap below is **not** a written acceptance
criterion — it is a robustness gap the spec's edge cases didn't anticipate
(missing/broken bundling of a *correctly-present* asset, as opposed to a
missing file in a developer's checkout).

## Findings (most severe first)

### 1. `selftest()` never exercises the new icon-loading path — a broken `--add-data` on any platform ships a build that crashes on launch, undetected by CI — must-fix
- File: `afk_clicker.py:228-254` (`selftest()`), `afk_clicker.py:3400-3402`
  (`--selftest` short-circuit), `.github/workflows/release.yml`'s three
  "Smoke test" steps (~192-207)
- Issue: `selftest()`'s docstring states its entire purpose: "a `--windowed`
  build has no console, so a missing hidden import does not show up as a
  traceback — it shows up as 'I double-clicked it and nothing happened'."
  `TECHSTACK.md`'s Build section states the same non-negotiable:
  "`--selftest` must run in CI." This project's own
  `docs/REVIEW-PROTOCOL.md` §6 ("Tech stack conformance") lists
  "`--selftest` still exercised" alongside no-`--onefile`/no-UPX as a
  build-flag check. `selftest()` was not extended to touch the new icon
  code, and structurally *cannot* be reached by it: `if "--selftest" in
  sys.argv: sys.exit(selftest())` returns before `AfkAutoclicker` is ever
  constructed (afk_clicker.py:3400-3402), so `root.iconphoto`/the four
  `tk.PhotoImage(...)` loads at afk_clicker.py:1794-1799 — the *only* new
  runtime code this spec adds — is never executed by any of the three
  per-platform Smoke test steps in `release.yml`.
- Failure scenario: `--add-data "assets;assets"`/`"assets:assets"` is wrong
  on any one of the three runners (wrong destination folder, PyInstaller
  version/OS quirk in how it lays out `sys._MEIPASS`, a future edit to
  `_asset_dir()` that silently breaks the frozen branch, etc.) — CI's Build,
  Smoke test, and Package steps all stay green because `--selftest` never
  reaches the code that would fail. The released `--windowed` .exe/.app then
  raises an uncaught `tk.TclError` the instant a real user double-clicks it
  (by design — this code deliberately has no `try/except`, per the spec's
  own "fail loudly" edge case), with no console to show it. This is exactly
  the "double-clicked it and nothing happened" failure `selftest()` exists
  to catch in CI instead of in the field, and nothing here catches it.
- Suggested direction (not a fix, for the developer): extend `selftest()` to
  resolve `_asset_dir()` and load the four `icon-*.png` files (mirrors the
  existing pattern of touching every other lazily-resolved/bundled
  dependency in that function) — this catches a broken `--add-data` path in
  CI without needing to verify the `.ico`/`.icns` *display* itself (which
  the spec already correctly scopes as CI-build-only, out of reach for
  `--selftest`).

No should-fix or nit findings — the rest of the diff (asset content, build
flags, Tk lifecycle, deviations) checked out cleanly against spec, design,
and the project's own conventions.

## Follow-ups (non-blocking)
- None beyond Finding #1, which is must-fix.

## Overall verdict
Changes requested — one must-fix (Finding #1). Everything else (all seven
written acceptance criteria, the asset content and per-slot artwork, the
`release.yml`/`build.bat` flags, Tk GC/rebuild safety, and the `master=root`
deviation) is implemented correctly and verified directly in this session,
including sabotage checks in both directions on three of the four new tests
plus the `master=root` fix. Route back to the developer to close the
`selftest()` coverage gap in Finding #1; no other rework needed.

---

## Round 2

Scope: round-2 diff only (the `selftest()`/`_load_app_icon()` fix for
Finding #1 and its one new test), per the dispatch instructions. Round 1's
asset content, `release.yml`/`build.bat` flags, and the three
already-sabotage-checked tests were not re-inspected — nothing in this diff
touches them.

Environment: fresh Xvfb `:94` (1280x1024x24), scratch venv at
`/tmp/claude-1000/-home-dev-projects-afk-clicker/46904a5e-d1e9-47ce-89fc-898b879994f7/scratchpad/devvenv`,
killed at the end of this pass.

### Diff read directly

```
afk_clicker.py: +34/-1 net across three hunks
```
- `selftest()` (afk_clicker.py:247-253): `tk.Tk().destroy()` →
  `icon_root = tk.Tk(); _load_app_icon(icon_root); icon_root.destroy()`.
- New module-level `_load_app_icon(root)` (afk_clicker.py:654-673): loads
  `icon-{16,32,48,256}.png` via `tk.PhotoImage(master=root, ...)`, calls
  `root.iconphoto(True, *imgs)`, returns `imgs`. No `try/except`.
- `AfkAutoclicker.__init__` (afk_clicker.py:1819): inline load replaced with
  `self._icon_imgs = _load_app_icon(root)`, same call site, same behavior.
- `tests/test_ui.py`: one new test,
  `Selftest.test_selftest_fails_when_icon_asset_missing` (lines 1810-1823) —
  monkeypatches `app._asset_dir` to an empty temp dir (save/restore, this
  file's existing style) and asserts `app.selftest()` raises `tk.TclError`.

Grepped the whole file for `PhotoImage(`/`iconphoto`: exactly the two
expected occurrences inside `_load_app_icon` itself, called from exactly two
places (`selftest()` line 248, `AfkAutoclicker.__init__` line 1819) — no
duplicate load path left anywhere. `master=root` and the `self._icon_imgs`
reference-holding from round 1 are both unchanged in the extracted function.

### Test cases (round 2)

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | `selftest()` now exercises `_load_app_icon` (closes Finding #1) | automated (`Selftest.test_selftest_fails_when_icon_asset_missing`) + manual CLI | pass | see below |
| 2 | `selftest()` still proves Tcl/Tk is bundled | code read + manual run | pass | `icon_root = tk.Tk()` is the same constructor call the old `tk.Tk().destroy()` line made; unchanged proof, now with the icon load between construction and teardown |
| 3 | `--selftest`, assets present, unfrozen, real subprocess | manual: `DISPLAY=:94 <venv>/bin/python afk_clicker.py --selftest; echo $?` | pass | `EXIT=0` |
| 4 | `--selftest`, one PNG renamed away | manual: same command with `assets/icon-32.png` moved out of the tree | pass | real traceback, `_tkinter.TclError: couldn't open ".../assets/icon-32.png": no such file or directory`, `EXIT=1`; file restored immediately after, `git status --porcelain assets/` showed only the pre-existing untracked `assets/` dir, no stray diff |
| 5 | Leaked `icon_root` / exit-code semantics on the failure path matter for CI's smoke step? | reasoned from code + the manual run above | no impact | `icon_root.destroy()` is skipped when `_load_app_icon` raises, but the process is crashing anyway — CPython's default excepthook prints the traceback and exits 1 before `sys.exit(selftest())` is ever reached. `release.yml`'s Windows step explicitly checks `$p.ExitCode -ne 0`; Linux/macOS `run:` steps use GitHub Actions' default bash `-e`, which fails the step on any non-zero exit. All three platforms already fail correctly; no leaked-process concern since the OS reclaims everything on process exit |
| 6 | New test genuinely detects the gap (not a coincidental pass) | sabotage: reverted `selftest()` to `tk.Tk().destroy()` (no icon load), ran `tests.test_ui.Selftest` alone | pass | `test_selftest_fails_when_icon_asset_missing` → `FAIL: AssertionError: TclError not raised`; `test_selftest_passes` still `ok`. Reverted from a saved copy, reran the same two tests: both `ok` again |
| 7 | Monkeypatch cleanup on both the pass and the injected-fail path | observed across the sabotage run above | pass | `finally: app._asset_dir = real_asset_dir` ran on both the induced failure and the restored-fix pass; no leakage into later tests (confirmed by the full-suite run below) |

### Regression check
`DISPLAY=:94 <devvenv>/bin/python -m unittest discover -s tests -t .` →
**298 tests, OK (skipped=5)**, run twice (baseline, post-sabotage-revert) —
matches the developer's reported count exactly, one more than round 1's 297
(the one new test), no regressions. `python -m py_compile afk_clicker.py
tests/test_ui.py` — clean.

### Spec/finding coverage
| Item | Status |
|---|---|
| Finding #1: `selftest()` exercises the icon-loading path | closed, verified (automated test + manual CLI both directions) |
| Round-1's seven acceptance criteria | unaffected by this diff, not re-verified this round (out of scope per dispatch) |

### Findings (round 2)
None. No must-fix, should-fix, or nit findings against the round-2 diff.

### Overall verdict (round 2)
**Approve.** Finding #1 is closed: `_load_app_icon(root)` is the single
shared load path for both `AfkAutoclicker.__init__` and `selftest()`,
verified by direct grep (no duplicate `PhotoImage`/`iconphoto` call sites),
by running `--selftest` from source with assets present (exit 0) and with one
asset renamed away (exit 1, real `TclError`), and by sabotage-reverting the
fix and watching the new test fail for the right reason, then restoring and
watching it pass again. The full suite is green at 298/298 (skipped=5), the
leaked-root/exit-code question raised in the dispatch has no practical impact
on any of the three CI smoke-test steps, and the diff introduces no new scope
beyond the finding it closes. No further rework needed; ready to return to
the product-manager agent.
