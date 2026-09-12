# Spec: Content fills the available vertical space (story #24, Feature 4 of 5)

## Summary
Each of the four tab panes (`hotkey_pane`, `clicking_pane`, `appearance_pane`,
`updates_pane`, all from Feature 2) gets a live-measured top/bottom margin
around its own card stack, sized from the actual leftover vertical space in
that pane — so a short tab (Hotkey, Appearance, Updates: one card each) no
longer leaves a large dead band below its last card while a tall tab
(Clicking, with Eating on Minecraft) is left untouched, without introducing
scrolling, touching `_apply_minsize()`'s floor, or routing through
`_request_rebuild()`/`_rebuild_ui()` at all.

## Goals
- Each pane's card stack "fills" its own available height by absorbing the
  leftover space into a top spacer and a bottom spacer that bracket the
  stack — mechanism only; the exact top:bottom split is the ux-designer's
  call (see "The treatment is not decided here").
- Works independently per pane, not per page: Hotkey/Clicking are measured
  and filled separately, as are Appearance/Updates — a short tab and a tall
  tab on the same page each get the fill amount their *own* content needs,
  not a page-wide average.
- Reacts correctly to every way a pane's own available/natural height can
  change post-launch: a live window resize, switching to/from that tab, and
  (Clicking only) a game switch that shows/hides the Eating card.
- Zero new persisted state, zero change to `_apply_minsize()`,
  `_request_rebuild()`, `_rebuild_ui()`, `_on_root_resize()`, or any
  existing widget's value/behavior.

## Non-goals
- **No scrolling.** Grep-confirmed: nothing in `afk_clicker.py` today
  references `Scrollbar`, `yscroll`, `MouseWheel`, or `scrollregion` — the
  app has never had a scroll mechanism on any page. This feature does not
  add one. See "What happens when content doesn't fit" below for the exact,
  narrow contract this implies.
- **No redistribution of space *between* individual cards/sections** (e.g.,
  growing the gap between Clicking's card and Eating's card specifically
  when Eating is present). The mechanism here only ever adds margin at the
  two ends of a pane's stack — before its first `section()`/`card()` call
  and after its last. Of the story's two named candidate treatments, a
  50:50 top:bottom split reads as **vertical centering**; a small,
  fixed-fraction top share (or a top share that grows with available
  height) reads as **breathing room that scales with height** — both are
  reachable by choosing the split ratio this spec's mechanism exposes,
  without a second, more invasive mechanism that touches every
  `section()`/`card()` call site's own `pady`. If the ux-designer's chosen
  treatment genuinely needs inter-card rhythm to scale independently of a
  boundary margin, that is a bigger change and belongs in its own follow-up,
  not folded into this one silently.
- **No change to `_apply_minsize()`'s floor** (`SIDEBAR_RAIL_W`/`CONTENT_W`
  math, `minh = 690 * s`, `afk_clicker.py:1766`) — Feature 3's territory.
  `minh` was already tuned to fit the tallest pane (Clicking+Eating on a
  Minecraft profile) without clipping; this feature's own margins are
  additive on top of that, never a substitute for it, and are a no-op
  exactly at the floor (see "extra" below — it clamps to zero, never
  negative).
