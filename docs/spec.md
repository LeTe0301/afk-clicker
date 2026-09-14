# Spec: App icon — the Loop icon (part 2 of 2 — depends on nothing from part 1, run after it)

## Summary
Give Clickwork an actual icon — currently there is none anywhere (no
`--icon` at build time, no `iconphoto`/`iconbitmap` call at runtime, so the
window uses Tk's default feather). Add the "Loop" icon Leo picked (a mouse
with a lit left button inside an endless-loop arrow) as the window icon and
the packaged executable/bundle icon on all three platforms, generating the
platform-specific formats from the one source SVG without adding a new
frozen runtime dependency.

Run this as its own build cycle after `docs/spec.md` (part 1, the rename)
has landed — no functional dependency between the two, but it keeps each
dispatch to one concern (part 1 is string/CI edits; this one is new
asset-generation tooling plus new runtime code).

## Goals
- The source SVG lives in the repo as the single source of truth for the
  icon.
- Windows build gets a multi-resolution `.ico` via PyInstaller's `--icon`.
- macOS build gets an `.icns` via PyInstaller's `--icon` (macOS bundle icon).
- Linux/all platforms: the running window shows the icon via Tk's
  `iconphoto`, sourced from a bundled PNG resolved correctly both when run
  from source and when frozen (`sys._MEIPASS`).
- None of this adds a new dependency to the *frozen build* — `TECHSTACK.md`
  is explicit that every frozen dependency is a chance for PyInstaller's
  static analysis to miss something and ship a build that dies at launch,
  and CI currently pins exactly two packages (`pyinstaller`, `pynput`); this
  spec does not change that pin list.

## Non-goals
- Not the product rename (`docs/spec.md`, part 1) — this spec assumes that
  work is already merged (title/header already say "Clickwork") but does
  not depend on it functionally; if run out of order, only the header text
  differs, nothing here breaks.
- Not deciding the simplified small-size icon variant's actual pixel art.
  The sketch note that the mouse gets muddy at 20px is a real, open design
  question — this spec surfaces it to the ux-designer stage rather than
  guessing at glyph simplification here (see "Open questions").
- Not a tray/notification icon (the app has no system tray presence today;
  out of scope unless a future spec adds one).
- Not re-theming any other UI chrome — only the icon.
- Not adding image manipulation as a runtime dependency (no Pillow import
  inside `afk_clicker.py` itself) — see "Proposed approach" for why
  generation happens once, out of band, not at build or run time.

## Background / current state
- No icon exists today: grepped `afk_clicker.py` for `iconphoto`,
  `iconbitmap`, `--icon` — zero matches. The window currently shows
  whatever default Tk provides per platform.
- `THEMES["dark"]` (`afk_clicker.py:78-83`) defines the app's dark palette;
  the accent color already in use is `#e08a55`, which the chosen icon reuses
  exactly (see the SVG below) — so the icon matches the in-app palette
  by construction, nothing to re-derive.
- Build pipeline (`.github/workflows/release.yml`, `build.bat`) invokes
  PyInstaller with `--name`, `--windowed`, `--noupx`, and a list of
  `--hidden-import`s — no `--icon` flag anywhere yet, and no `--add-data`
  either (nothing is bundled today beyond the interpreter and its imports).
- Runtime is `tkinter` only (per `TECHSTACK.md`) — `tk.PhotoImage` supports
  PNG natively since Tk 8.6, so a PNG can be loaded without Pillow. `.ico`/
  `.icns` are opaque, PyInstaller-consumed build inputs; nothing at runtime
  needs to parse them.

## Proposed approach

### The source asset
Commit the SVG verbatim as `assets/icon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#1c1f23"/>
  <path d="M100 64 A36 36 0 1 1 86 35" fill="none" stroke="#e08a55" stroke-width="9" stroke-linecap="round"/>
  <polygon points="96,42 84,24 76,42" fill="#e08a55"/>
  <clipPath id="c-mouse"><rect x="50" y="44" width="28" height="42" rx="14"/></clipPath>
  <rect x="50" y="44" width="14" height="17" fill="#e08a55" clip-path="url(#c-mouse)"/>
  <rect x="50" y="44" width="28" height="42" rx="14" fill="none" stroke="#e4e7ea" stroke-width="5"/>
  <line x1="64" y1="46" x2="64" y2="61" stroke="#e4e7ea" stroke-width="4"/>
</svg>
```

### Generation strategy: pre-rendered, committed, not generated in CI
**Decision: rasterize the SVG once, out of band (a one-off local/manual
step, documented, not run by CI or by the app), and commit the resulting
binaries.** Concretely:
- `assets/icon.ico` — multi-size Windows icon (16/32/48/256 px), used by
  `--icon` on the Windows build.
- `assets/icon.icns` — macOS bundle icon, used by `--icon` on the macOS
  build.
