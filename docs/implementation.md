# Implementation: Rename product to Clickwork (part 1 of 2 — branding/strings, G#33/GH#59)

## Summary

Renamed every user-visible occurrence of "AFK Farm Clicker" to "Clickwork"
(window title, header label, README, release asset names, release-body
table, updater `User-Agent` header, updater temp-dir prefix), while
deliberately leaving the packaged executable/bundle name, `APP_DIR_NAME`,
the Linux config directory, `GITHUB_REPO`, and `ASSET_SUFFIX` untouched, per
the spec's back-compat constraint (existing installs' `write_swap_script()`
scripts relaunch a hard-coded old-named exe/bundle path and would break on
their next auto-update otherwise). No production logic changed — this is a
string/text/CI-config/test-fixture rename only.

## Changes by file

- **`afk_clicker.py`**
  - `root.title("AFK Farm Clicker")` → `root.title("Clickwork")` (window
    title bar).
  - Header `tk.Label(..., text="AFK Farm Clicker", ...)` → `text="Clickwork"`.
  - `User-Agent: AFKFarmClicker/{__version__}` → `Clickwork/{__version__}`,
    at all three request sites (`latest_release()`, `fetch_checksums()`,
    `download_and_stage()`).
  - Temp-dir prefix `afkclicker-update-` → `clickwork-update-`, at both call
    sites (`download_and_stage()` and `write_swap_script()`'s fallback
    workdir).
  - Updated the comment above the `ChecksumError` in `download_and_stage()`
    that quotes an example asset name to justify the "fixed words first"
    message ordering — swapped the stale `AFK-Farm-Clicker-linux-x86_64.tar.gz`
    example for the real new name `Clickwork-linux-x86_64.tar.gz`, and
    re-verified the 40-char truncation budget claim still holds (see
    "Verification" below — it does, by a wider margin than before since the
    new name is shorter).
  - **Left unchanged, verified by direct read**: `APP_DIR_NAME =
    "AFKFarmClicker"`, the Linux `afk-farm-clicker` dir in `config_path()`,
    `GITHUB_REPO`, `ASSET_SUFFIX`.

- **`.github/workflows/release.yml`**
  - Build matrix `asset:` values → `Clickwork-windows-x64.zip`,
    `Clickwork-linux-x86_64.tar.gz`, `Clickwork-macos-arm64.zip`.
  - Release body's file-name table updated to the same three new names.
  - Added a one-line "why" comment directly above the `Build` step
    explaining that `--name "AFK Farm Clicker"` is deliberately not renamed
    yet, pointing at this implementation doc's future path
    (`docs/history/ac-33-implementation.md`) so a future editor doesn't "fix"
    it blind. (Placed as a YAML-level comment before the step, not inside the
    folded `run: >` scalar — a `#` inside that block would become part of
    the literal shell command line, not a YAML comment, and would have
    silently truncated the `pyinstaller` invocation.)
  - **Left unchanged, verified by direct read**: `--name "AFK Farm Clicker"`
    (the actual PyInstaller build name), all three smoke-test exe paths, and
    all three packaging-step `dist/AFK Farm Clicker...` paths.

- **`build.bat`**
  - Softened line 3's product description to "Builds the Clickwork Windows
    program (packaged internally as \"AFK Farm Clicker\" — see
    docs/history/ac-33-implementation.md)."
  - Added a 3-line comment directly above `--name "AFK Farm Clicker"`
    (line 59, now shifted by the inserted comment) explaining the same
    back-compat constraint.
  - **Left unchanged, verified by direct read**: `--name "AFK Farm Clicker"`
    itself, and every literal output path in the trailing echo block (lines
    that were 5, 77, 79 before the comment insertions — content unchanged,
    only shifted down by the added lines above them).

- **`README.md`**
  - Line 1 title `# AFK Farm Clicker` → `# Clickwork`.
  - Download table's three file names → the new `Clickwork-*` names.
  - **Left unchanged, verified by direct read**: the settings-path table
    (`AFKFarmClicker`, `afk-farm-clicker`, and the macOS path), byte-for-byte,
    since those directories are not being renamed.

- **`tests/test_updater.py`**
  - Renamed every mocked *release asset name* fixture from `AFK-Farm-Clicker-*`
    to `Clickwork-*`: the `AssetSelection.RELEASE` fixture, the
    "no matching platform" test, `test_picks_the_checksum_asset`, and the two
    status-line-truncation tests' `real_path` file names (plus their
    explanatory comments, which quoted the old name as the example).
  - **Left unchanged, verified by direct read**: every `"AFK Farm Clicker"`
    literal used as a *staged build-folder name* inside test zips/tarballs
    (the `Staging`, `ChecksumVerification`/`StagingSafety`, and swap-script
    tests) — these simulate PyInstaller's unchanged `--name` output, not a
    release asset.