- **No interaction with `_request_rebuild()`/`_rebuild_ui()`'s coalescing.**
  This feature's resize reaction is a small, cheap, always-safe-to-repeat
  geometry recompute local to one pane — the same *kind* of mechanism
  `card()`'s own `_redraw()` (`afk_clicker.py:1389-1409`) already is, not a
  discrete state-flip trigger like the rail's debounced collapse
  (`_on_root_resize`, `afk_clicker.py:1783-1806`). It never calls
  `_request_rebuild()`, so the entire hazard class Feature 3 was built to
  survive (a second rebuild landing mid-flight of another,
  `_rebuild_ui()`'s own docstring) does not apply to this feature at all —
  there is nothing here for that machinery to coalesce.
- No accent-color or rounded-vs-flat chrome change (Feature 5); `CARD_R`,
  `PILL_R`, `round_rect()`, `card()`'s own body are untouched except for the
  one new spacer widget described below.
- No change to `Row`, `CONTENT_W`, `CARD_INNER_W`, or any row/control
  geometry — Feature 1's territory, untouched.

## Background / current state

**Why there's a dead band today.** `self.content` (`afk_clicker.py:1749`,
`fill="both", expand=True`) and `body` inside it
(`_build_content`/`_build_settings`, `fill="both", expand=True`) both
already receive the *window's* real leftover height — proven, not assumed
(this session's own throwaway Xvfb probes, not committed anywhere; see
below). Feature 2's active tab pane (`hotkey_pane`/`clicking_pane`/
`appearance_pane`/`updates_pane`, each also `fill="both", expand=True`) is
the sole visible child of `body` at any moment and, confirmed empirically,
is handed *all* of body's remaining height regardless of its own children's
size — a pane's own reqheight never constrains it here, because it has no
sibling competing for that space once the inactive pane is hidden via
`pack_forget()`. But every `card()` inside a pane is packed with `fill="x"`
only (`afk_clicker.py:1385`, no `expand`), and `card()` itself sets its own
`shell` height explicitly, from its content, in `_redraw()`
(`h = inner.winfo_reqheight() + 2 * pad`, `afk_clicker.py:1407`) — a card is
always exactly as tall as it needs to be, never taller. So the pane already
*has* the window's full leftover height, but nothing inside it ever claims
any of it: the card stack sits top-anchored (pack's default) and everything
below the last card is simply unclaimed, empty `BG`. This is the dead band
the story names, and it is worst on the shortest tabs (Hotkey: one card;
Appearance/Updates: one card each) precisely because Feature 2 split what
used to be one tall, single-column stack into shorter, per-tab panes.

**What happens when content doesn't fit today (checked, not assumed).**
There is no scrollbar anywhere in this file (confirmed by grep). `minh =
690 * s` (`_apply_minsize()`, `afk_clicker.py:1766`) is the one thing
standing between a tab's natural content height and actual clipping: it was
tuned to admit the tallest real pane (Clicking with Eating showing) without
the window ever being draggable below that. Every dimension that feeds a
pane's natural height (fonts, row heights, `CARD_R`-driven padding) already
scales by the same `s` the floor itself scales by, so the fit that holds at
`s=1` holds at any other `s` by the same invariant-ratio argument
`docs/history/ac-17-f4-spec.md` §1 and this story's own Feature 3 spec
already rely on elsewhere in this file. This feature does not change that
contract in either direction — it only ever consumes genuinely *leftover*
(positive) space; if a future change ever made a pane's natural height
exceed its available height, this feature's own `extra = max(0, available -
natural)` clamp (see below) makes it a silent no-op, and today's pre-existing
(unimproved, but also not worsened) squeeze/clip behavior is exactly what
would show through. Introducing real scrolling to handle that case is out of
scope here (see Non-goals) — it is a materially bigger feature in its own
right.

**Empirical grounding for the mechanism below**, confirmed against this
session's own Xvfb (`DISPLAY=:99`) with small throwaway scripts, not
committed anywhere, because several of these are exactly the platform-shaped
traps this story has already been burned by twice:
1. Binding `<Configure>` on a plain (non-toplevel) `Frame` — unlike
   `root.bind(...)` — does **not** bubble from a descendant's own resize.
   Resizing a child `Frame` packed inside a bound parent `Frame` fired zero
   parent-level `<Configure>` callbacks; only the parent's *own* size
   changing (via `root.geometry(...)`) did. This means, unlike
   `_on_root_resize()` (`afk_clicker.py:1783`), a pane-level `<Configure>`
   binding needs **no** `event.widget is not self` guard — the bindtags
   hazard that guard exists for is specific to binding on the *toplevel*,
   whose tag is embedded in every descendant's own bindtags; an ordinary
   `Frame`'s tag is not.
2. **Toggling a child's `pack()`/`pack_forget()` does not fire a `<Configure>`
   on its parent** when that parent is already the sole `expand=True`
   claimant of its own space (exactly `hotkey_pane`/`clicking_pane`'s
   situation). Concretely: hiding/showing one of two cards inside a
   `fill="both", expand=True` pane changed the sum of the pane's children's
   requested heights from 180 to 100 and back, but produced **zero**
   `<Configure>` events on the pane itself in either direction — the pane's
   own allocated height never changed, only its children's occupancy of it.
   **This is why `_select()`'s Eating-toggle (`afk_clicker.py:2419-2424`)
   needs an explicit recompute call, not just a `<Configure>` binding** —
   nothing Tk-driven will ever fire for that specific case.
3. A pane that is currently hidden (`pack_forget()`'d) and then re-`pack()`ed
   (i.e., a tab switch) **does** receive an immediate, correct `<Configure>`
   carrying the window's *current* size the moment it's shown again — even
   if the window was resized while it was hidden and its own stale
   `winfo_height()` never tracked that resize in the meantime (matching
   Feature 2's own already-documented finding #4). So a tab switch alone,
   via `_set_content_tab()`/`_set_settings_tab()`'s own `.pack()` call, is
   sufficient to re-trigger a correctly-sized recompute with no separate
   "becoming visible" case to special-case.
4. Calling `update_idletasks()` on a pane **before** reading its
   `winfo_height()` reliably resolves real, final geometry even during the
   very first synchronous `_build_ui()` call from `__init__`, before
   `root.mainloop()` (or even a first `root.update()`) has ever run —
   exactly mirroring why `card()`'s own `_redraw()` already calls
   `inner.update_idletasks()` before reading `shell.winfo_width()`
   (`afk_clicker.py:1398-1401`). Without that call first, `winfo_height()`
   at that same pre-map moment returns Tk's placeholder (`1`), not the real
   value — the same class of hazard `card()`'s own `w = shell.winfo_width()
   or (...)` fallback exists for. This feature's own recompute function
   must call `update_idletasks()` first, unconditionally, the same way
   `card()` already does — not add a second, different guard.

## Proposed approach

### 1. One spacer pair per pane, added at the two ends of its own construction

For each of the four panes, wrap the existing section/card construction
with a top spacer and a bottom spacer — both plain `tk.Frame(pane, bg=BG,
height=0)` — added once, at construction, immediately before the pane's
first `section()`/`card()` call and immediately after its last:

```python
FILL_TOP_SHARE = 0.5   # fraction of a pane's own leftover vertical space
                        # given to the top spacer, the rest to the bottom --
                        # 0.5 reads as centering; a smaller/height-scaling
                        # value reads as the "breathing room" candidate.
                        # Proposed starting point ONLY -- same open-to-
                        # the-ux-designer's-tuning status Feature 2's
                        # TAB_HEIGHT/TAB_GAP and Feature 3's SIDEBAR_RAIL_W
                        # had. See "The treatment is not decided here."

