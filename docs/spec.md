# Spec: Icon rail — collapsing sidebar + rederived minimum width (story #24, Feature 3 of 5)

## Summary
Below a width threshold, the sidebar (`self.side`, `afk_clicker.py:1698-1729`)
collapses from its full `GameItem`/`SettingsItem` name-and-dot rows to a
narrow icon-only rail — width alone changes, navigation does not. The window's
`root.minsize()` floor (`_apply_minsize()`, `afk_clicker.py:1632`) is
rederived so the new, smaller floor actually reflects a *collapsed* rail, not
the always-expanded one it assumes today; without that change the collapse
threshold could never actually be reached, since `minsize()` is a hard WM
floor. The collapse trigger is **debounced on threshold-crossing**, reusing
`_request_rebuild()`/`_rebuild_ui()`'s existing coalescing machinery rather
than adding a second, live-toggle rebuild path — see "The debounce decision"
below for why.

## The debounce decision (settled here, not re-litigated downstream)
**Chosen: debounce-on-threshold-crossing (`docs/history/ac-24-story.md`'s
option 1).** A `<Configure>` handler bound once on `root` does a cheap width
comparison against a threshold and calls `_request_rebuild()` only when the
collapsed/expanded state actually flips — not on every pixel of a drag.

**Why not the in-place toggle (option 2):** it would need its own teardown/
rebuild path for exactly one visual transition, duplicating logic
`_rebuild_ui()` already owns for every other trigger in the file (Appearance,
UI-scale, Settings open/close), and — critically — it would *not* get
`_rebuilding`/`_rebuild_wanted`'s crash protection for free. `_rebuild_ui()`'s
own docstring (`afk_clicker.py:1791-1850`) is explicit that a second rebuild
landing mid-flight of another has already caused a real crash (Defect 1,
`docs/history/ac-17-f3a-test-review.md`), and a live resize drag firing
`<Configure>` dozens of times a second is exactly the kind of continuous
input that machinery was built to survive. A parallel in-place toggle would
need to reinvent that protection for the one path that can *also* race a
genuine Appearance/UI-scale rebuild (nothing stops a user from picking a
theme while mid-drag) — the debounce option instead calls the exact same
`_request_rebuild()` every other trigger calls, so that race is already
handled, proven, and reviewed.

