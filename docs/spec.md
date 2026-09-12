# Spec: Flat minimal restyle (story #24, Feature 5 of 5 — last feature)

## Summary
Removes rounded-corner chrome from every card/pill/row widget (`CARD_R`,
`PILL_R`, and all six `round_rect()` call sites), applies the reference's
sparing-accent discipline to the one place that doesn't have it yet (the
rail's active item), and gives `section()` sentence-case text plus an
optional right-aligned action slot — a pure chrome pass over geometry that
Features 1–4 already settled. Nothing moves, resizes, or re-layouts.

## Goals
- **Drop rounding everywhere.** `Button`, `Segmented` (both its outer track
  and its selection pill), `StatusPill`, `card()`'s shell, `GameItem`, and
  `SettingsItem` stop calling `round_rect()` and paint a plain
  `create_rectangle` instead. `CARD_R`, `PILL_R`, `round_rect()`,
  `_round_rect_points()`, and `_arc_points()` are deleted outright, not
  zeroed out — see "Why delete rather than pass r=0" below.
- **Section headers go sentence case.** `section()` stops calling
  `text.upper()`; callers already author their strings in sentence case
  (`"Hotkey  ·  shared by every game"`, `"Eating"`), so this is a
  one-line removal, not a rewrite of call sites.
- **`section()` gains an optional right-aligned action slot** — a real,
  tested mechanism (see "The action slot has no user yet" below), not
  wired to any call site today because none needs it.
- **The active rail item gets the accent it's missing today.** Of the
  story's three named "sparing accent" homes (active rail item, active tab
  underline, selection), two already use `ACCENT` — `TabBar`'s underline
  (`afk_clicker.py:1323`) and `NumBox`'s focus ring
  (`afk_clicker.py:1658`/`1661`). `GameItem`/`SettingsItem`'s `selected`
  state currently only changes fill to `CARD_HI` — no accent anywhere. This
  feature adds one, matching the reference's own pattern of a left-edge
  accent bar on the active nav item (`handoff/nvidia-reference/
  02-graphics-program-settings.png`, the green bar beside "Graphics").
- **`StatusPill` stops being a literal pill** and becomes a flat panel like
  every other card — same fill/outline/dot/text logic, only the shape
  changes. See "What the status indicator becomes" below.

## Non-goals
- **No geometry change of any kind.** `SIDEBAR_W`, `SIDEBAR_RAIL_W`,
  `CONTENT_W`, `CARD_INNER_W` (396 @ s=1), `ROW_LABEL_W`, `ROW_LABEL_GAP`,
  `TAB_HEIGHT`, `TAB_GAP`, `minh`, every row/card/button width and height —
  all stay bit-for-bit identical. This feature changes *how* a shape is
  drawn, never its size or position. `CARD_INNER_W`'s formula keeps the
  same three terms and the same output (396); only the name of its
  radius-turned-padding term changes (see "CARD_R's double duty" below).
- **No accent hue or theme-value change.** `ACCENT`/`ACCENT_INK`/
  `ACCENT_HI`/`OK`/`BAD` stay `#e08a55`/`#1a0f08`/(derived)/`#5cc9a4`/
  `#f06262` dark and `#2b58cc`/`#ffffff`/(derived)/`#0f7f4c`/`#cc3527`
  light — settled 2026-09-11, reconfirmed 2026-09-12, not reopened here.