def _fill_pane(pane, top_spacer, bottom_spacer):
    """Recompute this pane's own top/bottom margin from its *current* real
    available height vs. its own real content height -- safe to call
    repeatedly, including from a live resize drag (story #24 feature 4).

    Mirrors card()'s own _redraw() (afk_clicker.py:1389-1409) in two ways
    that are load-bearing, not stylistic: update_idletasks() BEFORE reading
    geometry (a pre-map winfo_height() is Tk's `1` placeholder, not the
    real value -- confirmed empirically, see docs/spec.md's "Empirical
    grounding" #4), and the same two winfo_exists() guards, for the same
    reason card()'s docstring gives: update_idletasks() can itself
    reentrantly service an already-queued idle callback (e.g. a pending
    _rebuild_ui()) that destroys this very pane while this call is still on
    the stack.
    """
    if not pane.winfo_exists():
        return
    top_spacer.config(height=0)          # neutralize before measuring, so
    bottom_spacer.config(height=0)       # a previous run's spacer height
                                          # never counts toward "natural"
    pane.update_idletasks()
    if not pane.winfo_exists():
        return
    available = pane.winfo_height()
    natural = sum(c.winfo_reqheight() for c in pane.winfo_children()
                  if c.winfo_ismapped() and c not in (top_spacer, bottom_spacer))
    extra = max(0, available - natural)
    top_spacer.config(height=int(extra * FILL_TOP_SHARE))
    bottom_spacer.config(height=extra - int(extra * FILL_TOP_SHARE))
```

Wiring, per pane (shown for `clicking_pane`; `hotkey_pane`/
`appearance_pane`/`updates_pane` are structurally identical, minus the
Eating-specific call in item 3 below):

```python
self.clicking_pane = tk.Frame(body, bg=BG)
self.clicking_pane.pack(fill="both", expand=True)
top_spacer = tk.Frame(self.clicking_pane, bg=BG, height=0)
top_spacer.pack(fill="x")
cl = card(self.clicking_pane, s)
# ... existing Clicking card body, unchanged ...
self.eat_section = section(self.clicking_pane, "Eating", s)
self.eat_card_inner = card(self.clicking_pane, s)
# ... existing Eating card body, unchanged ...
bottom_spacer = tk.Frame(self.clicking_pane, bg=BG, height=0)
bottom_spacer.pack(fill="x")
self._clicking_fill = (top_spacer, bottom_spacer)   # kept on self so
    # _select()'s Eating-toggle (item 3 below) can call _fill_pane() again
    # without a second lookup mechanism
