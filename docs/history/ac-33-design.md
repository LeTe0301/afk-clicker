# Design: Rename product to Clickwork (part 1 of 2 — branding/strings)

## Summary

Rename all user-visible product identity from "AFK Farm Clicker" to "Clickwork" in:
- Window title bar (`root.title()`)
- Header label (top-left of the application UI)
- README.md (title, download table, and prose)
- GitHub release asset names and release-body table
- Updater User-Agent header and temporary directory prefix (cosmetic, no wire-format impact)

Non-visual rationale: The executable and bundle paths, settings directories, and internal build name remain unchanged to preserve the auto-update mechanism for existing installs (see spec's "Proposed approach" for the constraint).

## Component Reuse & Existing Patterns

- **Window title** (`root.title()`): uses Tk's native title-bar API; no custom component needed.
- **Header label**: existing `tk.Label` widget with `bg=CARD`, `fg=INK`, `font=("Segoe UI", int(12 * s), "bold")` styling. This label is part of the header frame built at `afk_clicker.py:2033–2040`.
- **No new components**: this rename touches only text content; all styling, color, and layout remain unchanged.

## Visual Changes per Location

### 1. Window Title Bar
- **Current**: "AFK Farm Clicker"
- **New**: "Clickwork"
- **Display**: OS title bar text (rendered by the window manager, not by the app's own code)
- **Styling impact**: None — font and appearance are controlled by the OS

### 2. Header Label (In-App)
- **Location**: Top-left of the application, next to the ON/OFF toggle button (StatusPill)
- **Current state**: `tk.Label(..., text="AFK Farm Clicker", bg=CARD, fg=INK, font=("Segoe UI", int(12 * s), "bold"))`
- **Change**: Text only, from "AFK Farm Clicker" to "Clickwork"
- **Styling**: No change — keep Segoe UI 12pt bold, CARD background, INK foreground
- **Font rendering**: "Clickwork" is 9 characters vs. "AFK Farm Clicker" at 16 characters; the shorter text leaves additional whitespace to the right but does not affect the header's 52px height (`height=int(52 * s)`).
- **Responsive behavior**: The label is packed with `side="left", padx=int(16 * s)` into a fixed-height header. Because "Clickwork" is shorter, there are no layout regressions at any UI scale (90%, 100%, 115%, 130%) or when the sidebar collapses (story #24 responsive layout, `RAIL_COLLAPSE_THRESHOLD`).

### 3. README.md

#### Title (line 1)
- **Current**: `# AFK Farm Clicker`
- **New**: `# Clickwork`

#### Download table (lines 19–21)
- **Current**:
  ```
  | Windows 10/11 | `AFK-Farm-Clicker-windows-x64.zip` |
  | Linux (glibc 2.35+, X11) | `AFK-Farm-Clicker-linux-x86_64.tar.gz` |
  | macOS (Apple Silicon) | `AFK-Farm-Clicker-macos-arm64.zip` |
  ```
- **New**:
  ```
  | Windows 10/11 | `Clickwork-windows-x64.zip` |
  | Linux (glibc 2.35+, X11) | `Clickwork-linux-x86_64.tar.gz` |
  | macOS (Apple Silicon) | `Clickwork-macos-arm64.zip` |
  ```

#### Settings-path table (lines 59–61) — **unchanged**
Keep the literal paths exactly as they are:
```
| Windows | `%APPDATA%\AFKFarmClicker\settings.json` |
| Linux | `~/.config/afk-farm-clicker/settings.json` |
| macOS | `~/Library/Application Support/AFKFarmClicker/settings.json` |
```
The prose around this table may use "Clickwork" for the product name, but the paths themselves do not change because the directories they refer to are not being renamed.

### 4. GitHub Release Asset Names and Release Body

#### Release asset matrix (`.github/workflows/release.yml`, lines 110–116)
- **Current**:
  ```
  asset: AFK-Farm-Clicker-windows-x64.zip
  asset: AFK-Farm-Clicker-linux-x86_64.tar.gz
  asset: AFK-Farm-Clicker-macos-arm64.zip
  ```
- **New**:
  ```
  asset: Clickwork-windows-x64.zip
  asset: Clickwork-linux-x86_64.tar.gz
  asset: Clickwork-macos-arm64.zip
  ```

#### Release body table (`.github/workflows/release.yml`, lines 224–226)
- **Current**:
  ```
  | Windows 10/11 | `AFK-Farm-Clicker-windows-x64.zip` |
  | Linux (glibc 2.35+, X11) | `AFK-Farm-Clicker-linux-x86_64.tar.gz` |
  | macOS (Apple Silicon) | `AFK-Farm-Clicker-macos-arm64.zip` |
  ```
- **New**:
  ```
  | Windows 10/11 | `Clickwork-windows-x64.zip` |
  | Linux (glibc 2.35+, X11) | `Clickwork-linux-x86_64.tar.gz` |
  | macOS (Apple Silicon) | `Clickwork-macos-arm64.zip` |
  ```

## Styling Decisions

### Font Choice
- **Header label font**: Segoe UI, size 12 (scaled by `s`), weight **bold** — **keep as-is**
- **Rationale**: The font is already established and reflects the project's UI consistency. "Clickwork" renders at the same weight and size; no adjustment needed.

### Color Contrast
- **Background**: `CARD` token (defined in the theme system)
- **Foreground**: `INK` token (defined in the theme system)
- **Note**: Both colors are already in use across the application and meet WCAG AA contrast standards. No new color pairings are introduced in this rename, so contrast verification is inherited from the existing design.

### Layout Impact
- **Header height**: 52px (fixed) — unaffected by the text change
- **Label position**: left-aligned with 16px padding — unaffected
- **Whitespace**: The shorter "Clickwork" text creates more right-side whitespace in the header, but this is visual refinement (less cluttered), not a regression
- **Responsive thresholds**: 
  - `RAIL_COLLAPSE_THRESHOLD = SIDEBAR_W + 1 + CONTENT_W = 208 + 1 + 452 = 661px`
  - At 90% UI scale (the smallest supported): `661 × 0.9 = ~595px` minimum window width
  - The header label scales with the UI scale factor (`s`) and remains left-aligned; the shorter text poses no new min-width constraint

## State Coverage

### Load State
- When the window opens, the header label is immediately populated with "Clickwork" (it's set via `tk.Label(..., text="Clickwork", ...)`).
- No lazy loading or placeholder text — the label is static at widget construction time.

### Normal State
- The header displays "Clickwork" persistently whenever the window is visible.
- No state transitions (the label does not change based on user interaction or app state).

## Accessibility Notes

- **Text readability**: "Clickwork" is a 9-character proper noun without special glyphs or characters that might confuse assistive readers. Screen readers will read it as a single word.
- **Color contrast**: The `CARD`/`INK` pairing is unchanged from the existing design; no new a11y concerns are introduced.
- **No icon/graphic label**: The header label is text-only; no alt-text or icon-labeling is needed.

## Explanation of Technical Name Mismatch (for User-Facing Copy)

When users download and install, they will see:
- Window title and header: "Clickwork"
- Downloaded file: `Clickwork-windows-x64.zip` (or the Linux/macOS equivalent)

But on their disk after installation, the folder will still be:
- Windows: `dist\AFK Farm Clicker\AFK Farm Clicker.exe`
- Linux: `./AFK Farm Clicker/AFK Farm Clicker` (binary)
- macOS: `AFK Farm Clicker.app`

**User-facing explanation** (if needed in README or release notes):
A one-sentence note stating that the program file and internal folder names remain "AFK Farm Clicker" for compatibility with the existing auto-updater. Example: *"The program file is internally called 'AFK Farm Clicker' for update compatibility; the app itself is Clickwork."*

This appears in `README.md` in the existing settings-path table context (lines 59–61), where the old internal paths are documented. No separate callout is needed if the table's prose already makes this clear.

## Summary of Changes

| Location | Change Type | Old Value | New Value |
|---|---|---|---|
| `root.title()` | Window title | "AFK Farm Clicker" | "Clickwork" |
| Header label text | In-app header | "AFK Farm Clicker" | "Clickwork" |
| README.md line 1 | Title | `# AFK Farm Clicker` | `# Clickwork` |
| README.md lines 19–21 | Download table file names | `AFK-Farm-Clicker-*` | `Clickwork-*` |
| README.md lines 59–61 | Settings paths | (unchanged) | (unchanged) |
| `release.yml` asset matrix | Release asset names | `AFK-Farm-Clicker-*` | `Clickwork-*` |
| `release.yml` release body | Release body table | `AFK-Farm-Clicker-*` | `Clickwork-*` |
| `build.bat` line 59 | PyInstaller `--name` | (unchanged) | (unchanged) |
| Exe/bundle paths | Internal folder paths | (unchanged) | (unchanged) |
| Settings directories | Config paths | (unchanged) | (unchanged) |
| User-Agent header | HTTP header | `AFKFarmClicker/{version}` | `Clickwork/{version}` |
| Temp directory prefix | Temp folder name | `afkclicker-update-` | `clickwork-update-` |

## No New Components or Dependencies

- **Existing components used**: `tk.Label` (already in use for the header)
- **Existing styling tokens**: `CARD`, `INK` (already defined in the theme)
- **Existing font**: Segoe UI, 12pt, bold (already in use)
- **No new dependencies**: This rename requires no new libraries, widgets, or design patterns.

## Part 2 (Out of Scope for This Design)

The app icon design, including any new icon asset generation or CI steps, is part 2 and will be handled in a separate build cycle as `docs/spec-part2-icon.md`.
