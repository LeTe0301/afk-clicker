# Spec: Theme data + Quartz shape language (Story #17, Feature 1 of 4)

Part of Gitea `admin/afk-clicker#17` / GitHub #20 ("Story: themes that follow
the system, and a Settings tab"). Full breakdown: `docs/story.md` in this
worktree. This spec covers **Feature 1 only** — the other three
(OS detection, tab navigation + Settings tab, UI scale) are out of scope here
and listed with their own draft acceptance criteria in `docs/story.md`.

## Summary
Turn the module-level palette constants (`afk_clicker.py:41-49`) into a
`THEMES` dict holding both the Deepslate (dark) and Quartz (light) color sets
from the ticket, while the app keeps shipping **Deepslate only** — no
switcher, no OS detection, nothing new at runtime. Separately, and in the
same pass since both were chosen together as "Quartz's style on both"
(`docs/story.md`'s Decision block, mock's "Chosen" section), apply Quartz's
shapes everywhere: pill-shaped buttons and the segmented control, a pill
status, and radius-12 **borderless** cards and sidebar rows (replacing the
current 1px-bordered, square-cornered cards). Net user-visible effect: a
restyle, with the app still behaving exactly as it does today.

## Goals
- `afk_clicker.THEMES["dark"]` and `afk_clicker.THEMES["light"]` exist,
  each holding all eleven color names below, and `THEMES["dark"]`'s nine
  ticket-given values match the Deepslate hex exactly; `THEMES["light"]`'s
  nine match Quartz exactly.
- The ten existing module-level names (`BG`, `CARD`, `CARD_HI`, `LINE`,
  `INK`, `MUTED`, `ACCENT`, `OK`, `BAD`, plus the new `ACCENT_INK`) are
  derived from `THEMES["dark"]` at import time, so every one of the dozens of
  existing `bg=BG`/`fill=CARD`/etc. call sites needs **zero** changes — only
  the *values* those names resolve to change.
- `Button` and `Segmented` become true pills (corner radius clamps to
  half their height); `StatusPill` becomes a true pill; `card()`'s outer
  shell and `GameItem` become radius-12, borderless (no outline).
- The Minecraft/Global content pane, the hotkey card, the sidebar, and the
  status pill all render with no functional regressions — every value that
  reaches `settings.json` today still does, unchanged. `#14`'s resizability
  (once merged) keeps working with the new canvas-based cards.

## Non-goals
- **No theme switching.** `THEMES["light"]` is defined (see Goals) but never
  read anywhere at runtime this feature — it exists now because the ticket
  already fully specifies it and defining it alongside Deepslate is what
  makes `THEMES` a real two-entry "theme object" (`docs/story.md`'s seam-b
  framing) rather than the same nine constants moved sideways. It is wired
  up in Feature 2 (OS detection) and Feature 3 (manual override). A one-line
  comment at the `THEMES` definition says so, to preempt it reading as dead
  code in review (Round 9).
