# afk-clicker (Clickwork) — facts for agents

<!-- Per-repo facts only. Cross-repo rules (tickets, branches, review, releases, asking,
     models, session lifecycle) come from admin/agent-knowledge via ~/.claude/CLAUDE.md,
     ~/.codex/AGENTS.md and ~/.aider.conf.yml — do not copy them here.
     This repo's CLAUDE.md contains exactly one line: @AGENTS.md
     How to fill this file: templates/repo/FILLING.md in admin/agent-knowledge. -->

## What it is

Clickwork: a desktop autoclicker with game detection and settings per game, plus
per-game macros and chord hotkeys. It started as a Minecraft AFK-farm clicker with an
eating pause, and Minecraft is still the only profile with tuned numbers. One Python
file, shipped for Windows, Linux (X11) and macOS. The README is in German and written
for users.
Status: published on GitHub Releases (latest `v0.9.0`, 2026-09-29); installed copies
update themselves from there · version `0.9.0` (below 1.0.0 until Leo says otherwise).

## Tracking

| | |
|---|---|
| Branch code | `afk` — `feature/afk-{n}/{description}` (open 2-letter `ac-{n}` branches keep their names) |
| Ticket repo | Gitea `admin/afk-clicker` (issues only — its git repo holds just a placeholder README, not the code) |
| GitHub mirror | `LeTe0301/afk-clicker` — mirror every ticket (`ghr`). Gitea and GitHub numbers differ; `backlog.md` writes them **G#** / **GH#**, and `Closes #X` in a PR takes the GitHub number |
| PRs on | GitHub |
| Remotes | `github` = `git@github-afk:LeTe0301/afk-clicker.git` (deploy key; the code of record and the PRs); `origin` = `/srv/git/repos/afk-clicker.git` on CT110 (toggle-app mirror) |

## Stack

Python 3.12 (3.11 works), tkinter only, pynput 1.7.7 for mouse and keyboard, PyInstaller
6.11.1 `--onedir` builds on GitHub Actions, `unittest` (Xvfb on Linux). The constraints
and their reasons: `docs/TECHSTACK.md`.

## Commands

Run from the repo root. Verification date and environment: 2026-10-20 on CT110,
Python 3.11.2, venv `~/.venvs/afk-clicker-test` (it has pynput **1.8.2**, not the pinned
1.7.7).

| What | Command |
|---|---|
| Install / env setup | `pip install "pynput==1.7.7"`; Linux also needs `python3-tk` and Xvfb. Not run: no installs on CT110 (the existing venv was used) |
| Unit tests (PR suite) | CI: `xvfb-run -a --server-args="-screen 0 1280x1024x24 -maxclients 2048" python -m unittest discover -s tests -t . -v`. **On CT110 `xvfb-run` fails (`xauth command not found`)** — start `Xvfb :N -screen 0 1280x1024x24 -maxclients 2048 &` on a free display and run `DISPLAY=:N python -m unittest discover -s tests -t .`. Verified per module (2026-10-20): `tests.test_hotkey` 39 OK, `tests.test_updater` 78 OK, `tests.test_ui` 483 OK. **The combined `discover` in one process fails on CT110** from `test_ui.SettingsNavigation` onward and then hangs (cause not found; CI is green), so run the modules separately there |
| Slow / full tests (release gate) | `AFK_SLOW_TESTS=1` + the unit-test command above (the synthetic key-press sweep in `tests/test_chords_slow.py`). Verified: `AFK_SLOW_TESTS=1 python -m unittest tests.test_chords_slow` 5 OK in 65 s |
| Type-check / lint | none configured |
| Build | Windows: `build.bat` (local, pins the same versions as CI). Linux/macOS: the per-OS `pyinstaller ...` step in `.github/workflows/release.yml`. Not run: PyInstaller is not installed on CT110, and it cannot cross-compile — Windows and macOS builds exist only on their own runners |
| Smoke test | `python afk_clicker.py --selftest` (exit 0 = every lazily resolved backend loads). Verified from source on CT110 under Xvfb, exit 0. CI runs it against each built binary |
| Run locally | `python afk_clicker.py` (needs a display; on Linux an X11 session) |
| Deploy to test | none — a desktop app with no server. The release pipeline's three builds and their smoke tests run before the approval gate |
| Deploy to production | push `release/{version}` to `github`; the pipeline stops at the `release` environment gate until Leo approves in the Actions tab. Not run |
| Version source | `afk_clicker.py:__version__` — must match `release/{version}` |

## Release pipeline