self.clicking_pane.bind("<Configure>",
    lambda e: _fill_pane(self.clicking_pane, top_spacer, bottom_spacer))
```

Notes on the sketch (developer's job to finalize the exact spacer-storage
shape — e.g. one `self._pane_fills = {"clicking": (...), ...}` dict rather
than four separate `self._X_fill` attributes — this is the mechanism, not
final code, same status Feature 2's `TabBar` sketch had):
- The spacer is a plain `bg=BG` `Frame`, not a new widget class — it carries
  no chrome of its own, matching Feature 2's own "no visual restyle" scope
  (Feature 5 owns chrome).
- `height=0` at construction (not omitted) so the very first, pre-fill
  layout pass has a deterministic, zero-height placeholder rather than an
  unset default — avoids a one-frame flash of an arbitrary Tk default
  height before the first real recompute lands.
- Excluding the two spacers themselves from the `natural` sum (by identity,
  `c not in (top_spacer, bottom_spacer)`) plus resetting both to `height=0`
  before measuring is what makes this idempotent under repeated calls
  (including from a continuous resize drag) without any feedback loop —
  each call always measures the *real* content only, never its own
  previous output.

### 2. Where each pane's `_fill_pane` call is triggered from

Three trigger points, each covering a different way a pane's own
available-vs-natural height can change (see "Empirical grounding" above for
why each one is necessary and why no single trigger covers all three):

- **Live window resize while the pane is visible** — the `pane.bind(
  "<Configure>", ...)` call in the sketch above. Fires continuously during
  a drag, exactly like `card()`'s own `<Configure>`-bound `_redraw()`
  already does, and for the same reason: cheap, idempotent, pure-geometry
  work with no widget teardown, safe to run once per event with no
  debouncing needed (contrast with the rail's collapse, which debounces
  specifically because *its* trigger calls the expensive, teardown-based
  `_request_rebuild()` — this trigger never does).
- **A tab switch** — needs no new call: `_set_content_tab()`/
  `_set_settings_tab()`'s own `.pack(fill="both", expand=True)` call on the
  newly-active pane (`afk_clicker.py:2358-2359`, `2378-2379`) already fires
  a `<Configure>` on that pane carrying its *current*, correct size the
  moment it's shown (Empirical grounding #3) — the existing `<Configure>`
  binding from the point above already catches this for free. Recommended
  anyway: add one explicit `_fill_pane(...)` call at the tail of each
  toggle method regardless, so behavior does not depend on exactly when
  Tk chooses to dispatch a `<Configure>` it generated — belt-and-suspenders
  with the same "bind AND call once directly" shape `card()`'s own
  `_redraw()` already uses (`afk_clicker.py:1414-1417`: bound twice, called
  once explicitly).
- **`_select()`'s Eating-toggle** (`afk_clicker.py:2419-2424`) — the one
  genuinely required explicit call, per Empirical grounding #2: toggling
  `eat_section`/`eat_card`'s own pack state never fires a `<Configure>` on
  `clicking_pane`, so nothing else will ever recompute this case. **Must be
  guarded on `self._content_tab == "clicking"`**: if Clicking isn't the
  currently visible tab, `clicking_pane.winfo_height()` would read a
  hidden pane's stale-but-plausible geometry (the exact unmapped-widget
  hazard class this story has hit before) — skip the call when hidden, and
  rely on the tab-switch trigger above to compute the correct numbers the
  moment the user actually switches to Clicking.

No change to `_rebuild_ui()`, `_apply_appearance()`, `_apply_ui_scale()`,
`_on_root_resize()`, or `_request_rebuild()` — a full rebuild reconstructs
every pane from scratch, and each pane's own tail (`_set_content_tab(...)`/
`_set_settings_tab(...)`, already called once per build today) already
performs the "call once explicitly" step above for free.

## The treatment is not decided here
`FILL_TOP_SHARE = 0.5` (symmetric — vertical centering) is this spec's
proposed starting point, not a mandate. The story names two candidates:
- **Vertical centering** — `FILL_TOP_SHARE = 0.5`, unconditionally.
- **Rhythm/padding that scales with available height** — reachable with
  this same mechanism by making the top share small-and-fixed (content
  still reads as "starting near the top," just with more breathing room
  below than today) or itself a function of `extra` rather than a flat
  fraction. Either is a one-constant (or one-small-function) change inside
  `_fill_pane` — no different mechanism, no different call sites.

Both read correctly against a single-card pane (Hotkey/Appearance/Updates)
and a two-card pane (Clicking-with-Eating) with zero extra logic: the split
is always computed from whatever `extra` actually is for that pane, at that
moment, never from an assumption about how many cards it has.

## Affected areas
- `afk_clicker.py` only:
  - One new constant, `FILL_TOP_SHARE`, placed with `TAB_HEIGHT`/friends
    (`afk_clicker.py:1279` area) or `SIDEBAR_RAIL_W`/friends
    (`:160-161` area) — developer's choice, whichever the file's existing
    grouping convention favors.
  - One new function, `_fill_pane(pane, top_spacer, bottom_spacer)` (or
    equivalent), placed near `card()`/`section()` (`:1371-1409`) since it is
    the same kind of small, reusable layout helper.
  - `_build_content(s)` (`:2057-2149`) and `_build_settings(s)`
    (`:2151-2261`): one top spacer + one bottom spacer added per pane (four
    panes total), each pane's `<Configure>` bound to `_fill_pane`, plus one
    explicit call at each pane's own construction end.
  - `_set_content_tab`/`_set_settings_tab` (`:2333-2379`): one explicit
    `_fill_pane(...)` call added to each, for the newly-active pane, at the
    end of the existing toggle logic.
  - `_select()` (`:2394-2429`): one guarded `_fill_pane(...)` call added
    immediately after the existing Eating `pack()`/`pack_forget()` block
    (`:2419-2424`).
- No data model, schema, or API changes — `Store`/`settings.json`
  untouched; spacer heights are never persisted, recomputed fresh on every
  build/resize/switch exactly like everything else this story has added
  (`self._rail_collapsed`, `self._content_tab`, `self._settings_tab`).
- One test file, `tests/test_ui.py` — see "Test impact" below.

## Edge cases
- **A pane at exactly its natural height** (the tallest tab, at the window's
  minimum size): `extra = max(0, available - natural)` evaluates to (at
  most, off-by-rounding) `0` — both spacers stay `height=0`, a true no-op,
  matching today's look exactly. This is the case `minh = 690 * s` was
  tuned around, and this feature must never make it worse (see Non-goals).
- **A live resize drag**: each `<Configure>` on the visible pane recomputes
  independently and idempotently — no debounce needed (unlike the rail's
  collapse-triggered `_request_rebuild()`), because this work never tears
  down or reconstructs anything, only resizes two already-existing `Frame`s.
- **A resize while a pane is hidden**: no `<Configure>` reaches it (it's
  unmapped), so its spacer heights go stale — corrected the instant the
  user switches to it, per Empirical grounding #3, exactly mirroring how
  Feature 2 already documented the same staleness for a hidden card's own
  width.
- **Switching games while Clicking is hidden** (Hotkey tab active) and the
  new game's Eating visibility differs from the old one's: `clicking_pane`'s
  spacers go stale (still reflecting the old game's card count), but this
  is invisible — the pane isn't shown — and self-corrects on the next
  Clicking-tab switch, per the `self._content_tab == "clicking"` guard in
  §2's third trigger. Never asserts wrong output because it's never read
  while stale.
- **Reentrant teardown mid-`update_idletasks()`**: `_fill_pane`'s two
  `winfo_exists()` guards (before and after the call) exist specifically
  because `update_idletasks()` can reentrantly service an already-queued
  idle callback (e.g. a pending `_rebuild_ui()`) that destroys the very
  pane/spacers `_fill_pane` is mid-computation on — the identical,
  already-proven hazard `card()`'s own `_redraw()` guards against
  (`afk_clicker.py:1392-1401`), not a new one this feature invents.
- **`FILL_TOP_SHARE` applied to a pane with zero cards** — not reachable
  today (every pane always has at least one card: `hk`/`cl`/`ap`/`up`), so
  not specifically handled, but the formula degrades safely regardless
  (`natural` would just be whatever the section labels/title alone request).

## Test impact, argued per case

**Given the recommended defaults**, no existing test reads or asserts a
pane's own height, a card's vertical position, or any spacer — grep-checked
across `tests/test_ui.py`: `WindowResize` and `RailCollapse`
(`tests/test_ui.py:781-880ish`) assert `winfo_width()` exclusively, never
`winfo_height()`, and every `RowValueColumn`/`CardResize` test reads
horizontal geometry (`winfo_x()`, `winfo_width()`). **No existing test needs
to change or is at risk of a hollow-pass from this feature.**

**New tests needed** (a new `VerticalFill(UITestCase)` class):
- `test_short_tab_gains_margin_on_a_tall_window` — resize well above
  `minh` (e.g. `f"{default_w}x{int(1000 * s)}"`, matching the existing
  900x760/1000x900-class precedents already used elsewhere in this file
  for CI display headroom), switch to `Hotkey` (single card, the shortest
  pane), and assert the top spacer's `winfo_height()` is now `> 0` — the
  direct proof the dead band is being consumed, not merely repositioned.
- `test_top_and_bottom_spacers_sum_to_the_real_leftover_space` — on the
  same tall window, assert `top_spacer.winfo_height() +
  bottom_spacer.winfo_height() == pane.winfo_height() -
  <sum of the other children's winfo_reqheight()>`, computed the same way
  `_fill_pane` computes it — an assertion **true by construction**
  (comparing two things measured the same way, per this story's own
  "Lessons that cost a round each" note), not a fixed pixel constant that
  could legitimately differ by platform/DPI/font metrics.
