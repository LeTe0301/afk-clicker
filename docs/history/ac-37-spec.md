# Spec: Pane content sits directly under its tab bar (G#37 / GH#66)

## Summary
Flip `FILL_TOP_SHARE` (`afk_clicker.py:221`) from `0.5` (vertical centering,
story #24 feature 4) to `0.0`, so every tab pane's card stack hugs its own
tab bar and all of the pane's leftover vertical space collects below the
last card instead of being split evenly above and below it — reusing the
exact, five-rounds-hardened `_fill_pane()`/`_request_pane_fill()` mechanism
unchanged, with no new widgets, call sites, or platform-specific logic.

## Goals
- Every pane whose content is shorter than the window (Hotkey's Record/Apply
  card, the Clicking tab's cards, Settings → Appearance's card, Settings →
  Updates' card) starts immediately below its own tab bar, with only a
  small, fixed floor-level gap (governed by the existing `max(1, ...)`
  spacer floor, not a new constant) — not a large, height-dependent band
  above it.
- Identical treatment on every pane, every UI-scale step (90/100/115/130%),
  and both rail states (expanded sidebar and the collapsed icon rail) — the
  mechanism already guarantees this today (see "Why this is provably
  cross-cutting-safe" below) and this change does not alter that guarantee.
- `WINDOW_MIN_H` (`afk_clicker.py:163`, `= 620`) and the floor invariant it
  protects ("the tallest pane, Clicking+Eating on Minecraft, is never
  clipped") continue to hold, unchanged, at the exact same margin as today.
- Zero change to any widget's construction, value, persisted state, the
  `_request_pane_fill`/`_run_pane_fill` coalescing machinery, `card()`'s
  `on_settle` hook, or the spacer recovery/clamp logic added across G#28's
  five review rounds.

## Non-goals
- **G#38 / GH#67 (UI scale following window size)** — separate ticket, not
  touched here. This spec's change is scale-*independent* by construction
  (see below), so it neither depends on nor blocks that work.
- **The Macros tab (G#13 / GH#15), still on its own unmerged, unrebased
  branch** — backlog.md already flags that branch builds its own settings
  pane on top of the same centered-pane mechanism this spec changes, so it
  will need the identical `FILL_TOP_SHARE` treatment when it's rebased.
  Not actioned here; flagged for whoever rebases that branch next.
- **No restyle.** `CARD_R`, `PILL_R`, `card()`'s own shape, colors, and
  every other Feature-5-owned chrome decision are untouched. This is a
  single-constant layout change, not a visual refresh.
- **No change to `WINDOW_MIN_H`, `_apply_minsize()`, `SIDEBAR_RAIL_W`,
  `RAIL_COLLAPSE_THRESHOLD`, or any width-axis constant.** Verified below
  that the height floor's own invariant is provably unaffected by which
  value `FILL_TOP_SHARE` holds.
- **No new persisted state, no new widgets, no new constant beyond the
  existing `FILL_TOP_SHARE`.** See "Why not remove the top spacer instead"
  for why a mechanism-level rewrite (deleting the top spacer outright) is
  deliberately rejected in favor of the one-line constant flip.

## Background / current state

**Today's mechanism** (story #24 feature 4, hardened over five review
rounds by G#28/GH#48 — read `docs/history/ac-24-f4-{spec,design,implementation}.md`
and `docs/history/ac-28-{spec,implementation}.md` before touching any of
this): each of the four tab panes (`hotkey_pane`, `clicking_pane`,
`appearance_pane`, `updates_pane`, built in `_build_content()`/
`_build_settings()`, `afk_clicker.py:2425-2500` and the equivalent
Settings-page block ~`:2540-2640`) is wrapped in a top spacer `Frame` and a
bottom spacer `Frame`, stored as `self._pane_fills[key] = (pane, top,
bottom)`. `_fill_pane(pane, top_spacer, bottom_spacer)` (`afk_clicker.py:1571`)
measures the pane's real leftover height (`extra = max(0, available -
natural)`) and splits it `FILL_TOP_SHARE`/`1 - FILL_TOP_SHARE` between the
two spacers, each floored at 1px (Tk silently ignores a literal
`height=0`) and clamped so their sum never exceeds `extra` (the G#28 round-4
fix for a Windows-only packer bug where an over-floored pair got permanently
unmapped). `FILL_TOP_SHARE = 0.5` (`afk_clicker.py:221-225`) is the only
thing that currently makes this read as centering rather than top-alignment
— it is a pure fraction, applied identically regardless of scale, rail
state, or which pane it's computed for.

**The ticket.** Leo's 2026-09-13 feedback on 0.5.0 screenshots (maximised
Windows): the Hotkey Record/Apply card, the Clicking cards, and Settings →
Appearance all float mid-page with a large empty band above them. This is
centering doing exactly what story #24 feature 4 designed it to do — see
`docs/history/ac-24-f4-design.md`'s own "Key design decision: FILL_TOP_SHARE
= 0.5" section, which explicitly chose centering to *halve* the largest
dead band, not eliminate it, and flagged the residual 44%-of-pane empty
band as a known, accepted limitation at the time. This ticket reverses that
call: Leo wants content to start at the top, with the (now larger, single)
dead band pushed below the last card instead of split around it.

**Why this is provably cross-cutting-safe.** `_fill_pane()` is called from
exactly the same four places regardless of `FILL_TOP_SHARE`'s value — each
pane's own `<Configure>` binding, `_set_content_tab()`/`_set_settings_tab()`'s
tail, and `_select()`'s guarded Eating-toggle call, all routed through
`_request_pane_fill()`'s coalescing (`afk_clicker.py:2713-2760`) — and none
of those call sites, nor the coalescing logic itself, reads or branches on
`FILL_TOP_SHARE`. The split happens in exactly two lines
(`afk_clicker.py:1636-1637`); everything before and after those lines
(`update_idletasks()`/`winfo_exists()` guards, the span-based `natural`
measurement, the `max(1, ...)` floor, the overflow clamp, `_set_spacer_height()`'s
re-`.pack()` recovery) is untouched by this change and applies identically
to any split ratio.

**Why the floor invariant (`WINDOW_MIN_H`) is provably unaffected.** Worked
through the arithmetic at the two floor-relevant values of `extra`:
- `extra = 0`: `top_h = int(0 * share) = 0` for *any* `share`, floored to
  `1`; `bottom_h = 0`, also floored to `1`; sum `2` exceeds `extra` by `2`,
  and the overflow loop trims down to `top_h=1, bottom_h=0` — independent
  of `share`.
- `extra = 1`: `top_h = int(1 * share)` is `0` for any `share < 1`
  (including both `0.5` and `0.0`), so the same trim path produces the same
  `top_h=1, bottom_h=0` regardless of `share`.

Both are exactly the values `WINDOW_MIN_H = 620` was tuned around (G#28
round 4's own derivation leaves the tallest pane, Clicking+Eating on
Minecraft, with `extra` in this same 0-1px range at the floor on the
tightest platform measured, Windows CI). Since the split ratio never enters
the computation at these two boundary values, `FILL_TOP_SHARE`'s value has
**zero effect** on whether the floor clips — the invariant this ticket must
preserve (`natural <= pane.winfo_height()`, asserted by every
`WindowMinimumHeight` test) is governed entirely by `WINDOW_MIN_H` and the
platform's own font metrics, neither of which this spec touches. This is a
worked proof, not an assumption — the reviewer should still re-derive it
against the live app per this project's own "verify against the live
system" discipline, but it is not an open risk this spec is leaving
unaddressed.

## Proposed approach

### The one substantive change
`afk_clicker.py:221`: `FILL_TOP_SHARE = 0.5` → `FILL_TOP_SHARE = 0.0`.
Update the constant's own comment (currently "0.5 (centering) minimizes the
largest single dead band — see docs/design.md's 'Key design decision'...")
to state the new rationale and supersede the story #24 framing: content now
hugs the top of its pane (the top spacer only ever sits at its unavoidable
1px `max(1, ...)` floor — see "Residual: the top spacer becomes
structurally inert" below), and all of a pane's leftover space collects in
the bottom spacer instead. Cite this ticket (G#37/GH#66) alongside the
story #24/G#28 history already there, matching this file's own established
comment convention (e.g. `WINDOW_MIN_H`'s comment at `:163-188` layering
G#28's own re-derivation on top of #14's original tuning).

No other line in `_fill_pane()`, `_set_spacer_height()`,
`_request_pane_fill()`, `_run_pane_fill()`, `card()`, `_on_eat_card_settled()`,
`_select()`, `_set_content_tab()`, `_set_settings_tab()`, `_build_content()`,
or `_build_settings()` changes. Every spacer `Frame`, every `<Configure>`
binding, every guard, and every stored `self._pane_fills[...]` tuple is
already generic over the split ratio.

### Why not remove the top spacer instead
Considered and rejected. Once `FILL_TOP_SHARE = 0.0`, the top spacer's
height is provably a hard-coded `1` in every reachable state (worked
through above for `extra ∈ {0, 1}`; for `extra >= 2`,
`top_h = int(extra * 0) = 0` floored to `1`, and the overflow clamp trims
the *bottom* spacer back down, never the top, since the clamp always
prefers shrinking whichever spacer is currently larger — see
`afk_clicker.py:1651-1658`'s `bottom_h >= top_h` check). That makes the top
spacer genuinely inert, not merely "less important" — a real case for
deleting it under "don't leave dead machinery that only existed for
centering."

Deleting it anyway was rejected for a concrete reason, not aesthetics: the
two-spacer shape (`self._pane_fills[key] = (pane, top, bottom)`) is threaded
through `_fill_pane()`'s signature, the overflow-clamp arithmetic, the
`_set_spacer_height()` recovery path, all four pane-construction call sites
in `_build_content()`/`_build_settings()`, and roughly fifteen call sites in
`tests/test_ui.py` (`VerticalFill`, `WindowMinimumHeight`, and
`FillPaneOverflow`) that unpack the same three-tuple. That shape, and the
overflow arithmetic built around *two* floored spacers colliding, is
exactly what took five separate review rounds (G#28/GH#48, documented in
`docs/history/ac-28-implementation.md`) to get right across three
platforms, including one Windows-only packer bug that silently unmapped a
spacer forever. Reworking it to a single-spacer shape now would re-open
that entire surface for re-verification (a new CI round-trip per platform)
to remove code that, while inert, is provably harmless — it always writes
the same constant `1`, never wrong, never clipping, never unmapped-and-stuck
(the floor/clamp/recovery logic that protects it is unconditional, not
`FILL_TOP_SHARE`-dependent). This is squarely the shared-conventions case
for "never rename or re-scope pre-existing code as part of a feature" —
minimal diff wins over a structurally-cleaner rewrite of already-hardened,
cross-platform-verified code. Flagged under "Open questions" below as a
legitimate, low-priority follow-up if Leo wants the dead spacer gone later,
decoupled from this ticket's own risk profile.

### Residual: the top spacer becomes structurally inert
Worth stating plainly rather than leaving implicit: after this change, the
top spacer's height is always exactly `1`px, on every pane, at every window
size, at every UI-scale step. It still exists, still gets measured/excluded
from `natural` correctly, and still costs nothing — but it no longer does
the job its name implies. This is the direct, provable consequence of
`FILL_TOP_SHARE = 0.0`, not a defect to fix in this cycle (see above for
why removal is out of scope here).

## Affected areas
- `afk_clicker.py`: one constant value + its comment (`:221-225`). No other
  production-code line changes.
- `tests/test_ui.py`: assertion-level changes only, in the existing
  `VerticalFill` class (`:1186-1409`) — see "Test impact" below. No changes
  to `WindowMinimumHeight` (`:925-1023`) or `FillPaneOverflow` (`:1413-1465`)
  — both are provably split-ratio-independent (verified line-by-line: the
  former only ever asserts `natural <= winfo_height()` / spacer-mapped
  state, the latter drives `_fill_pane()` directly against a synthetic
  pane/spacer harness that never reads `FILL_TOP_SHARE`).
- No data model, schema, `Store`, or `settings.json` change.
- No design/UX pass for widget bodies (nothing inside a card changes) — see
  "Routing" below for the narrow ux-designer question this *does* still
  raise.

## Test impact, argued per case

**No change needed (split-ratio-independent, verified above and by direct
reading):**
- `test_top_and_bottom_spacers_sum_to_the_real_leftover_space` (`:1208`) —
  pure sum invariant.
- `test_live_resize_drag_updates_margin_without_a_rebuild` (`:1370`) — same
  sum invariant, plus the zero-rebuild-calls assertion; neither depends on
  the split.
- `test_floor_case_still_splits_symmetrically_with_no_clipping` and its
  `..._reverse_order` sibling (`:1225`, `:1270`) — assert
  `top + bottom == max(2, extra)` and `abs(top - bottom) <= 1`. Both hold
  identically under `FILL_TOP_SHARE = 0.0`, because at the floor's `extra`
  range (`0` or `1`) the split ratio never enters the computation (worked
  above). **Optional, non-blocking cleanup**: rename both to drop
  "symmetrically" (e.g. `test_floor_case_still_fits_with_no_clipping...`),
  since "symmetric" no longer describes the general-case treatment, even
  though it happens to still be numerically true at this specific boundary
  — a documentation nit, not a required change.
- Every `WindowMinimumHeight` test (`:925-1023`) — none reads
  `FILL_TOP_SHARE` or asserts a specific split; all assert `natural <=
  pane.winfo_height()` and/or that both spacers stay mapped.
- `FillPaneOverflow.test_a_spacer_pack_already_gave_up_on_is_recovered_once_room_exists`
  (`:1448`) — drives `app._fill_pane()` against its own synthetic
  pane/spacer harness; re-derived by hand for `extra=168` under
  `FILL_TOP_SHARE=0.0` (`top=1, bottom=167` after the clamp) — the
  assertion (`bottom` mapped, `winfo_height() > 0`) holds unchanged.

**Must change (the test's own point depends on which spacer moves):**
- `test_short_tab_gains_margin_on_a_tall_window` (`:1200`) — today asserts
  `top.winfo_height() > 0` as "proof the dead band is being consumed."
  Under `FILL_TOP_SHARE=0.0` that assertion still technically passes
  (`top` is always `1`, and `1 > 0`), but it stops testing the right thing
  — the real proof now lives in the bottom spacer. Rewrite to assert
  `top.winfo_height() <= 1` (content hugs the tab bar) **and**
  `bottom.winfo_height()` is materially large — reuse the same
  natural/extra span measurement `test_top_and_bottom_spacers_sum_to_the_real_leftover_space`
  already uses on this pane, and assert `bottom.winfo_height() >= extra - 1`
  (true-by-construction, matching this project's own "no fixed pixel
  constants" discipline), rather than an arbitrary threshold.
- `test_switching_tabs_recomputes_each_panes_own_margin` (`:1297`) —
  currently compares `hotkey_top` vs. `clicking_top`. Under
  `FILL_TOP_SHARE=0.0` both are pinned to `1` regardless of content height,
  so `assertGreater(hotkey_margin, clicking_margin)` would fail (both
  equal). Swap both reads to the **bottom** spacer
  (`self.ui._pane_fills["hotkey"][2]` /
  `self.ui._pane_fills["clicking"][2]`) — the assertion direction is
  unchanged (Hotkey's own leftover is still bigger than Clicking's, so its
  bottom margin is still bigger), only which spacer is read changes.
- `test_toggling_eating_recomputes_the_clicking_panes_margin` (`:1310`) —
  same swap, top→bottom, same direction (`without_eating > with_eating`).
- `test_hidden_tabs_own_margin_does_not_desync_the_visible_one` (`:1327`) —
  **needs a full rewrite of its technique, not just a top/bottom swap.**
  Its whole method infers whether the `self._content_tab == "clicking"`
  guard in `_select()` (`afk_clicker.py:2925`, called from inside
  `_on_eat_card_settled`) fired, by watching whether a spacer's height
  changed while the pane was hidden. Under `FILL_TOP_SHARE=0.0` this
  breaks structurally either way: the top spacer is pinned to `1`
  regardless of the guard (so `assertEqual`/`assertNotEqual` against a
  seeded top value can never discriminate guard-present from
  guard-removed), and the bottom spacer is already known (per this
  ticket's own history, `docs/history/ac-24-f4-implementation.md`'s "Round
  2" section) to move for an *unrelated* reason — `_select()`'s
  `eat_section.pack(before=clicking_bottom)` re-pack, which runs whether or
  not the fill guard fires — so it was never a safe signal either, even
  under the old split.

  **Concrete replacement technique** (front-loaded so the developer
  doesn't have to re-derive it): spy directly on `self.ui._request_pane_fill`
  instead of inferring from geometry — this tests the guard's own actual
  condition, is immune to `FILL_TOP_SHARE`'s value entirely, and is a
  strictly more direct assertion than the geometry-inference technique it
  replaces:
  ```python
  calls = []
  original = self.ui._request_pane_fill
  self.ui._request_pane_fill = lambda key: (calls.append(key), original(key))[1]
  self.ui._set_content_tab("hotkey")
  self.root.update()
  calls.clear()
  self.ui._select("minecraft")   # toggles Eating on the hidden Clicking pane
  self.root.update()
  self.assertNotIn("clicking", calls)   # guard suppressed the request entirely
  self.ui._set_content_tab("clicking")
  self.root.update()
  self.assertIn("clicking", calls)      # and it isn't stuck stale forever
  ```
  Keep the existing `assertFalse(self.ui._pane_fills["clicking"][0].winfo_ismapped())`
  check after switching to Hotkey (still valid, unrelated to the split) as
  the precondition proving the pane really is hidden when `_select()` is
  called.

## Edge cases
- **A pane at exactly its natural height (the tallest pane, at the window's
  floor)**: unaffected — worked above, `FILL_TOP_SHARE` never enters the
  computation at `extra ∈ {0, 1}`. Same `(top=1, bottom=0)` result as
  today's `0.5` split.
- **Every UI-scale step (90/100/115/130%)**: `FILL_TOP_SHARE` is applied to
  `extra`, which is already computed from scaled `available`/`natural` —
  the ratio itself carries no scale dependency, so behavior is identical at
  every step. No special-casing needed; verify by screenshotting at least
  one non-default step (see "Visual verification plan").
- **Collapsed icon rail**: orthogonal — the rail only affects sidebar
  width (`SIDEBAR_RAIL_W`) and triggers `_rebuild_ui()` on a width-only
  threshold crossing; it never touches `_fill_pane()`, `_pane_fills`, or
  any pane's own height. No interaction either way.
- **A live resize drag**: unaffected — `_request_pane_fill()`'s coalescing
  and `_fill_pane()`'s own idempotence are both untouched.
- **The hidden-pane staleness case** (a resize or Eating-toggle while a
  pane isn't the active tab): unaffected — the guard and the tab-switch
  recompute are both untouched; see the rewritten test above for the one
  place this needed a new verification technique, not a behavior change.

## Acceptance criteria
- [ ] Given the Hotkey tab active on a window well above `WINDOW_MIN_H`,
      when comparing the pane's own top and bottom spacer heights, then the
      top spacer is at its `1px` floor and the bottom spacer holds
      (approximately) all of the pane's real leftover space — content
      visibly starts immediately below the tab bar, not mid-page.
- [ ] Given the same tall window, when checking Clicking, Settings →
      Appearance, and Settings → Updates in turn, then each shows the same
      top-hugging treatment — the constant is pane-agnostic by construction,
      verify it holds visually on all four, not just Hotkey.
- [ ] Given the default (floor) window size, when measuring the tallest
      pane's real content span (`natural`) against its own `winfo_height()`,
      then `natural <= winfo_height()` still holds, and both spacers stay
      mapped — the floor invariant this ticket must not regress (see "Why
      the floor invariant is provably unaffected" for the worked proof;
      still to be independently re-confirmed against the live app, not
      trusted from this document alone).
- [ ] Given a live window resize, when dragging through several heights,
      then spacer heights update continuously and `_rebuild_ui()` is never
      called for this feature's own trigger (unchanged invariant, already
      covered by an existing, unmodified test).
- [ ] Given the full suite (`DISPLAY=:99 <venv>/bin/python -m unittest
      discover -s tests -t .`) after this change, then it passes at the
      current baseline test count with exactly the `VerticalFill`
      assertion changes described in "Test impact" applied, and zero other
      tests modified.
- [ ] Given screenshots taken under Xvfb (`import -window <id>`, matching
      the technique already established in `docs/history/ac-28-implementation.md`'s
      rounds 2/4/5 — throwaway scripts in the scratchpad, never committed)
      at both the default/minimum window size and a tall window, for every
      one of the four panes, then each visibly shows content hugging its
      tab bar with the empty band entirely below the last card.

## Open questions
- **Whether `FILL_TOP_SHARE` should be exactly `0.0` (content flush against
  the 1px floor) or a small non-zero share (e.g. `0.02-0.05`) for a touch
  of deliberate breathing room between the tab bar and the first card**,
  consistent across all four panes. Proceeding under `0.0` as this spec's
  concrete, ready-to-build default — it directly matches Leo's own wording
  ("start right below the tab it belongs to") and is the simplest possible
  value — but this is a real, if small, visual-treatment call the
  ux-designer should confirm or override in a short design note (see
  "Routing" below) before the developer builds against a specific number,
  the same way the original story #24 feature 4 spec left the *treatment*
  (not the mechanism) open for its own ux-designer pass.
- **Whether to remove the now-structurally-inert top spacer as a follow-up
  cleanup.** Not actioned here (see "Why not remove the top spacer
  instead"). If Leo wants it gone, that's a separate, small, low-urgency
  ticket, deliberately decoupled from this one's minimal-diff/low-risk
  profile.
- **G#13's Macros branch** will need the identical `FILL_TOP_SHARE` change
  applied on rebase — noted for whoever picks that branch up next, not
  actioned here (it doesn't exist on `main` today).

## Risk / rollback notes
- Smallest possible surface: one constant value, one comment, and
  assertion-only changes in one existing test class. No new widget, no new
  call site, no new persisted state, no touch to any of G#28's five rounds
  of cross-platform hardening logic.
- Revert is: `FILL_TOP_SHARE = 0.0` → `0.5` (or whatever `main` currently
  holds), plus reverting the `VerticalFill` assertion changes back to their
  current form. Single-line, single-concern, trivially bisectable.
- The one invariant most worth a reviewer independently re-deriving against
  the live app, not trusting from this document: that the floor case really
  is unaffected by the split ratio (worked through above for `extra ∈ {0,
  1}`) — re-run `WindowMinimumHeight`'s three tests and, ideally, the same
  live-app screenshot technique `docs/history/ac-28-implementation.md`'s
  round 4/5 used, on Windows CI specifically, since that is the platform
  every prior round of this exact mechanism found the tightest margin on.

## Routing
**Feature / design change — `workflows/feature.md`.** This is a deliberate
reversal of a prior, explicitly-chosen visual treatment (story #24 feature
4's centering), not a bug in the mechanism — the mechanism worked exactly
as designed and hardened; only the desired *outcome* has changed.

**ux-designer needed, narrowly scoped.** Nothing about card bodies, colors,
or any widget's construction changes, so this does not need a full mockup
pass — but the "Open questions" section above leaves one real, visible
decision (`FILL_TOP_SHARE = 0.0` flush vs. a small fixed breathing-room
share) that a full pipeline convention says should not be silently decided
by product-manager. Recommend a short design note confirming: (1) the exact
share value, (2) that the same value applies uniformly to all four panes
(the mechanism already guarantees this — the design note only needs to
confirm it's the *desired* outcome, not re-derive it), and (3) no visible
divider or chrome is wanted in the space between the tab bar and the first
card (matching this spec's own "no restyle" non-goal). This should be a
quick pass, not a redesign.
