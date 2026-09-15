# Spec: Warn when the Minecraft interval minus jitter drops below 650 ms (G#22 / GH#33)

Branch: `feature/ac-22/minecraft-interval-sweep-warning`

## Summary
On the Minecraft profile only, show a muted hint under the Interval row when
the effective minimum interval (`click_ms − jitter_ms`, floored at 50 ms —
the same number the click worker actually floors at) drops below 650 ms, and
switch that hint to the bad colour once it drops below 550 ms. No value is
ever blocked or clamped; this only makes an existing silent effect (some
hits landing as non-sweeps) visible.

## Goals
- Warn, visually, when the Minecraft profile's own numbers put the person
  below the 650 ms threshold their app already ships as the safe default
  (`DEFAULT_CLICK_MS`, `afk_clicker.py:150`) — i.e. when jitter is eating
  into or past the one-tick margin that default banks on.
- Escalate to the bad colour once the numbers are decisively in Java's
  documented non-sweep territory (see "Thresholds" below for the exact cut
  and its justification).
- Keep the hint live: it must reflect the two number fields' *current*
  typed contents (including invalid/empty text, coerced the same way the
  worker itself coerces them) at every keystroke, on profile switch, and
  across a theme/UI-scale rebuild — never a stale value from when the
  pane was last built.
- Show this only for the Minecraft profile. Every other profile (Global,
  any custom game added from a window title) shows nothing new.

## Non-goals
- No blocking or clamping of `click_ms`/`jitter_ms` — the person can still
  set any rhythm they want on purpose; this is visibility only, exactly
  the ticket's own framing ("without blocking anyone who wants a faster
  rhythm on purpose").
- No Bedrock detection. The app cannot tell Java from Bedrock today (both
  match the same `"minecraft"` window-title fragment, `PROFILES[0]
  ["titles"]`), and this feature does not add that capability — see
  "Java only" below for how the wording carries this limitation instead
  of solving it in code.
- Nothing for any other game/profile. Global and custom profiles get no
  hint, no matter what numbers are typed into their Interval/jitter
  fields.
