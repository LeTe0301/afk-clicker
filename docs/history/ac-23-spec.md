# Spec: macOS font-size floor (`fs(base, s)`)

## Summary
Add a small `fs(base, s)` helper that floors every computed font point size at 6pt, and route all ~20-30 `int(base * s)` font-size expressions in `afk_clicker.py` through it, so macOS's low `_dpi_s` (~0.75) no longer renders 5pt labels at the 90% UI-scale step.

## Goals
- Introduce `fs(base, s) -> int`, a pure module-level helper (alongside `UI_SCALE_FACTORS`/`UI_SCALE_DEFAULT`, `afk_clicker.py:130`), that computes the same value as today's `int(base * s)` except it never returns less than a floor of **6**.
- Replace every font-size `int(base * s)` expression in the file with `fs(base, s)`, so the floor applies uniformly rather than only to the one call site the ticket happened to quote.
- Fix the specific reported case: mac `_dpi_s ~= 0.75`, 90% UI scale (`s = 0.675`) — `int(8 * 0.675) == 5` today, `fs(8, 0.675) == 6` after this change.
- Leave the already-shipping mac 100%-scale look (`s = 0.75`, `int(8 * 0.75) == 6`) bit-for-bit unchanged — `fs(8, 0.75) == 6` too, since 6 already meets the floor.
- Leave every non-mac (`_dpi_s == 1.0`) computed size unchanged at all four scale steps — none of them are currently below 6, so the floor never engages there (see Acceptance criteria for the specific numbers).
- Shape `fs()` so G#38 (UI scale follows window size, queued after this) can reuse it unmodified for continuous (non-stepped) scale values — it already works for any `s`, since it's a pure function of two numbers, but call this out so nobody "improves" it into something tied to the four discrete `UI_SCALE_FACTORS` keys.

## Non-goals
- No new user-facing setting, toggle, or preference for the floor value — it is a fixed constant.
- No change to `WINDOW_MIN_H` or any pane-fit/layout floor logic.
- No change to the 90/100/115/130% `UI_SCALE_FACTORS` step values themselves, and no dropping the 90% step.
- No implementation of G#38 (continuous/"Auto" scaling, drag-resize debounce, screen-relative reference) — this hotfix only lands the helper G#38 will later reuse.
- No fix for G#42/GH#81 (the `WindowMinimumHeight` floor tests measuring allocated instead of required height) — that ticket is explicitly flagged in the backlog as needing to land "before trusting [those tests] on G#23/G#38." This spec's own tests must not lean on those tests as their correctness gate; see Acceptance criteria and Risk notes.
- No fix for G#4/GH#6 (macOS CI click-interval timing) — unrelated, separate ticket.
- No attempt to raise the already-shipping 6pt mac-100% baseline on its own merits — only the newly-broken 5pt mac-90% case is being corrected, up to parity with what already ships. If 6pt itself is later judged too small, that's a new ticket.

## Background / current state
`afk_clicker.py:2287-2288` (`AfkAutoclicker.__init__`):
```python
self._dpi_s = root.tk.call("tk", "scaling") / 1.333  # 1.0 at 96 dpi
self.s = s = self._dpi_s * UI_SCALE_FACTORS[self.store.data["ui_scale"]]
```
`self.s` (often shadowed locally as `s`) is threaded into essentially every widget constructor and font tuple in the file. Every font-size call site multiplies a literal base point size by `s` and truncates with `int()`, e.g. `afk_clicker.py:1726`: `font=("Segoe UI", int(8 * s), "bold")`.