- **No pruning of `ACCENT`'s other existing uses.** The primary `Button`
  fill, `NumBox`'s focus ring, the hotkey-recording label
  (`afk_clicker.py:2830`), the `EATING` status state
  (`afk_clicker.py:2982`), the pending-update version label
  (`afk_clicker.py:2665`), and `SettingsItem`'s `has_update` corner
  dot/text (`1575-1584`, `1616-1619`) are all contextual *state* signals
  (recording, eating, an update is available), not decorative chrome. The
  "sparing accent" decision is about restraint and about filling the one
  gap (the rail's selected state), not an audit-and-strip pass over every
  existing semantic use.
- **No new header on Appearance or Updates.** Both panes deliberately have
  no `section()` call today — feature 2's design decision that the tab
  label above already names the page. The `Check for updates` button
  (`afk_clicker.py:2365`) looks like the obvious first user of the new
  action slot, and the reference's own "Driver Settings … RESTORE" header
  row is exactly this pattern — but moving that button from inside its
  card into a new header row is a **relayout**, which the story
  explicitly forbids this feature from doing. Considered and rejected;
  the action slot ships with zero real call sites (see below).
- **No change to `Row`, `NumBox`, `Segmented`'s selection logic,
  `_fill_pane`, `_apply_minsize`, `_request_rebuild`/`_rebuild_ui`, the
  rail's collapse debounce, or any persisted state.** Chrome only, over
  geometry and behavior Features 1–4 already locked in.
- **No unifying of the app's two different shape-inset conventions.**
  `Button`/`StatusPill`/`GameItem`/`SettingsItem`/`Segmented`'s outer track
  all inset their shape by 1px (`1, 1, w-1, h-1`) to leave outline-stroke
  room; `card()`'s shell insets by 0 (`0, 0, w, h`). Both conventions are
  preserved exactly as-is at every call site — reconciling them is a
  separate, undecided cosmetic question, not part of "drop rounding."
- **No typography decision** (section-header size/weight once it's no
  longer uppercase-compensated-for-being-tiny) beyond "stop calling
  `.upper()`" — left to the ux-designer, same status Feature 4 left
  `FILL_TOP_SHARE` in.
- No change to hotkey/click/updater logic, `THEMES`' light/dark *values*,
  or anything outside `afk_clicker.py` and `tests/test_ui.py`.

## Background / current state

**Why `round_rect()` can be deleted, not just called with r=0.**
`_round_rect_points()` (`afk_clicker.py:1165-1180`) already collapses to a
plain 4-point rectangle when `r <= 0` — so `round_rect(cv, ..., 0, **kw)`
would already *render* flat. But it would still call `create_polygon`, and
the ticket's own wording is explicit that this feature drops "round_rect()
call sites," not just their radius argument. There are exactly six direct
`round_rect()` calls in the whole file (grep-confirmed) — `Button:1205`,
`Segmented:1252` (outer track) and `:1254` (selection pill), `StatusPill:
1353`, `card():1418`, `GameItem:1509`, `SettingsItem:1563` — plus
`Segmented._pill_pts` (`:1280-1282`), which calls `_round_rect_points`
directly (not through `round_rect`) to reposition the selection pill on
every value change. `_arc_points()` (`:1155-1162`) has no caller besides
`_round_rect_points`. Once all seven of these go, `round_rect`,
`_round_rect_points`, and `_arc_points` have zero remaining callers
anywhere in the file (grep-confirmed) and should be deleted as dead code,
not left orphaned.

**`CARD_R`'s double duty** (`afk_clicker.py:143`, `1388`). `CARD_R` is used
two ways today: as `round_rect()`'s corner radius (`card():1418`,
`GameItem:1509`, `SettingsItem:1563`), and, independently, as `card()`'s
own content inset (`pad = int(CARD_R * s)`, `:1388`, used to place the
inner `Frame` at `(pad, pad)` and size it `w - 2*pad` wide). The radius use
disappears entirely once `round_rect()` is gone. The inset use does not —
it is genuine padding, unrelated to rounding, and `CARD_INNER_W`'s formula
(`CONTENT_W - 2*CONTENT_PAD - 2*CARD_R`, `:163`, feature 1's territory)
depends on that exact number (12) to keep producing 396. Proposed: rename
this surviving role to `CARD_PAD = 12` (same value, same three call
sites — `card()`'s `pad`, and `CARD_INNER_W`'s formula), and delete
`CARD_R` outright. `PILL_R` has no second role anywhere — every one of its
uses is a bare radius argument (`Button`, `Segmented` ×2, `StatusPill`,
plus the now-dead clamp math in `Segmented._pill_pts`/`_paint`) — so it is
a clean, no-rename deletion.

**What the status indicator becomes.** `StatusPill` (`afk_clicker.py:
1345-1364`) draws its shell with `round_rect(self, 1, 1, w-1, h-1, PILL_R *
s, fill=CARD, outline=LINE)` — a true capsule today, self-clamped to
`height/2`. Dropping `PILL_R` makes it a flat panel the same width as the
content column (`width=CONTENT_W`) and the same height (58), using the
same `1, 1, w-1, h-1` inset every sibling canvas already uses — i.e., it
becomes visually the same *kind* of flat surface `card()`'s shell already
is, just a fixed-height one that isn't wrapped around a variable-height
`Frame`. Its dot (`create_oval`, fill `BAD`/`OK`/`ACCENT` depending on
state — `:1354-1364`) and its text/hint labels are untouched; only the
shell's shape call changes.

**The rail's running/idle dots are unaffected.** `GameItem`'s state dot
(both the expanded `create_oval` at `:1519` and the collapsed badge dot at
`:1513`) is a separate canvas item from `self.shape` (the row's background
highlight, `:1509`) — dropping `CARD_R` from `self.shape` touches zero
lines of the dot's own fill logic (`OK` when `running`, `LINE` otherwise,
`_paint():1539`). Feature 3's collapsed rail, which leans on this dot
entirely once the label is gone at `SIDEBAR_RAIL_W`, is unaffected by
anything in this feature.

