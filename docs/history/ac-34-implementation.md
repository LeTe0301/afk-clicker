# Implementation: App icon — the Loop icon (part 2 of 2, G#34/GH#60)

## Summary

Gave Clickwork a real icon end to end: a committed `assets/icon.svg` (full)
and `assets/icon-simplified.svg` (loop-only, per `docs/design.md`'s small-size
decision) are the sources; `assets/icon-{16,32,48,256}.png`, `assets/icon.ico`
and `assets/icon.icns` are the rasterized/packaged outputs, generated once,
out of band, and committed. `afk_clicker.py` loads the four PNGs at startup
via a new `_asset_dir()` helper and calls `root.iconphoto(True, *self._icon_imgs)`
next to `root.title("Clickwork")`, holding the `PhotoImage`s on `self` so they
survive `_rebuild_ui()` and never get garbage-collected. `release.yml` and
`build.bat` now pass `--icon`/`--add-data` to PyInstaller, per platform. No
new frozen or CI dependency was added — Pillow/cairosvg were only ever used
in a throwaway venv to generate the committed binary assets.

## Changes by file

- **`assets/icon.svg`** (new) — the full-icon source, copied byte-for-byte
  from `docs/spec.md`'s "Proposed approach" block.
- **`assets/icon-simplified.svg`** (new) — the loop-arrow-only variant from
  `docs/design.md` (drops the mouse `clipPath`/rects/line), used to rasterize
  the 16/32 px outputs.
- **`assets/icon-16.png`, `icon-32.png`** (new) — rasterized from
  `icon-simplified.svg`; **`icon-48.png`, `icon-256.png`** (new) — rasterized
  from `icon.svg`. All RGBA PNGs, exact pixel sizes. Used at runtime via
  `tk.PhotoImage`.
- **`assets/icon.ico`** (new) — Windows multi-size icon: 16×16/32×32 from the
  simplified SVG, 48×48/256×256 from the full SVG, built with Pillow's ICO
  writer using exact per-size art (`sizes=`/`append_images=`, matched by
  exact pixel dimensions — no proportional-scale fallback used for any of
  the four sizes).
