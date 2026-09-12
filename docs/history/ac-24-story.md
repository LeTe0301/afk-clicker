# Story: Responsive layout and an icon-led minimal restyle (ac-24 / GitHub #36)

## Summary
The window (made resizable by #14) does not actually reflow: at 1200x820 the
sidebar stays frozen at `SIDEBAR_W = 208`, row controls stay pinned to the far
right of a much-wider card leaving a dead gulf, and roughly half the window's
height sits empty below a fixed stack of cards. Alongside that, the shell
that commit `b6a7602` built against the NVIDIA App reference never picked up
the reference's actual visual language (rounded pill cards instead of flat
surfaces, no icon rail, no in-page tab bar). This story makes every page
genuinely reflow with the window, adds the two agreed navigation levels
(an icon rail that collapses when narrow, and a horizontal tab bar under each
page's title), and restyles the shell flat and minimal to match the reference.

## Current architecture (read before touching anything)
- `afk_clicker.py` is one file, 2551 lines. Layout is fixed-pixel-times-scale:
  `SIDEBAR_W = 208`, `CONTENT_W = 452` (`afk_clicker.py:160-161`), multiplied
  by `self.s` everywhere a widget is sized.
- The shell is two `pack()`ed panes built once per `_build_ui(s)` call
  (`afk_clicker.py:1583-1702`): `side` (the sidebar, `pack_propagate(False)`,
  fixed width) and `content` (`pack_propagate(False)`, also nominally fixed
  width but `fill="both", expand=True` lets `pack` hand it real extra space
  when the window grows — this is *why* cards inside it already stretch
  today; nothing downstream of that reacts to the extra width).
- `_build_content(s)` (`afk_clicker.py:1794-1858`) stacks Hotkey, Clicking,
  and (Minecraft-only) Eating as three `card()`s in one scrolling column.
  `_build_settings(s)` (`afk_clicker.py:1860-1945`) stacks Appearance and
  Updates the same way. Neither has any concept of tabs today.
- `Row` (`afk_clicker.py:1416-1429`) packs a label frame `side="left",
  fill="x", expand=True` and a control frame `side="right"` with no packing
  option — the control is pinned to the card's true right edge, which is why
  a stretched card creates a growing gulf between label and control.
- The sidebar's rows are `GameItem` (`afk_clicker.py:1338-1370`) and
  `SettingsItem` (`afk_clicker.py:1373-1413`): a colored state dot (or, for
  Settings, none) plus a text label on a `tk.Canvas`, width fixed at
  `SIDEBAR_W - 16`. There is no icon glyph anywhere in the app today.
- Visual chrome: `CARD_R = 12` (`afk_clicker.py:143`) rounds every `card()`
  shell and every `Button`/`Segmented`/`GameItem`/`SettingsItem`/`StatusPill`
  via `round_rect()` (`afk_clicker.py:1151-1159`) at `PILL_R = 999` for the
  fully-pill controls. `section()` (`afk_clicker.py:1285-1289`) renders tiny
  uppercase muted labels with no room for a right-aligned action.
- Rebuild machinery: `_request_rebuild()` (`afk_clicker.py:1568-1579`) and
  `_rebuild_ui()` (`afk_clicker.py:1704`, docstring 1705-1765) coalesce
  Appearance/UI-scale changes into at most one pending, and at most one
  *running*, full teardown-and-rebuild of every widget under `root`
  (`self._rebuilding` / `self._rebuild_wanted` / `self._rebuild_after_id`).
  It was designed around **discrete** triggers (a settings change fires once)
  — nothing in the app today drives it from a **continuous** event stream
  like a live window-resize drag.
- `_apply_minsize()` (`afk_clicker.py:1545-1566`) derives the window's hard
  floor as `(SIDEBAR_W + 1 + CONTENT_W) * s` wide — i.e. today's floor
  assumes the sidebar is always at its full, expanded width. This matters
  directly for the icon-rail feature below.
- `self.s = self._dpi_s * UI_SCALE_FACTORS[...]` (`afk_clicker.py:1466`,
  `1466`/`2007`) is the existing DPI+UI-scale compound. None of this story's
  features touch `_dpi_s` or `UI_SCALE_FACTORS` — the new width-driven
  breakpoints below are a different axis from that existing scale bug (#23).
- Accent color today: `ACCENT = "#e08a55"` in the dark theme, `"#2b58cc"` in
  light (`afk_clicker.py:78-80`, `THEMES` dict). The ticket's own text calls
  this "the current red"; whichever word fits, its hex is on record here so
  Feature 5's design stage has the exact before-value to compare against.
- What already matches the reference (commit `b6a7602`, "Per-game settings,
  NVIDIA-style shell..."): the two-pane games-left/settings-right split, and
  the dark near-black palette. What never landed: icon rail, tab bar, flat
  (non-rounded, non-pill) chrome, sentence-case headers with right-aligned
  actions, and the value-column row alignment.

## Feature breakdown

| # | Feature | Depends on | Status | Notes |
|---|---|---|---|---|
| 1 | Row controls dock into a fixed-width value column instead of the card's true right edge | none | done | Fixes the horizontal "gulf" named in the ticket. `Row`-only change (`afk_clicker.py:1416-1429`); touches every `Row(...)` call site in `_build_content`/`_build_settings` only to the extent their control frames now sit in a bounded column, not floating at the far edge. No icons, no tabs, no color/shape changes. |
| 2 | Horizontal tab bar under the page title: game pages get `Hotkey \| Clicking`, Settings gets `Appearance \| Updates` | none | done | New tab-bar component (extend `Segmented`'s canvas-drawing approach, or a sibling class) plus splitting `_build_content`/`_build_settings` into panes with persisted active-tab state, mirroring the existing `self._settings_open` pattern. See Open question 2 (where Eating lands) before implementing. |
| 3 | Icon rail: the sidebar collapses to icon-only below a width threshold, and the window's minimum width is rederived for the collapsed state | none (logically benefits from 1 & 2 landing first — see notes) | done | **The riskiest feature — see "Risk" below.** Requires real icon glyphs (`GameItem`/`SettingsItem` have none today), a resize-reactive collapse mechanism, and a new `_apply_minsize()` floor since today's floor assumes the sidebar's full expanded width. Sequenced third so it collapses/expands a rail whose *content* (tabs, value-column rows) is already in its final shape, rather than being redone twice. |
| 4 | Content fills available vertical space; no large dead band below the last card | #2 | done | Sequenced after the tab bar because splitting Hotkey/Clicking/Settings into shorter panes changes how much dead space there actually is to close — fixing this against the old single-column stack would likely need redoing once #2 lands. Exact treatment (vertical centering vs. rhythm/padding that scales with available height vs. something else) is a design-stage call, not decided here. |
| 5 | Flat minimal restyle: drop `CARD_R`/`PILL_R` rounding, single sparingly-used accent, sentence-case section headers with a right-aligned action slot | #1, #2, #3, #4 | pending | Last on purpose — a chrome/theme pass over stable geometry, not geometry that's still being restructured underneath it. Touches `Button`, `Segmented`, `card()`, `section()`, `StatusPill`, `GameItem`, `SettingsItem`, `round_rect()` call sites and `CARD_R`/`PILL_R`. Accent color is Open question 1 — do not decide it inside this feature's own spec. |

Status values: `pending`, `in-progress`, `blocked`, `done`.

## The riskiest part: Feature 3 (icon rail collapse)

`_rebuild_ui()`'s own docstring (`afk_clicker.py:1704-1765`) is explicit that
its coalescing (`_rebuilding`/`_rebuild_wanted`/`_rebuild_after_id`) exists
because a *second* rebuild landing while one is pending, or while one is
already running, has previously caused real crashes (docs/test-review.md's
Round 2 "Defect 1" / "Finding #1", referenced in that docstring). Every
existing trigger for a rebuild today is **discrete**: one Appearance pick,
one UI-scale pick, one settings-page open/close. A live window-resize drag
fires `<Configure>` continuously — potentially dozens of times a second —
and naively calling `_request_rebuild()` (a full destroy-and-rebuild of every
widget under `root`) on every one of those events is exactly the kind of
input this machinery was never exercised against: a resize-driven rebuild
request landing mid-flight of another one is a live path to reproducing that
same crash class through a different door.

Feature 3's spec needs to pick, explicitly, one of:
- **Debounce the collapse check**, not the collapse itself: bind
  `<Configure>` to a cheap width comparison against the threshold, and only
  call `_request_rebuild()` when the collapsed/expanded *state actually
  flips* — not on every pixel of the drag. This keeps the existing
  discrete-trigger contract intact (state changes are still discrete events)
  and needs no change to the coalescing machinery itself.
- **A cheaper in-place toggle** that swaps icon-only vs. icon+label without
  tearing down the whole tree — but this breaks the "everything rebuilds via
  `_rebuild_ui()`" invariant every other rebuild trigger in the file
  currently relies on, and needs its own justification if chosen.

Recommend the first (debounce-on-threshold-crossing) as the default going
into that feature's spec, since it reuses proven machinery rather than
introducing a second rebuild path — but this is a real implementation
decision for that feature's own spec/design stage, not settled here.

Also on Feature 3: today's `_apply_minsize()` floor
(`(SIDEBAR_W + 1 + CONTENT_W) * s`) assumes the sidebar is always at its
full expanded width. If the rail can now collapse, the window's actual
achievable minimum width should shrink to reflect that (collapsed-rail-width
+ a redefined minimum content width) — leaving the floor untouched would
mean the collapse threshold could never be reached in practice, since
`root.minsize()` is a hard floor the window can never be dragged below.
This rederivation belongs in Feature 3, not left as a stray leftover of the
pre-responsive design.

## Test impact

Baseline: 240 tests, `OK (skipped=5)` under
`DISPLAY=:99 .../venv/bin/python -m unittest discover -s tests -t .`
(one pre-existing flake, `Tcl_AsyncDelete`/exit 134 at shutdown with no
summary, roughly 1 run in 4 — re-run, don't chase it).

`tests/test_ui.py`'s `WindowResize` class (`tests/test_ui.py:739-761`) is the
concentration point:

- `test_both_axes_are_resizable` (741) — untouched, stays true regardless of
  any feature here.
- `test_minsize_matches_todays_default_size` (743-746) — its hardcoded
  formula (`SIDEBAR_W + 1 + CONTENT_W`) must be updated once Feature 3
  rederives the floor for a collapsible rail. Legitimate: the *quantity*
  being asserted (today's minimum supported size) is genuinely changing by
  design, not being loosened to dodge a failure — the new expected value
  should be derived from Feature 3's own spec'd minimum, not backed into
  from whatever the code happens to produce.
- `test_growing_the_window_expands_content_not_the_sidebar` (748-754) —
  **must change**, and is the one test that most directly encodes the old
  "sidebar is always rigid" assumption this whole story exists to break
  (`self.assertEqual(self.ui.side.winfo_width(), side_before)`). Replace with
  tests for the actual new invariant: the rail stays at its expanded width
  above the collapse threshold (so growing an already-wide window doesn't
  need to grow the rail further — see Open question 4) and shrinks to
  icon-only width below it. Do not just delete the assertion; the new
  behavior needs its own explicit coverage or a real regression (rail
  growing/shrinking when it shouldn't) goes unnoticed.
- `test_shrinking_below_minsize_is_clamped` (756-761) — should keep passing
  unchanged; it only checks the WM-level clamp, not any specific width.
- `test_card_inner_w_has_no_border_allowance_left` (891-896,
  `tests/test_ui.py`) — asserts `CARD_INNER_W == CONTENT_W - 2*CONTENT_PAD -
  2*CARD_R`. Once Feature 5 removes rounded-corner chrome, the `2*CARD_R`
  border allowance may no longer apply to a flat panel at all — the formula
  (and possibly `CARD_INNER_W`'s own definition) needs to be re-derived from
  the new flat-panel geometry Feature 5 actually ships, not just edited to
  whatever passes.

No other test file (`test_hotkey.py`, `test_chords_slow.py`,
`test_updater.py`) references any layout constant, so this story's blast
radius on the existing suite is contained to `test_ui.py`.

## Non-goals for this story
- No new domain content is added just because the reference shows it: no
  GPU-style stat tiles, no sliders replacing `NumBox`'s typed-entry fields
  (ms-precision interval tuning is the right control for this app; a slider
  is not), no new boolean toggle-switch widget (every existing multi-choice
  control here is genuinely 2-3-way, i.e. `Segmented`, not boolean — only
  its chrome flattens in Feature 5). Only the reference's *layout and chrome
  patterns* are adopted, not its literal widget inventory.
- The Macros tab (#15, GitHub #15 mirror) is not implemented here. Feature 2's
  tab bar should not preclude a future third tab, but building Macros is
  blocked on the settings-schema-version work in `docs/ROADMAP.md` and is
  out of scope for this story.
- The macOS `_dpi_s` ≈ 0.75 / 90%-UI-scale label-size bug (#23) is not
  addressed here. This story's breakpoints are window-width-driven; none of
  the five features touch `_dpi_s` or `UI_SCALE_FACTORS`, so #23 is neither
  fixed nor worsened by this work — it stays a separate, already-open ticket.
- No change to hotkey recording/matching, the click worker, update
  integrity/download logic, or theme *detection* (the actual light/dark
  palette values in `THEMES`) — only how existing controls are arranged and
  drawn.
- Settings-schema versioning (a separate `docs/ROADMAP.md` "before 1.0" item)
  is not touched by this story.

## End-to-end acceptance criteria (whole story, not any single feature)
- [ ] Given the window at 1200x820 (the size named as broken in the ticket),
      when viewing any game page or Settings, then row controls sit in a
      bounded value column near their label, not pinned to the far right
      edge of a much-wider card.
- [ ] Given the window resized to and below the rail's collapse threshold,
      when the rail is icon-only, then every rail item (each game plus
      Settings) still navigates correctly on click — the collapse is purely
      visual, never functional.
- [ ] Given the window resized to and above the rail's collapse threshold,
      when the window grows further, then the rail's width does not keep
      growing indefinitely (see Open question 4 for the exact contract).
- [ ] Given a game page, when the window is any supported size, then the
      `Hotkey`/`Clicking` tab bar is visible under the title and switching
      tabs shows only that tab's content.
- [ ] Given Settings, when switching between `Appearance`/`Updates` tabs,
      then in-progress update state (idle/checking/an offer/downloading/an
      error) survives the switch exactly as `_settings_open`'s existing
      replay logic already preserves it across a full rebuild today.
- [ ] Given the default (minsize) window, when comparing before and after
      this story, then the dead band below the last visible card is
      materially smaller — not merely relocated by shortening one page while
      leaving another just as empty.
- [ ] Given the finished shell, when compared against the NVIDIA reference
      screenshots, then rounded cards/pills are gone, section headers are
      sentence-case with a right-aligned action slot, and a single accent is
      used only for the rail's active item, the tab bar's active underline,
      and the app's existing OK/status usages.
- [ ] Given the full test suite after all five features land, when run under
      Xvfb (`DISPLAY=:99 .../venv/bin/python -m unittest discover -s tests -t
      .`), then it passes green, accounting for the specific `test_ui.py`
      revisions called out under "Test impact" above (not a net loss of
      coverage — replaced assertions must cover the new invariant, not just
      disappear).

## End-to-end test results
Filled in after all five features are individually done — see
`workflows/story.md` step 4.

## Decisions (owner, 2026-09-11)

All four open questions from the breakdown are answered. Downstream stages
should treat these as settled, not re-litigate them.

1. **Accent stays as it is** — `ACCENT = "#e08a55"` dark / `"#2b58cc"` light
   (`afk_clicker.py:78-80`). The reference's green is NVIDIA's brand, not a
   property of the minimal style; borrowing the layout language while keeping
   the app's own identity is the explicit intent. Feature 5 adopts the
   reference's *sparing accent discipline* (active rail item, active tab
   underline, selection) without adopting its hue. Note the accent is **not**
   red — the red in the screenshots is `BAD = "#f06262"`, the OFF-state pill,
   a different token and out of scope.
2. **Eating nests inside the `Clicking` tab** as a sub-section, confirming the
   breakdown's assumption. A game page has exactly two tabs, `Hotkey |
   Clicking`. Eating stays conditionally shown (Minecraft-only,
   `afk_clicker.py:1842-1852`) — nesting it does not make it unconditional,
   and a Clicking pane with no Eating section must still look deliberate.
3. **The rail is pinned; it only collapses.** One expanded width and one
   collapsed width, switching at a threshold. It does not grow on wide
   windows — extra width goes to content. Matches both reference screenshots.
4. **The minimum window should get genuinely small** — roughly the collapsed
   rail plus a usable content column. The point of a collapsing rail is that
   the window can be parked narrow beside a game. Feature 3's own spec still
   proposes a *specific* floor for sign-off, derived from the narrowest row
   that must not clip at the smallest UI-scale step (and see #23: macOS
   `_dpi_s` ~0.75 makes that step smaller than it looks) — "genuinely small"
   is the direction, not a licence to pick a number ad hoc.

## Status
Breakdown signed off by the owner, with the four decisions above. Feature 1 of
5 (Row value-column alignment) is cleared to begin its own product-manager
pass.