- `test_no_margin_at_the_minimum_window_size` — at default/minimum launch
  geometry (no manual resize), assert both spacers are `height <= 1` (a
  1px rounding allowance, not a hardcoded platform-specific number) for
  whichever pane is tallest at that size (Clicking, Minecraft profile
  selected, Eating showing) — proving the floor case stays a no-op.
- `test_switching_tabs_recomputes_each_panes_own_margin` — on a tall
  window, assert Hotkey's and Clicking's own top-spacer heights differ
  (Clicking's own content is taller, so its leftover — and therefore its
  margin — is smaller) after switching to each in turn — the direct proof
  that fill is computed **per pane**, not per page.
- `test_toggling_eating_recomputes_the_clicking_panes_margin` — with
  Clicking active and a tall window, select a Minecraft profile (Eating
  shows, margin shrinks) then a non-Minecraft profile (Eating hides, margin
  grows) — asserting the top-spacer height increases — the direct
  regression test for Empirical grounding #2 (no `<Configure>` fires for
  this case; only the explicit call in `_select()` does).
- `test_hidden_tabs_own_margin_does_not_desync_the_visible_one` — with
  Hotkey active, switch games to toggle Eating (irrelevant to the visible
  tab); assert Hotkey's own spacer heights are unaffected — proving the
  `self._content_tab == "clicking"` guard actually prevents a
  cross-pane write, not merely that it happens to not crash.