**Why debouncing on state-flip, not on a timer:** a naive `after(150, ...)`
debounce would still eventually fire once per drag regardless of whether the
state actually changed, and would introduce a new made-up delay constant with
no principled value. Comparing against the threshold and only acting on an
actual flip means: zero rebuilds for a resize that never crosses it (the
overwhelmingly common case — most drags don't cross the threshold at all),
and exactly one coalesced rebuild request per crossing, timed by the existing
`after_idle` machinery rather than a guessed interval.

## Goals
- `self.side` collapses to a fixed icon-only width below a threshold, and
  returns to its full expanded width above it — one threshold, no hysteresis
  gap, matching Decision 3 (`docs/history/ac-24-story.md`, "the rail is
  pinned; it only collapses... it does not grow on wide windows").
- Every rail item (`GameItem`, `SettingsItem`) keeps navigating correctly by
  click in both states — the collapse is purely visual (story's own
  end-to-end acceptance criterion).
- `_apply_minsize()`'s floor is rederived from the *collapsed* rail width,
  not the expanded one, so the window can actually be dragged down to a
  genuinely small size (Decision 4) — while the window's own **default
  launch size** stays exactly what it is today (unchanged, still expanded),
  since minsize (the floor) and the startup geometry are no longer the same
  number.
- `GameItem`/`SettingsItem` gain a real icon glyph usable both expanded (small,
  next to the label, as today's dot already is) and collapsed (the sole
  visible content) — see "Icon mechanism" below for what the glyph actually
  is and why.
- Threshold-crossing is debounced through the existing `_request_rebuild()`/
  `_rebuild_ui()` coalescing, not a second rebuild path (see decision above).

## Non-goals
- No change to `content`'s own width, `Row`, `CARD_INNER_W`, or `CONTENT_W`.
  The new minimum floor is entirely a rail-width change — content keeps
  exactly today's tuned `CONTENT_W`, at every window size the app supports,
  collapsed rail or not (see "Deriving the new floor" below for why shrinking
  content further was considered and rejected). Any further content
  shrinking is out of scope here, and isn't needed for Decision 4's "genuinely
  small" floor — the rail alone gives up ~144px.
- No accent-color change (Feature 5) and no rounded-vs-flat chrome change
  (also Feature 5) — `CARD_R`, `PILL_R`, `round_rect()` are untouched; the new
  icon badge reuses `create_oval`, the same primitive `GameItem`'s existing
  dot already uses.
- No vertical-fill change (Feature 4).
- No hover tooltip revealing a collapsed item's full name. No tooltip
  mechanism exists anywhere in this file today, and building one is a new,
  separate UI primitive this feature does not need to introduce — a
  collapsed item's own initial-letter glyph plus its running/selected state
  is judged sufficient identification (see "Icon mechanism" for the accepted
  limitation this implies: two profiles sharing a first letter render
  identical collapsed badges apart from state color, exactly as two idle
  games already render identical `LINE`-colored dots today).
- No persistence of rail-collapsed state across a restart. `self._rail_collapsed`
  is a plain instance attribute, session-only, following the exact precedent
  already established for `self._content_tab`/`self._settings_tab`/
  `self._settings_open` — never read from or written to `settings.json`. A
  restart always launches expanded, regardless of what size the window was
  last closed at (window geometry itself is not persisted anywhere today
  either — nothing here changes that).
- No bespoke vector icon set (e.g., a hand-drawn gear for Settings). See
  "Icon mechanism" for why a uniform initial-letter badge was chosen instead,
  and what a future upgrade would look like.
- No new "Add current game" behavior — same command, same thread-based scan,
  just a shorter label when collapsed (see "The 'Add current game' button").

## Background / current state

**The two panes today** (`_build_ui(s)`, `afk_clicker.py:1670-1789`): `side`
(`:1698`, `pack_propagate(False)`, fixed `width=int(SIDEBAR_W * s)`) and
`content` (`:1725`, also `pack_propagate(False)` but `fill="both",
expand=True` lets `pack` hand it extra width when the window grows — this is
already why content stretches today and the sidebar never has).

**`GameItem`** (`afk_clicker.py:1408-1440`) draws, per instance: a rounded
background shape (`round_rect(..., CARD_R * s, ...)`, the hover/selected
fill), a small state dot (`create_oval`, 7px, `fill=OK` running / `LINE`
idle), and the profile's name as left-anchored text at `x=30*s`. `_paint()`
(`:1436-1440`) only ever `itemconfig`s three canvas item ids by their stored
handles (`self.shape`/`self.dot`/`self.text`) — it never re-reads their
geometry, only their fill/text.

**`SettingsItem`** (`:1443-1483`) is structurally the same minus the running
dot (there's nothing to run) plus `has_update` (`docs/history/
ac-17-f3b-spec.md`), rendered today as swapping the text to `"Settings ·
Update"` in `ACCENT`.

**`_apply_minsize()`** (`:1632-1650`): `minw = int((SIDEBAR_W + 1 + CONTENT_W)
* self.s)`, and — critically — this single formula also sets the window's
*default launch geometry* on the very first call (`grow_only=False`:
`root.geometry(f"{minw}x{minh}")`). Minsize and default-startup-size are the
same number today. This feature has to break that coupling: the new minsize
floor must shrink (to admit a collapsed rail), but the app must still *launch*
at today's familiar expanded size, not immediately at the new, smaller floor
— see "Deriving the new floor."

**`_request_rebuild()`/`_rebuild_ui()`** (`:1655-1667`, `:1791-1876`): at most
one rebuild ever pending (`_rebuild_after_id`) or running (`_rebuilding`);
a request arriving while one is running only sets `_rebuild_wanted`, serviced
by the `finally` block once the running one finishes. This exists because a
second rebuild landing mid-flight of the first has previously crashed the app
(see `_rebuild_ui()`'s own docstring). Every existing trigger — an Appearance
pick, a UI-scale pick, opening/closing Settings — fires this once, discretely.
Nothing before this feature has ever driven it from a continuous event
stream.

**`_rebuild_list()`** (`:2207-2215`) is the one place `GameItem`s are actually
constructed, and it is called both from `_build_ui()` and, independently
(without a full `_rebuild_ui()`), from `_add_game()` (`:2280-2293`) when a new
custom game is added mid-session.

## Icon mechanism: an initial-letter badge, not per-game artwork

`docs/TECHSTACK.md` is explicit about why this project carries no third-party
dependency: every one is a chance for PyInstaller's static analysis to miss
something and ship a binary that silently fails to launch, for an app whose
whole job doesn't need it. The same reasoning rules out a per-game icon asset
pipeline here, independent of any packaging risk: `self.profiles`
(`afk_clicker.py:1712`) is not a fixed, enumerable set — it's `PROFILES` plus
whatever `make_profile()` builds on the fly for a custom game added via
"Add current game" (`_add_game`, `:2280`), keyed off whatever window title
`foreground_title()` happens to return. There is no art to ship for a game
nobody has named yet, and no image library in this stack to source one live
even if there were (`docs/TECHSTACK.md`: "GUI: tkinter only").

**What the reference actually shows two different things.** The story's own
two screenshots are two different UI patterns, not one:
- `01-system-performance.png`'s left rail (Home/Drivers/Graphics/System/
  Redeem/Settings) is a **fixed, small set of generic nav destinations**,
  each a hand-drawn vector glyph, icon stacked above label. This is the
  pattern this story calls "the icon rail."
- `02-graphics-program-settings.png`'s list (Portal, DaVinci Resolve, Alan
  Wake 2, ...) is **per-program box art** — real images, one per installed
  program, sourced from each game's own store listing.

Our sidebar's list is a `GameItem`-per-profile row, i.e. structurally the
second pattern (a per-entry, per-*item* list, not a small fixed nav set) —
but unlike NVIDIA's list, our items have no backing artwork source. So this
spec proposes the *first* pattern's simplicity (one flat, generic vector
treatment) applied to content shaped like the *second* (arbitrary, growing,
user-defined entries): a single mechanism that needs no asset per item and
degrades gracefully to any future profile name.

**The mechanism**: a centered circular badge (`create_oval`, the same
primitive `GameItem`'s own dot already uses — no new drawing primitive) with
the profile name's first character, uppercased, drawn on top via
`create_text`. The badge's fill still carries the running/idle signal exactly
as today's dot does (`OK`/`LINE`); the letter's fill still carries
selected/running vs. idle exactly as today's text fill does (`INK`/`MUTED`).
`SettingsItem` gets the literal letter `"S"` the same way, for the same
reason: one mechanism, not two, and no bespoke gear icon to hand-draw and
tune across four UI-scale steps for a project this size. `SettingsItem`'s
`has_update` signal (today: swapping the whole label to `"Settings · Update"`
in `ACCENT`) becomes a small `ACCENT` corner dot on the collapsed badge when
collapsed — this mirrors the reference's own "Redeem" nav icon, which shows
exactly this small accent-dot-on-icon pattern for a pending-action signal
(`01-system-performance.png`), so it isn't an invented convention.

**A known, accepted limitation**: two profiles sharing a first letter (e.g.
a hypothetical "Minecraft" and "Minetest") render identical collapsed badges
apart from running-state color. This is judged acceptable — see Non-goals —
and is not new in kind: two *idle* games already render identical
`LINE`-colored dots today; this just extends the same ambiguity to the label
too, only while collapsed, only for entries a user has typed the same first
letter of.

**Left open, deliberately**: whether a real hand-drawn glyph set (matching
the reference's actual vector icons more closely) is worth the investment for
`SettingsItem` — Settings *is* a fixed, single, enumerable destination, so
the "no per-item artwork" argument above doesn't apply to it the way it does
to `GameItem`. This spec proposes the same initial-letter mechanism for both,
for consistency and the smallest diff, but flags this explicitly as a
design-stage call the ux-designer is free to override for `SettingsItem`
alone (see Open questions) — exactly the status Feature 2's `TabBar` pixel
constants had.

## Proposed approach

### 1. New constants (placed with `SIDEBAR_W`/`CONTENT_W`, `afk_clicker.py:160-161`)

```python
SIDEBAR_RAIL_W = 64          # collapsed rail width -- room for a centered
                              # COLLAPSED_BADGE_D badge plus symmetric
                              # margin either side (64 - 28 = 36, 18px each
                              # side), narrower than any real game name on
                              # purpose. Proposed starting point, same status
                              # ROW_LABEL_W/TabBar's pixel constants had --
                              # open to the ux-designer's/reviewer's tuning.
RAIL_COLLAPSE_THRESHOLD = SIDEBAR_W + 1 + CONTENT_W
    # Collapse exactly at today's old expanded-only minimum width -- the
    # number that used to be the *entire* floor before this feature. Below
    # it, the expanded rail plus a full CONTENT_W no longer both fit; above
    # it, this feature changes nothing about today's behavior. Reusing the
    # existing constants ties "when does it collapse" to "when does the
    # current layout stop fitting," rather than a second, independently
    # guessed number.
COLLAPSED_BADGE_D = 28        # collapsed-badge diameter -- big enough to
                              # read one capital letter at the smallest
                              # UI-scale step (90%). Centered dynamically off
                              # the canvas's own w/h (unlike ROW_LABEL_W's
                              # fixed offset), so unlike Row's fixed-column
                              # design this needs no separate per-scale
                              # fit-check: centering scales with s by
                              # construction.
```

### 2. `self._rail_collapsed`: one plain attribute, two writers

Initialized in `__init__`, next to `self._settings_open`
(`afk_clicker.py:1587`):

```python
self._rail_collapsed = False   # the rail always launches expanded (see
                                # "Deriving the new floor" -- the app's
                                # default geometry is always >= the
                                # threshold by construction, so False is
                                # correct on first launch without querying
                                # anything). Session-only, same precedent as
                                # self._settings_open/_content_tab/
                                # _settings_tab: never persisted, survives
                                # _rebuild_ui() untouched (plain attribute,
                                # not a Tk object).
```

**Writer 1 — re-derived at the top of every `_build_ui(s)` call**
(`afk_clicker.py:1670`), before anything is built:

```python
if self.root.winfo_ismapped():
    self._rail_collapsed = (
        self.root.winfo_width() < int(RAIL_COLLAPSE_THRESHOLD * s))
# else: root has never been drawn yet (this is the very first _build_ui()
# call, from __init__, before any event loop has run) -- winfo_width() would
# return Tk's unmapped placeholder (0 or 1, platform-dependent), not the
# just-requested geometry, the exact hazard class docs/spec.md's "Test
# impact" describes for a hidden pane's geometry. winfo_ismapped() is the
# standard, reliable guard for this -- unlike winfo_width() on an unmapped
# widget, it does not return a plausible-looking wrong answer, it returns
# False. Leave self._rail_collapsed at whatever __init__ set (False).
```

This is why the value is re-derived, not just read: **`self.s` can change
between builds** (a UI-scale pick), and `RAIL_COLLAPSE_THRESHOLD * self.s`
changes with it — a window whose raw pixel width never moved can still
legitimately flip collapsed/expanded purely because the UI got bigger or
smaller around it. Re-deriving from live geometry on every build closes that
gap for free; trusting a value only ever set by the `<Configure>` handler
below would not (that handler only fires when `root`'s own pixel width
actually changes, which a UI-scale change alone does not guarantee — see
`_apply_minsize(grow_only=True)`, which only calls `root.geometry(...)` when
the window is *currently smaller* than the new floor).

**Writer 2 — the debounced `<Configure>` handler**, bound once in `__init__`,
after `self._rebuild_wanted = False` (`afk_clicker.py:1607`) — i.e. after
every attribute `_request_rebuild()` reads exists, following the exact
precedent already set for `root.bind_all("<Button-1>", self._maybe_drop_focus)`
(`:1560`, "bound once, here — NOT inside `_build_ui()`: root itself survives
every rebuild"):

```python
self.root.bind("<Configure>", self._on_root_resize)
```

```python
def _on_root_resize(self, event):
    """Debounce the rail's collapse check, not the collapse itself (story
    #24 feature 3): a live resize drag fires <Configure> continuously, but
    _request_rebuild() must only ever be called on an actual state flip --
    see docs/spec.md's 'The debounce decision.'

    event.width is trustworthy unconditionally here (Tk only ever fires a
    real <Configure> for a widget that has actually just been drawn/resized
    -- unlike a bare winfo_width() query, there is no unmapped-placeholder
    risk on an event Tk itself generated), so this needs none of _build_ui()'s
    own winfo_ismapped() guard.
    """
    collapsed = event.width < int(RAIL_COLLAPSE_THRESHOLD * self.s)
    if collapsed != self._rail_collapsed:
        self._rail_collapsed = collapsed
        self._request_rebuild()
```

Reusing `_request_rebuild()` verbatim is what makes this safe against every
hazard `_rebuild_ui()`'s own docstring already documents and defends against:
a flip landing while a rebuild is already running only sets
`_rebuild_wanted` (exactly the same path an Appearance change racing a
UI-scale change already takes); a flip landing while one is already pending
is a no-op (the `elif self._rebuild_after_id is None` branch already
short-circuits it) — no new locking, no new state machine, the same proven
mechanism every other trigger already uses.

### 3. `_apply_minsize()`: two different numbers where there was one

```python
def _apply_minsize(self, grow_only=False):
    minw = int((SIDEBAR_RAIL_W + 1 + CONTENT_W) * self.s)
    minh = int(690 * self.s)
    self.root.minsize(minw, minh)
    if not grow_only:
        default_w = int((SIDEBAR_W + 1 + CONTENT_W) * self.s)
        self.root.geometry(f"{default_w}x{minh}")
        return
    cur_w, cur_h = self.root.winfo_width(), self.root.winfo_height()
    new_w, new_h = max(cur_w, minw), max(cur_h, minh)
    if (new_w, new_h) != (cur_w, cur_h):
        self.root.geometry(f"{new_w}x{new_h}")
```

Only two lines actually change: `minw`'s formula (`SIDEBAR_RAIL_W` instead of
`SIDEBAR_W` — this is the "genuinely small" floor from Decision 4), and the
`not grow_only` branch, which now computes its own `default_w` off the *old*
formula instead of reusing `minw` — this is the one deliberate decoupling
this feature introduces: **the hard floor and the default launch size are no
longer the same number.** The `grow_only=True` branch (called from
`_apply_ui_scale`, `afk_clicker.py:2148`) needs no change at all: `minw` being
smaller only ever makes `max(cur_w, minw)` less likely to force growth, never
more — a UI-scale bump on an already-collapsed, narrow window correctly does
not yank it back wide.

### 4. Deriving the new floor: why content is untouched

Decision 4 asks for "roughly the collapsed rail plus a usable content
column." The obvious naive move is to also shrink `CONTENT_W`, but the
existing fit-check test
(`test_ui_scale_row_never_overflows_its_card_at_any_scale_step`,
`tests/test_ui.py:806-819`) already asserts, unscaled: `ROW_LABEL_W +
ROW_LABEL_GAP + 220 <= CARD_INNER_W`, i.e. `140 + 12 + 220 = 372 <= 396`. That
is only 24px of slack at `CONTENT_W`'s *current* value — there is essentially
no room to shrink content further without either overflowing the widest
existing row (the UI-scale `Segmented`, 220px wide) or reopening Feature 1's
already-settled row-alignment work to retune `ROW_LABEL_W`/`CARD_INNER_W`,
which is out of scope for a feature about the rail. The floor this spec
proposes instead keeps `CONTENT_W` completely untouched and gets "genuinely
small" entirely from the rail: `SIDEBAR_W - SIDEBAR_RAIL_W = 208 - 64 = 144px`
recovered, at zero risk to any already-tuned row.

### 5. `GameItem`/`SettingsItem`: `collapsed` decides what's drawn, not how it's painted

`GameItem.__init__` (`afk_clicker.py:1408`) gains one new parameter and
changes `width`'s default from a concrete number to a per-call decision:

```python
def __init__(self, parent, profile, on_click, s, collapsed=False,
             width=None, height=38):
    if width is None:
        width = SIDEBAR_RAIL_W - 16 if collapsed else SIDEBAR_W - 16
    super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0,
                     cursor="hand2", width=int(width * s), height=int(height * s))
    self.profile = profile
    self.on_click = on_click
    self.collapsed = collapsed
    self.selected = False
    self.running = False
    w, h = int(width * s), int(height * s)
    self.shape = round_rect(self, 1, 1, w - 1, h - 1, CARD_R * s, fill=BG, outline="")
    if collapsed:
        d = COLLAPSED_BADGE_D * s
        cx, cy = w / 2, h / 2
        self.dot = self.create_oval(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2,
                                    fill=LINE, outline="")
        initial = profile["name"][:1].upper() if profile["name"] else "?"
        self.text = self.create_text(cx, cy, text=initial, fill=MUTED,
                                     font=("Segoe UI", int(10.5 * s), "bold"))
    else:
        self.dot = self.create_oval(12 * s, h / 2 - 3.5 * s, 19 * s, h / 2 + 3.5 * s,
                                    fill=LINE, outline="")
        self.text = self.create_text(30 * s, h / 2, anchor="w", text=profile["name"],
                                     fill=MUTED, font=("Segoe UI", int(9.5 * s)))
    self.bind("<Enter>", lambda e: self._paint(hover=True))
    self.bind("<Leave>", lambda e: self._paint())
    self.bind("<Button-1>", lambda e: self.on_click(self.profile["id"]))
    self._paint()
```

**`_paint()` needs zero changes.** It only ever `itemconfig`s `self.shape`/
`self.dot`/`self.text` by their stored canvas-item ids
(`afk_clicker.py:1436-1440`) — it has never cared about their geometry, only
their fill/text values, and the same three fill rules (`CARD_HI`/`CARD`/`BG`
for the shape; `OK`/`LINE` for the dot; `INK`/`MUTED` for the text) are
correct whether `self.dot`/`self.text` are the small dot-and-label pair or
the collapsed badge-and-letter pair. This is the whole reason `collapsed`
only branches inside `__init__`: everything downstream of construction is
already state-shape-agnostic.

`SettingsItem` gets the structurally identical treatment: same
`collapsed`/`width=None` parameters, same collapsed branch (badge + `"S"`),
plus the corner `ACCENT` dot when `collapsed and has_update` (a fourth,
small `create_oval`, only ever created in the collapsed branch — expanded
mode is untouched, still the existing `"Settings · Update"` text swap).

**Call sites** (`_build_ui`, `afk_clicker.py:1698-1729`, and `_rebuild_list`,
`:2207-2215`) pass `collapsed=self._rail_collapsed` and `width=int((SIDEBAR_RAIL_W
if self._rail_collapsed else SIDEBAR_W) * ... )` — actually just
`collapsed=self._rail_collapsed`, since `width=None`'s own default already
resolves correctly from that same flag. `_rebuild_list()` needs no other
change: it already re-reads `self.s`/`self.profiles` fresh on every call
(including the standalone call from `_add_game()`, `:2292`, which runs
without a full `_rebuild_ui()`), so reading `self._rail_collapsed` the same
way keeps a mid-session "Add current game" correctly matching whatever rail
state is currently visible.

### 6. `side`'s own width, and what gets hidden when collapsed

`afk_clicker.py:1698-1699`:

```python
side = self.side = tk.Frame(
    shell, bg=BG,
    width=int((SIDEBAR_RAIL_W if self._rail_collapsed else SIDEBAR_W) * s))
```

Two things stop being packed when `self._rail_collapsed` (both are still
*constructed* unconditionally, so no other code needs an `if hasattr(...)`
guard — this mirrors the "always build, only toggle visibility" convention
Feature 2 established for its own tab panes, `afk_clicker.py`'s
`_build_content`/`_build_settings`):
- `self.count_label` ("GAMES N") — no room for it at `SIDEBAR_RAIL_W`, and
  the reference's own icon rail (`01-system-performance.png`) has no
  section header above its icons either. `_rebuild_list()`'s existing
  `self.count_label.config(text=...)` call (`:2215`) is untouched — it's
  legal to configure an unpacked widget's text, so this needs no guard.
- Nothing else — the divider (`tk.Frame(side, bg=LINE, height=1)`,
  `:1721-1722`) and the "Add current game" button both still render, just
  narrower (see next section).

### 7. The "Add current game" button

`Button` (`afk_clicker.py:1172-1210`) already takes `text`/`width` as plain
constructor arguments — no new widget or mechanism needed, just a shorter
label when collapsed, reusing the exact `-28` inset convention the existing
call site already uses:

```python
label = "+" if self._rail_collapsed else "Add current game"
width = (SIDEBAR_RAIL_W if self._rail_collapsed else SIDEBAR_W) - 28
Button(side, label, self.add_current_game, s, width=width).pack(
    pady=(int(12 * s), int(4 * s)))
```

`self.add_current_game`/`_add_game()` (`:2274-2293`) receive no changes at
all — same command, same background thread, same
`foreground_title()`-driven scan. Collapsing only ever changes what's drawn,
never what a click does, satisfying the story's own "purely visual, never
functional" criterion for this control too, not just the rail items.

## Affected areas
- `afk_clicker.py` only:
  - Three new constants (`SIDEBAR_RAIL_W`, `RAIL_COLLAPSE_THRESHOLD`,
    `COLLAPSED_BADGE_D`), placed with `SIDEBAR_W`/`CONTENT_W` (`:160-161`).
  - One new instance attribute (`self._rail_collapsed`) and one new bound
    method (`_on_root_resize`), placed near `self._settings_open`/the
    `bind_all` call (`:1560-1607`).
  - `_apply_minsize()` (`:1632-1650`): `minw`'s formula, and a new
    `default_w` in the `not grow_only` branch.
  - `_build_ui(s)` (`:1670-1789`): the `winfo_ismapped()`-guarded
    re-derivation at the top; `side`'s width; `count_label`'s pack call
    becomes conditional; the "Add current game" `Button`'s label/width;
    `GameItem`/`SettingsItem`/construction passes `collapsed=`.
  - `GameItem.__init__`/`SettingsItem.__init__` (`:1408-1483`): the new
    `collapsed` parameter and construction branch. `_paint()` on both:
    unchanged.
  - `_rebuild_list()` (`:2207-2215`): pass `collapsed=self._rail_collapsed`
    to each `GameItem(...)` call.
- No data model, schema, or API changes — `Store`/`settings.json` untouched
  (rail-collapsed state is session-only, see Non-goals).
- One test file, `tests/test_ui.py` — see "Test impact" below.

## Edge cases
- **Exact-threshold width**: `width < threshold` is a strict inequality, so
  a window exactly at the threshold stays expanded — deterministic, no
  flicker at the boundary in either direction.
- **A drag oscillating right at the threshold**: each crossing calls
  `_request_rebuild()`, but `_rebuild_ui()` only actually runs once Tk goes
  idle (`after_idle`) — a continuous drag keeps generating more `<Configure>`
  events before the loop ever idles, so in practice this coalesces to (at
  most) one rebuild per pause in the drag, exactly the existing
  `_rebuilding`/`_rebuild_wanted` guarantee already gives every other
  trigger.
- **A `<Configure>` firing reentrantly mid-rebuild**: `_rebuild_ui()`'s own
  `_redraw()`-triggered `update_idletasks()` calls (see its docstring,
  `:1791-1850`) can reentrantly service other queued callbacks while a
  rebuild is running. If `_on_root_resize` fires in that window and flips
  `self._rail_collapsed`, `_request_rebuild()` correctly only sets
  `self._rebuild_wanted` (the `if self._rebuilding:` branch) rather than
  scheduling a second rebuild — this is precisely the scenario that
  machinery exists for, not a new hole this feature opens.
- **A UI-scale change flips the derived state without root's raw pixel width
  ever moving**: handled by `_build_ui()`'s own top-of-function
  re-derivation (§2, Writer 1), which recomputes from *current* `self.s`
  every single build — not by the `<Configure>` handler, which only fires
  when `root`'s pixel geometry itself actually changes and would otherwise
  miss this case.
- **The very first `_build_ui()` call, before `root` is ever mapped**:
  `winfo_width()` would return Tk's unmapped placeholder, not the
  just-requested geometry — guarded by `winfo_ismapped()` (§2), leaving
  `self._rail_collapsed` at its `__init__`-set `False`, which is always
  correct on first launch since the default geometry is always `>=` the
  threshold by construction (§3's `default_w` uses the same, unchanged
  `SIDEBAR_W`-based formula the threshold itself is derived from).
- **A collapsed `GameItem`/`SettingsItem` click**: unaffected — the
  `<Button-1>` binding (`lambda e: self.on_click(self.profile["id"])` /
  `lambda e: self.on_click()`) is identical in both branches; only what's
  drawn under it changes.
- **Two profiles sharing a first letter**: accepted, not solved — see Non-
  goals and "Icon mechanism."
- **`_apply_minsize(grow_only=True)`'s own `root.geometry(...)` call
  (`_apply_ui_scale`, `:2148-2149`) generating a `<Configure>` that lands
  after `_request_rebuild()` has already been called synchronously right
  after it**: harmless regardless of arrival order, by the same
  `_request_rebuild()` coalescing already relied on throughout — at most one
  rebuild results either way.

## Test impact, argued per case

**Required changes — the minsize floor formula moved (`SIDEBAR_W` →
`SIDEBAR_RAIL_W`) everywhere it's asserted exactly:**
- `WindowResize.test_minsize_matches_todays_default_size`
  (`tests/test_ui.py:743-746`) — **rename and update.** The name is no longer
  accurate: minsize and the default launch size are now deliberately
  different numbers (§3). Rename to
  `test_minsize_reflects_the_collapsed_rail_floor` and assert:
  `expected = (int((app.SIDEBAR_RAIL_W + 1 + app.CONTENT_W) * s), int(690 * s))`.
- `UIScale.test_minsize_updates_on_every_scale_change` (`:2027-2033`) — same
  formula swap (`SIDEBAR_W` → `SIDEBAR_RAIL_W`), same reasoning: this test
  runs at default (expanded, never manually resized) window state throughout,
  proving the floor itself is always `SIDEBAR_RAIL_W`-based regardless of
  what's currently *visible* — the floor is a property of `self.s`, not of
  `self._rail_collapsed`.
- `UIScale.test_a_manually_enlarged_window_is_never_shrunk_by_a_scale_change`
  (`:2044-2051`) — **no change required.** It uses `SIDEBAR_W`-based math only
  to derive a value guaranteed to exceed *any* real floor before manually
  enlarging past it (`big_w = min_w + 200`); since the real floor is now
  smaller, this stays a safe (if now over-generous) margin. Leaving it
  matches "don't touch what doesn't need touching," though a one-line
  comment noting the constant is now doing double duty (a safe upper bound,
  not the literal floor) would help the next reader.

**Required changes — the old rigid-sidebar assumption is what this story
exists to break:**
- `WindowResize.test_growing_the_window_expands_content_not_the_sidebar`
  (`:748-754`) — **replace**, per the story's own explicit instruction. Its
  `self.assertEqual(self.ui.side.winfo_width(), side_before)` is the literal
  "sidebar is always rigid" assumption. Split into:
  - `test_rail_stays_at_expanded_width_on_a_wide_window` — grow well above
    the threshold (e.g. `geometry("1400x900")`, clamped-safe per the existing
    900x760 precedent used elsewhere in this file for CI display limits);
    assert `self.ui.side.winfo_width() == int(app.SIDEBAR_W * self.ui.s)`
    unchanged, and `self.ui.content.winfo_width()` grows — the direct
    replacement for the deleted assertion, covering Decision 3 ("it does not
    grow on wide windows").
  - `test_shrinking_past_the_threshold_collapses_the_rail` — resize to a
    width between the new floor and the threshold; assert
    `self.ui.side.winfo_width() == int(app.SIDEBAR_RAIL_W * self.ui.s)` and
    `self.ui._rail_collapsed is True`.
  - `test_growing_back_past_the_threshold_re_expands_the_rail` — from a
    collapsed window, grow back above the threshold; assert re-expansion,
    proving there's no hysteresis/dead zone (Decision 3, one threshold).

**New tests needed** (a new `RailCollapse(UITestCase)` class):
- `test_rail_starts_expanded_at_default_launch` — freshly constructed `ui`:
  `self.ui._rail_collapsed is False`, `self.ui.side.winfo_width() ==
  int(app.SIDEBAR_W * s)`, and a `GameItem`'s own text item reads the full
  profile name (`itemcget(item.text, "text") == profile["name"]`) — proves
  the app does not launch into the new, smaller floor by accident (the
  single most important regression this spec exists to prevent, per §3).
- `test_default_geometry_still_matches_the_old_expanded_minimum` —
  `self.root.winfo_width() == int((app.SIDEBAR_W + 1 + app.CONTENT_W) * s)`
  while `self.root.minsize()[0]` is strictly smaller — proving minsize and
  default launch size are deliberately decoupled, not accidentally reunified
  by some future edit.
- `test_collapsed_items_still_navigate_by_click` — collapse the rail
  (resize below threshold, `root.update()`), then a real `<Button-1>` on a
  collapsed `GameItem` (`event_generate`, matching the existing
  `NumBoxFocus`/`test_a_game_item_still_selects` technique,
  `tests/test_ui.py:718`) changes `self.ui.current`; same for
  `self.ui.settings_item` toggling `self.ui._settings_open` — the direct
  test of the story's own "purely visual, never functional" end-to-end
  criterion, scoped to this feature.
- `test_repeated_threshold_crossings_coalesce_to_one_rebuild` — wrap
  `self.ui._rebuild_ui` to count calls (same spy technique available via
  `CapturesCallbackExceptions`'s pattern elsewhere in this file, or a plain
  monkeypatched wrapper), then `event_generate("<Configure>", width=W,
  height=H)` on `self.root` several times oscillating across the threshold
  before a single `self.root.update()`; assert the wrapped `_rebuild_ui` was
  invoked no more than once. A second variant sends several `<Configure>`
  events that never cross the threshold and asserts zero rebuilds — proving
  the debounce is on the *flip*, not on `<Configure>` itself.
- `test_add_current_game_button_survives_collapse` — collapsed rail: exactly
  one `app.Button` still exists under `self.ui.side` (reusing
  `SettingsNavigation`'s own `winfo_children()`-filtering technique,
  `tests/test_ui.py:2137`), with a shorter label than expanded mode.

**No change, argued:**
- `WindowResize.test_both_axes_are_resizable` (`:741`) — untouched by this
  feature.
- `WindowResize.test_shrinking_below_minsize_is_clamped` (`:756-761`) — reads
  `self.root.minsize()` live, asserts only the WM-level clamp, never a
  specific width; correct regardless of which formula produced the floor.
- `test_game_item_shape_uses_card_radius_not_pill_radius` (`:1676-1677`) —
  constructs a `GameItem` with no `collapsed`/`width` args, exercising only
  the (unchanged) default-`False` branch; `self.shape`'s own `round_rect(...,
  CARD_R * s, ...)` call is unconditional, before the `if collapsed:` split,
  so this is unaffected either way.
- `SettingsNavigation`/`SettingsUpdates`/`OverlappingAppearanceChanges` and
  every other `test_ui.py` class not named above — none resize the window,
  so all run at default (expanded) rail state throughout, matching today's
  behavior exactly. `SettingsNavigation.test_sidebar_no_longer_holds_the_
  update_widgets` (`:1856-1867`) in particular is explicitly unaffected: its
  `winfo_children()`-based checks see `self.ui.count_label` and the "Add
  current game" `Button` regardless of whether they're currently *packed*
  (`winfo_children()` lists all children, mapped or not), so hiding
  `count_label` when collapsed changes nothing this test asserts, since
  the test never resizes the window and therefore never runs against the
  collapsed branch.
- No test in `test_hotkey.py`, `test_chords_slow.py`, or `test_updater.py`
  references any layout constant or `GameItem`/`SettingsItem`/`side`
  (confirmed by grep) — this feature's blast radius stays contained to
  `test_ui.py`, matching the story's own note.

## Acceptance criteria
- [ ] Given a freshly constructed app, when checking its initial state, then
      `self.ui._rail_collapsed is False`, `self.ui.side.winfo_width() ==
      int(SIDEBAR_W * s)`, and `self.root.winfo_width() == int((SIDEBAR_W + 1
      + CONTENT_W) * s)` — the app launches exactly as it does today, not at
      the new, smaller floor.
- [ ] Given the same freshly constructed app, when reading `self.root.minsize()`,
      then its width is `int((SIDEBAR_RAIL_W + 1 + CONTENT_W) * s)` — strictly
      smaller than the default launch width, proving the floor and the
      startup size are no longer coupled.
- [ ] Given the window resized below `RAIL_COLLAPSE_THRESHOLD * s`, when the
      resize settles, then `self.ui.side.winfo_width() == int(SIDEBAR_RAIL_W *
      s)`, `self.ui._rail_collapsed is True`, and every `GameItem`'s visible
      text is a single initial letter, not the full profile name.
- [ ] Given the rail collapsed, when a real `<Button-1>` lands on a
      `GameItem`/`self.ui.settings_item`, then navigation happens exactly as
      it does expanded (`self.ui.current` changes / `self.ui._settings_open`
      toggles) — the collapse is purely visual.
- [ ] Given the window resized back above `RAIL_COLLAPSE_THRESHOLD * s` from a
      collapsed state, then the rail re-expands to `SIDEBAR_W * s` — no
      hysteresis, one threshold, both directions.
- [ ] Given the window grown well above the threshold, when it keeps growing,
      then `self.ui.side.winfo_width()` stays fixed at `SIDEBAR_W * s` and
      `self.ui.content.winfo_width()` keeps growing — the rail never grows
      past its expanded width (Decision 3).
- [ ] Given a live resize drag that crosses the threshold multiple times
      before the event loop next idles, when it settles, then `_rebuild_ui`
      was invoked at most once for that settle — the debounce coalesces
      through the existing `_request_rebuild()` machinery, not a new one.
      Given a resize that never crosses the threshold, `_rebuild_ui` is
      invoked zero times.
- [ ] Given the rail collapsed, when "Add current game" is clicked, then it
      still calls `self.add_current_game` exactly as expanded — same
      command, shorter label only.
- [ ] Given the full suite (`DISPLAY=:99 .../venv/bin/python -m unittest
      discover -s tests -t .`) after this change, then it passes at the
      current baseline plus this feature's new `RailCollapse` tests, with
      exactly the "Test impact" section's required changes applied and zero
      other existing tests modified. The known `Tcl_AsyncDelete` shutdown
      flake (~1 run in 4, exit 134, no summary) is pre-existing — re-run
      once, do not chase it.

## Open questions
- **Should `SettingsItem`'s collapsed icon be a real hand-drawn glyph
  (closer to the reference's gear) instead of the same initial-letter badge
  `GameItem` uses?** Proceeding under "same mechanism, `'S'`" for the
  smallest diff and because Settings is the one destination where a bespoke
  icon would actually be justified (it's fixed and enumerable, unlike
  `GameItem`) — but this is exactly the kind of pixel/visual-identity call
  the ux-designer is better positioned to make once they can see it rendered
  against the reference, same status Feature 2's `TabBar` constants had. Not
  a blocker either way: reverting to a bespoke glyph later touches only
  `SettingsItem.__init__`'s collapsed branch.
- **Exact `SIDEBAR_RAIL_W`/`COLLAPSED_BADGE_D` pixel values** (64 / 28) are
  proposed starting points, checked only for "does a badge fit with
  reasonable margin," not against the reference screenshots' own rail width
  (which uses a different icon-above-label layout this feature doesn't
  adopt — see "Icon mechanism"). Same open-to-tuning status as every other
  pixel constant introduced by this story so far.

## Risk / rollback notes
- The single highest-risk mechanism this spec introduces — reusing
  `_request_rebuild()` from a continuous `<Configure>` stream — is designed
  to add *zero* new state machinery to `_rebuild_ui()` itself; every
  protection it relies on (`_rebuilding`/`_rebuild_wanted`/
  `_rebuild_after_id`) already exists and is already exercised by two other
  triggers. The new code is confined to: a width comparison, a bool flag,
  and a call to a method that already knows how to coalesce.
- Revert is: drop `_on_root_resize`/the `root.bind("<Configure>", ...)` call,
  drop `self._rail_collapsed` (or hardcode it `False`), revert
  `_apply_minsize()`'s two formula lines, revert `GameItem`/`SettingsItem`'s
  `collapsed` parameter and branch, revert `side`'s width and the "Add
  current game" button's label/width. No schema, no persisted state, no
  cross-file dependency — a clean, single-file revert.
- The one invariant most worth a reviewer double-checking directly (not just
  reading the diff): that a freshly launched app is provably still expanded
  — a wrong `winfo_ismapped()`/`winfo_width()` interaction here is exactly
  the class of bug that passes on Linux/Xvfb (where an unmapped widget can
  return a stale-but-plausible size) and only fails on Windows CI (where the
  same call returns 0/1) — the same hazard class flagged from Feature 2's own
  cycle. `test_rail_starts_expanded_at_default_launch` and
  `test_default_geometry_still_matches_the_old_expanded_minimum` above are
  written specifically to catch this on every platform, not just locally.