**Contrast, recomputed, not assumed** (WCAG relative-luminance formula,
computed directly against the live `THEMES` hex values, not carried over
from a prior doc):

| Pair | Ratio |
|---|---|
| `ACCENT` dark (`#e08a55`) on `BG` dark (`#15171a`) | **6.79:1** |
| `ACCENT` light (`#2b58cc`) on `BG` light (`#e8ebf0`) | **5.21:1** |
| `ACCENT` dark on `CARD_HI` dark (`#262a30`) — the selected rail item's own background | **5.45:1** |
| `ACCENT` light on `CARD_HI` light (`#eff2f7`) — same, light theme | **5.55:1** |
| `OK` dark (`#5cc9a4`) on `BG` dark — the collapsed rail's running dot | **8.85:1** |
| `OK` light (`#0f7f4c`) on `BG` light | **4.22:1** |

The first two match the numbers already on record and are unchanged
(accent hex values are untouched by this feature). The `CARD_HI` pair is
new: it's the background the rail's new accent indicator actually sits
against once an item is selected, not `BG` — both dark and light clear
WCAG's 3:1 floor for non-text UI components (1.4.11) with room to spare.
No color value needs to change to hit these; they're reported so the
ux-designer/developer don't have to re-derive them, and so nobody
introduces a fourth wrong-contrast-number incident checking them by eye.

**The action slot has no user yet.** Checked both existing `section()`
call sites (`afk_clicker.py:2173`, `2218`) and both suppressed ones
(Appearance/Updates, which have no header at all, `:2286-2287`,
`2357-2358`) — nothing today has a natural right-aligned action. The one
plausible candidate, `Check for updates`, is explicitly rejected above for
relayout reasons. Per this story's own "TabBar accepts a height it then
ignores" backlog item (an untested, unreachable constructor param that
became a latent trap the moment something finally used it) — this feature
does **not** repeat that shape. The action slot is real, exercised by a
dedicated unit test against `section()` directly (see "Test impact"), even
though zero production call sites pass it.

## Proposed approach

### 1. The mechanical round_rect → create_rectangle swap
Six call sites, each a direct 1:1 replacement (same `x1, y1, x2, y2`
already computed, radius argument dropped):

```python
# Button (afk_clicker.py:1205)
self.shape = self.create_rectangle(1, 1, w - 1, h - 1, fill=CARD, outline=LINE)

# Segmented outer track (:1252) and selection pill (:1254)
self.create_rectangle(0, 0, self.w, self.h, fill=BG, outline=LINE)
self.pill = self.create_rectangle(2, 2, seg - 2, self.h - 2, fill=CARD_HI, outline="")

# StatusPill (:1353)
self.shape = self.create_rectangle(1, 1, w - 1, h - 1, fill=CARD, outline=LINE)

# card()'s shell (:1418)
shape_id = shell.create_rectangle(0, 0, w, h, fill=CARD, outline="")

# GameItem (:1509) / SettingsItem (:1563)
self.shape = self.create_rectangle(1, 1, w - 1, h - 1, fill=BG, outline="")
```