- **`tests/test_ui.py`**
  - Renamed the six mocked release-asset-name fixtures from
    `AFK-Farm-Clicker-linux-x86_64.tar.gz` to `Clickwork-linux-x86_64.tar.gz`
    (lines that were 683, 715, 3038, 3169, 3222, 3245 pre-edit).
  - `test_ui.py:3038`'s hand-truncated literal
    `"checksum: not in SHA256SUMS: AFK-Farm-Clicker-linux-x86_64.tar.gz"[:40]`
    updated in lockstep to use `Clickwork-linux-x86_64.tar.gz`; re-verified
    the truncated 40-char result still contains "checksum" (it does — the
    fixed prefix `"checksum: not in SHA256SUMS: "` is 29 characters, well
    inside the 40-character budget regardless of which asset name follows).
  - Note: contrary to the task brief's assumption, `tests/test_ui.py` turned
    out to have **no** build-folder-name (`"AFK Farm Clicker"` literal)
    fixtures at all — confirmed by grep after the edits (see "Verification").
    The spec's background section's line list for `test_ui.py`'s
    folder-name fixtures (64, 72, 75, 97, 155, 162, 175, 177, 185, 209, 267,
    286, 287) matches `tests/test_updater.py`'s actual line numbers, not
    `test_ui.py`'s — an apparent copy/paste mix-up in the spec's own
    background research, not something requiring a spec change (it's
    non-load-bearing background detail; the acceptance criteria and
    per-file "Test changes" section were followed as written and are
    correct).

## Key decisions

- Followed the spec's explicit instruction to place the two "--name stays
  unchanged, here's why" comments as a genuine explanatory note rather than
  skip them, since both `release.yml` and `build.bat` are exactly the kind
  of file a future editor might "clean up" without this context.
- In `release.yml`, inserted the explanatory comment as a step-level YAML
  comment immediately before `- name: Build`, not inside the `run: >` folded
  scalar. A folded scalar has no comment syntax of its own — a `#` inside it
  is passed straight through as a shell comment character on that same
  logical command line, which would have truncated the `pyinstaller`
  invocation exactly at `--name "AFK Farm Clicker"` and dropped every flag
  after it (`--windowed`, all six `--hidden-import`s, and the script
  argument). Verified the final YAML round-trips through `yaml.safe_load()`
  correctly and that the `Build` step's `run:` string is unaffected.

## Deviations from spec

None. Every "Non-goal" site was checked by direct read before editing
(`APP_DIR_NAME`, Linux config dir, `GITHUB_REPO`, `ASSET_SUFFIX`, the
PyInstaller `--name` in both `release.yml` and `build.bat`, all smoke-test
and packaging paths, the README settings-path table) and left untouched. The
one place this implementation diverges from the task brief's line-number
hints (not the spec itself) is documented above under `tests/test_ui.py` —
those specific line numbers named no real fixtures in that file; the actual
work item (rename the six release-asset fixtures, update the 3038
truncation literal in lockstep) was carried out per the spec's own
"Test changes" section, which was correct.

## Known limitations

- As designed by the spec: the packaged executable/bundle still exists on
  disk as `AFK Farm Clicker.exe` / `AFK Farm Clicker` / `AFK Farm
  Clicker.app` after this cycle. A user downloads "Clickwork," sees
  "Clickwork" everywhere in the UI, but the installed folder/exe name is
  unchanged under the hood. This is the deliberate, spec'd outcome, not a
  bug — tracked as a follow-up once every currently-installed copy has had
  a chance to update through this build (see spec's "Open questions").
- `__version__` was not bumped, per the spec's explicit non-goal (that
  happens at release-cut time on a `release/{version}` branch).

## Verification

Ran the following in this session:

- `python3 -m py_compile afk_clicker.py tests/test_ui.py
  tests/test_updater.py` — succeeds, no syntax errors introduced.
- `yaml.safe_load()` against the modified `.github/workflows/release.yml`
  — parses successfully; the `Build` step's `run:` string was inspected
  directly to confirm the added comment sits outside it.
- Repo-wide sweep: `grep -rn "AFK Farm Clicker\|AFK-Farm-Clicker\|
  AFKFarmClicker\|afk-farm-clicker\|afkclicker" --exclude-dir=.git
  --exclude-dir=history .` — every remaining hit is one of: `build.bat`/
  `release.yml`'s unchanged `--name`/smoke-test/packaging paths, the README
  settings-path table, `afk_clicker.py`'s `APP_DIR_NAME`/config dir, the
  `tests/test_updater.py` build-folder fixtures, and `docs/spec.md`/
  `docs/design.md` themselves (which describe the rename and are expected
  to quote the old name throughout). No unintended occurrence remained.
- Full test suite, under Xvfb (this project's documented headless test
  environment — no system pynput/xauth on this box): created a venv at
  `/tmp/claude-1000/-home-dev-projects-afk-clicker/46904a5e-d1e9-47ce-89fc-898b879994f7/scratchpad/devvenv`,
  `pip install pynput`, started `Xvfb :93 -screen 0 1280x1024x24 -nolisten
  tcp`, then ran
  `DISPLAY=:93 <venv>/bin/python -m unittest discover -s tests -t .`
  from the repo root.
  **Result: `Ran 293 tests in 61.358s — OK (skipped=5)`** — matches main's
  known CI baseline of 293 green tests, no new failures. Killed the Xvfb
  process afterward; no leftover processes or scratch files remain in the
  repo.

### How to re-verify locally

```
python3 -m venv /tmp/some-venv && /tmp/some-venv/bin/pip install pynput
Xvfb :93 -screen 0 1280x1024x24 -nolisten tcp &
cd /home/dev/projects/afk-clicker
DISPLAY=:93 /tmp/some-venv/bin/python -m unittest discover -s tests -t .
pkill -f "Xvfb :93"
```

To eyeball the UI rename directly:
```
DISPLAY=:93 /tmp/some-venv/bin/python afk_clicker.py
```
(the window title and header label should both read "Clickwork").
