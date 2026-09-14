# Design: Loop app icon (multi-platform, multi-size rasterization)

## Summary

A single 128×128 rounded-square SVG source (`assets/icon.svg`) rasterized into platform-specific formats (`.ico`, `.icns`, PNG) with size-specific variant handling: at small sizes (16 and 32 px), the mouse detail becomes illegible, so switch to a simplified loop-arrow-only variant; at 48 px and above, render the full icon. The tile shape (rounded corners, no extra padding) applies uniformly; the dark background reads on light taskbars without additional outline.

## ui-ux-pro-max choices

- **Style**: Glassmorphism-adjacent palette (dark tile, amber accent, light gray outlines) matches the app's existing `THEMES["dark"]` (`afk_clicker.py:78-83`). The icon reuses the already-established accent color (`#e08a55`) by construction.
- **Palette**: No new colors introduced; all three colors (`#1c1f23` dark tile, `#e08a55` amber loop/arrow, `#e4e7ea` light mouse outline) are already in the design system. The tile is near-black for maximum contrast on any background. The accent amber is the app's existing accent.
- **Legibility at scale**: Platform-aware simplification at small sizes follows macOS/Windows icon conventions (iOS, macOS App Store, Windows taskbar all simplify glyphs at 16–32 px to maintain coherence).
- **Contrast and accessibility**: WCAG AA/AAA checked per color pairing and size (see "Accessibility & platform notes" below).

## Component reuse

- **No components**: This is a static icon asset (SVG source + rasterized outputs), not a React/React Native component. The runtime integration (`tk.PhotoImage` loading, `root.iconphoto` call) happens in `afk_clicker.py`, not in a component library; the icon is an inert image payload, not a widget.

## Icon sizes and variants

### Full icon (original design, 128×128)

Used at **48 px and above** (rendering: 48, 128, 256 px). All elements present: dark rounded tile, amber loop arrow with arrowhead, light mouse outline with filled left button and dividing line.

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

**Rationale**: At 48 px and above, the mouse is large enough (≈11×16 px at 48 px, ≈21×31 px at 128 px, ≈42×63 px at 256 px) that its strokes, button fill, and dividing line remain visually distinct and legible. The stroke widths scale proportionally, preserving the original design's balance.

### Simplified icon (loop arrow only, no mouse)

Used at **16 and 32 px** (rendering: 16, 32 px). Only the dark tile, amber loop arrow, and arrowhead; mouse, button fill, and dividing line are removed entirely.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#1c1f23"/>
  <path d="M100 64 A36 36 0 1 1 86 35" fill="none" stroke="#e08a55" stroke-width="9" stroke-linecap="round"/>
  <polygon points="96,42 84,24 76,42" fill="#e08a55"/>
</svg>
```

**Rationale**: At 16 px, the original mouse (28×42 px in 128×128) scales to 3.5×5.25 px — smaller than a typical single-pixel stroke. The mouse outline (5 px stroke in original) becomes 0.625 px; the button dividing line vanishes entirely. At 32 px, the mouse is 7×10.5 px with 1.25 px stroke — marginal, and on the borderline of legibility. The simplified variant avoids visual mud at these sizes: the loop arrow (stroke: 9 px → 1.1 px at 16 px, 2.25 px at 32 px) remains recognizable, and the arrowhead (≈20×18 px original → 2.5×2.25 px at 16 px, 5×4.5 px at 32 px) is minimal but present. This follows platform conventions: many icon sets (iOS, macOS, Windows, Material Design) simplify glyphs at ≤32 px.

**Size cutoff decision**:
- **16 px**: Simplified (loop + arrow)
- **32 px**: Simplified (loop + arrow)
- **48 px**: Full icon (mouse restored)
- **128 px**: Full icon (mouse restored)
- **256 px**: Full icon (mouse restored)

## Tile shape and padding per platform

### Windows (`.ico`)

- **Tile shape**: Rounded square (rx=28), fills the frame.
- **Padding**: None; the rounded tile extends edge-to-edge within the icon bounding box. Windows `.ico` embeds pixels as-is; no platform-level inset is needed.
- **Rendering**: At each size, rasterize the SVG at that pixel dimension (e.g., 256 px SVG → 256×256 PNG → embed in `.ico` as 256×256 entry).

### macOS (`.icns`)

- **Tile shape**: Rounded square (rx=28), fills the frame.
- **Padding**: None in the rasterized image; the `.icns` format itself handles the standard iOS/macOS rounded-square grid alignment. The rasterized PNG edges out to the full pixel bounds.
- **Rendering**: At each size, rasterize the SVG at that pixel dimension; the `.icns` container (built by external tooling) will align it to the macOS icon grid automatically.

### Linux / all platforms (Tkinter runtime PNGs)

- **Tile shape**: Rounded square (rx=28).
- **Padding**: None in the rasterized image; Tkinter's `iconphoto` displays the PNG as-is, and window managers (GNOME, KDE, etc.) handle any platform-specific grid alignment.
- **Rendering**: Rasterize to exact pixel dimensions (16, 32, 48, 256).

**Unified decision**: No extra padding added to any raster. The rounded tile as designed (rx=28 on 128×128 → proportionally scaled down) is the asset; platform tooling (Windows `.ico` embedding, macOS `.icns` bundling, Linux window managers) handles inset/grid alignment per platform convention.

## Accessibility & platform notes

### Color contrast (WCAG 2.1 AA / AAA)

**Dark tile on light backgrounds** (Windows taskbar, macOS Dock, light-theme desktop):
- Tile color: `#1c1f23` (near-black), luminance ≈ 0.022
- Light taskbar gray (~`#f0f0f0`), luminance ≈ 0.93
- **Contrast ratio**: (0.93 + 0.05) / (0.022 + 0.05) ≈ **13.8:1** (exceeds AAA, 7:1)
- **Verdict**: Excellent visibility on light backgrounds; no outline needed.