`release/{version}` is the trigger (`.github/workflows/release.yml`); pushing a tag
publishes nothing. In order:

1. **Version** — the version comes from the branch name (or the `workflow_dispatch`
   input) and must be `MAJOR.MINOR.PATCH` (`re.fullmatch`, via `env:`, never `${{ }}`
   inside `run:`).
2. **The `__version__` gate** — the run fails if `__version__` in `afk_clicker.py` is not
   the branch's version: a binary reporting the wrong version breaks the in-app updater's
   comparison quietly and permanently.
3. **Full suite** on `ubuntu-latest` with `AFK_SLOW_TESTS=1`, i.e. including the slow
   synthetic-key-press sweep that the PR suite skips.
4. **Three builds**, `fail-fast: false`: `windows-latest`, `ubuntu-22.04` (oldest runner,
   because PyInstaller links the build host's glibc) and `macos-latest`, each followed by a
   **smoke test** that runs the built binary with `--selftest`; then packaged
   (`Clickwork-windows-x64.zip`, `Clickwork-linux-x86_64.tar.gz`,
   `Clickwork-macos-arm64.zip` — macOS with `ditto`, not `zip`).
5. **Manual approval gate** — the `publish` job runs in GitHub Environment `release`,
   which requires a reviewer (LeTe0301; checked via the API 2026-10-20, environment
   created 2026-09-10, `can_admins_bypass: true`).
6. **Publication** — `SHA256SUMS` over the assets, then a GitHub Release `v{version}`
   tagged on the tested commit (`target_commitish: github.sha`). This is the only job
   with `contents: write`.

The PR suite (`.github/workflows/ci.yml`) runs on every pull request and every push to
`main`, on Linux, Windows and macOS (macOS is required, not `continue-on-error`).

## Guardrails

- **Versions stay below `1.0.0`** until Leo says otherwise — minor and patch only.
  `1.0.0` also means the UI and the settings format have stopped moving
  (`docs/ROADMAP.md`).
- **Bump `__version__` before pushing `release/{version}`** (0.9.0 was a one-line
  `Release 0.9.0` commit, now on both `main` and `release/0.9.0`), or the pipeline
  refuses to build (see above).
- **Build flags are not incidental:** no `--onefile`, no UPX, a `--hidden-import` for every
  pynput backend, `--selftest` in CI, and `--name "AFK Farm Clicker"` must not be renamed
  to Clickwork — installed copies' swap scripts relaunch that exact path
  (`docs/TECHSTACK.md`, `docs/history/ac-33-implementation.md`).
- **Only the main thread touches Tk** (`docs/CODING-GUIDELINES.md`).
- **Tests on Linux need an X display.** pynput resolves its backend at import time; with
  `CI` set and no `DISPLAY` the suite raises instead of reporting `OK (skipped=…)`
  (`tests/context.py`). Start Xvfb with `-maxclients 2048` — the suite exceeds the default
  256 clients (`ci.yml`).
- **One suite per Xvfb display.** Two Tk processes on one window-manager-less Xvfb display
  contend for X input focus and produce focus-test flakes that belong to the harness
  (`docs/history/README.md`, ac-24-f2); give each run its own display number.
- **XTEST under Xvfb delivers every synthetic press and release twice** — assert
  properties, not exact fire counts (`docs/TECHSTACK.md`).
- **A local Linux run is not the cross-platform result.** Windows and macOS evidence comes
  from the CI matrix.
- **Per-cycle scratch docs are never committed.** `docs/spec.md`, `docs/design.md`,
  `docs/implementation.md`, `docs/test-review.md` (and `docs/story.md`) live only in a
  worktree; the reviewer archives them verbatim into `docs/history/` when the cycle is
  approved (`docs/history/README.md`). Untracked copies in a working tree are that
  convention, not lost work.
- **Linux means X11.** Wayland cannot observe keys sent to other windows; the hotkey does not
  work there.

## Pointers

- `docs/TECHSTACK.md` — constraints paid for once
- `docs/CODING-GUIDELINES.md` — how code is written here and why
- `docs/ROADMAP.md` — planned, done, and explicitly not planned
- `docs/REVIEW-PROTOCOL.md` — the lenses for the single PR review
- `docs/SESSION-HANDOFF.md` — where the last session left off
- `backlog.md` — open items with their G#/GH# numbers, and the older session handoffs
- `docs/history/README.md` — archived per-cycle docs and their naming scheme
- `review-calibration/README.md` — the cases used to calibrate the review agent
- `README.md` — user-facing (German): download, settings, build, release, tests