- **`assets/icon.icns`** (new) — macOS bundle icon. Pillow's ICNS writer only
  ever emits a fixed set of slots (32/64/128/256/512/1024 physical px, i.e.
  the 16pt/32pt/128pt/256pt/512pt logical icons at 1x/2x) — there is no
  writable slot below 32 physical px. The simplified SVG went into the two
  smallest slots it has (32 px → `ic11`, the 16pt icon's Retina slot; 64 px →
  `ic12`, the 32pt icon's Retina slot); the full SVG filled every slot from
  128 px up (`ic07`/`ic13`/`ic08`/`ic14`/`ic09`/`ic10`). This reproduces
  design's "16/32 simplified, 48+ full" cutoff exactly, using the only slots
  the format and Pillow's writer actually have for a small icon.
- **`assets/README.md`** (new) — short note (per spec) that the two SVGs are
  the editable sources and everything else here is regenerated from them;
  points at this doc for the exact regeneration commands.
- **`afk_clicker.py`**
  - New `_asset_dir()` (module-level, right after `is_frozen()`, which it
    reuses rather than re-checking `sys.frozen` inline): returns
    `sys._MEIPASS/assets` when frozen, else the directory next to
    `afk_clicker.py`.
  - In `AfkAutoclicker.__init__`, right after `root.title("Clickwork")`:
    loads `icon-{16,32,48,256}.png` into `self._icon_imgs` and calls
    `root.iconphoto(True, *self._icon_imgs)`. No `try/except` around this —
    a missing PNG is a packaging bug and must raise, per the spec's edge
    case and `docs/CODING-GUIDELINES.md`'s input-validation section.
    `self._icon_imgs` sits outside `_build_ui()`/`_rebuild_ui()`'s scope
    (that method only tears down `root`'s *children*, never `root` itself),
    so the icon survives every rebuild without being re-created.
  - `tk.PhotoImage(master=root, ...)` — **not** the spec snippet's bare
    `tk.PhotoImage(file=...)`. Without an explicit `master`, `PhotoImage`
    binds to Tkinter's process-global "default root" (the first `Tk()`
    instance ever created in the process), not necessarily the `root`
    argument this constructor was actually given. This is invisible in
    normal use (one `Tk()` per process) but broke immediately under the
    existing test suite, which builds many separate `tk.Tk()` interpreters
    in one process (see "Deviations from spec" below).
- **`.github/workflows/release.yml`** — the single shared `Build` step split
  into three (`Build (Windows)`/`(Linux)`/`(macOS)`, each `if: runner.os ==
  '...'`), matching the file's own existing convention for `Smoke test`/
  `Package` (already split three ways for the same platform-specific-flag
  reason). All six `--hidden-import`s are kept on all three platforms,
  unchanged from the original shared step — only `--add-data`/`--icon` were
  added, per platform:
  - Windows: `--add-data "assets;assets" --icon assets\icon.ico`
  - Linux: `--add-data "assets:assets"` (no `--icon` — no PyInstaller
    equivalent on Linux, per spec)
  - macOS: `--add-data "assets:assets" --icon assets/icon.icns`
- **`build.bat`** — same two flags added to the Windows PyInstaller
  invocation (`--add-data "assets;assets" --icon assets\icon.ico`), with a
  comment noting it's kept in sync with `release.yml`'s Windows build step.
  `--name "AFK Farm Clicker"` untouched, as required.
- **`tests/test_ui.py`** — four new tests (see "Key decisions" for the
  sabotage-check results):
  - `AssetDir.test_unfrozen_resolves_next_to_the_module` — `_asset_dir()`
    returns `<dir of afk_clicker.py>/assets` when unfrozen.
  - `AppIcon.test_icon_images_are_loaded_non_empty` — `self.ui._icon_imgs`
    is non-empty and every image's `width()`/`height()` > 0.
  - `AppIcon.test_icon_reference_survives_a_rebuild` — after
    `_apply_appearance("light")` (a real, synchronous `_rebuild_ui()` call,
    the same trigger `RunningClickerSurvivesRebuild` already uses), the
    *same* `self._icon_imgs` list object is still on `self` (not a
    freshly-built one) and every image is still alive.
  - `AppIconMissingAsset.test_missing_png_raises_instead_of_starting_blank`
    — monkeypatches `app._asset_dir` (save/restore in setUp/tearDown, this
    suite's existing monkeypatch style, no `unittest.mock`) to an empty
    directory and asserts `AfkAutoclicker(...)` raises `tk.TclError` rather
    than starting with a blank icon.

## Key decisions / tradeoffs

- **`master=root` on every `PhotoImage`** (see above) was not in the spec's
  code snippet but is required for correctness, not a style preference:
  running the new tests without it, `SetActiveThemeWidgets
  .test_dark_is_restored_after_light` (a pre-existing, unrelated test that
  builds two separate `tk.Tk()` roots back to back in one process) failed
  with `_tkinter.TclError: can't use "pyimageNNN" as iconphoto: not a photo
  image` — the second root's `iconphoto` call was handed an image bound to
  the *first* root's interpreter. `master=root` fixes this and is a strict
  correctness improvement over the spec's literal snippet; recorded under
  "Deviations from spec" below since it changes the exact call shown there.
- **`.icns` slot mapping**: Pillow's `IcnsImagePlugin._save` hard-codes its
  output slots to `{ic07:128, ic08:256, ic09:512, ic10:1024, ic11:32,
  ic12:64, ic13:256, ic14:512}` (verified by reading
  `PIL/IcnsImagePlugin.py` directly in the throwaway venv) — there is no
  writable 16px-physical slot at all, and no "48" slot either. Rather than
  write a raw ICNS container by hand (design's non-mandated "any tool"
  clause allows this), the simplified variant was placed in the two
  smallest slots the format/writer actually expose (32 px = the 16pt icon's
  @2x representation, 64 px = the 32pt icon's @2x representation) — visually
  and semantically equivalent to design's "16pt/32pt simplified" intent, and
  full art fills every slot 128 px and up, matching design's "48+ full" (the
  format's smallest non-Retina full-icon slot is 128 px, well past 48).
  Verified by extracting each slot's image back out with
  `PIL.IcnsImagePlugin.IcnsFile.getimage()` and inspecting the pixels (see
  "How to verify locally").
- **`.ico` construction**: Pillow's ICO writer matches `sizes=` entries to
  images by *exact* pixel size among `[im] + append_images`, falling back to
  a proportional `thumbnail()` of the base image only for sizes with no
  exact match. All four sizes (16/32/48/256) were supplied as exact,
  purpose-rendered images, so no fallback thumbnailing was used anywhere in
  `icon.ico`.
- **`release.yml`'s `Build` step split into three** rather than one step
  with inline OS branching inside the folded scalar: the file already splits
  `Smoke test`/`Package` this exact way for the same "flags differ per OS,
  and a folded `run: >` scalar has no comment syntax and no shell
  conditionals of its own" reason (see `ac-33-implementation.md`'s note on
  this same constraint) — this keeps the new step consistent with the
  file's existing convention rather than inventing a new one. All six
  `--hidden-import` flags were kept on every platform's step, unchanged
  from the original single step, since trimming them was never asked for
  and isn't implied by anything in the spec/design.
- **`selftest()` was not extended** in round 1 to load the bundled PNGs.
  Neither `docs/spec.md` nor `docs/design.md` mentions `selftest()` anywhere
  (both grepped — zero hits), and the spec's own acceptance criteria stop at
  "the Windows `.exe`/macOS `.app` shows the Loop icon" as a CI-build-only,
  not-locally-verifiable check. This was flagged explicitly for the
  reviewer, who correctly caught it as a must-fix (round 1 under-scoped a
  real robustness gap rather than a pure "not asked for" case) — **see
  "Round 2" below**, which extends `selftest()` accordingly.

## Deviations from spec

- `tk.PhotoImage(file=...)` → `tk.PhotoImage(master=root, file=...)`. The
  spec's own snippet omits `master=`; omitting it is a latent bug that only
  surfaces when more than one `Tk()` root exists in a process (exactly what
  this test suite does, and what a hypothetical future `Toplevel` would also
  trigger). This is the only functional change from the spec's literal code;
  everything else (helper name/shape, call site, `self._icon_imgs` naming,
  `True` as the first `iconphoto` arg) matches the spec as written.
- `.icns` slot sizes are `{32, 64, 128, 256, 512, 1024}` physical px rather
  than design's literal `{16, 32, 48, 128, 256, 512}` table — see "Key
  decisions" above. This is a tooling constraint (Pillow's ICNS writer has
  no other slots to write to, and there is no standard 48px ICNS chunk type
  at all), not a design disagreement; the *logical* icon sizes users
  actually see (16pt, 32pt menu bar/Dock icons; 128pt+ Finder icons) get the
  same simplified/full split design specified.

## Known limitations

- Per spec's own acceptance criteria: the Windows `.ico`/macOS `.icns`
  embedding can only be proven by an actual CI build on those runners —
  this local environment is Linux-only. What *was* verified locally: both
  files parse as valid ICO/ICNS via Pillow, and the correct per-size
  artwork (simplified vs. full) was extracted and visually inspected for
  every slot in both containers (see "How to verify locally").
- `assets/icon.ico`/`icon.icns` are binary and not human-diffable in a
  typical `git diff` — reviewable by extracting and viewing, same as any
  committed binary asset (the spec's own stated tradeoff for not generating
  these in CI).

## How to verify locally

Test suite (this project's documented headless setup):
```
python3 -m venv /tmp/some-venv && /tmp/some-venv/bin/pip install pynput==1.7.7
Xvfb :93 -screen 0 1280x1024x24 -nolisten tcp &
cd /home/dev/projects/afk-clicker
DISPLAY=:93 /tmp/some-venv/bin/python -m unittest discover -s tests -t .
pkill -f "Xvfb :93"
```
Result in this session: **297 tests, OK (skipped=5)** — up from the
293/skipped=5 baseline (confirmed identical on `git stash` of this cycle's
changes), i.e. exactly the 4 new tests added, no regressions.

`python3 -m py_compile afk_clicker.py tests/test_ui.py` — no syntax errors.

`yaml.safe_load()` against the modified `.github/workflows/release.yml` —
parses cleanly; each `Build (…)`/`Smoke test (…)`/`Package (…)` step's `run:`
string was printed and inspected directly to confirm the folded scalars
produced the intended single-line commands with the right `--icon`/
`--add-data` per platform.

To eyeball the running window's icon directly (Linux/X11):
```
DISPLAY=:93 /tmp/some-venv/bin/python afk_clicker.py
```

### Regenerating the committed assets

Not run by CI or the app — a one-off, out-of-band step. Requires a
throwaway venv only (never a project or CI dependency):
```
python3 -m venv /tmp/some-venv
/tmp/some-venv/bin/pip install cairosvg Pillow
```
Then, from a small script (see below) run as
`/tmp/some-venv/bin/python gen_icons.py /home/dev/projects/afk-clicker`,
which:
1. Rasterizes `assets/icon-simplified.svg` to 16×16 and 32×32 PNGs, and
   `assets/icon.svg` to 48×48 and 256×256 PNGs, via
   `cairosvg.svg2png(url=..., output_width=N, output_height=N)` →
   `PIL.Image.open(io.BytesIO(...))`. Saves these four as
   `assets/icon-{16,32,48,256}.png`.
2. Builds `assets/icon.ico` with
   `png_256.save("icon.ico", sizes=[(16,16),(32,32),(48,48),(256,256)],
   append_images=[png_16, png_32, png_48])` — Pillow matches each requested
   size to the provided image of that exact size.
3. Builds `assets/icon.icns` with `icns_1024.save("icon.icns",
   append_images=[icns_32, icns_64, icns_128, icns_256, icns_512])`, where
   `icns_32`/`icns_64` are rendered from the simplified SVG and
   `icns_128`/`icns_256`/`icns_512`/`icns_1024` (the base image) from the
   full SVG — see "Key decisions" for why these particular six sizes.

The script itself was not committed (throwaway per this project's "don't add
to the tree what you can't remove" convention) — the four bullet points
above plus the exact Pillow/cairosvg calls used are sufficient to
reconstruct it if `assets/icon.svg`/`icon-simplified.svg` ever change.

Verification of per-size artwork (both containers), done in this session
via the throwaway venv:
```python
from PIL import Image
im = Image.open("assets/icon.ico")
im.ico.sizes()                       # {(16,16), (32,32), (48,48), (256,256)}
im.ico.getimage((16, 16)).save(...)  # inspected — simplified (loop only)
im.ico.getimage((48, 48)).save(...)  # inspected — full (mouse present)

from PIL.IcnsImagePlugin import IcnsFile
icns = IcnsFile(open("assets/icon.icns", "rb"))
icns.itersizes()                     # (16,16,2),(32,32,2),(128,128,1/2),(256,256,1/2),(512,512,1/2)
icns.getimage((32, 32, 2)).save(...) # 64px physical, inspected — simplified
icns.getimage((128, 128, 1)).save(...)  # inspected — full
```
Every extracted PNG was viewed directly (Read tool) and confirmed to match
the intended variant per size.

## Round 2 (docs/test-review.md Finding #1)

### What was verified before acting
Read `selftest()` (afk_clicker.py:228-254 before this round), the
`--selftest` short-circuit (`if "--selftest" in sys.argv: sys.exit(selftest())`,
before `AfkAutoclicker` is ever constructed), and the icon-loading code in
`AfkAutoclicker.__init__` (afk_clicker.py:1794-1799 before this round). The
finding was correct as written: `selftest()` never touched `_asset_dir()` or
any `icon-*.png`, and `--selftest` returns before `AfkAutoclicker.__init__`
ever runs, so none of the three per-platform Smoke test steps in
`release.yml` exercised the icon-loading code this ticket's part 1 added. A
broken `--add-data` destination on any OS would stay green through Build,
Smoke test, and Package, then crash the shipped `--windowed` build on first
launch with an uncaught `tk.TclError` (by design — this code deliberately
does not catch it, per the spec's "fail loudly" edge case). Also confirmed
Linux CI already runs `--selftest` under `xvfb-run -a` (`release.yml:205`,
pre-existing) and Windows/macOS runners have native GUIs, so a real `tk.Tk()`
root was already provably safe to open in `selftest()` on all three platforms
(the pre-existing `tk.Tk().destroy()` line proved this before this round;
nothing about opening one more root changes that).

### Fix
- **`afk_clicker.py`**: extracted a new module-level `_load_app_icon(root)`
  (placed right after `_asset_dir()`, which it calls) that does exactly what
  `AfkAutoclicker.__init__` used to do inline: load the four
  `icon-{16,32,48,256}.png` files as `tk.PhotoImage(master=root, ...)` and
  call `root.iconphoto(True, *imgs)`, returning the image list. No
  `try/except` — same fail-loudly rationale as before, now documented once in
  the shared function's docstring instead of duplicated at both call sites.
  - `AfkAutoclicker.__init__` now does `self._icon_imgs = _load_app_icon(root)`
    instead of the inline load, same behavior, same place in the constructor.
  - `selftest()` now opens a real `tk.Tk()` root (`icon_root`), calls
    `_load_app_icon(icon_root)`, then destroys it — replacing the previous
    `tk.Tk().destroy()` line that never touched the icon path. This is the
    same root construction the docstring's stated purpose already relied on;
    it now does one more thing with that root before tearing it down.
  - This makes `--selftest` and `AfkAutoclicker.__init__` share one code
    path, so they cannot drift apart again the way they did in round 1 — a
    future change to icon loading is automatically covered by CI's
    `--selftest` smoke step on all three platforms.
- **`release.yml`**: untouched, per the finding's own instruction — the
  existing `--selftest` invocations (`release.yml:198-199` Windows,
  `release.yml:205` Linux via `xvfb-run -a`, `release.yml:209` macOS) already
  run against the frozen build; no separate icon-specific smoke step was
  needed once `selftest()` itself covers the load.
- **`tests/test_ui.py`**: extended the existing `Selftest` class with
  `test_selftest_fails_when_icon_asset_missing` (mirrors
  `AppIconMissingAsset`'s existing save/restore-`app._asset_dir`
  monkeypatch style already used elsewhere in this file) — points
  `_asset_dir()` at an empty temp dir and asserts `app.selftest()` raises
  `tk.TclError` instead of returning 0.

### Sabotage checks (both directions)
- **Fix removed, test should fail**: temporarily reverted `selftest()` to
  the pre-round-2 `tk.Tk().destroy()` line (no `_load_app_icon` call) and ran
  `tests.test_ui.Selftest` alone: `test_selftest_fails_when_icon_asset_missing`
  failed with `AssertionError: TclError not raised`, `test_selftest_passes`
  still passed. Confirms the new test actually detects the gap Finding #1
  described. Reverted back immediately (restored from a copy taken before
  the sabotage edit) and reran the same two tests: both green again.
- **Right root cause, not a coincidental error**: ran `selftest()` directly
  from a Python REPL with `_asset_dir` monkeypatched to an empty dir (no
  test framework involved) and printed the traceback — the `tk.TclError`
  originates inside `_load_app_icon`'s list comprehension
  (`tk.PhotoImage(master=root, file=os.path.join(_asset_dir(), "icon-16.png"))`),
  `couldn't open ".../icon-16.png": no such file or directory` — not from
  some unrelated empty-directory side effect.
- **Manual CLI, both directions**: `DISPLAY=:93 <devvenv>/bin/python
  afk_clicker.py --selftest; echo $?` with all assets present → `exit=0`.
  Renamed `assets/icon-32.png` out of the way, reran the same command →
  uncaught `_tkinter.TclError: couldn't open
  ".../assets/icon-32.png": no such file or directory` and `exit=1`. Restored
  the file immediately afterward; `ls assets/` and `git status --porcelain`
  confirmed the working tree was left clean (no `assets/` diff, no stray
  files).

### Regression check
`DISPLAY=:93 <devvenv>/bin/python -m unittest discover -s tests -t .` →
**298 tests, OK (skipped=5)** — the 297 from round 1 plus this round's one
new test, no regressions. `python -m py_compile afk_clicker.py
tests/test_ui.py` — clean.

### Deviations from spec/design (round 2)
None. This closes a reviewer-identified gap in `selftest()`'s own coverage,
not a new product requirement; the fix is the minimal shared-function
extraction the finding itself suggested, with `release.yml` left untouched
as instructed since its existing `--selftest` invocations already cover the
fix once `selftest()` itself was extended.

### Known limitations (round 2)
Same as round 1: Windows `.ico`/macOS `.icns` *display* in Explorer/Finder
still cannot be verified from this Linux-only local environment — this round
only closes the "does a broken `--add-data` destination get caught at all"
gap, which is fully verifiable headless. It does not and cannot newly verify
icon *rendering* on Windows/macOS, which remains, as before, a CI-build-only
check per the spec's own acceptance criteria.

### How to verify locally (round 2, additive to the block above)
```
Xvfb :93 -screen 0 1280x1024x24 -nolisten tcp &
cd /home/dev/projects/afk-clicker
DISPLAY=:93 <devvenv>/bin/python -m unittest discover -s tests -t .
DISPLAY=:93 <devvenv>/bin/python afk_clicker.py --selftest; echo $?   # expect 0
mv assets/icon-32.png assets/icon-32.png.hidden
DISPLAY=:93 <devvenv>/bin/python afk_clicker.py --selftest; echo $?   # expect 1, TclError
mv assets/icon-32.png.hidden assets/icon-32.png
pkill -f "Xvfb :93"
```