`Segmented._paint()`'s pill reposition (`:1276`, currently `self.coords(
self.pill, *self._pill_pts(seg*idx+2, 2, seg*(idx+1)-2, self.h-2))`)
becomes a direct 4-coordinate `self.coords(self.pill, seg*idx+2, 2,
seg*(idx+1)-2, self.h-2)` — `_pill_pts` (`:1280-1282`) is deleted, its only
job (capsule corner math) no longer exists.

Delete `round_rect()` (`:1183-1191`), `_round_rect_points()` (`:1165-
1180`), and `_arc_points()` (`:1155-1162`) — zero remaining callers.
Delete `CARD_R` (`:143`) and `PILL_R` (`:141`); add `CARD_PAD = 12` next to
where `CARD_R` lived, with a comment carrying over its one surviving job
(content inset, not radius) — `CARD_INNER_W`'s formula (`:163`) updates to
reference `CARD_PAD` in place of `CARD_R`, same output, 396.

### 2. `section()`'s sentence case and action slot

```python
def section(parent, text, s, top=14, action_factory=None):
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(int(top * s), int(6 * s)))
    label = tk.Label(row, text=text, bg=BG, fg=MUTED, anchor="w",
                     font=("Segoe UI", int(9 * s), "bold"))  # size/weight:
        # ux-designer's call once it's no longer uppercase-compensated
    label.pack(side="left")
    if action_factory is not None:
        action_factory(row).pack(side="right")
    return row
```

`action_factory`, not a pre-built widget: a Tk widget's parent is fixed at
construction, so a caller can't hand `section()` an already-built widget
and have it retroactively reparent into the new header row — a factory
(`callable(row) -> widget`) lets the caller build against the real parent.
`section()` now returns the header `row` `Frame` instead of the bare
`Label`; both real call sites (`hotkey_pane`'s header, `eat_section`) only
ever call `.pack()`/`.pack_forget()` on the return value
(`afk_clicker.py:2553`, `2557-2558`), which works identically on a `Frame`
as it did on a `Label` — no call-site change needed beyond dropping
`.upper()`'s absence (i.e., nothing; the call sites already pass sentence
case). `top=14`'s default and `eat_section`'s explicit
`pady=(int(14*self.s), int(6*self.s))` override stay meaningful exactly as
before, now applied to `row` instead of `label`.

### 3. The rail's active-item accent indicator

`GameItem`/`SettingsItem`'s `_paint()` (`:1535-1539`, `:1602-1619`) gains
one more canvas item, created once at `__init__` alongside `self.shape`
and toggled by `state=` in `_paint()` (matching `SettingsItem.update_dot`'s
own existing show/hide-by-state pattern, `:1581-1584`) rather than
recreated per paint:

```python
# GameItem.__init__, after self.shape:
bar_w = int(3 * s)   # exact thickness/treatment: ux-designer's call;
    # 3px is a starting point, not a mandate — matches this file's own
    # precedent of shipping a concrete default alongside an open question
    # (Feature 4's FILL_TOP_SHARE = 0.5)
self.accent_bar = self.create_rectangle(0, 0, bar_w, h, fill=ACCENT,
                                        outline="", state="hidden")