- `test_live_resize_drag_updates_margin_without_a_rebuild` — wrap
  `self.ui._rebuild_ui` to count calls (same spy technique
  `RailCollapse.test_repeated_threshold_crossings_coalesce_to_one_rebuild`,
  `tests/test_ui.py:872-880`, already establishes), resize the window
  several times, and assert **zero** rebuilds occurred while the spacer
  heights did change — the direct proof this feature never touches
  `_request_rebuild()`/`_rebuild_ui()`'s coalescing machinery at all (Non-
  goals).

**No change, argued:**
- Every test in `WindowResize`, `RailCollapse`, `RowValueColumn`,
  `CardResize`, `SettingsNavigation`, `SettingsUpdates`,
  `OverlappingAppearanceChanges` — none reads a pane's own height or a
  card's vertical (`y`) position; all horizontal-geometry and direct-
  Python-call assertions are unaffected by adding two zero-chrome `Frame`s
  that only ever change their own `height`.
- No test in `test_hotkey.py`, `test_chords_slow.py`, or `test_updater.py`
  references any layout constant or pane geometry (grep-confirmed) — this
  feature's blast radius stays contained to `test_ui.py`, matching the
  story's own established pattern for every prior feature.

## Acceptance criteria
- [ ] Given the default (minsize) window, when comparing the tallest visible
      pane's spacers before and after this change, then both are `<= 1px` —
      the floor case is an exact no-op (story's own end-to-end criterion:
      "materially smaller [dead band]... not merely relocated by shortening
      one page while leaving another just as empty" — verified per-pane,
      not just for whichever page happened to be open).