- No work from the other queued tickets mentioned alongside this one in
  the backlog (G#23 macOS font floor, G#40 flake, G#41 stray `.tmp`) —
  unrelated, not touched here.
- No change to the click worker's own math (`afk_clicker.py:~4283-4288`).
  The hint is a read-only display computed off the same numbers the
  worker already uses; it does not change what the worker does with them.

## Background / current state
- `DEFAULT_CLICK_MS = 650` (`afk_clicker.py:150`) already carries the
  full rationale as a code comment: Java's sword sweep needs 12 server
  ticks (600 ms) at full charge, and 650 is that plus one tick of margin
  for click/tick quantization. This feature reuses that same constant as
  the hint's "no hint above this" threshold rather than introducing a
  second `650` literal that could drift out of sync with it.
- The Minecraft profile lives in `PROFILES` (`afk_clicker.py:1361-1370`,
  id `"minecraft"`), the only profile with real tuning
  (`docs/CODING-GUIDELINES.md`'s comment on that list: "the only game
  whose numbers I can actually vouch for"). `"global"` (`:1372-1381`) is
  the always-available fallback, and `make_profile()` (`:1386-1390`)
  builds a profile dict for any custom window-title game the person adds
  via "add current game." All three already share one conditional-UI
  precedent worth following exactly: the `"eating"` boolean, which
  `_select()` (`:3392-3446`) reads to show/hide the Eating section —
  `True` only on the Minecraft profile dict, `False` on Global and every
  custom profile.
- Clicking pane build (`afk_clicker.py:2917-2923`):
  ```
  r = Row(cl, "Interval", s); r.pack(fill="x")
  self.click_ms = NumBox(r.control, DEFAULT_CLICK_MS, "ms", s)
  self.click_ms.pack()
  r = Row(cl, "Random jitter", s, hint="spreads the rhythm so it is not exact")
  r.pack(fill="x", pady=(int(6 * s), 0))
  self.jitter_ms = NumBox(r.control, 0, "±ms", s); self.jitter_ms.pack()
  ```
  `Row.__init__` (`:2168-2189`) already supports a `hint=` string: it
  renders a second, smaller `MUTED`-coloured `Label` under the row's own
  label (same label column, `wraplength=int(ROW_LABEL_W * s)` — the
  precedent test `RowValueColumn.
  test_random_jitter_hint_wraps_instead_of_overlapping_the_control`,
  `tests/test_ui.py:1720`, is exactly this mechanism, proving the wrap
  geometry and no-overlap-with-the-control property already hold for a
  static hint). **But it is static**: the hint `Label` is only ever built
  when `hint` is truthy at `Row.__init__` time, and nothing keeps a
  reference to it afterward — there is no way today to show/hide it, or
  change its text/colour, once the row is built. This feature needs a
  hint that changes at runtime (on/off, `MUTED`/`BAD`, retexted), which
  the existing param does not support. That gap is squarely part of what
  this spec's "Proposed approach" below asks the developer to close.
- `_persist()` (`afk_clicker.py:3453-3469`) is the one place that already
  reads both fields on every relevant trigger: a per-keystroke `"write"`
  trace on `self.click_ms.var`/`self.jitter_ms.var` (`:2953-2956`), and
  an explicit call at the tail of `_select()` (`:3451`, i.e. every
  profile switch) and at the head of `_rebuild_ui()` (per its own
  comment at `:3121`, i.e. every theme/scale rebuild). It already
  computes exactly the two numbers this feature needs, the same way the
  worker itself will eventually read them:
  ```
  "click_ms": self._num(self.click_ms, profile["defaults"]["click_ms"], 50),
  "jitter_ms": self._num(self.jitter_ms, 0, 0),
  ```
  `_num()` (`:4066-4071`) is the untrusted-input coercion the whole app
  already uses ("never trust an entry box at click time" per
  `docs/CODING-GUIDELINES.md`): invalid or empty text falls back to the
  given fallback, never raises. `_sync_settings()` (`:4120-4141`, the
  snapshot the click worker's thread actually reads) uses the identical
  `_num()` calls with the identical fallbacks/minimums. Reusing
  `_persist()`'s own already-computed `values["click_ms"]`/
  `values["jitter_ms"]` for the hint math (rather than a second,
  independent `_num()` call) guarantees the hint can never show a number
  that doesn't match what the worker will actually run with.
- `_persist()` guards on `self._loading` (set `True` for the duration of
  `_select()`'s value-fill, `:3404-3415`) and no-ops while it's set, so
  every keystroke-driven `_persist()` call during a profile switch's own
  var-set burst is already a no-op — the real recompute for a profile
  switch happens once, at `_select()`'s own explicit tail call
  (`:3451`), after `_loading` is back to `False`. This is exactly the
  same shape this feature's hint update needs, so hooking the hint
  recompute into `_persist()` covers keystroke edits, profile switch, and
  rebuild with no new trigger plumbing.
- Dynamic-height layout is already a solved problem in this file: toggling
  the Eating section's visibility in `_select()` (`:3417-3435`) changes
  the Clicking pane's natural height at runtime, and the app already has
  a coalescing mechanism for exactly that —
  `_request_pane_fill(key)`/`_run_pane_fill()` (`:3223-3276`), which
  measures the pane's actual content height against `WINDOW_MIN_H`
  (`:166`, the hard floor) and reflows the fill spacer, collapsing
  however many requests land in one burst into a single pass. `_select()`
  already calls `self._request_pane_fill("clicking")` (`:3446`) guarded
  on the Clicking tab actually being visible (`:3445`) — the same guard
  this feature's hint-visibility toggle should reuse, since reading a
  hidden pane's geometry is the exact hazard `_on_eat_card_settled()`'s
  own docstring (`:3278-3307`) warns about.
- Theme/colour tokens: `MUTED` and `BAD` are both already module globals
  sourced from `THEMES` (`:81-104`), used throughout the file for exactly
  this "quiet note" vs. "something's wrong" distinction (e.g.
  `_set_status`'s `MUTED`/`OK`/`BAD` usage at `:4107-4118` and
  `:4059-4062`). No new colour is needed.
- The click worker's actual math (`afk_clicker.py:~4283-4288`):
  ```
  interval = cfg.get("click_ms", DEFAULT_CLICK_MS) / 1000.0
  jitter = cfg.get("jitter_ms", 0) / 1000.0
  if jitter:
      interval = max(0.05, interval + random.uniform(-jitter, jitter))
  ```
  Jitter is symmetric and *subtracts* down to `click_ms − jitter_ms` in
  the worst case, floored at 50 ms (`0.05` s) — so the true effective
  minimum interval in milliseconds is `max(50, click_ms − jitter_ms)`,
  exactly the number named in the ticket and the task brief.

## Proposed approach

### 1. What drives "Minecraft-ness": a data-driven profile key
Add a new key to every `PROFILES` dict entry and to `make_profile()`'s
return value, mirroring the existing `"eating"` boolean precedent exactly
rather than introducing a second, parallel way to special-case Minecraft:

- `PROFILES[0]` (`"minecraft"`, `:1361-1370`): `"min_sweep_ms":
  DEFAULT_CLICK_MS,` (reusing the existing constant, not a fresh `650`
  literal — see "Background" above for why).
- `PROFILES[1]` (`"global"`, `:1372-1381`): `"min_sweep_ms": None,`
- `make_profile()` (`:1386-1390`, custom games): `"min_sweep_ms": None,`

Consumer code reads `profile["min_sweep_ms"]` (present and explicit on
every profile dict, same as `"eating"`) rather than `profile.get(...)` or
a bare `profile["id"] == "minecraft"` string check.

**Rejected alternative: `profile["id"] == "minecraft"`.** Works today,
but hardcodes an id string directly into the hint-update code path,
unlike every other profile-conditional behaviour in this file (`"eating"`
is the one precedent, and it's data, not an id check). It would also
silently need updating in a second place if a future profile ever wanted
the same sweep-timing treatment (e.g. a modded Java variant with
different tick math), whereas a data key generalizes for free and costs
nothing extra today — the two "off" profiles just carry `None`.

A new small constant, next to `DEFAULT_CLICK_MS` (`afk_clicker.py:150`):
```python
# Below this, click_ms - jitter_ms has dropped to 10 ticks (500 ms) or
# worse -- the ticket's own cited failure case (G#22): 84% charge, 76%
# damage, no sweep. Between this and DEFAULT_CLICK_MS the one-tick
# quantization margin DEFAULT_CLICK_MS banks on is already gone (11
# ticks/550 ms) -- a hit can still often land as a full sweep, but there
# is no margin left, hence a hint rather than nothing, and MUTED rather
# than BAD.
MIN_SWEEP_BAD_MS = 550
```

### 2. Thresholds, stated precisely
Let `effective_min_ms = max(50, values["click_ms"] - values["jitter_ms"])`,
computed from `_persist()`'s own already-`_num()`-coerced `values` dict
(§ see "Background"), only when `profile["min_sweep_ms"]` is not `None`:

- `effective_min_ms >= profile["min_sweep_ms"]` (i.e. `>= 650` on
  Minecraft): no hint at all — today's behaviour, unchanged.
- `MIN_SWEEP_BAD_MS <= effective_min_ms < profile["min_sweep_ms"]` (i.e.
  `550 <= effective_min_ms < 650`): hint shown, `MUTED`.
- `effective_min_ms < MIN_SWEEP_BAD_MS` (i.e. `< 550`): hint shown,
  `BAD`.

Both comparisons are on the profile's own `min_sweep_ms`/the module
constant, not hardcoded `650`/`550` inline, so the arithmetic stays
correct even though today only one profile ever has a non-`None`
`min_sweep_ms`.

**On reconciling 550 with the physics, precisely:** the ticket cites two
data points — 10 ticks (500 ms) is "84% charge, 76% damage, no sweep,"
and 650 ms is "the default with one tick of margin" over the 12-tick
(600 ms) full-charge floor. 550 ms is 11 ticks: one tick short of full
charge, but one tick *above* the ticket's own cited failure case. Reading
the ticket's two numbers as marking two different states — "still likely
fine, margin gone" (550–649) vs. "in the cited failure's own territory"
(<550) — is this spec's interpretation, not a re-measurement of the game
itself in this session; flagged under "Open questions" as an assumption,
not a blocker (a second, more conservative cut is a one-constant change
if wrong).

### 3. Java only — wording carries the limitation, not new detection
The window-title match (`PROFILES[0]["titles"] == ("minecraft",)`) fires
identically for a Java and a Bedrock launcher/window title; the app has
no way to tell them apart, and this spec deliberately doesn't add one
(non-goal, ticket's own scope: "Java only: Bedrock has no cooldown").

**Decision: the hint's wording must name "Java" explicitly.** A wording
that doesn't scope the claim (e.g. "sweep attacks may not land") would be
an actively false statement for a Bedrock player, who has no sweep
cooldown to lose. A wording that does name Java is always a true
statement regardless of which edition is actually running — a Bedrock
player simply sees an inapplicable-but-not-wrong note. The exact copy is
ux-designer's call (see item 6 below), but the constraint — the word
"Java" (or equivalent unambiguous scoping) must appear — is fixed here as
a product decision, not left open.

**Rejected alternative: omit "Java," rely on brevity.** Saves a handful
of characters in the label column's already-narrow wraplength, but turns
a true-but-inapplicable note into a false one for Bedrock players; not
worth the saved width given the existing jitter hint already
demonstrably wraps to two lines at this column width (precedent test
cited above) — a Java-qualified hint wrapping to two lines is not a new
problem this feature introduces.

### 4. When it updates
Hook the recompute into `_persist()` (`:3453-3469`), immediately after
its existing `values` dict is built, reusing `values["click_ms"]`/
`values["jitter_ms"]` verbatim (no second `_num()` call):

```python
min_sweep = profile["min_sweep_ms"]
effective_min = max(50, values["click_ms"] - values["jitter_ms"])
if min_sweep is not None and effective_min < min_sweep:
    color = BAD if effective_min < MIN_SWEEP_BAD_MS else MUTED
    self._set_sweep_hint(text, color)   # exact copy: ux-designer, item 6
else:
    self._clear_sweep_hint()
```

This one hook, with no new trace/callback wiring, covers every trigger
the ticket and task brief ask for:
- **Every keystroke** in either field — already routes through the
  existing `"write"` traces on `self.click_ms.var`/`self.jitter_ms.var`
  (`:2953-2956`) into `_persist()`.
- **Profile switch** — `_select()`'s own tail call to `_persist()`
  (`:3451`), which by then has already loaded the new profile's values
  into the fields and reset `self._loading = False`.
- **Theme/scale rebuild** — `_rebuild_ui()`'s own leading `_persist()`
  call (per the comment at `:3121`) re-derives the hint from
  whatever the freshly-rebuilt fields currently hold, so a rebuilt
  Interval row starts in the correct state without a separate init path.
- **Invalid/empty field text** — already handled, for free, because
  `values["click_ms"]`/`values["jitter_ms"]` are `_persist()`'s own
  `_num()`-coerced numbers, the same coercion (`_num`, `:4066-4071`) and
  the same fallbacks the worker's own `_sync_settings()` snapshot uses —
  the hint can never disagree with what the worker will actually run.

`_set_sweep_hint`/`_clear_sweep_hint` are new small methods on
`AfkAutoclicker` that mutate the Interval row's dynamic hint widget (see
item 5) and, only on an actual shown/hidden *transition* (not on every
keystroke — most keystrokes just change text/colour within an already-
shown or already-hidden state), call `self._request_pane_fill("clicking")`
guarded the same way `_select()` already guards it (`:3445`, `_content_tab
== "clicking"`) — reusing the existing coalescing mechanism rather than
inventing a second one.

### 5. Placement, and the `Row` capability gap
Placement is under the **Interval** row's own label column — the same
visual slot the existing static hints already occupy (`Row.__init__`'s
`hint=` mechanism, `:2168-2189`), and the exact slot the ticket names.
The condition reads both fields, but the ticket is explicit about where
it renders, and the label-column-hint slot is a per-row concept anyway —
putting it under jitter instead would be no more "correct" and would
break the ticket's own stated placement for no gain.

**Gap this exposes:** `Row.__init__`'s hint is built once, from a static
string, with no reference kept — there is no existing way to show/hide
it or change its text/colour after construction. This feature needs
`Row` (or the Interval row specifically) to gain that capability:
keep a reference to the hint `Label` (created once, initially unpacked/
empty when no static `hint=` string is given, or extend `Row` with a way
to opt into a mutable hint), and expose a small `set_hint(text, color)` /
`clear_hint()` pair `AfkAutoclicker` can call from `_set_sweep_hint`/
`_clear_sweep_hint`. Exact implementation shape (a new `Row` method vs. a
one-off widget built alongside just the Interval row) is the developer's
call — constraint: every *existing* `hint=` call site (jitter's, auto-
stop's `"0 means never"`) and their existing tests must keep behaving
exactly as today; this is additive capability, not a rewrite of `Row`.

**Height and pane fill:** the hint appearing/disappearing changes the
Interval row's — and therefore the Clicking card's — natural height at
runtime, the same category of change `_on_eat_card_settled()`'s own
docstring already documents and solves for the Eating card
(`:3278-3307`). Reuse `_request_pane_fill("clicking")` for this (see
item 4) rather than a second mechanism. **Decision: do not reserve space**
for the hint when hidden — the Clicking pane already tolerates
height changes at runtime today (the Eating section itself appears/
disappears the same way on profile switch), so a second source of the
same category of layout change is consistent with the existing design,
not a new risk. **Rejected alternative: always reserve the hint's line
height.** Would avoid a layout shift when the hint first appears, but
wastes vertical space in the common case (a Minecraft session with no
hint showing) purely to avoid a kind of shift the app already accepts
elsewhere for the Eating section.

### 6. What ux-designer must decide
This spec fixes the mechanism, the two thresholds, the two colours
(`MUTED`/`BAD`, both existing tokens), the profile-conditionality, and
the constraint that "Java" must appear in the wording. It does **not**
fix:
- **Exact copy** for the `MUTED` (550–649 ms) state and the `BAD` (<550
  ms) state — same sentence with a different lead-in, or two genuinely
  different sentences; must fit the label column's existing
  `wraplength=int(ROW_LABEL_W * s)` without becoming unreadable at two
  lines (the jitter-hint precedent already wraps at this width, so two
  lines is an accepted look, not something to design around).
- Whether the `BAD`-state copy should say anything different from the
  `MUTED`-state copy beyond a more urgent tone (e.g. "may not land"
  vs. "likely won't land"), given the underlying claim's confidence is
  genuinely different between the two bands.
- Confirm the hint sits directly under "Interval" (not, say, indented or
  boxed) and doesn't visually compete with jitter's own already-static
  hint immediately below it on the Minecraft profile — two hint lines
  stacked in adjacent rows is new to this profile specifically (jitter's
  hint is unconditional; this one is conditional), worth a designer's
  look even though no new layout primitive is involved.

## Edge cases
- **Global profile, any numbers:** `min_sweep_ms` is `None` → no hint,
  ever, regardless of how low `click_ms − jitter_ms` goes.
- **Custom profile, any numbers:** same as Global — `make_profile()`'s
  `min_sweep_ms: None`.
- **Empty/non-numeric text in either field:** `_num()`'s existing
  fallback applies (profile's own default `click_ms` for the Interval
  field, `0` for jitter) — same as every other consumer of these fields
  today; the hint reflects the fallback, not garbage.
- **Jitter exceeds click_ms** (e.g. `click_ms=200`, `jitter_ms=500` on a
  *non*-Minecraft profile, or hypothetically on Minecraft if someone
  types it): `effective_min_ms` floors at 50 via `max(50, ...)`, matching
  the worker's own `max(0.05, ...)` floor exactly — never negative,
  never a display artifact.
- **Exactly at a threshold boundary** (`effective_min_ms == 650` or
  `== 550`): defined precisely in "Thresholds" above (`>=` no-hint,
  `<` triggers) — not left to floating-point luck.
- **Rapid typing / mid-edit intermediate states** (e.g. clearing the
  field to type a new number, briefly empty): the hint may flicker
  through fallback-derived states for the duration of the edit — this
  is the same behaviour `_sync_settings()`'s live worker snapshot
  already has (it re-reads every 200 ms regardless of whether typing is
  "finished"), so it's consistent with how every other live-reading
  field in this app already behaves, not a new class of glitch.
- **Switching away from Minecraft mid-hint:** the hint must disappear the
  same tail call (`_select()`'s `_persist()`) that already hides the
  Eating section — no separate cleanup path, no leftover coloured label
  after switching to Global.
- **Theme switch while a hint is showing:** rebuilt widgets read the
  still-persisted field values fresh (per item 4), so the correct
  colour/text/visibility is restored on the very first `_persist()` call
  after rebuild, not left in a stale pre-rebuild state.

## Affected areas
- `afk_clicker.py`:
  - New `MIN_SWEEP_BAD_MS = 550` constant near `DEFAULT_CLICK_MS`
    (`:150`), with its own why-comment (see item 1).
  - `PROFILES` (`:1361-1381`) — new `"min_sweep_ms"` key on both entries
    (`DEFAULT_CLICK_MS` on Minecraft, `None` on Global).
  - `make_profile()` (`:1386-1390`) — new `"min_sweep_ms": None` key.
  - `Row` (`:2168-2189`) — additive capability: a hint that can be
    created empty/hidden and later shown/hidden/retexted/recoloured,
    without changing any existing `hint=` call site's behaviour.
  - Clicking pane build (`:2917-2923`) — keep a reference to the
    Interval row (or its hint widget) so `_persist()` can reach it.
  - `_persist()` (`:3453-3469`) — compute `effective_min` from its own
    `values`, call `_set_sweep_hint`/`_clear_sweep_hint`.
  - New `AfkAutoclicker` methods: `_set_sweep_hint(text, color)`,
    `_clear_sweep_hint()`, each guarded/coalesced through the existing
    `_request_pane_fill("clicking")` on an actual visibility transition
    (`:3223-3276`, guard pattern from `:3445`).
- `tests/test_ui.py` — a new test class alongside the existing
  `RowValueColumn` (`:1640`) hint-wrap precedent, covering the
  acceptance criteria below. Any test that constructs the app through
  the existing `UITestCase.setUp()` helper (`:69-191`) already gets
  whatever hotkey-watcher stubbing that fixture provides; only a test
  that separately drives `apply_hotkey()` directly needs its own
  `app.HotkeyWatcher` stub (per `HotkeyPersistence`'s own comment,
  `:2058`) — not expected to be relevant to this feature, noted only
  because the task brief flagged it as a standing hazard.
- No `Store`/schema change: `min_sweep_ms` lives on the in-memory
  `PROFILES` definition, never persisted per-game (matches `"eating"`'s
  own precedent — a profile-shape fact, not a per-save-slot setting).
- No change to `.github/workflows/ci.yml` or `release.yml`.

## Acceptance criteria
- [ ] Given the Minecraft profile with Interval 650 and jitter 0, when the
      Clicking pane is showing, then no sweep hint is visible.
- [ ] Given the Minecraft profile with Interval 649 and jitter 0, then the
      sweep hint is visible, `MUTED`-coloured, and its text names "Java".
- [ ] Given the Minecraft profile with Interval 600 and jitter 50
      (effective minimum 550), then the sweep hint is visible and
      `MUTED` (the `>= 550` boundary is inclusive on the muted side).
- [ ] Given the Minecraft profile with Interval 600 and jitter 51
      (effective minimum 549), then the sweep hint is visible and `BAD`.
- [ ] Given the Minecraft profile with Interval 500 and jitter 0, then the
      sweep hint is visible and `BAD`.
- [ ] Given the Minecraft profile with Interval 100 and jitter 500
      (effective minimum floored at 50), then the sweep hint is visible
      and `BAD` (never a negative or nonsensical displayed number).
- [ ] Given the Global profile, at any Interval/jitter combination
      (including ones that would trigger a hint on Minecraft), then no
      sweep hint is ever visible.
- [ ] Given a custom profile added via "add current game," at any
      Interval/jitter combination, then no sweep hint is ever visible.
- [ ] Given the Minecraft profile with the Interval field emptied (blank
      text) mid-edit, then the hint reflects the profile's default
      `click_ms` fallback (the same `_num()` fallback `_persist()`/
      `_sync_settings()` already use) rather than raising or showing a
      garbage value.
- [ ] Given the sweep hint is currently shown, when the Interval or
      jitter field is edited by one more keystroke that raises the
      effective minimum back to >= 650, then the hint disappears without
      requiring focus-out, Enter, or a profile switch.
- [ ] Given the Minecraft profile is selected while the hint would be
      showing, when the profile is switched to Global and back to
      Minecraft, then the hint is hidden while Global is selected and
      correctly restored (text/colour) upon returning to Minecraft.
- [ ] Given the sweep hint is showing, when a theme or UI-scale change
      triggers `_rebuild_ui()`, then the rebuilt Interval row shows the
      same hint state (visible/hidden, and colour) with no stale value
      from before the rebuild.
- [ ] Given the sweep hint transitions from hidden to shown (or shown to
      hidden), then `_request_pane_fill("clicking")` is invoked (directly
      observable via the existing pane-fill test infrastructure/geometry
      assertions, per the `RowValueColumn`/`VerticalFill` precedent
      style) so the Clicking pane's fill spacer reflows instead of
      leaving a dead gap or an overflow past `WINDOW_MIN_H`.
- [ ] Given the hint is visible at the app's default scale, then its text
      wraps at the same `wraplength=int(ROW_LABEL_W * s)` every other row
      hint uses and does not overlap `self.click_ms`'s control — same
      geometry assertions as
      `RowValueColumn.test_random_jitter_hint_wraps_instead_of_overlapping_the_control`
      applied to the Interval row.
- [ ] Given every existing static `hint=` call site (`Random jitter`,
      `Auto-stop`), then their hints render exactly as before — this
      feature's `Row` change is additive and must not alter existing
      behaviour or break `RowValueColumn`'s existing tests.
- [ ] Given the full test suite, when run via `DISPLAY=:99 <venv>/bin/python
      -m unittest discover -s tests -t .`, then it passes with no new
      failures beyond the ones this feature's own new tests are meant to
      exercise (baseline: 388 OK, skipped=10).

## Open questions
1. **The 550 ms cut is this spec's interpretation of the ticket's own two
   cited numbers (500 ms/10-tick failure case, 650 ms/12-tick+margin
   default), not a re-measurement of Minecraft's cooldown table in this
   session.** Proceeding under "550 ms (11 ticks) is the boundary between
   'margin gone but often still fine' and 'in the cited failure's own
   territory.'" Flag if a different, more conservative or more permissive
   cut is preferred — it is a one-constant change (`MIN_SWEEP_BAD_MS`).
2. **Exact hint copy for both colour states** — deferred to ux-designer
   (item 6 above) by design, not a gap in this spec; the only fixed
   constraint is that "Java" (or equally unambiguous edition-scoping
   language) appears in the text.
3. **Whether `Row` should be reworked to always support a mutable hint**
   (accepting `hint=None` up front and exposing `set_hint`/`clear_hint`
   unconditionally) **vs. a narrower one-off addition scoped to just the
   Interval row.** Proceeding under "developer's call, additive only" —
   flagged only because it's the one place this spec deliberately leaves
   the exact shape open rather than dictating it, since either shape
   satisfies every acceptance criterion above and neither is a product
   decision.

## Risk / rollback notes
- Purely additive and purely visual: one new profile key (defaulting to
  `None`, i.e. off, everywhere except Minecraft), one new constant, one
  new `Row` capability, one new hook inside an already-existing method
  (`_persist()`). A `git revert` of the commit fully removes it.
- Cannot affect the click worker's actual behaviour: the worker thread
  never reads `min_sweep_ms` or anything this feature adds — it's a
  read-only consumer of the same two numbers the worker already uses,
  never a producer the worker depends on.
- Worst-case failure mode is cosmetic: a hint that shows when it
  shouldn't, or fails to show when it should, or reflows the pane
  incorrectly — none of which can touch `Controller`, `hk_listener`, or
  any worker-thread state, matching the same risk shape ac-36 documented
  for its own purely-additive dialog feature.

## Orchestrator correction (before design/build) — the `_persist()` hook and rebuilds

Decision 4 hooks the hint update into `_persist()`. `_persist()` is also the **first** thing `_rebuild_ui()` runs, and at that point the old widget tree is about to be destroyed and the new one does not exist yet. That exact shape crashed G#21 / PR #78 round 1: `_note_save()` painted `save_failed_label` from that flush, and got `AttributeError` for a never-built label, then `TclError` for a destroyed one. See `docs/history/ac-21-implementation.md` Round 2 and `docs/history/ac-21-test-review.md`.

Binding constraint for this feature, in addition to the acceptance criteria above:
- **Never touch the hint widget while `self._rebuilding` is True.** Compute and remember the state if useful, but paint it only once the current tree exists. `_build_ui()`'s tail, where `_paint_save_notice()` is already called, or `_select()`'s tail after the fields are loaded, are the safe paint points. The hint must still come out right after a rebuild.
- **Add acceptance criterion:** with the Minecraft profile selected and the hint visible (e.g. 600/51), a theme change, a UI-scale change, and opening then closing Settings each complete without exception, and the hint is still shown in the right state afterwards. Also cover a first-ever build where the Minecraft profile is the saved selection at startup.