# _paint():
self.itemconfig(self.accent_bar, state="normal" if self.selected else "hidden")
```

Same shape for `SettingsItem`, both its expanded and collapsed branches —
the bar runs the item's full left edge regardless of `collapsed`, so it
needs no width-dependent branching (unlike the dot/text pair, which does
differ by `collapsed`). This is additive: `self.shape`'s own fill logic
(`CARD_HI` selected / `CARD` hover / `BG` idle) is untouched, the accent
bar layers on top of it as a second, independent signal — matching how the
reference itself pairs a filled-nav-row background with a separate accent
edge mark, not one flattened into the other.

### 4. `StatusPill`
Shell becomes `create_rectangle` per §1; nothing else in the class
changes.

## Affected areas
- `afk_clicker.py` only:
  - Constants: delete `PILL_R` (`:141`), `CARD_R` (`:143`); add
    `CARD_PAD = 12` in `CARD_R`'s place; `CARD_INNER_W`'s formula (`:163`)
    updates its third term's name only (396 unchanged).
  - Delete `_arc_points()` (`:1155-1162`), `_round_rect_points()` (`:1165-
    1180`), `round_rect()` (`:1183-1191`).
  - `Button.__init__` (`:1194-1211`): shape call.
  - `Segmented.__init__`/`_paint` (`:1242-1282`): two shape calls, pill
    reposition, delete `_pill_pts`.
  - `StatusPill.__init__` (`:1345-1364`): shape call.
  - `section()` (`:1377-1381`): header-row wrapper, drop `.upper()`, add
    `action_factory`.
  - `card()` (`:1384-1427`): shape call, `pad` now reads `CARD_PAD`.
  - `GameItem.__init__`/`_paint` (`:1486-1539`): shape call, new
    `accent_bar` item + toggle.
  - `SettingsItem.__init__`/`_paint` (`:1542-1619`): shape call, new
    `accent_bar` item + toggle.
  - No changes to `_build_content`/`_build_settings`'s own call sites to
    any of the above (same positional args; `section()`'s two call sites
    pass no `action_factory`, same as passing none today by omission).
- `tests/test_ui.py` — see "Test impact" below; this is the bulk of the
  real work in this feature, more than the widget edits themselves.
- No data model, schema, `Store`, or `settings.json` changes. No new
  persisted state.

## Edge cases
- **Selected AND running** (a game that's both the active rail item and
  currently clicking): the accent bar (edge) and the `OK` dot (its own
  fixed position, `:1519`/`:1513`) occupy different regions of the same
  canvas and never visually compete — both stay independently legible by
  construction, not by tuning.
- **Selected AND `has_update`** (`SettingsItem` only): the existing
  `has_update` signal is `ACCENT`-colored text/dot (`:1616-1619`), already
  independent of `selected`'s fill. Adding a `selected`-only accent bar
  must not make a merely-`has_update`-but-unselected Settings row look
  selected — the bar is gated strictly on `self.selected`, never on
  `self.has_update`, so the two signals stay visually distinct (a
  has-update-but-not-open Settings item shows accent text with no bar; the
  currently-open Settings item shows the bar regardless of update state).
- **Collapsed rail** (`SIDEBAR_RAIL_W`, feature 3): the accent bar is
  created and toggled in the same `__init__`/`_paint()` regardless of
  `collapsed` — verify it renders correctly at both widths, not just the
  expanded one, since the collapsed branch already diverges for the
  dot/text pair and it would be easy to accidentally gate the bar on that
  same branch.
- **`section()` with no `action_factory`** (both real call sites today):
  header height/layout must be pixel-equivalent to today's bare-`Label`
  version aside from the sentence-case text itself — no dead right-hand
  gap reserved when nothing occupies it, since `action_factory(row)` is
  simply never called.
- **`section()`'s header `Frame` feeding `_fill_pane`'s "natural" height
  measurement** (feature 4, `afk_clicker.py:1430-1483`): the header row is
  now a `Frame` wrapping a `Label` instead of a bare `Label`, and it's one
  of the mapped, non-spacer children `_fill_pane` measures by
  `winfo_y()`/`winfo_height()`. The measurement is generic over its
  children's actual geometry (no assumption about widget class or count),
  so this should self-adjust with zero code change — call this out for
  the reviewer to verify empirically (measure, don't assume — this
  story's own repeated lesson), not just trust that it's fine.
- **Compound scale** (`self.s = self._dpi_s * UI_SCALE_FACTORS[...]`,
  worst case `s = 0.675`): the new `accent_bar` width (`bar_w = int(3 *
  s)`) is `3px` at `s=1` and `2px` at `s=0.675` (`int(3 * 0.675) = 2`) —
  stays visible at both. Any different thickness the ux-designer picks
  must be checked the same way at both `s=1` and `s=0.675`, not just at
  `s=1` (this story's TabBar underline precedent, `TAB_UNDERLINE_H = 2`,
  rounds to `1` at `s=0.675` and was accepted as a floor — a new value
  should not go below that floor without a deliberate call).
- **`RoundedCanvasBackgrounds`'s finder breaks by construction, not by
  accident** (`tests/test_ui.py:2206-2230`): it currently finds "rounded"
  canvases by `widget.type(item) == "polygon"`, which only worked because
  `round_rect()`'s single `create_polygon` call (`:1191`) was, until now,
  the *only* polygon-producing call anywhere in the file (grep-confirmed).
  Once it's deleted, that finder returns `[]` and the test's own
  `assertTrue(canvases, "setup failed to find any rounded canvas")` fails
  loudly — correct, not a bug to route around. **Rewriting the finder to
  "any `create_rectangle` item" instead is a trap of the same shape**:
  `TabBar`'s 2px active-underline rectangle (`:1322`) and `Segmented`'s own
  selection pill are both legitimate small rectangles that were never
  meant to cover their canvas edge-to-edge, unlike the six flat-panel
  shapes this feature adds. The rewritten invariant needs to key off which
  *widget classes* draw a full-bleed background shape (`Button`,
  `Segmented`'s outer track specifically, `StatusPill`, `card()`'s shell,
  `GameItem`, `SettingsItem`) — or, more robustly, off whether a
  rectangle's own bbox spans (approximately) its canvas's full
  width/height — not off item type alone, since item type stopped being a
  reliable proxy for "this is a background shape" the moment
  `create_rectangle` became the app's general-purpose canvas primitive
  instead of `round_rect`'s exclusive signature.

## Test impact

**Existing tests requiring real rewrites** (not just touch-ups — their
premise changes):
- `PillAndCardRadii` (`tests/test_ui.py:1960-2057`) — every test in this
  class monkeypatches `app.round_rect` and asserts recorded radius
  arguments. `app.round_rect` won't exist after this feature; the whole
  class needs replacing. Proposed replacement, `FlatChrome`:
  - `test_no_widget_calls_round_rect` — `hasattr(app, "round_rect")` is
    `False` (or, if the reviewer prefers not deleting the function
    outright, assert it has zero callers by some other means — but this
    spec's own recommendation is deletion, see "Why delete rather than
    pass r=0").
  - `test_card_r_and_pill_r_are_gone` — `hasattr(app, "CARD_R")` and
    `hasattr(app, "PILL_R")` are both `False`.
  - One test per widget (`Button`, `Segmented`'s track item, `StatusPill`,
    `card()`'s shell, `GameItem`, `SettingsItem`) asserting
    `cv.type(item) == "rectangle"` for that widget's own shape item —
    replaces the old radius-recording assertions with the same per-widget
    granularity, just checking shape kind instead of a now-nonexistent
    radius argument.
  - `test_segmented_selection_pill_moves_to_the_correct_segment` replaces
    `test_pill_pts_stays_in_sync_with_the_constructors_radius` and
    `test_segmented_selection_pill_matches_round_rects_true_capsule`:
    assert `seg.coords(seg.pill)` equals the expected 4-coordinate
    rectangle for a given selected index — position, not capsule geometry
    (which no longer exists).
  - `test_round_rect_draws_a_true_capsule_not_a_smoothed_approximation`
    (`:2003-2029`) is deleted outright — it tests a function this feature
    removes.
- `RoundedCanvasBackgrounds` (`:2206-2230`) — rewritten per the "Edge
  cases" entry above, same underlying invariant (a canvas's own background
  must match its parent's, wherever its drawn shape doesn't cover the full
  canvas), re-keyed off the widget classes (or the bbox heuristic) instead
  of item type.
- `test_card_inner_w_has_no_border_allowance_left`-class test
  (`tests/test_ui.py:1645-1651`, per the story's own tracking of this
  exact test) — update its formula to reference `app.CARD_PAD` in place of
  `app.CARD_R`; assert `CARD_INNER_W == 396` unchanged.

**New tests needed**, a `SectionHeader` class:
- `test_section_text_is_not_uppercased` — call `section(parent, "Mixed
  Case", 1.0)`, assert the label's own `cget("text")` is exactly
  `"Mixed Case"`.
- `test_section_with_no_action_has_no_reserved_gap` — call `section()`
  without `action_factory`, assert the header row's `winfo_reqwidth()`
  matches the label's alone (no invisible second column).
- `test_section_action_factory_is_actually_wired` — call `section(parent,
  "Test", 1.0, action_factory=lambda row: tk.Button(row, text="Do"))` and
  assert the action's `winfo_x()` is greater than the label's `winfo_x() +
  winfo_width()` (right of the label, same row) — the direct regression
  test against repeating the `TabBar.height`-shaped latent-trap mistake:
  this mechanism gets real coverage even with zero production callers.

**New tests needed**, a `RailAccent` class:
- `test_selected_game_item_shows_the_accent_bar` /
  `test_unselected_game_item_hides_the_accent_bar` — `set_state(selected=
  True/False)`, assert `itemcget(accent_bar, "state")` toggles
  `"normal"`/`"hidden"` accordingly, both `collapsed=True` and
  `collapsed=False`.
- `test_settings_item_accent_bar_is_independent_of_has_update` — a
  `SettingsItem` with `has_update=True, selected=False` shows no accent
  bar; `selected=True, has_update=False` does — proving the two signals
  don't collapse into each other (per "Edge cases" above).
- `test_running_dot_and_accent_bar_coexist` — a selected, running
  `GameItem`: both the dot (`OK`) and the accent bar are visible, distinct
  canvas items — regression guard against one accidentally suppressing
  the other.

**Unaffected, argued:** every test in `WindowResize`, `RailCollapse`,
`RowValueColumn`, `CardResize`, `VerticalFill`, `SettingsNavigation`,
`SettingsUpdates`, `OverlappingAppearanceChanges`, `test_hotkey.py`,
`test_chords_slow.py`, `test_updater.py` — none references `round_rect`,
`CARD_R`, `PILL_R`, or any shape's polygon/rectangle item type
(grep-confirmed against the same list this story's own prior features
already checked). This feature's test blast radius stays contained to the
handful of classes named above in `test_ui.py`.

**Platform traps that apply here, restated so they aren't rediscovered:**
- A `section()`-action test that measures `winfo_x()` on a widget must do
  so while the widget's pane is genuinely mapped (visible tab), not a
  hidden one — `winfo_rootx()`/absolute geometry on an unmapped widget is
  stale-but-plausible on X11 and `0`/`1` on Windows; `winfo_x()` (parent-
  relative) is safe either way, and this feature's own new tests above are
  written to run against a freshly-built, directly-parented `section()`
  call (not one buried in a hidden tab pane) specifically to sidestep this
  rather than needing the guard at all.
- No new window-geometry assertions are introduced by this feature (no
  resize, no minsize change), so the "requested geometry isn't granted on
  a ~1024x768 CI runner" trap doesn't apply here — flagged only so nobody
  adds one without re-reading that caution first.

## Acceptance criteria
- [ ] Given `afk_clicker.py` after this change, when grepping for
      `round_rect`, `_round_rect_points`, `_arc_points`, `CARD_R`, or
      `PILL_R`, then none of these names exist anywhere in the file.
- [ ] Given `Button`, `Segmented`'s outer track, `StatusPill`, `card()`'s
      shell, `GameItem`, and `SettingsItem`, when their shape item is
      inspected via `canvas.type(item)`, then each reports `"rectangle"`,
      never `"polygon"`.
- [ ] Given `CARD_INNER_W`, when computed after this change, then it still
      equals `396` at `s=1` — Feature 1's row-alignment math is untouched.
- [ ] Given `section()` called with either of today's two real call sites'
      arguments, when the header renders, then the label's text is exactly
      the string passed in, never `.upper()`'d.
- [ ] Given `section()` called with no `action_factory` (both real call
      sites), when the header renders, then its layout is unchanged versus
      today aside from casing — no reserved empty right-hand column.
- [ ] Given `section()` called directly with an `action_factory`, when the
      header renders, then the factory's widget sits right of the label in
      the same row — verified by a dedicated test even though no
      production call site exercises this yet.
- [ ] Given a `GameItem`/`SettingsItem` with `selected=True`, when painted
      at either rail width (expanded or collapsed), then an `ACCENT`-filled
      element is visible that is not present when `selected=False`.
- [ ] Given a `SettingsItem` with `has_update=True` and `selected=False`,
      when painted, then no accent bar shows — the update signal and the
      selection signal stay independently controlled.
- [ ] Given a `GameItem` that is both `selected=True` and `running=True`,
      when painted, then both the `OK`-colored running dot and the accent
      bar are simultaneously visible as distinct canvas items.
- [ ] Given `THEMES`'s `ACCENT`/`OK`/`BAD` hex values, when compared before
      and after this change, then they are byte-identical.
- [ ] Given the full test suite (`DISPLAY=:99 .../venv/bin/python -m
      unittest discover -s tests -t .`) after this change, then it passes
      green against the pre-feature-5 baseline (276 tests, per backlog.md's
      2026-09-12 session handoff) plus this feature's new tests, minus the
      specific existing tests this spec calls for rewriting/deleting (none
      of which represents a net loss of coverage — each replaced assertion
      covers the same underlying invariant under the new flat-chrome
      reality). The known `Tcl_AsyncDelete` shutdown flake (~1 run in 4,
      exit 134, no summary) is pre-existing — re-run once, do not chase it.

## Open questions
- **Section-header typography** (size/weight, now that sentence case
  replaces small-caps-for-legibility) is left to the ux-designer, same
  status Feature 4 left `FILL_TOP_SHARE` in. This spec's sketch keeps
  today's `8pt` bold as a placeholder only.
- **The accent bar's exact thickness/treatment** (`bar_w = int(3 * s)`
  proposed) is the ux-designer's call, same status as Feature 3's
  `SIDEBAR_RAIL_W`/Feature 4's `FILL_TOP_SHARE` had at spec stage — a
  concrete default is given so the mechanism has something to build and
  test against, not a recommendation on the final visual.