- [ ] Given the window resized well above the minimum, when viewing the
      shortest tab on either page (Hotkey, or Appearance/Updates), then its
      top and/or bottom spacer height is materially greater than zero, and
      the two spacers' combined height equals that pane's own available
      height minus its real content's requested height (an assertion true
      by construction, not a fixed pixel comparison).
- [ ] Given the same tall window, when comparing Hotkey's fill amount to
      Clicking's, then they differ in the direction predicted by their
      actual content height (Clicking's is smaller) — fill is computed per
      pane, not per page.
- [ ] Given Clicking is the active tab, when a game switch toggles Eating's
      visibility, then Clicking's own spacer heights update accordingly with
      no window resize involved — the one case with no natural `<Configure>`
      trigger, covered by an explicit call.
- [ ] Given Hotkey is the active tab, when a game switch toggles Eating's
      visibility on the (hidden) Clicking pane, then Hotkey's own spacer
      heights are unaffected — the visibility guard prevents cross-pane
      writes.
- [ ] Given a live resize drag (several `<Configure>` events before the
      loop next settles), when it completes, then spacer heights reflect
      the final size and `_rebuild_ui` was called zero times for this
      feature's own trigger — proving no interaction with the rail's
      rebuild-coalescing machinery.
- [ ] Given the full suite (`DISPLAY=:99 .../venv/bin/python -m unittest
      discover -s tests -t .`) after this change, then it passes at the
      current 269-test baseline plus this feature's new `VerticalFill`
      tests, with zero existing tests modified (per "Test impact," none are
      expected to need it). The known `Tcl_AsyncDelete` shutdown flake
      (~1 run in 4, exit 134, no summary) is pre-existing — re-run once, do
      not chase it.

## Open questions
- **The exact `FILL_TOP_SHARE` value (or a height-scaling function in its
  place) is the ux-designer's call**, per the story's own explicit framing
  of the treatment as undecided — 0.5 (centering) is this spec's proposed
  starting point purely so the mechanism has a concrete default to build
  and test against; not a recommendation on the visual outcome.
- **Should the spacer read `bg=BG` unconditionally, or match whatever
  `card()`'s own body background is at the pane's outer edge?** Proceeding
  under `bg=BG` (the pane's own background, i.e., invisible chrome, exactly
  like `title`/`game_note`'s own frames) since no visual chrome decision
  belongs in this spec (Feature 5's territory) — flagged in case the
  ux-designer's chosen treatment wants a visible divider or texture in that
  space instead of true empty margin, which would need its own follow-up.
- **Exact test window heights** used above (`1000 * s`-class geometries) are
  proposed, matching this file's own existing precedent for CI-safe display
  headroom (`docs/history/ac-24-story.md`'s "Test impact" already notes
  Xvfb's runners clamp to ~1024x768 on some CI legs) — the developer should
  confirm against whatever the CI runners' actual screen constraints are
  before finalizing exact numbers, the same way every prior feature in this
  story has had to.

## Risk / rollback notes
- Additive and structurally isolated: two new zero-chrome `Frame`s per pane,
  one new pure-function-shaped helper, and a handful of call sites that
  never touch any existing widget's construction, value, or persisted
  state. No schema change, no new persisted attribute, no change to any
  rebuild/debounce machinery.
- Revert is: drop the two spacer `Frame`s and their `<Configure>` bindings
  from each of the four panes, drop `_fill_pane`/`FILL_TOP_SHARE`, drop the
  explicit calls from `_set_content_tab`/`_set_settings_tab`/`_select()`.
  Every existing widget's construction call is completely unchanged (only
  parented alongside two new siblings), so this is a clean, single-file,
  single-concern revert.
- The one invariant most worth a reviewer double-checking directly, not
  just reading the diff for: that the floor case (default/minimum window
  size, tallest pane) is genuinely a no-op, not merely small — a wrong sign
  or off-by-one in the `extra` computation at exactly that boundary would
  either silently do nothing (harmless) or, worse, produce a small negative
  margin that Tk clamps to `0` anyway (so still harmless) — but a
  *reviewer* should re-derive `available`/`natural` at that boundary
  directly rather than trust this spec's own arithmetic, matching this
  story's own established "verify against the live system, not the spec's
  prose" discipline (`docs/history/ac-24-f3-implementation.md`'s corrected
  trace-ordering claim is the precedent for why).