**Amber loop on dark tile** (primary icon pairing):
- Loop color: `#e08a55` (warm amber), luminance ≈ 0.371
- Tile color: `#1c1f23`, luminance ≈ 0.022
- **Contrast ratio**: (0.371 + 0.05) / (0.022 + 0.05) ≈ **5.94:1** (exceeds AA, 4.5:1; graphical element minimum 3:1)
- **Verdict**: Strong text-level contrast; clearly legible.

**Light mouse outline on dark tile** (secondary detail, when present in full icon):
- Mouse outline: `#e4e7ea` (light gray), luminance ≈ 0.807
- Tile color: `#1c1f23`, luminance ≈ 0.022
- **Contrast ratio**: (0.807 + 0.05) / (0.022 + 0.05) ≈ **12.1:1** (exceeds AAA, 7:1)
- **Verdict**: Excellent visibility; the mouse outline is highly legible at 48 px and above.

**At small sizes (16, 32 px)** with simplified variant (no mouse):
- Only the loop arrow and tile are present, both with strong contrast ratios (13.8:1 and 5.94:1 respectively).
- The removal of the mouse avoids visual clutter without sacrificing accessibility.

### Touch targets and small-size rendering

- **16 px / 20 px**: Used in window title bars, Alt-Tab lists, small tray icons. The simplified variant ensures the loop arrow remains clear.
- **32 px**: Dock icons (macOS), taskbar previews (Windows). The simplified variant keeps the design coherent at this transition size.
- **48 px+**: Full icon visible in file explorers, desktop shortcuts, Finder windows. The mouse adds narrative (a clickable object completing a loop cycle), justifying the extra detail.
- **256 px**: Display, branding. Full detail supports high-resolution viewing.

No minimum touch target is relevant here; icon rendering is the operating system's responsibility, not a touch-interactive surface.

### Platform differences

- **Windows**: `.ico` multiresolution container handles size switching at render time; no runtime logic needed.
- **macOS**: `.icns` bundle and `.app` bundle integration is handled by PyInstaller's `--icon` flag and Finder/system APIs.
- **Linux**: `root.iconphoto` in Tkinter selects the nearest-size PNG from those loaded; no OS-level icon standard. The app loads 16, 32, 48, 256 px and lets Tk/WM choose the best fit per context.

## Output matrix for developer

The developer (or a one-off out-of-band tool invocation per the spec) must generate these files:

### Asset source files (committed to `assets/`)

| File | Purpose | Contents |
|------|---------|----------|
| `assets/icon.svg` | Source, full icon | Full design (loop, arrow, mouse); used as reference and for editing. |
| `assets/icon-simplified.svg` | Source, simplified | Loop arrow only; used to generate 16 and 32 px sizes. |

### `.ico` file (Windows bundle icon, via `--icon assets/icon.ico`)

Multi-resolution Windows icon. Each size sourced from the appropriate SVG variant:

| Size | Source SVG | Purpose |
|------|-----------|---------|
| 16×16 | `icon-simplified.svg` | Window title bar, Alt-Tab, small taskbar previews. |
| 32×32 | `icon-simplified.svg` | Taskbar, small file icons. |
| 48×48 | `icon.svg` | File explorer, larger taskbar contexts. |
| 256×256 | `icon.svg` | Display, branding, high-DPI contexts. |

**Generation**: Use any standard tool (Inkscape CLI, ImageMagick, online `.ico` builder, etc.) to rasterize each SVG variant at its corresponding size to a PNG, then embed the four PNGs into a single `.ico` container. Output: `assets/icon.ico`.

### `.icns` file (macOS bundle icon, via `--icon assets/icon.icns`)

macOS icon set. Each size sourced from the appropriate SVG variant:

| Size | Source SVG | Purpose |
|------|-----------|---------|
| 16×16 | `icon-simplified.svg` | Menu bar, small contexts. |
| 32×32 | `icon-simplified.svg` | Finder detail list, smaller previews. |
| 48×48 | `icon.svg` | Finder icon view (standard). |
| 128×128 | `icon.svg` | Finder cover flow, larger previews. |
| 256×256 | `icon.svg` | High-resolution display, App Store. |
| 512×512 | `icon.svg` | Retina display, notification, extra large. |