On Windows/Linux, `_dpi_s` is 1.0 (or very close to it), so the smallest shipped size (`int(8 * 1.0) = 8` at 100%, `int(8 * 0.9) = 7` at 90%) is already legible. The spec that introduced `UI_SCALE_FACTORS` (`docs/history/ac-17-f4-spec.md` §2/§3) assumed `_dpi_s >= 1.0`; on macOS `tk scaling` reports ~0.75 (mac's 72-dpi-native `tk scaling` convention vs. this app's 96-dpi baseline), so the same arithmetic produces `int(8 * 0.75) = 6` at 100% (already shipping, not itself broken) and `int(8 * 0.675) = 5` at 90% (`s = 0.75 * 0.9`, the ticket's reported case) — below what's legible. `backlog.md`'s lessons section (line ~526-529) already flags that the compound scale multiplies (worst case is low-DPI *and* 90% together, `s = 0.675`) and that `int()` truncates rather than rounds.

`tests/test_ui.py:1148-1168` (`WindowMinimumHeight.test_tallest_pane_still_fits_at_worst_case_compound_scale`) already establishes the pattern for simulating this in tests without a real Mac: `self.ui._dpi_s` is a plain instance attribute, safe to set directly (`self.ui._dpi_s = 0.75`), followed by `self.ui._apply_ui_scale("90")` to recompute `self.s` and trigger a rebuild. `UITestCase.restart()` (`tests/test_ui.py:162-167`) gives a fresh instance at a persisted `ui_scale` value, the pattern `MinecraftSweepHint`'s floor test (`tests/test_ui.py:1222-1226`) uses when a scale change must be reached via a real relaunch rather than a mid-test `_apply_ui_scale()` call.

## Proposed approach

**1. The helper** (module level, near `UI_SCALE_FACTORS`/`UI_SCALE_DEFAULT`, `afk_clicker.py:130`):
```python
# G#23/GH#35: macOS reports tk scaling ~0.75 (its 72-dpi-native convention vs.
# this app's 96-dpi baseline), so self.s can land well under 1.0 even before
# the 90% UI-scale step multiplies it further (worst case _dpi_s * 0.9 ~= 0.675,
# see backlog.md's compound-scale lesson). int() truncates, so an
# already-small base like 8 crosses from 6pt (100%, ships today) to 5pt (90%,
# illegible) purely from that one extra multiply. FONT_SIZE_FLOOR is chosen to
# match the smaller of those two, not raise it: 6 leaves every already-shipping
# size (mac 100%, and every non-mac step -- none of which are under 6 today)
# untouched, and only lifts the newly-broken 90% case up to parity with 100%.
# G#38 (UI scale follows window size) will reuse this unmodified for its own
# continuous-s scaling -- keep it a pure function of (base, s), not tied to
# the four discrete UI_SCALE_FACTORS keys.
FONT_SIZE_FLOOR = 6


def fs(base, s):
    """int(base * s), floored at FONT_SIZE_FLOOR so no label renders
    illegibly small on a low-DPI display. Truncates (matches every existing
    call site's int() today) rather than rounds -- rounding would silently
    change already-shipped sizes at scale steps this ticket isn't about."""
    return max(FONT_SIZE_FLOOR, int(base * s))
```

**2. The sweep.** Replace every font-size `int(<base> * s)` expression with `fs(<base>, s)`. Confirmed by grep (`grep -n 'int([0-9.]* \* s)' afk_clicker.py` plus the two variable-fed call sites) — the call sites found during this spec's own archaeology, given here so the developer doesn't need to re-derive the list:

| Line(s) | Base | Notes |
|---|---|---|
| 1625 | 9.5, bold | `Button` label |
| 1676 | 9 | `Segmented` option text |
| 1726 | 8, bold | `ToggleCheckbox` checkmark — **actually changes value** at worst case (5→6) |
| 1770-1771 | 9.5, bold | `TabBar`: `font` tuple **and** the `tkfont.Font` width-measurer must use the identical size — compute once (`font_size = fs(9.5, s)`) and feed both, rather than calling `fs()` twice inline, so a future edit to one can't silently desync from the other |
| 1791 | (reuses `font` var from 1770) | — |
| 1828 | 11.5, bold | |
| 1830 | 8.5 | **actually changes** (5→6) |
| 1861 | 10, bold | |
| 2076, 2137 | 10.5, bold | |
| 2081, 2152 | 9.5 | |
| 2202 | 9.5 | |
| 2213 | 8 → `self._hint_size` | **actually changes** (5→6); reused at 2217 and 2235, no separate fix needed there |
| 2223 | 8 | **actually changes** (5→6) |
| 2253 | 9 | |
| 2259 | 10, Consolas | |
| 2672 | 12, bold | |
| 2692 | 8, bold | **actually changes** (5→6) |
| 2924, 3068, 3917 | 14, bold | |
| 2927, 3925, 3929 | 9 | (3925 also has an unrelated `wraplength=int(560 * s)` on the same line — that is not a font size, leave it as `int()`) |
| 2931 | 8.5 | **actually changes** (5→6) |
| 2976, 3943 | 10, Consolas | |
| 3131 | 9.5 | |
| 3141 | 8 | **actually changes** (5→6) |
| 3180, 4121 | 9, Consolas | |
| 3956 | 9.5 | |

Of these, only the seven marked rows (bases 8 and 8.5) actually produce a different rendered value at the worst-case `s = 0.675` — `8 * 0.675 = 5.4 -> 5` and `8.5 * 0.675 = 5.7375 -> 5`, both floored to 6. Every base of 9 or higher already truncates to >= 6 at `s = 0.675` (`9 * 0.675 = 6.075 -> 6`), so `fs()` is a no-op there — they're still converted for consistency and G#38's future reuse, not because they're currently broken.

**3. Do not touch** non-font `int(x * s)` expressions (padding, wraplength, widget width/height in pixels, e.g. `afk_clicker.py:1617`, `2217`, `3925`'s `wraplength`) — `fs()` is for point sizes only.

## Affected areas
- `afk_clicker.py` only: one new constant + helper near line 130, and the font-size call sites listed above (all in the same file, same architectural layer — UI widget construction). No schema, no settings, no other module.
- `tests/test_ui.py`: new unit-style coverage for `fs()` itself, plus one integration-style check reusing the existing `_dpi_s`/`_apply_ui_scale` simulation pattern.

## Edge cases
- **Non-mac platforms, all four scale steps.** `_dpi_s == 1.0`: smallest base (8) at 90% gives `int(8 * 0.9) = 7`, still above the floor — `fs()` must not change anything here. Worth an explicit test so a future floor-value change can't silently regress Windows/Linux without a failing test noticing.
- **Mac at 115%/130%.** `s = 0.75 * 1.15 = 0.8625` -> `int(8 * 0.8625) = 6` (already at the floor, `fs()` is a no-op); `s = 0.75 * 1.3 = 0.975` -> `int(8 * 0.975) = 7` (above floor). Neither needs special-casing, but worth one test point confirming the floor doesn't over-fire at the less-extreme mac steps.
- **`TabBar`'s measurer/font pairing** (see table above) — a desync here wouldn't crash, just silently misalign tab width vs. rendered text, which is the kind of thing CI's macOS visual leg is the only realistic way to catch. Calling `fs()` once into a shared local avoids the desync at the source rather than relying on the two calls happening to agree.
- **`self._hint_size`** is computed once and reused by two later call sites (2217, 2235) — same "compute once, reuse" shape, already correct in the current code, `fs()` is a drop-in replacement.
- **G#38 reuse (future, not built here).** `fs()` must keep working for any `s`, not just the four `UI_SCALE_FACTORS` values — already true since it's `max(FLOOR, int(base * s))` with no reference to the scale-step dict. No code needed now, just don't add one.

## Acceptance criteria
- [ ] `fs(8, 0.75) == 6` (mac 100%, already-shipping case — unchanged)
- [ ] `fs(8, 0.675) == 6` (mac 90%, the ticket's reported 5pt case — now floored, was 5 via plain `int()`)
- [ ] `fs(9.5, 0.675) == 6` (an unaffected base at the worst-case scale — floor is a no-op, same value plain `int()` would already give)
- [ ] `fs(8, 1.0) == 8` (Windows/Linux 100% — unchanged)
- [ ] `fs(8, 0.9) == 7` (Windows/Linux 90% — unchanged, still above floor)
- [ ] `fs(8, 0.8625) == 6` and `fs(8, 0.975) == 7` (mac 115%/130% — floor is a no-op at both)
- [ ] Every font-size `int(<literal> * s)` expression in `afk_clicker.py` (the table above) is replaced with `fs(<literal>, s)`; `grep -n 'int([0-9.]* \* s)' afk_clicker.py` after the change returns only non-font hits (padding/width/height/wraplength), none feeding a `font=` tuple or `tkfont.Font(size=...)`
- [ ] `TabBar`'s label font and its width-measurer (`afk_clicker.py` ~1770-1791) read the same `fs(9.5, s)` value (single computed local, not two independent calls) — read the code to confirm, no separate runtime check needed since a desync wouldn't throw
- [ ] Given a `UITestCase`-style instance, when `self.ui._dpi_s = 0.75` and `self.ui._apply_ui_scale("90")` are applied (mirroring `tests/test_ui.py:1148-1168`'s existing pattern) and the window is updated, then a widget built from one of the seven "actually changes" call sites above (e.g. `ToggleCheckbox`'s checkmark, or the sidebar hint's `_hint_size`) reports an actual font size of 6, not 5 — verified via `tkfont.Font(font=widget.itemcget(item_id, "font")).actual("size")` (or the widget's own `cget("font")` where it's a real `tk.Label`/`tk.Entry` rather than a canvas text item)
- [ ] Given the same simulated-mac setup at 100% scale instead of 90%, then the same widget's font size is still 6 (proves the floor didn't accidentally shift the already-shipping baseline)
- [ ] CI's macOS leg is green after this change lands — this is the only real-Mac verification available (ticket: "Only verifiable via CI; no real Mac available"); call this out explicitly in the PR description rather than treating a green local/Linux run as sufficient, per `backlog.md`'s lesson #1 ("a green local run is not evidence for behaviour this box cannot produce")

## Open questions
None blocking. One assumption worth surfacing explicitly rather than silently baking in: **`FONT_SIZE_FLOOR = 6`** is derived directly from the ticket's own numbers (100% already ships at 6pt; 90% currently renders 5pt) rather than from any independent legibility study — proceeding on the assumption that "raise the newly-broken case to parity with the already-accepted baseline" is the right bar, not "pick an objectively-legible minimum from scratch." If Leo wants a higher floor than 6 on its own merits, that's a follow-up, not a blocker to this hotfix landing as scoped.

## Risk / rollback notes
- **Blast radius is wide but shallow**: ~20-30 call sites change, but each is a one-line `int(...)` -> `fs(...)` substitution with no behavior change except at the seven bases-8/8.5 sites, and even those only differ at scale steps this ticket is specifically about. A mechanical, low-risk diff.
- **Real risk is unverifiable locally**: this box has no real Mac, so the only way to know the fix actually renders correctly is CI's macOS leg (or a real device Leo has access to). Don't ship confidence from a green Linux/Xvfb run alone.
- **Do not lean on `WindowMinimumHeight`'s older floor tests as evidence of correctness** — G#42/GH#81 (open, out of scope here) already documents that those specific tests measure allocated rather than required height and can pass even when content is genuinely clipped. This spec's own `fs()`-focused tests (direct value assertions, plus the one widget-level check above) are the real gate; the existing pane-fit tests are a bonus signal at best.
- **Rollback**: a single-file, single-commit revert (`fs`/`FONT_SIZE_FLOOR` plus the call-site substitutions) — no data/schema/settings changes to unwind.