- **No `_build_ui()`/rebuild-in-place mechanism.** Nothing in this feature
  changes theme or scale at runtime, so there is nothing to rebuild.
  Building that scaffolding here would be unused, speculative abstraction —
  it lands in Feature 3, the first feature that needs it
  (`docs/story.md`'s cross-cutting Decision).
- **No Settings tab, no tab navigation.** Feature 3.
- **No UI scale.** Feature 4.
- **No settings.json changes of any kind.** This feature touches no `Store`
  code and adds no new persisted key.
- **No new dependency, no second GUI toolkit** (`docs/TECHSTACK.md`).
- **No change to `NumBox`'s field shape.** The mock's Quartz variant doesn't
  override `--rf` (the field radius CSS var stays at its base `0px`), so
  number-entry fields stay square-cornered — matches the ticket, which lists
  card/button/segmented/status shapes explicitly and says nothing about
  fields.
- **No change to fonts, DPI scaling (`self.s`), or window geometry.**
  Untouched by this feature; `#14`'s in-flight `resizable`/`minsize` work is
  read and built to be compatible with (see "Card resize" below), not
  reimplemented.

## Background / current state
Palette (`afk_clicker.py:41-49`, verified directly in this worktree — the
ticket's own line numbers, 44-52, were off by a few lines against `main`,
possibly a different baseline; treat the numbers in this spec as current):
```
BG      = "#0e0f13"
CARD    = "#16181f"
CARD_HI = "#1d202a"      # hover / pressed
LINE    = "#262a35"
INK     = "#e8eaf0"
MUTED   = "#868c9e"
ACCENT  = "#ffc542"
OK      = "#35d07f"
BAD     = "#ff5f56"
```
These ten (nine plus the primary-button ink, see below) are read as plain
module globals at *every* widget construction site — confirmed by grep,
there is no theme object, no `self.theme`, nothing passed as a parameter
anywhere in the file today.

**Shape call sites** (all `round_rect`, `afk_clicker.py:747-755`, whose own
clamp `r = min(r, (x2-x1)/2, (y2-y1)/2)` already self-limits any radius to
half the smaller dimension — this is the mechanism the pill radius below
relies on, not new code):
- `Button.__init__` (`758-775`): `round_rect(self, 1, 1, w-1, h-1, 9*s, fill=CARD, outline=LINE)` — line 769.
- `Segmented.__init__` (`806-827`): outer track `round_rect(self, 0, 0, self.w, self.h, 9*s, fill=BG, outline=LINE)` (816) and the selection pill `round_rect(self, 2, 2, seg-2, self.h-2, 7*s, fill=CARD_HI, outline="")` (818).
- `Segmented._pill_pts` (`844-847`): `r = min(7*self.s, ...)` (845) — recomputes the same selection-pill radius when the value changes; must stay in sync with the constructor's radius or the pill "jumps" shape when selection moves.
- `StatusPill.__init__` (`850-869`): `round_rect(self, 1, 1, w-1, h-1, 12*s, fill=CARD, outline=LINE)` — line 858.
- `card()` (`889-894`): **not currently a canvas at all** — `f = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)` (890), a plain 1px-bordered, square-cornered `Frame`; `inner = tk.Frame(f, bg=CARD)` (892) is packed inside with `padx=int(12*s), pady=int(10*s)` (893) and is the value returned to callers. This is the one call site with no `round_rect` at all today, since `tk.Frame` cannot be rounded — it has to become a canvas to satisfy "radius 12" (see Decision 3 below).
- `GameItem.__init__` (`897-929`): `round_rect(self, 1, 1, w-1, h-1, 8*s, fill=BG, outline="")` — line 908. Already borderless (`outline=""`); only the radius (8→12) changes.

**`card()`'s three call sites**, all in `_build_content`
(`afk_clicker.py:1061-1125`): `hk = card(body, s)` (1080, the hotkey card),
`cl = card(body, s)` (1095, the clicking-interval card),
`self.eat_card_inner = card(body, s)` (1110, the eating card) — and
`self.eat_card = self.eat_card_inner.master` (1111), used later purely to
`.pack()`/`.pack_forget()` the whole eating card as a unit when a non-eating
profile is selected (`_select`, 1163-1168). Any `card()` rewrite must keep
`inner.master` resolving to something that supports `.pack()`/`.pack_forget()`
identically — a `tk.Canvas` does, no special-casing needed.

**Primary-button ink is hardcoded, not themed.** `Button._colors`
(`777-782`): `return (ACCENT, ACCENT, "#12131a") if not hover else
("#ffd66b", "#ffd66b", "#12131a")` — the label ink (`"#12131a"`) and the
hover fill (`"#ffd66b"`) for a primary button are two more colors that need
to move into the theme, not stay hardcoded: `"#ffd66b"` was tuned against
the *old* accent (`#ffc542`, also golden-yellow) and has no defined relation
to Deepslate's new copper accent (`#e08a55`).

**`CARD_INNER_W`** (`afk_clicker.py:71`): `CONTENT_W - 2 - 24        # 1px
border each side, 12px padding` — used as `Segmented`'s default `width`
(`809`) at both of its call sites in `_build_content` that don't pass an
explicit width (the mouse-button segmented control, 1106-1107, and the
eating-mode segmented control, 1113-1115). The `- 2` accounts for `card()`'s
current 1px border on each side; once `card()` is borderless this formula is
wrong (leaves 2px of unused width) and must be recomputed.

**`#14` (in-flight, `.worktrees/afk-clicker/ac-14`, not yet merged)** makes
the window resizable and the content pane grow to fill extra width
(`docs/spec.md`/`docs/design.md` in that worktree). Its `self.content` still
grows via plain `pack(fill="both", expand=True)` — no changes to how `body`
or cards are packed inside it. This feature's canvas-based `card()` needs to
track `body`'s width on resize (see Decision 3) specifically so it stays
compatible with `#14` once both are merged, not because this feature touches
resizing itself.

## Proposed approach

### Decision 1 — theme dict shape, and how the ten old names survive

Add, near the current constants (`afk_clicker.py:41-49`):

```python
# ── palette ───────────────────────────────────────────────────────────────
# Two named palettes (ticket #17 / mock "Chosen": Deepslate for dark, Quartz
# for light). "light" is unused until #17's OS-detection and Settings-tab
# features land -- kept here, not stubbed, because every value is already
# decided (ticket + theme-board.html's "quartz-pair" entry), so there is
# nothing left to design later, only to wire up.
def _lighten(hex6, factor):
    # Blends a hex color toward white by `factor` (0-1). Used only to derive
    # a primary button's hover fill from its own ACCENT, so a new theme
    # never needs a fourth hand-picked hex just for hovering.
    r, g, b = (int(hex6[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (int(c + (255 - c) * factor) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _theme(bg, card, card_hi, line, ink, muted, accent, accent_ink, ok, bad):
    return {"BG": bg, "CARD": card, "CARD_HI": card_hi, "LINE": line,
            "INK": ink, "MUTED": muted, "ACCENT": accent,
            "ACCENT_INK": accent_ink, "ACCENT_HI": _lighten(accent, 0.18),
            "OK": ok, "BAD": bad}


THEMES = {
    "dark": _theme("#15171a", "#1c1f23", "#262a30", "#3a4048", "#e4e7ea",
                   "#9299a3", "#e08a55", "#1a0f08", "#5cc9a4", "#f06262"),
    "light": _theme("#e8ebf0", "#ffffff", "#eff2f7", "#d3d8e0", "#161a22",
                    "#596170", "#2b58cc", "#ffffff", "#0f7f4c", "#cc3527"),
}

_ACTIVE = THEMES["dark"]      # feature 1 ships dark-only; #17 features 2-3 pick this
BG, CARD, CARD_HI, LINE, INK, MUTED = (
    _ACTIVE["BG"], _ACTIVE["CARD"], _ACTIVE["CARD_HI"], _ACTIVE["LINE"],
    _ACTIVE["INK"], _ACTIVE["MUTED"])
ACCENT, ACCENT_INK, ACCENT_HI, OK, BAD = (
    _ACTIVE["ACCENT"], _ACTIVE["ACCENT_INK"], _ACTIVE["ACCENT_HI"],
    _ACTIVE["OK"], _ACTIVE["BAD"])
```

`ACCENT_INK` values (`#1a0f08` dark, `#ffffff` light) come directly from the
mock's own `THEMES` array (`theme-board.html`, the `deepslate`/`quartz`
entries' `t.ACCENT_INK`), not invented here. `ACCENT_HI` is **not** in the
mock (the mock is a static reference with no hover state) — it's computed
via `_lighten`, a small pure function in the same spirit as the file's
existing local helpers (e.g. `fmt_num`), not a new dependency.

Rejected alternatives:
- *Keep nine/ten separate hand-picked hex constants per theme, including a
  manually-tuned hover color.* Rejected for `ACCENT_HI` specifically:
  there's no ticket or mock value to copy, so hand-picking one now would be
  an invented, unverified color exactly where `_conventions.md`'s "report
  honestly... an explicit gap is useful, a confident guess is not" argues
  against guessing. A deterministic function keeps the theme's only inputs
  to the nine ticket-given colors, and works for Quartz's blue accent later
  with no new tuning.
- *Pass a theme object into every widget constructor instead of deriving
  module globals.* This is what real live-switching (Feature 3) will need,
  but doing it now touches every one of the dozens of `bg=BG`/`fill=CARD`
  call sites for a feature that doesn't switch anything yet — much larger
  diff, much larger review surface, for zero behavior change. Deferred to
  Feature 3, which actually needs per-instance theme access to rebuild.

### Decision 2 — pill radius for buttons, segmented control, and status

Add two named radius constants beside `THEMES` (mirrors the mock's own
`--rp`/`--rc` CSS custom properties, so the mapping from mock to code stays
traceable — `CODING-GUIDELINES.md`: "comment the why"):

```python
PILL_R = 999     # self-clamps to height/2 via round_rect's own min() -- a
                  # true capsule regardless of the widget's exact height.
CARD_R = 12       # cards and sidebar rows (mock's --rc / --rb at 12px)
```

Apply `PILL_R * s` at:
- `Button.__init__:769` — `9 * s` → `PILL_R * s`.
- `Segmented.__init__:816` (outer track) and `:818` (selection pill) —
  `9 * s` and `7 * s` → `PILL_R * s`.
- `Segmented._pill_pts:845` — `r = min(7 * self.s, ...)` → `r = min(PILL_R *
  self.s, ...)`. Must change together with `:818` or the pill's shape
  changes visibly when the selected segment moves.
- `StatusPill.__init__:858` — `12 * s` → `PILL_R * s`. (The ticket calls
  this out explicitly: "a pill status.")

Apply `CARD_R * s` at:
- `GameItem.__init__:908` — `8 * s` → `CARD_R * s`.
- The new `card()` shell (Decision 3) — `CARD_R * s`, not `PILL_R`.

**Why `GameItem` gets `CARD_R`, not `PILL_R`, while `Button`/`Segmented` get
`PILL_R`:** the mock's CSS scopes this precisely. `.w-game`'s radius comes
from the base `--rb` var (`12px` under the Quartz vars block the "Chosen"
pair reuses); the `.btn-pill` class — which is what actually makes buttons
and the segmented control pills — only overrides `.w-btn`/`.w-seg`'s
`border-radius`, never `.w-game`'s. So sidebar rows and cards both stay at a
fixed 12px; only buttons, the segmented control, and the status pill go
fully round. This is a direct, checkable reading of the mock's CSS
(`theme-board.html:208-210` for the `.btn-pill` scoping), not a judgment
call.

### Decision 3 — `card()` becomes a borderless, radius-12 canvas shell

`tk.Frame` cannot be rounded, so the outer shell has to become a `tk.Canvas`
hosting the existing `inner` content `Frame` via `create_window` — the same
technique every other rounded widget in this file already uses for its own
shape (`round_rect` + canvas items), applied here for the first time to host
*arbitrary child widgets* rather than draw everything as canvas items
directly.

```python
def card(parent, s):
    """Borderless, radius-12 card: a rounded canvas shell hosting a plain
    Frame via create_window -- the standard Tk technique for real widgets
    inside a round_rect, since Frame itself cannot be rounded."""
    pad = int(CARD_R * s)          # inset MUST be >= the radius on every
                                    # side, or inner's own square corners
                                    # poke past the shape's rounded corners
                                    # and the rounding never shows through.
    shell = tk.Canvas(parent, bg=BG, highlightthickness=0)
    shell.pack(fill="x")
    inner = tk.Frame(shell, bg=CARD)
    win_id = shell.create_window(pad, pad, window=inner, anchor="nw")
    shape_id = None

    def _redraw(_event=None):
        nonlocal shape_id
        inner.update_idletasks()
        w = shell.winfo_width() or (inner.winfo_reqwidth() + 2 * pad)
        h = inner.winfo_reqheight() + 2 * pad
        shell.config(height=h)
        shell.itemconfig(win_id, width=w - 2 * pad)
        if shape_id is not None:
            shell.delete(shape_id)
        shape_id = round_rect(shell, 0, 0, w, h, CARD_R * s, fill=CARD, outline="")
        shell.tag_lower(shape_id)      # behind inner, so inner's flat area
                                        # sits on top and only the corners --
                                        # which inner's padding never reaches
                                        # -- show the rounded silhouette.

    shell.bind("<Configure>", _redraw)
    inner.bind("<Configure>", _redraw)
    _redraw()
    return inner
```

The current `pady=int(10*s)` (`afk_clicker.py:893`, vs. `padx=int(12*s)`) is
folded into one uniform `pad = int(CARD_R * s)` on all four sides — a
deliberate, minor density change (2px more vertical breathing room per row
group), not a silent one, forced by the geometry constraint above: at the
old 10px vertical pad, `inner`'s own corner would land 2px inside the
radius-12 arc, visibly squaring off the top/bottom corners.

`shell` keeps `bg=BG` (matching `body`'s background, same as today) so the
four corner triangles excluded by the rounded polygon show the page
background — this *is* the "raised card on the ground" look ("borderless
raised cards," ticket), not a defect to hide.

Rejected alternatives:
- *Keep `card()` a `Frame`, drop only `highlightthickness` to remove the
  border.* Satisfies "borderless" but not "radius 12" — `Frame` has no
  rounding capability at all. Doesn't meet the ticket.
- *Fixed canvas height per call site instead of `<Configure>`-driven
  redraw.* There are three call sites (`hk`/`cl`/`eat_card_inner`) with
  different row counts, and the eating card is shown/hidden as a whole unit
  via `pack()`/`pack_forget()` — a fixed height is fragile against any future
  row addition or `s` changing (font metrics change with DPI), and buys
  nothing over the `<Configure>` version, which is barely more code and
  already the file's existing idiom for reacting to size ("if content
  changes, redraw" is exactly what `Segmented._paint`/`_pill_pts` already do
  on value change).
- *Clip the embedded Frame's corners with a true rounded mask.* Tk has no
  clip-path primitive; every rounded shape in this file (`Button`,
  `Segmented`, `StatusPill`, `GameItem`) already works around this by never
  putting an opaque rectangular widget on top of the rounded silhouette —
  `card()` is the first one that *must* host real child widgets, so the
  inset-padding technique above (inset ≥ radius) is the established
  lowest-risk way to get the same effect without a new drawing primitive.

**`CARD_INNER_W`** (`afk_clicker.py:71`): `CONTENT_W - 2 - 24` → `CONTENT_W
- 2 * CARD_R` (452 − 24 = 428, was 426), comment updated from `# 1px border
each side, 12px padding` to `# 12px padding each side, no border now that
cards are borderless`.

### Decision 4 — primary button ink and hover use the theme, not hardcoded literals

`Button._colors` (`afk_clicker.py:777-782`):
```python
def _colors(self, hover):
    if not self._enabled:
        return CARD, LINE, MUTED
    if self.primary:
        return (ACCENT_HI, ACCENT_HI, ACCENT_INK) if hover else (ACCENT, ACCENT, ACCENT_INK)
    return (CARD_HI if hover else CARD), LINE, INK
```
(Order of the returned tuple — fill, outline, ink — is unchanged; only the
two previously-hardcoded literals become the new theme names.)

## Affected areas
`afk_clicker.py` only — one file, one architectural layer (Tk presentation).
Touched: the palette block (`41-49` → `THEMES`/`_theme`/`_lighten` block),
`round_rect` call sites in `Button` (769), `Segmented` (816, 818, 845),
`StatusPill` (858), `GameItem` (908), `card()` (889-894, rewritten), `Button.
_colors` (777-782), and `CARD_INNER_W` (71). No other function signature
changes; `card()`'s return value (`inner`, a `Frame`) and `inner.master`'s
`.pack()`/`.pack_forget()` behavior are preserved exactly, so none of
`_build_content`'s three call sites (1080, 1095, 1110-1111) need to change.
No data model, schema, or settings.json changes.

`tests/test_ui.py`: no existing test references `card()`'s internals,
`round_rect` radii, or any color constant directly (confirmed by grep) — no
existing test needs to change. New tests are additive (see Acceptance
criteria).

## Edge cases
- **`s` far from 1.0** (very low/high DPI). `round_rect`'s clamp is scale-
  invariant — `PILL_R * s` still clamps to exactly `height/2` at any `s`,
  same as `CARD_R * s` staying a fixed 12px-equivalent radius at any `s`.
  No special-casing needed.
- **Eating card show/hide at runtime** (`_select`, `1163-1168`,
  `self.eat_card.pack(fill="x")` / `.pack_forget()`). `self.eat_card` is now
  a `tk.Canvas`, not a `tk.Frame` — both support `.pack()`/`.pack_forget()`
  identically, so this keeps working with no code change at the call site,
  but is exactly the kind of thing that must be exercised by a test (see
  Acceptance criteria), not just reasoned about.
- **Window resize** (once `#14` merges — `content`/`body` grow to fill extra
  width). `card()`'s `shell.bind("<Configure>", _redraw)` re-measures `shell.
  winfo_width()` on every resize, so a wider window widens the card's drawn
  shape to match, not just its embedded content. Before `#14` merges, the
  window is fixed-size, so this path exists but its "wider" case isn't
  exercised until then — noted, not a blocker for this feature to merge on
  its own.
- **Segoe UI unavailable** (`__main__`'s `tkfont.families()` fallback,
  `1569-1571`). Untouched by this feature; theme colors are independent of
  font choice.
- **Contrast.** Deepslate's nine values are exactly the mock's own
  already-WCAG-checked "Chosen" set (`theme-board.html`'s `checksHTML`
  function, run against the `deepslate`/`quartz` entries) — this feature
  reproduces them faithfully rather than re-deriving contrast ratios.
- **`THEMES["light"]` defined but unread.** Confirmed dead-but-intentional
  (see Non-goals) — flagged with an inline comment specifically so Round 9
  doesn't mistake it for accidental dead code.

## Acceptance criteria
- [ ] `afk_clicker.THEMES["dark"]` and `["light"]` each contain
  `BG`/`CARD`/`CARD_HI`/`LINE`/`INK`/`MUTED`/`ACCENT`/`ACCENT_INK`/
  `ACCENT_HI`/`OK`/`BAD`; the nine ticket-given hex values per theme match
  exactly (Deepslate: `#15171a #1c1f23 #262a30 #3a4048 #e4e7ea #9299a3
  #e08a55 #5cc9a4 #f06262`; Quartz: `#e8ebf0 #ffffff #eff2f7 #d3d8e0 #161a22
  #596170 #2b58cc #0f7f4c #cc3527`); `ACCENT_INK` matches the mock's
  `deepslate`/`quartz` `t.ACCENT_INK` (`#1a0f08` / `#ffffff`).
- [ ] The derived module names (`afk_clicker.BG`, `.CARD`, …, `.ACCENT_HI`)
  equal `THEMES["dark"]`'s corresponding values — i.e. the app still ships
  dark-only.
- [ ] Given `Button`/`Segmented`/`StatusPill` are constructed with
  `round_rect` monkeypatched to record its `r` keyword, then the recorded
  radius equals `PILL_R * s` for each of their `round_rect` calls (`Button`'s
  shape, `Segmented`'s track and selection pill, `StatusPill`'s shape).
- [ ] Given `card()`/`GameItem` are constructed the same way, then the
  recorded radius equals `CARD_R * s`.
- [ ] Given a `card()` instance, when its shell is inspected, then
  `isinstance(shell, tk.Canvas)` is true, `int(shell.cget("highlightthickness"))
  == 0`, and the round_rect shape's `outline` config is `""` — confirming
  the border is genuinely gone, not just visually thin.
- [ ] Given the eating card (`self.eat_card_inner.master`), when a
  non-eating profile is selected (`_select`) then a profile with `eating:
  True`, then `.pack_forget()`/`.pack(fill="x")` on the canvas shell hide and
  reshow it exactly as they did on the pre-feature `Frame`-based card — a
  non-regression check on the `.master`-based show/hide idiom.
- [ ] Given `card()`'s `inner` Frame gains or the `shell`'s packed width
  changes (simulate via `root.update()` after a `configure(width=...)` on a
  parent, or after `#14`'s resize path once merged), when `<Configure>`
  fires, then the shape is redrawn at the new bounds (no stale/clipped
  shape) — check via the shape's `coords()` bounding box matching
  `shell.winfo_width()`/`winfo_height()` after the update.
- [ ] `afk_clicker.CARD_INNER_W == CONTENT_W - 2 * CARD_R` (428, given
  `CONTENT_W == 452`).
- [ ] Given a primary `Button`, when hovered, then its shape's `fill`
  equals `THEMES["dark"]["ACCENT_HI"]`, and its label's `fill` equals
  `THEMES["dark"]["ACCENT_INK"]` in both hover and non-hover states — a
  regression check that these no longer read the old hardcoded
  `"#ffd66b"`/`"#12131a"` literals.
- [ ] The full existing suite (`DISPLAY=:99
  .../scratchpad/venv/bin/python -m unittest discover -s tests -t .`) still
  reports the 84-test, OK, 5-skipped baseline (no existing test broken by
  the `card()`/radius/theme changes).

## Open questions
None blocking for this feature specifically — it's data plus a shape rewrite
with no runtime switching to get wrong yet. The three genuinely open
questions for the story as a whole (rebuild-vs-restart, whether to land a
schema version anyway, UI scale's exact steps) are in `docs/story.md` and
don't affect this feature's scope.

## Risk / rollback notes
- The `THEMES`/derived-constants change is additive and mechanical — every
  existing `bg=BG`/`fill=CARD`/etc. call site is untouched, only the values
  those names resolve to change, so a revert is a straight diff revert with
  no follow-on cleanup.
- `card()`'s rewrite is the single riskiest piece (new canvas-embedding
  technique, first use of `create_window` in this file) — if it turns out
  fragile in practice (e.g. a `<Configure>` storm on some platform, or a
  layout that doesn't redraw cleanly), the safe fallback is reverting just
  `card()` to its current `Frame`-based form while keeping every other
  radius/color change, since nothing else in this feature depends on
  `card()`'s internals — `_build_content`'s three call sites only rely on
  `card()`'s return value behaving like a packable `Frame`, which a revert
  restores exactly.
- No settings/data-format risk: this feature touches no persisted state.