- **Whether "selection" (the third of the three named sparing-accent
  homes) refers to `NumBox`'s existing focus ring or to `Segmented`'s
  active-segment pill** is genuinely ambiguous in the story's own
  decisions text. Proceeding under the assumption it means the former
  (`NumBox`'s focus ring, `afk_clicker.py:1658`/`1661`, already
  `ACCENT`-colored, already shipped, needs no change) — `Segmented`'s pill
  stays `CARD_HI`, matching a card's own selected-fill treatment rather
  than becoming a second accent surface. If the intent was actually the
  latter, that's a materially different (and larger) change and should be
  confirmed before implementation, not discovered mid-build.
- **Whether `round_rect()`/`_round_rect_points()`/`_arc_points()` should
  be deleted outright versus kept-but-unused** — this spec recommends
  deletion (dead code with zero callers, per "Why `round_rect()` can be
  deleted, not just called with r=0"), but if the reviewer or developer
  has a reason to keep them (e.g., a near-term plan to reuse the arc math
  elsewhere that isn't visible from this spec's vantage point), that's a
  cheap reversal — flagging rather than assuming.

## Risk / rollback notes
- Low-risk, mechanical, and narrowly scoped: six shape-drawing call sites
  swap one canvas primitive for another with identical fill/outline/
  position arguments, three functions and two constants get deleted, one
  new optional parameter is added to one existing function, and two
  widgets gain one new (independently toggled) canvas item each. No
  geometry, no persisted state, no rebuild-machinery interaction.
- Revert is: restore the six `round_rect()` calls, `CARD_R`/`PILL_R`,
  `round_rect()`/`_round_rect_points()`/`_arc_points()`, `section()`'s
  `.upper()` and bare-`Label` return, and remove the two `accent_bar`
  items. Every other widget's construction is untouched, so this is a
  single-file, single-concern revert exactly like Features 1–4's own risk
  notes describe.
- The one thing most worth a reviewer re-deriving directly rather than
  trusting this spec's numbers: the `ACCENT`-on-`CARD_HI` contrast figures
  above (5.45:1 dark, 5.55:1 light) — this project's design docs have been
  wrong about contrast three separate times already; re-run the WCAG
  formula against the live `THEMES` dict rather than copying this table.
- `RoundedCanvasBackgrounds`'s rewrite (see "Edge cases") is the one part
  of this feature with a real design decision buried in a test file, not
  just a mechanical swap — worth the reviewer's direct attention rather
  than a diff skim, since a naive "any rectangle" rewrite would silently
  under- or over-fire against `TabBar`'s underline and `Segmented`'s pill.

## After this feature: the story's end-to-end pass
Story #24 closes after one full pass covering its own end-to-end
acceptance criteria (`docs/history/ac-24-story.md`, "End-to-end acceptance
criteria" section) — most relevantly, for this last feature specifically:
the "rounded cards/pills are gone, section headers are sentence-case with
a right-aligned action slot, and a single accent is used only for the
rail's active item, the tab bar's active underline, and the app's existing
OK/status usages" criterion, checked directly against the finished shell
side-by-side with `handoff/nvidia-reference/*.png` — plus a full suite run
at whatever the post-feature-5 test count settles at (276 baseline + this
feature's new tests, minus the ones this spec calls for replacing). That
pass is the story's own closing step, not this feature's — noted here only
so it isn't lost once this cycle's own `docs/spec.md` is archived.