**Generation**: Rasterize each SVG variant at its size to PNG, then use a tool like `iconutil` (macOS, built-in) or an online `.icns` builder to bundle them. Output: `assets/icon.icns`. (Note: modern `.icns` files often use `@2x` suffixed assets for Retina; if the tool auto-generates these, allow it—they're internal to the `.icns` container and transparent to PyInstaller.)

### PNG files (Tkinter runtime, via `root.iconphoto`)

Rasterized PNGs used by the app at runtime (unfrozen and frozen). Source SVG per size:

| File | Size | Source SVG | Purpose |
|------|------|-----------|---------|
| `assets/icon-16.png` | 16×16 | `icon-simplified.svg` | Title bar, small window contexts. |
| `assets/icon-32.png` | 32×32 | `icon-simplified.svg` | Taskbar, Dock, small preview. |
| `assets/icon-48.png` | 48×48 | `icon.svg` | Standard window icon. |
| `assets/icon-256.png` | 256×256 | `icon.svg` | High-resolution fallback, scaling. |

**Generation**: Rasterize each SVG variant at its size to PNG. Use any standard tool (Inkscape, ImageMagick, online converter, Pillow+cairosvg in a throwaway script, etc.). Output four PNG files directly to `assets/`.

### PyInstaller and build flags

The developer adds these flags to the existing PyInstaller invocations:

**`.github/workflows/release.yml` (Linux and macOS jobs)**:
```bash
--add-data "assets:assets" --icon assets/icon.icns  # macOS job only
--add-data "assets:assets"                          # Linux job only
```

**`.github/workflows/release.yml` (Windows job)**:
```bash
--add-data "assets;assets" --icon assets\icon.ico
```

**`build.bat` (Windows local build)**:
```batch
--add-data "assets;assets" --icon assets\icon.ico
```

(Note: PyInstaller's path separator is `:` on POSIX, `;` on Windows; backslash escaping in batch is literal.)

## Traceability to spec

| Acceptance criterion (from docs/spec.md) | Where it's addressed in this design |
|---|---|
| SVG committed to `assets/icon.svg` byte-for-byte as specified. | Criterion is on the developer; design confirms the SVG shape and color values match. Source file listed in "Output matrix" section. |
| `root.iconphoto` called with non-empty PhotoImage, no exception. | Runtime wiring is in `afk_clicker.py` (spec `line:130–141`); design specifies four PNG sizes Tkinter will load via that call. |
| Reference held on `self` to avoid garbage collection. | Spec requirement for developer; design output (PNG files, sizes) enables this. |
| Missing PNG file raises visibly (uncaught exception). | Spec requirement for developer error handling; design output (four specific PNG files) removes ambiguity about which assets must exist. |
| `.github/workflows/release.yml` per-platform PyInstaller invocations include `--icon`/`--add-data` flags. | Design specifies exact flags per platform in "Output matrix → PyInstaller and build flags" section. |
| `build.bat` includes same flags as release workflow Windows job. | Same. |
| CI builds embed `.ico`/`.icns` correctly (Windows/macOS). | Verified by CI; design specifies `.ico` (16/32/48/256) and `.icns` (16/32/48/128/256/512) embedded sizes and source SVG variants. |
| Open question: simplified small-size variant. | **Resolved in this design**: 16 and 32 px sizes use simplified variant (loop arrow only); 48+ px use full icon. Rationale: legibility at scale, platform conventions. Two SVG sources provided: `assets/icon.svg` (full) and `assets/icon-simplified.svg` (simplified). |

## Design notes

### Why simplify at 16 and 32 px?

- **Technical**: The mouse (28×42 px at 128×128) scales to 3.5×5.25 px at 16 px, 7×10.5 px at 32 px. Strokes become hairlines; details vanish.
- **Convention**: macOS icons (App Store, Finder), Windows icons (taskbar, file explorer), and Material Design all simplify glyphs at ≤32 px. A loop arrow alone is visually coherent and instantly recognizable.
- **Clarity**: The simplified variant reduces visual ambiguity; there is no risk of the mouse appearing as noise or an artifact at small sizes.

### Why no outline on the dark tile?

The dark background (#1c1f23) achieves 13.8:1 contrast on light backgrounds—well above AAA. An outline would:
- Reduce legibility by adding a visual distraction.
- Be unnecessary; the contrast already passes all standards.
- Risk muddying the icon at small sizes if the outline stroke is proportional.

No outline is added.

### Why keep the rounded tile uniformly?

The rounded-square shape (rx=28) is the intended design from the spec. It:
- Matches platform conventions (iOS app icons, macOS App Store, modern desktop icon sets all use rounded squares).
- Scales proportionally, so it remains visually coherent at any size.
- Aligns naturally with window-manager and OS icon grids (no extra padding needed).

The tile is not inset or padded; the rounded corners themselves define the visual boundary.
