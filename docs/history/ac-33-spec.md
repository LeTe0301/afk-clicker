# Spec: Rename product to Clickwork (part 1 of 2 — branding/strings; icon is part 2)

## Summary
Rename the product's user-visible identity from "AFK Farm Clicker" to
"Clickwork" everywhere a person reads it (window title, header, README,
release page), while deliberately keeping every on-disk name that an
already-installed client's auto-updater depends on unchanged, so existing
0.3.1/0.5.0 installs keep updating successfully instead of self-destructing.

This is part 1 of a two-part split (see "Affected areas" for why): part 2,
the Loop icon, is `docs/spec-part2-icon.md` and should run as its own
build cycle after this one lands, not in the same dispatch.

## Goals
- Every string a user actually reads says "Clickwork", not "AFK Farm Clicker":
  window title, header label, README (product name, download table, settings
  path table's prose), release-page body text, release archive file names.
- The in-app self-updater keeps working, unattended, for every copy of the
  app already installed (0.3.1 and 0.5.0 are both confirmed live per the
  handoff note) — this rename must not be the thing that breaks it.
- Existing users' saved per-game settings (`settings.json`) survive the
  upgrade untouched.

## Non-goals
- **Not renaming the packaged executable/bundle.** `AFK Farm Clicker.exe`
  (Windows), `AFK Farm Clicker` (Linux binary), `AFK Farm Clicker.app`
  (macOS bundle) keep their exact current names this cycle. See "Proposed
  approach" for why — this is the one deliberate, load-bearing decision in
  this spec.
- **Not renaming the settings directory.** `APP_DIR_NAME = "AFKFarmClicker"`
  and the Linux `afk-farm-clicker` config dir stay as-is. No migration code
  is written, because nothing moves.
- **Not renaming the GitHub repo** (`LeTe0301/afk-clicker`) or `GITHUB_REPO`.
  The updater polls `https://api.github.com/repos/{GITHUB_REPO}/...`; renaming
  the repo would change that URL for every already-shipped client that has
  the old value baked in via `__version__`'s module constant — no benefit
  here outweighs that.
- **Not the app icon.** That is `docs/spec-part2-icon.md`.
- **Not fixing the open Windows update bug** (install closes the app, a
  console flashes, files never replaced, still v0.3.1 — reported by Leo,
  root cause unconfirmed). Noted only in "Open questions" insofar as it
  interacts with this rename.
- **Not bumping `__version__`.** That happens at release-cut time on a
  `release/{version}` branch per the existing process (see "Open questions"
  — main's `__version__` is currently behind the last published tag for
  unrelated reasons, not something this spec fixes).

## Background / current state
Every occurrence of "AFK Farm Clicker" today (grep, excluding `docs/history`
and `.git`):

- **UI strings**: `root.title("AFK Farm Clicker")` at `afk_clicker.py:1772`;
  header `tk.Label(..., text="AFK Farm Clicker", ...)` at `afk_clicker.py:2036`.
  No `iconphoto`/`iconbitmap` call exists anywhere today (that's part 2).
- **Updater identity** (cosmetic, no wire-format meaning): `User-Agent:
  AFKFarmClicker/{__version__}` at `afk_clicker.py:606, 670, 745`; temp
  directory prefix `afkclicker-update-` at `afk_clicker.py:741, 819`; a
  comment at `afk_clicker.py:771` referencing the old name in a message that
  is itself string-length-budgeted (see "Edge cases").
- **Settings location**: `APP_DIR_NAME = "AFKFarmClicker"` at
  `afk_clicker.py:854`; Linux config dir `afk-farm-clicker` in
  `config_path()` (`afk_clicker.py:857-864`). `README.md:59-61` documents
  these paths in a table.
- **Build/CI**: `--name "AFK Farm Clicker"` in `.github/workflows/release.yml:131`
  and `build.bat:59` (PyInstaller's internal build name — **not changing**,
  see below); the release matrix's asset display names
  `AFK-Farm-Clicker-{windows-x64.zip,linux-x86_64.tar.gz,macos-arm64.zip}`
  (`release.yml` matrix, ~lines 110-116); smoke-test paths that reference the
  *build* name, not the asset name (`release.yml:149,157,161` — unaffected,
  see below); packaging steps that reference the *build* name
  (`release.yml:166,170,176` — unaffected); release body text listing the
  asset table (`release.yml:224-226`); `README.md:1,19-21` (title, download
  table); `build.bat` comments at lines 3, 5, 77, 79.
- **Tests hard-code both kinds of name** and need to be told apart:
  `tests/test_updater.py` and `tests/test_ui.py` use `"AFK-Farm-Clicker-*"`
  as mock *release asset* names (safe to rename — matched by suffix only,
  see below) at `test_updater.py:26-28,42,100` and `test_ui.py:35-37,51,3038,
  3169,3222,3245`; the same files separately use the literal string
  `"AFK Farm Clicker"` as the *staged build folder name* inside test tarballs/
  zips, simulating PyInstaller's `--name` output — `test_updater.py:55,63,66,
  88,352,375` and `test_ui.py:64,72,75,97,155,162,175,177,185,209,267,286,287`.
  Those folder-name fixtures must **not** change, because the actual `--name`
  is not changing either.

## Proposed approach

### The hard constraint and the decision
Every already-installed copy (0.3.1, 0.5.0, and anything shipped before this
change) carries its own `write_swap_script()`-generated script
(`afk_clicker.py:806-848`), already written to disk from a *previous* run of
the *old* code. That script does two fixed things once the current process
exits: mirror the staged new build over `install_root()` (robocopy `/MIR` on
Windows, `rm`+`cp -a` on POSIX — either way, the *directory itself* keeps its
existing name/path, only its contents change), then relaunch the **exact
`sys.executable` path it was given when written** — i.e. the *old* exe/bundle
path, hard-coded into a script that already exists and cannot be rewritten
retroactively.

If this release renamed the packaged executable (`AFK Farm Clicker.exe` →
`Clickwork.exe`) or, on macOS, the `.app` bundle itself (`install_root()`
*is* the bundle path there, per `afk_clicker.py:640-647`), the mirror step
would delete the old-named file/bundle-internals as "extra" and write the
new-named one in its place — and then the relaunch line tries to start a
path that no longer exists. Every installed copy's *next* update would
silently fail to relaunch (files replaced, app just doesn't come back) —
which is close to, though not confirmed identical to, the open Windows bug
already being chased separately.

**Decision: keep the built executable/bundle name exactly as it is
(`AFK Farm Clicker`) this cycle.** Rename only what a human reads: the
window title, header label, README prose, and the *release asset archive
names* (`AFK-Farm-Clicker-windows-x64.zip` → `Clickwork-windows-x64.zip`,
etc.) — the latter is safe because `pick_asset()` (`afk_clicker.py:619-625`)
matches an asset by **suffix only** (`ASSET_SUFFIX`, `afk_clicker.py:566-570`),
never by the full file name, so an old client downloading a `Clickwork-*.zip`
works identically to downloading an `AFK-Farm-Clicker-*.zip`. The archive's
*internal* top-level folder (what `download_and_stage()` flattens,
`afk_clicker.py:797-799`) still comes straight from PyInstaller's unchanged
`--name`, so it stays `AFK Farm Clicker` inside the zip/tarball too — that's
fine, it's never displayed to a user, only copied by the swap script.

Rejected alternatives:
- **Rename everything now (exe, bundle, dir) + one-time settings migration.**
  A settings migration only protects `settings.json`; it does nothing for the
  swap-script relaunch problem above, which migration code can't reach
  (it's a script already sitting on disk before the new version's code ever
  runs). This would still break every existing install's next auto-update.
- **Ship a transitional dual-name build** (old-named exe as a thin launcher
  that execs the real new-named one, or vice versa). Doubles the packaging
  surface (two entry points to build, sign-check, and smoke-test per
  platform) for a problem that has a zero-cost alternative below. Revisit
  only if Leo decides the executable/bundle name must change soon — see
  "Open questions".
- **Do nothing (skip the archive-name rename too).** Would leave the
  release page itself saying "AFK-Farm-Clicker-windows-x64.zip" under a
  release titled Clickwork, which is exactly the half-renamed state Leo is
  asking to fix from the user-facing side. Since it's provably safe (suffix
  match), there's no reason to leave it.

The net effect: after this cycle, a user downloads "Clickwork," sees
"Clickwork" in the title bar, header, and README, and updates seamlessly —
but a `dist/AFK Farm Clicker/AFK Farm Clicker.exe` path still exists on disk
under the hood. That inconsistency is real and worth a follow-up once every
install currently in the wild has updated at least once through this build
(tracked as a roadmap/backlog item, not solved here — see "Open questions").

### String-level changes
- `afk_clicker.py:1772` — `root.title("AFK Farm Clicker")` → `root.title("Clickwork")`.
- `afk_clicker.py:2036` — header `text="AFK Farm Clicker"` → `text="Clickwork"`.
- `afk_clicker.py:606,670,745` — `User-Agent: AFKFarmClicker/{__version__}` →
  `User-Agent: Clickwork/{__version__}`. Purely an HTTP identification header;
  GitHub does not validate its content, so this has no back-compat
  implication either direction.
- `afk_clicker.py:741,819` — temp-dir prefix `afkclicker-update-` →
  `clickwork-update-`. Purely an ephemeral local directory name created and
  consumed within a single run; no other code or on-disk state depends on
  its exact text.
- `afk_clicker.py:771` — the comment referencing `"AFK-Farm-Clicker-linux-
  x86_64.tar.gz"` as the example that motivates trailing the asset name in
  the error message: update the example name to the new asset name (see
  below) and re-verify the 40-char budget claim still holds (see "Edge
  cases" — the comment's own arithmetic depends on the exact string it
  quotes).
- `README.md:1` — title `# AFK Farm Clicker` → `# Clickwork`.
- `README.md:19-21` — download table's three file names → the new
  `Clickwork-*` asset names (see below); update the prose describing the
  updater ("Der Tausch läuft...") only if it names the app, it currently
  doesn't.
- `README.md:59-61` — settings-path table: **leave the actual paths
  unchanged** (`AFKFarmClicker`, `afk-farm-clicker`) since those directories
  are not renamed; the surrounding prose may still say "Clickwork" for the
  product name itself.

### Release asset / CI changes
- `.github/workflows/release.yml` build matrix `asset:` values
  (~lines 110-116): rename to `Clickwork-windows-x64.zip`,
  `Clickwork-linux-x86_64.tar.gz`, `Clickwork-macos-arm64.zip`.
- `--name "AFK Farm Clicker"` at `release.yml:131` and `build.bat:59`:
  **unchanged**. Add a one-line "why" comment next to each (per
  `docs/CODING-GUIDELINES.md`'s comment convention) explaining that this is
  deliberately not "Clickwork" yet, so the next person editing this line
  doesn't "fix" it without reading this spec's history.
- Smoke-test steps (`release.yml:149,157,161`) and packaging steps
  (`release.yml:166,170,176`): unchanged — they all reference the *build*
  name (`dist/AFK Farm Clicker/...`), which isn't moving.
- Release body text (`release.yml:224-226`): update the file-name table to
  the new `Clickwork-*` names; the surrounding prose ("Download the archive
  for your system...") is already name-agnostic.
- `build.bat` comments at lines 3, 5, 77, 79: these describe the *actual*
  build output path, which still says "AFK Farm Clicker" — leave the paths
  as-is; optionally soften line 3's product description (e.g. "Builds the
  Clickwork Windows program (packaged internally as \"AFK Farm Clicker\" —
  see docs/spec.md)") but do not touch lines 5/77/79, which must stay
  literally accurate to the folder/exe names PyInstaller actually produces.

### Test changes
- `tests/test_updater.py:26-28,42,100` and `tests/test_ui.py:35-37,51,3169,
  3222,3245` — update the mocked *release asset* name fixtures from
  `AFK-Farm-Clicker-*` to `Clickwork-*`, to match the real renamed archives.
  This is cosmetic realism, not required for correctness (suffix matching is
  name-agnostic), but keeps the fixtures honest.
- `tests/test_ui.py:3038` — the hand-built truncation fixture
  `"checksum: not in SHA256SUMS: AFK-Farm-Clicker-linux-x86_64.tar.gz"[:40]`
  must be updated **in lockstep** with whichever asset name that specific
  test's mocked release JSON uses; it is a literal, not derived from the
  production format string at test time, so a rename here is manual and
  easy to get out of sync (see "Edge cases").
- Do **not** touch the `"AFK Farm Clicker"` *folder-name* fixtures listed in
  "Background / current state" — they simulate PyInstaller's `--name`
  output, which this spec deliberately does not rename.

## Affected areas
- `afk_clicker.py` — 7 string sites (title, header, 3× User-Agent, 2× temp
  prefix) + 1 comment.
- `.github/workflows/release.yml` — asset matrix values, release body table,
  2 explanatory comments next to the unchanged `--name`.
- `build.bat` — 1 explanatory comment, optionally 1 description line.
- `README.md` — title, download table, (settings-path table prose only).
- `tests/test_updater.py`, `tests/test_ui.py` — asset-name fixtures per
  above; no production-code test assertions change in meaning.

This is a single conceptual change (a scoped rename plus one back-compat
decision) touching source, CI config, docs and tests — not a multi-layer
spread in the schema/API/edge-function/UI sense skill 11 is about, so it is
kept as one spec rather than split further. The icon (a genuinely separate
concern: new asset-generation tooling, new runtime code, a new CI step) is
already split out as part 2.

## Edge cases
- **Truncated error messages**: `afk_clicker.py:775`'s
  `f"checksum: not in {CHECKSUM_ASSET}: {asset['name']}"` is displayed via
  `str(exc)[:40]` (`afk_clicker.py:2925`). The comment at `afk_clicker.py:771`
  justifies *why* the fixed words come first, using the old asset name as its
  example of a name long enough to matter — verify the new, shorter
  `Clickwork-*` names still make the same point (they're shorter than
  `AFK-Farm-Clicker-*`, so if the comment's specific claim no longer holds,
  reword it rather than leave a stale example).
- **Partial rename mid-flight**: during the interval between this release
  going out and every existing install picking it up, the release page will
  show `Clickwork-*.zip` while some users are still running a build whose
  title bar says "AFK Farm Clicker" — this is expected and self-resolving
  (next auto-update), not a bug to guard against.
- **Windows update bug overlap**: the known Windows install-fails-silently
  bug (files not replaced, console flash) is independent of this rename, but
  a Windows user hitting it while a Clickwork-branded release is out will
  have to manually download and install fresh — same as today, just under
  the new name. No spec change needed; noted here only so the reviewer
  doesn't conflate the two.
- **Non-English users**: README is in German; the rename applies to the
  German prose the same way (do not translate "Clickwork" — it's a proper
  noun/brand name in any language).

## Acceptance criteria
- [ ] Given a fresh checkout, when grepping `afk_clicker.py`, `README.md`,
  `.github/workflows/release.yml`, and `build.bat` for `AFK Farm Clicker`
  (case-sensitive) outside of the deliberately-unchanged build-name/paths
  listed in "Non-goals"/"Proposed approach", then no remaining matches exist.
- [ ] Given the app is launched (headless/Xvfb is fine per this project's
  test env), when the window opens, then the OS title bar text and the
  in-app header label both read "Clickwork".
- [ ] Given `.github/workflows/release.yml`'s build matrix, when read, then
  the three `asset:` values are `Clickwork-windows-x64.zip`,
  `Clickwork-linux-x86_64.tar.gz`, `Clickwork-macos-arm64.zip`, while
  `--name "AFK Farm Clicker"` (line 131) and every `dist/AFK Farm Clicker...`
  path in the smoke-test/packaging steps are byte-for-byte unchanged.
- [ ] Given `build.bat`, when read, then `--name "AFK Farm Clicker"` (line 59)
  and the literal output paths in the trailing echo block are unchanged.
- [ ] Given the existing `pick_asset()`/`ASSET_SUFFIX` logic
  (`afk_clicker.py:566-570,619-625`), when fed a release whose assets are
  named `Clickwork-*`, then it selects the correct asset for the running
  platform exactly as it does today for `AFK-Farm-Clicker-*` names (i.e. the
  matching is suffix-based and the rename doesn't require touching that
  function) — a test should assert this directly rather than relying on
  inspection.
- [ ] Given the full test suite (`python -m unittest discover -s tests -t .`,
  under Xvfb per this project's test env), when run, then it passes with no
  new failures, including the updated fixtures in `test_updater.py` and
  `test_ui.py`.
- [ ] Given `README.md`, when read, then the settings-path table
  (`AFKFarmClicker` / `afk-farm-clicker` / the macOS path) is byte-for-byte
  unchanged, and the download table lists the new `Clickwork-*` file names.
- [ ] Given `config_path()` and `APP_DIR_NAME`, when read, then both are
  byte-for-byte unchanged from today — no migration code is introduced
  because nothing needs migrating.

## Open questions
- **Main's `__version__` (0.3.1) is behind the latest published tag
  (v0.5.0)** — confirmed via `git log`: the version bump for 0.5.0
  (`9f995bb`, "Release 0.5.0") was made on a release branch and never merged
  back to `main`. This is a pre-existing process gap, unrelated to this
  rename. **Assumption: out of scope for this spec** — whoever next cuts a
  release branch handles the version bump per the existing `version:` job in
  `release.yml`, same as always. Flagging only so the reviewer doesn't
  expect this spec to fix it.
- **When does the executable/bundle actually get renamed to Clickwork?**
  This spec deliberately defers it (see "Proposed approach"). Leo should
  decide the trigger for that follow-up — e.g. "after the next release
  every currently-installed copy has had a chance to pick up" — but it does
  not block this spec and isn't decided here. Proceeding under the
  assumption that the string/branding rename in this spec is the whole of
  what's wanted *right now*, and the exe/bundle rename is intentionally a
  separate, later piece of work.
- **Release-body wording**: `release.yml`'s release body currently says
  nothing about the product name at all (just "Download the archive for
  your system..."), so no change is strictly needed there beyond the file
  table — proceeding under the assumption that's sufficient and Leo doesn't
  want e.g. a "Clickwork" callout line added to the body text.

## Risk / rollback notes
- All changes are string/text/config edits plus test-fixture renames — no
  logic changes to `pick_asset()`, `download_and_stage()`, `write_swap_script()`,
  `install_root()`, or `config_path()`. Risk is limited to a missed
  occurrence (caught by the grep-based acceptance criterion above) or a
  fixture edited inconsistently with its paired assertion (the `test_ui.py:
  3038` truncation case called out explicitly).
- Rollback is a straight revert of this commit; nothing here is stateful or
  destructive (no data migration, no renamed on-disk directories).