- `assets/icon-16.png`, `assets/icon-32.png`, `assets/icon-48.png`,
  `assets/icon-256.png` — used at runtime via `tk.PhotoImage`/`iconphoto`
  (Tk picks the closest size per platform when given several).
- `assets/icon.svg` stays in the repo alongside them as the editable
  source, referenced in a short README note under `assets/` explaining that
  the rasters are regenerated from it (by hand or with any SVG tool — this
  spec does not mandate which) whenever the SVG changes.

Rejected alternative: **generate the rasters at CI build time** (e.g. add
`cairosvg`/`Pillow` to the pinned pip install step, rasterize, then feed
PyInstaller). Rejected because:
- It's a new frozen-adjacent build dependency in a project whose
  `TECHSTACK.md` treats every dependency addition as a static-analysis/
  frozen-build risk worth writing down and pinning explicitly — an icon
  that never changes between releases doesn't need to be rebuilt on every
  release run.
- `cairosvg` needs a system Cairo install on the Windows/macOS runners,
  which is a new per-platform CI dependency, not just a `pip install` line
  — meaningfully more moving parts for an asset that is static.
- Committed binaries are trivially reviewable (a reviewer can open the PNG)
  and don't add nondeterminism to what a release build produces from a
  given commit.

The generation step itself (SVG → ico/icns/png) is a one-time task for
whoever implements this spec — any standard tool works (Inkscape CLI,
`rsvg-convert`, an online converter, a local Pillow+cairosvg script run
once and discarded per this project's "don't add to the tree what you
can't remove" convention for scratch tooling). The *output* is what's
committed; the *tool* is not part of this repo or its CI.

### Runtime wiring
- Resolve the assets directory so it works both from source and frozen:
  ```python
  def _asset_dir():
      if getattr(sys, "frozen", False):
          return os.path.join(sys._MEIPASS, "assets")
      return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
  ```
  (Mirrors the existing `is_frozen()` check at `afk_clicker.py:‑` used by the
  updater — reuse that helper rather than duplicating the `sys.frozen`
  check inline.)
- After `root` is constructed (near `afk_clicker.py:1772`, alongside
  `root.title(...)`), load the PNGs and call `iconphoto`:
  ```python
  icons = [tk.PhotoImage(file=os.path.join(_asset_dir(), f"icon-{n}.png"))
           for n in (16, 32, 48, 256)]
  root.iconphoto(True, *icons)
  # keep a reference on self (e.g. self._icon_imgs = icons) -- PhotoImage
  # is garbage-collected the moment nothing holds it, which blanks the
  # icon silently; a bare local list works too as long as its scope
  # outlives root, but attaching to self matches this file's existing
  # pattern of holding Tk state on the instance.
  ```
  `True` as the first arg makes it the default for this toplevel and any
  future `Toplevel` (there are none today, but harmless if one is added
  later).
- PyInstaller needs the assets folder bundled: add
  `--add-data "assets/icon-16.png:assets"` (repeat per PNG, or
  `--add-data "assets:assets"` to bundle the whole folder in one flag —
  prefer the whole-folder form, it's one line instead of four and doesn't
  need updating if a PNG size is added later) to both `release.yml`'s
  PyInstaller invocation and `build.bat`'s. Note PyInstaller's separator is
  `;` on Windows and `:` on POSIX — `build.bat` and `release.yml`'s Windows
  job need `--add-data "assets;assets"`, the Linux/macOS jobs need
  `--add-data "assets:assets"`.
- Add `--icon assets/icon.ico` (Windows) / `--icon assets/icon.icns`
  (macOS) to the respective PyInstaller invocations. Linux PyInstaller
  builds have no `--icon` equivalent (there's no single Linux binary-icon
  standard PyInstaller targets) — the running window's `iconphoto` call is
  the only icon Linux gets, which is already covered above.

## Affected areas
- New files: `assets/icon.svg`, `assets/icon.ico`, `assets/icon.icns`,
  `assets/icon-{16,32,48,256}.png`.
- `afk_clicker.py` — new `_asset_dir()` helper (or reuse `is_frozen()` +
  inline path join), `iconphoto` call near `root.title(...)`
  (`afk_clicker.py:1772`).
- `.github/workflows/release.yml` — `--icon`/`--add-data` flags added to
  the `Build` step, per-platform (~`release.yml:126-138`).
- `build.bat` — same two flags added to the Windows PyInstaller invocation
  (`build.bat:58-64`).
- No test-file renames needed (unlike part 1) — this is new surface, not a
  rename of existing strings.

This is a self-contained set of changes (one new asset folder, one runtime
code addition, one build-flag addition per platform) — a single spec is
appropriate; it does not need a further split.

## Edge cases
- **PhotoImage garbage collection**: if the loaded `PhotoImage` objects
  aren't kept alive somewhere with `root`'s lifetime, the icon can go blank
  after the reference is dropped (a well-known Tk gotcha) — the acceptance
  criteria below check for this explicitly.
- **Running from source (unfrozen) vs frozen**: `_asset_dir()` must resolve
  correctly in both cases; the existing test environment runs unfrozen
  (Linux, Xvfb, no PyInstaller build), so this is the path most likely to
  be exercised by the test suite — the frozen path can only be verified by
  an actual CI build (see "Acceptance criteria").
- **Missing/unbuilt asset files**: if a developer's checkout is missing
  `assets/icon-*.png` (e.g. a shallow export before assets are committed),
  `iconphoto` should fail loudly at startup rather than silently produce a
  blank window that's hard to diagnose — do not wrap the load in a bare
  `try/except` that swallows the error, per
  `docs/CODING-GUIDELINES.md`'s input-validation section's spirit (fail
  visibly, don't guess). A missing asset is a packaging bug, not bad user
  input, so this is a startup-time crash, not a "corrupt config, start from
  defaults" case.
- **Linux has no equivalent of `--icon`**: covered above — `iconphoto` is
  the whole story there, and that's an accepted platform difference, not a
  gap to work around.
- **Small-size legibility**: per Leo's own sketch note, the mouse detail
  goes muddy at 20px. This spec does not resolve it (see "Open questions").

## Acceptance criteria
- [ ] Given `assets/icon.svg`, when read, then its contents are
  byte-for-byte the SVG in "Proposed approach" above.
- [ ] Given the app launched from source (unfrozen, Xvfb), when the window
  opens, then `root.iconphoto` was called with at least one non-empty
  `PhotoImage` and no exception was raised — checkable via a UI test that
  constructs the app and inspects `self._icon_imgs` (or equivalent) is
  non-empty and each image's `width()`/`height()` is > 0.
- [ ] Given the same launch, when the test suite runs a second time (or the
  UI is rebuilt, per the existing `_rebuild_ui` pattern elsewhere in this
  codebase), then the icon references are not dropped/garbage-collected —
  i.e. the reference is held on `self` or another object with `root`'s
  lifetime, not a bare local that falls out of scope.
- [ ] Given `assets/icon-16.png` (or any one PNG) is deleted, when the app
  is launched, then it raises visibly (an uncaught or explicitly-surfaced
  error) rather than starting with a silently blank icon.
- [ ] Given `.github/workflows/release.yml`'s Build step per platform, when
  read, then the Windows job's PyInstaller invocation includes
  `--icon assets\icon.ico` (or `assets/icon.ico` — whichever separator
  PyInstaller accepts on that runner) and `--add-data "assets;assets"`; the
  macOS job includes `--icon assets/icon.icns` and
  `--add-data "assets:assets"`; the Linux job includes
  `--add-data "assets:assets"` (no `--icon`).
- [ ] Given a CI build actually runs (this can only be verified once merged
  and built — flag this explicitly to the reviewer, since local test env is
  Linux-only per this project's conventions and cannot prove the Windows
  `.ico`/macOS `.icns` embedding), when the Windows `.exe` is inspected,
  then it shows the Loop icon in Explorer/taskbar; when the macOS `.app` is
  inspected in Finder, then it shows the Loop icon.
- [ ] Given `build.bat`, when read, then it includes the same `--icon`/
  `--add-data` flags as the release workflow's Windows job (kept in sync,
  per the project's existing "build.bat pins the same versions CI does"
  convention in `TECHSTACK.md`).

## Open questions
- **Simplified small-size variant**: Leo's own sketch note says the mouse
  gets muddy at 20px, and suggests a simplified small-size variant (drop
  the mouse, keep loop+arrow) as "a legitimate design question." This spec
  deliberately does not decide it — **routing this to the ux-designer
  stage**: either (a) ship one icon at all sizes (simplest, matches "don't
  guess at pixel art" — the assumption this spec proceeds under if
  ux-designer has no objection), or (b) ux-designer specifies a simplified
  16/32px glyph (loop+arrow only) as a second SVG variant, in which case
  `assets/icon-16.png`/`icon-32.png` are rasterized from that variant
  instead of a straight downscale of the full icon. Whichever is chosen,
  the acceptance criteria above (non-empty PhotoImage, no GC, visible
  failure on missing asset) hold unchanged.
- **`.ico`/`.icns` generation tool**: not mandated (see "Proposed
  approach") — whoever implements this picks any tool that produces a
  correct multi-size `.ico`/valid `.icns` from the SVG; not a blocking
  decision, just noted so the developer doesn't wait on an answer.

## Risk / rollback notes
- All additions are new files plus new, narrowly-scoped code (one helper,
  one `iconphoto` call, a few build flags) — nothing existing is modified
  behaviorally. Risk is concentrated in the two things only CI can prove
  (correct `.ico`/`.icns` embedding on Windows/macOS) — called out
  explicitly in "Acceptance criteria" as not locally verifiable.
- Rollback is a straight revert; no on-disk user state (settings, staged
  updates) is touched by any of this.
