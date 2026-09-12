# Spec: Horizontal tab bar under the page title (story #24, Feature 2 of 5)

## Summary
Add a new, reusable tab-bar widget and use it to split each page's stacked
sections into named panes — a game page becomes `Hotkey | Clicking` (with
Eating nested inside Clicking as a sub-section), and Settings becomes
`Appearance | Updates` — mirroring the underline-tab pattern in both NVIDIA
reference screenshots, without touching any control's own values, the click
worker, or the updater's logic.

## Goals
- A new `TabBar` widget: an arbitrary list of `(value, label)` tabs bound to
  a `tk.StringVar`, left-aligned, natural (not equal-fraction) per-label
  width, with a bottom underline under the active tab in `ACCENT`.
- Game pages get `Hotkey | Clicking`; `Clicking` contains `Eating` as a
  nested sub-section exactly where it lives today, still Minecraft-only and
  conditionally shown (Decision 2, `docs/story.md` "Decisions" — settled,
  not re-litigated here).
- Settings gets `Appearance | Updates`.
- Active-tab state survives a rebuild (`_rebuild_ui()`), exactly like
  `self._settings_open` already does today.
- Zero change to any value, to `_persist()`/`_sync_settings()`/the click
  worker, or to the updater's own logic/guards — every widget a hidden pane
  currently owns keeps existing and keeps being read/written exactly as
  today; only which pane is *visible* changes.

## Non-goals
- No visual restyle: `CARD_R`, `PILL_R`, colors, and `round_rect()` are
  untouched — that's Feature 5. `TabBar`'s own proposed pixel constants
  below (height, gap, underline thickness) are a *functional* starting
  point for spacing/hit-testing, explicitly open to the ux-designer's
  adjustment, not a chrome decision.
- No decision on whether the existing `section(pane, "Clicking", s)` /
  `section(pane, "Appearance", s)` / `section(pane, "Updates", s)` header
  labels are now redundant with their tab's own label (they arguably are —
  "Hotkey · shared by every game" carries information beyond the word
  "Hotkey" and is kept verbatim; "Clicking"/"Appearance"/"Updates" do not).
  These `section()` calls are relocated into their new pane frames
  **unchanged** — dropping a redundant label is a content/rhythm call for
  the ux-designer to make in `design.md`, not decided here.
- No icon rail (Feature 3), no `_apply_minsize()` change, no vertical-fill
  behavior (Feature 4).
- The Macros tab (`#15`) is not built. `TabBar`'s own `options` list is
  exactly as extensible as `Segmented`'s (any list of `(value, label)`
  pairs) — a future `#15` adds one more tuple to the game page's
  instantiation (`("macros", "Macros")`) and one more pane frame; no
  `TabBar` change is needed. This is also where the reserved seam from
  `docs/history/ac-17-f3a-spec.md` ("directly below `game_title`/
  `game_state`/`game_note`... a `Clicker | Macros` row scoped to whichever
  game is currently selected") already pointed — that spec named the seam
  and built nothing in it; this feature is what actually occupies it, with
  `Hotkey | Clicking` instead of that spec's placeholder `Clicker` label
  (superseded by Decision 2), plus room for a third `Macros` tab later.
- No change to `Store`/`settings.json` — active-tab state is session-only
  (see "Where active-tab state lives" below), so no new persisted key.
- No change to `_persist()` (`afk_clicker.py:2085`), `_sync_settings()`
  (`:2313`), the click worker, or update integrity/download logic.

## Background / current state

**`_build_content(s)` (`afk_clicker.py:1807-1871`)** stacks, directly into
one `body` frame: a title row (`game_title`/`game_state`), `game_note`, then
`section(body, "Hotkey  ·  shared by every game", s, top=0)` + the `hk` card,
then `section(body, "Clicking", s)` + the `cl` card, then
`self.eat_section = section(body, "Eating", s)` + `self.eat_card_inner`
(Minecraft-only, shown/hidden today via `.pack()`/`.pack_forget()` inside
`_select()`, `afk_clicker.py:2073-2078`).

**`_build_settings(s)` (`afk_clicker.py:1873-1962`)** stacks, directly into
its own `body` frame: a title row, `section(body, "Appearance", s)` + the
`ap` card (Theme + UI-scale `Row`s, plus the "System is currently…" hint),
then `section(body, "Updates", s)` + the `up` card (`version_label` +
`update_button`).

**The reserved seam.** `docs/history/ac-17-f3a-spec.md` ("Rejected — a
top-level tab row above `self.content`") already named exactly this shape
for a future per-game tab row — "inside `self.content`'s body,
`_build_content`'s `body` frame… directly below `self.game_title`/
`self.game_state`/`self.game_note`… and above the 'Hotkey' section" — and
explicitly built nothing there so a later feature could extend
`_build_content` "rather than restructuring the split this spec
introduces." This feature is that later extension.

**Rebuild machinery.** `_rebuild_ui()` (`afk_clicker.py:1717`) destroys
every widget under `root` and calls `_build_ui(self.s)` again. Plain
instance attributes set in `__init__` (not widget state) survive this
teardown untouched — `self._settings_open` (`:1525`) is the existing
precedent: it decides, at the top of `_build_ui()`
(`afk_clicker.py:1685-1701`), whether `_build_content(s)` or
`_build_settings(s)` runs, and it is never read from or written to
`settings.json` — a real process restart always reopens on the game page
(confirmed by `tests/test_ui.py`'s `SettingsNavigation` class never
asserting persistence of `_settings_open` across `restart()`).

**Cross-references into "hidden" widgets that must keep working
unconditionally.** Three call sites read/write `self.click_ms`/
`self.jitter_ms`/`self.autostop_min`/`self.button_name`/`self.eat_mode`/
`self.eat_every`/`self.eat_hold` (all Clicking/Eating widgets) with **no
guard on which tab is showing**:
- `_select()` (`afk_clicker.py:2046-2081`) — fills every one of these from
  the profile's saved values every time a game is picked, regardless of
  which tab happens to be active.
- `_persist()` (`:2085-2103`) — reads all of them into `settings.json` on
  every var-write trace (`afk_clicker.py:1868-1870`).
- `_sync_settings()` (`:2313-2326`) — reads all of them **every 200ms** via
  `self.root.after(200, self._sync_settings)`, into `self.settings`, which
  the click-worker thread reads. This one is the least tolerant of any
  change: it already runs forever regardless of visibility, at a fixed
  interval, feeding a live-running worker thread.

Two more, guarded only on `self._settings_open` (not on which *Settings*
tab is active): `_offer_update()` (`:2163-2176`) and `_set_update_state()`
(`:2226-2233`) both do `if not self._settings_open: return` before touching
`self.update_button`/`self.version_label` — i.e. today's contract is
already "these two widgets exist and are safe to touch whenever Settings is
open," not "whenever the Updates section happens to be scrolled into view."
`tests/test_ui.py`'s `SettingsNavigation.test_sidebar_no_longer_holds_the_
update_widgets` (`:1855-1867`) pins the other half of that contract:
`hasattr(self.ui, "update_button")` is `False` **only** while Settings is
closed, not while some other Settings tab is active.

**Why `Segmented` (`afk_clicker.py:1215-1255`) cannot serve as the tab
bar.** Segmented's entire geometry model is built around dividing one
caller-supplied `width` into `len(options)` **equal** segments (`seg =
self.w / len(options)`, `afk_clicker.py:1226`), hit-tested the same way in
`_click()` (`idx = int(event.x / (self.w / len(self.options)))`,
`:1239`), and its "selected" state is a filled, moving rounded pill
(`self.pill`, `_paint()`/`_pill_pts()`, `:1227-1255`) drawn *behind* the
text. A tab bar, per both reference screenshots
(`handoff/nvidia-reference/01-system-performance.png`,
`02-graphics-program-settings.png`), is the opposite on every one of those
axes: tabs are left-aligned and **each sized to its own label's measured
text width** ("Displays" is visibly narrower than "Performance"), the
container has no background/outline at all (it sits directly on the page's
own background, not inside a bounded track), and the active tab is marked
by a thin **underline sized to that tab's own text width**, with the label
itself going bold — no filled pill, nothing drawn behind any tab. Retrofitting
this into `Segmented` means replacing its constructor's width-division math,
its `_click()` hit-test, and its entire `_paint()`/pill-drawing body — i.e.
keeping only the outer shape (`tk.Canvas` + a bound `tk.StringVar` + a
`<Button-1>` handler), which is the *contract*, not the implementation.
`Segmented` also keeps three existing, working call sites
(`button_name`, `appearance_var`, `ui_scale_var`) whose equal-width/pill
behavior is exactly what they still want — changing `Segmented` itself
in place to support both shapes would branch its whole body on a "style"
flag, coupling two visually and structurally unrelated widgets. A sibling
class is the smaller, safer diff.

## Proposed approach

### 1. `TabBar` — a new class, sibling to `Segmented`

Add `TabBar(tk.Canvas)` directly after `Segmented`
(`afk_clicker.py:1255`, before `StatusPill`), following the same
constructor shape (`parent, options, variable, s`) so both read the same at
a glance:

```python
TAB_HEIGHT = 32       # canvas height; proposed, ux-designer may retune
TAB_GAP = 28          # horizontal gap between adjacent tab labels
TAB_PAD_BOTTOM = 6    # space between text baseline and the underline
TAB_UNDERLINE_H = 2   # active-tab underline thickness

class TabBar(tk.Canvas):
    """Left-aligned, natural-width tabs with an active-tab underline --
    the NVIDIA-reference pattern (handoff/nvidia-reference/*.png), distinct
    from Segmented's equal-width filled-pill selector (see docs/spec.md's
    'Why Segmented cannot serve')."""

    def __init__(self, parent, options, variable, s, height=TAB_HEIGHT):
        self.s = s
        self.options = options                # [(value, label), ...]
        self.var = variable
        font = ("Segoe UI", int(9.5 * s), "bold")   # bold width is the
                                                     # layout width for
                                                     # every tab, active or
                                                     # not, so the active
                                                     # tab going bold never
                                                     # shifts anything else
        measurer = tkfont.Font(family="Segoe UI", size=int(9.5 * s), weight="bold")
        gap = int(TAB_GAP * s)
        x = 0
        self._tabs = []                       # [(value, label, x1, x2, text_id), ...]
        for value, label in options:
            w = measurer.measure(label)
            self._tabs.append([value, label, x, x + w, None])
            x += w + gap
        total_w = max(x - gap, 0)
        h = int(height * s)
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0,
                         width=total_w, height=h, cursor="hand2")
        for tab in self._tabs:
            value, label, x1, x2, _ = tab
            tab[4] = self.create_text((x1 + x2) / 2, (h - TAB_PAD_BOTTOM * s) / 2,
                                      text=label, font=font)
        self.underline = self.create_rectangle(0, 0, 0, 0, fill=ACCENT, outline="")
        self.bind("<Button-1>", self._click)
        self.var.trace_add("write", lambda *_a: self._paint())
        self._paint()

    def _click(self, event):
        for value, _label, x1, x2, _tid in self._tabs:
            if x1 <= event.x < x2 + int(TAB_GAP * self.s):
                self.var.set(value)
                return

    def _paint(self):
        current = self.var.get()
        h = int(TAB_HEIGHT * self.s)
        for value, _label, x1, x2, text_id in self._tabs:
            self.itemconfig(text_id, fill=INK if value == current else MUTED)
        active = next((t for t in self._tabs if t[0] == current), self._tabs[0])
        _v, _l, x1, x2, _tid = active
        underline_h = int(TAB_UNDERLINE_H * self.s)
        self.coords(self.underline, x1, h - underline_h, x2, h)
```

Notes on the sketch above (the developer's job to finalize, this is the
shape, not final code):
- `total_w`/hit-testing use **bold** metrics for every tab uniformly (not
  each tab's own weight), so the underline/hit-box geometry never shifts
  when the active tab changes — only fill colors and the underline's
  position change on `_paint()`. This mirrors `Segmented`'s own approach of
  computing all geometry once at construction and only moving `self.pill`
  afterward.
- No background track, no outline, no fill behind any tab — the canvas's
  own `bg` is `parent.cget("bg")`, i.e. it visually disappears into the
  page background except for the text and the one underline, matching both
  reference screenshots.
- `variable.trace_add("write", ...)` is registered the same way
  `Segmented` does it. Unlike `_apply_appearance()`/`_apply_ui_scale()`
  (`afk_clicker.py:1964-2024`), switching tabs **never calls
  `_request_rebuild()`** (see §2) — it only toggles which sibling pane
  frame is packed. So the Tcl trace-ordering hazard those two methods'
  own comments describe (a rebuild destroying a `Segmented` mid-repaint)
  does not apply here: nothing this widget's own trace does can destroy
  the `TabBar` itself. No special registration-order care is needed,
  and a reviewer should not need to re-derive this — it's stated here so
  it isn't mistaken for an oversight.

### 2. Where active-tab state lives, and why it is not persisted

Two new plain instance attributes, initialized once in `__init__` next to
`self._settings_open` (`afk_clicker.py:1525`):

```python
self._content_tab = "hotkey"       # which per-game tab is showing:
                                    # "hotkey" / "clicking"
self._settings_tab = "appearance"  # which Settings tab is showing:
                                    # "appearance" / "updates"
```

These are session-only, exactly matching `self._settings_open`'s own
precedent: never read from or written to `settings.json`, so **a real
process restart always reopens on `Hotkey`/`Appearance`** — the same
behavior a restart already has today for `_settings_open` (always reopens
on the game page). This is the recommended default, not an open question:
it is zero new persisted surface, it is the smallest diff, and it matches
the one existing precedent in the file for "which sub-view is showing."

They **do** survive `_rebuild_ui()` (an Appearance/UI-scale change, or
leaving/entering Settings), because they are plain Python attributes on
`self`, never touched by `_rebuild_ui()`'s `root.winfo_children()` teardown
— identical to how `self._settings_open` already survives a rebuild today.

**They also survive switching games or opening/closing Settings** — i.e.
`_select()` (`:2046`) and `_show_settings()` (`:2028`) do not reset either
attribute. A user who scrolled to `Clicking` while tuning one game and then
picks a different game (or opens Settings and comes back) stays on
`Clicking`, not bounced back to `Hotkey`. This is a real, non-blocking
product judgment call, not dictated by the story's own settled decisions —
flagged explicitly under "Open questions" below, with the alternative
named, rather than silently assumed.

Two small new methods, next to `_show_settings()`:

```python
def _set_content_tab(self, value):
    if value not in ("hotkey", "clicking"):
        value = "hotkey"
    self._content_tab = value
    self.hotkey_pane.pack_forget()
    self.clicking_pane.pack_forget()
    (self.hotkey_pane if value == "hotkey" else self.clicking_pane).pack(
        fill="both", expand=True)

def _set_settings_tab(self, value):
    if value not in ("appearance", "updates"):
        value = "appearance"
    self._settings_tab = value
    self.appearance_pane.pack_forget()
    self.updates_pane.pack_forget()
    (self.appearance_pane if value == "appearance" else self.updates_pane).pack(
        fill="both", expand=True)
```

### 3. `_build_content(s)` / `_build_settings(s)`: build both panes, always;
show exactly one

Both panes' full contents are constructed **every time**, whichever tab is
active — this is what keeps every cross-reference above (`_select()`,
`_persist()`, `_sync_settings()`, `_offer_update()`/`_set_update_state()`)
correct with **zero changes to any of them**: the widgets they read/write
exist unconditionally whenever the game page (or Settings) is open, exactly
as today. Only which pane is *packed* (visible) differs, using precisely
the same `.pack()`/`.pack_forget()` idiom already proven for `eat_section`/
`eat_card` today (`afk_clicker.py:2073-2078`,
`tests/test_ui.py`'s `EatingCardCanvas` class, `:1517-1531`) — this feature
does not invent a new visibility mechanism, it reuses the one already
shipped and tested.

`_build_content(s)` (`afk_clicker.py:1807-1871`), after the existing
`game_note.pack(...)` line and before today's first `section(...)` call:

```python
self.content_tab_var = tk.StringVar(value=self._content_tab)
TabBar(body, [("hotkey", "Hotkey"), ("clicking", "Clicking")],
      self.content_tab_var, s).pack(anchor="w", pady=(0, int(12 * s)))
self.content_tab_var.trace_add("write",
    lambda *_a: self._set_content_tab(self.content_tab_var.get()))

self.hotkey_pane = tk.Frame(body, bg=BG)
self.hotkey_pane.pack(fill="both", expand=True)
section(self.hotkey_pane, "Hotkey  ·  shared by every game", s, top=0)
hk = card(self.hotkey_pane, s)
# ... existing Hotkey card body, unchanged, just built into hk ...

self.clicking_pane = tk.Frame(body, bg=BG)
self.clicking_pane.pack(fill="both", expand=True)
section(self.clicking_pane, "Clicking", s)
cl = card(self.clicking_pane, s)
# ... existing Clicking card body, unchanged ...
self.eat_section = section(self.clicking_pane, "Eating", s)
self.eat_card_inner = card(self.clicking_pane, s)
# ... existing Eating card body, unchanged ...

self._set_content_tab(self._content_tab)   # hide whichever pane is not active
```

**Build order is load-bearing, not stylistic**: both panes must be built
and `.pack()`ed (in this stacked order, exactly as `_build_content` already
lays out Hotkey-then-Clicking today) *before* `_set_content_tab()` hides
one of them. `card()`'s own `_redraw()` (`afk_clicker.py:1297-1334`) is
invoked once, synchronously, at the end of each `card(...)` call, and reads
`shell.winfo_width()` at that moment — verified empirically (throwaway
Tkinter script under this session's Xvfb, not committed anywhere) that:
a card built while its pane is still packed gets the *real* width from
that synchronous `_redraw()` call, and calling `pack_forget()` on the pane
immediately afterward (still inside the same synchronous `_build_content`
call, before Tk's event loop ever runs) **does not erase that already-computed
geometry** — `winfo_width()`/`winfo_x()` on the now-hidden card's children
keep reporting the last real values they were given, exactly like
`eat_card`'s own already-proven pack/pack_forget cycle. Building a pane's
cards *after* hiding it (or never packing it at all before hiding) would
instead leave them stuck at Tk's placeholder defaults, since a card that is
never part of a mapped tree never gets a real `_redraw()` pass. This
ordering constraint is why the sketch above builds `hotkey_pane` fully,
*then* `clicking_pane` fully, *then* calls `_set_content_tab()` last — not
interleaved, and not with the hide-call moved earlier.

`_build_settings(s)` (`afk_clicker.py:1873-1962`) gets the structurally
identical treatment: a `TabBar` after the title row, `self.appearance_pane`
holding today's Appearance section+card+hint, `self.updates_pane` holding
today's Updates section+card, and `self._set_settings_tab(self._settings_tab)`
as the last line.

### 4. `_apply_appearance()` / `_apply_ui_scale()` / `_select()` / `_show_settings()`

**No changes.** Each already ends its own synchronous work by either
calling `_request_rebuild()` (the two Appearance/UI-scale methods) or
directly finishing `_build_content`'s tail inline (`_select`, via
`_build_ui`'s own branch at `afk_clicker.py:1701`). In every case,
`_build_content`/`_build_settings` runs again in full (or, for `_select`,
its per-game value-fill runs against already-existing widgets), and each
one's own tail (`_set_content_tab`/`_set_settings_tab`) re-establishes the
correct visible pane from the untouched `self._content_tab`/
`self._settings_tab` — this is exactly the same replay pattern
`_build_ui()`'s own tail already uses for `self._pending`/`self._update_text`
(`afk_clicker.py:1671-1698`), just for one more piece of session state.

## Affected areas
- `afk_clicker.py` only:
  - New `TabBar` class + four constants (`TAB_HEIGHT`, `TAB_GAP`,
    `TAB_PAD_BOTTOM`, `TAB_UNDERLINE_H`), placed after `Segmented`
    (`afk_clicker.py:1255`).
  - Two new instance attributes (`self._content_tab`, `self._settings_tab`)
    and two new methods (`_set_content_tab`, `_set_settings_tab`), placed
    near `self._settings_open` (`:1525`) and `_show_settings()` (`:2028`).
  - `_build_content(s)` (`:1807-1871`): insert the `TabBar` + wrap the
    existing Hotkey/Clicking(+Eating) construction into `hotkey_pane`/
    `clicking_pane`. No existing widget's construction call changes, only
    which frame it is parented into.
  - `_build_settings(s)` (`:1873-1962`): same treatment with
    `appearance_pane`/`updates_pane`.
- No data model, schema, or API changes — `Store`/`settings.json` are
  untouched (see Non-goals).
- One test file, `tests/test_ui.py` — see "Test impact" below.

## Edge cases
- **A game with no Eating section** (any non-Minecraft profile): the
  Clicking pane shows only the `cl` card; `eat_section`/`eat_card_inner`
  stay `pack_forget()`'d exactly as `_select()` already does today
  (`afk_clicker.py:2077-2078`) — unaffected by this feature, still correct,
  still "must look deliberate, not truncated" per Decision 2. No new
  spacing/padding change is proposed here — a bare `cl` card with nothing
  below it is the same look Feature 1 already ships; if the ux-designer
  judges it needs more breathing room, that's a design-stage call, not a
  functional one.
- **Switching to Settings while Clicking is the active game-page tab, then
  back to a game**: unaffected — `self._content_tab` is untouched by
  `_show_settings()`/`_select()`'s Settings-closing branch (`:2048`), so the
  game page reopens on whichever tab was last active, per the recommended
  default above.
- **A resize while a pane is hidden**: a hidden pane's `card()` shells do
  not receive real `<Configure>` events while unmapped (confirmed
  empirically — a hidden card's `winfo_width()` does not track a live
  `root.geometry(...)` change the way a visible one does), so if the window
  is resized while, say, `Hotkey` is active, `Clicking`'s cards keep
  whatever width they had from their last real layout pass until the user
  actually switches to `Clicking` — at which point `pack()`'s own
  `<Configure>` fires immediately and the card corrects itself before the
  next paint. This is a real, momentary staleness, invisible in practice
  (it never renders at the stale size — Tk resolves it before the newly
  shown pane is ever drawn), and is exactly why the two `RowValueColumn`
  tests that resize-then-measure need updating (see "Test impact" below) —
  called out here as the mechanism, not left implicit.
- **A rebuild mid-tab-switch**: not reachable — switching tabs never calls
  `_request_rebuild()` (see §1's note on trace ordering), so there is no
  window where a tab switch and an Appearance/UI-scale rebuild can race.
- **`TabBar` with a single option**: not exercised by this feature (both
  bars have exactly two tabs), but the class makes no assumption requiring
  ≥2 — `_click()`'s loop and `_paint()`'s `next(...)` both degrade
  correctly to "the one tab is always active." Relevant for a future
  Macros tab landing as a third option, not tested here.

## Test impact, argued per case

**Empirical grounding, not assumption**: two Tkinter behaviors below were
confirmed directly against this session's own Xvfb (`DISPLAY=:99`) with
small throwaway scripts (not added to the repo), because guessing wrong
here would either under- or over-state this feature's real blast radius:
1. `focus_set()` on a widget inside a frame that has never been `.pack()`ed
   (or has been `.pack_forget()`'d) does **not** move real Tk input focus —
   `root.focus_get()` stays `None`/unchanged. Confirmed with a minimal
   `Entry` inside an unpacked `Frame`.
2. `event_generate("<Button-1>", x=.., y=..)` targeted at a `Canvas` inside
   an unmapped ancestor does **not** dispatch the bound handler (0 calls
   recorded vs. 1 after the same canvas is packed). Confirmed with a
   minimal bound `<Button-1>` handler.
3. A widget's `winfo_x()`/`winfo_width()` **do** retain their last
   correctly-computed values after their ancestor is `pack_forget()`'d —
   confirmed by building two `card()`-style canvas+`create_window` shells
   side by side, `pack_forget()`-ing the second immediately (no
   `root.update()` in between, matching this spec's own synchronous build
   order), and finding both report the same, correct width once the
   window is finally drawn.
4. That same hidden shell's width does **not** track a subsequent
   `root.geometry(...)` change while it stays hidden — it snaps to the
   current correct value only once it is shown again. This is the source
   of the two `RowValueColumn` updates below.

**Given the recommended defaults** (`_content_tab = "hotkey"`,
`_settings_tab = "appearance"`), every test that reads/writes a widget via
its Python attribute (`.var.get()`/`.set()`, `.cget()`, direct method calls
like `self.ui._set_update_state(...)`) is unaffected regardless of which
tab it lives in — per finding 3 above and the already-proven `eat_mode`/
`eat_card` precedent. Only tests that drive a widget through a **real Tk
event or real focus** are at risk, and only if that widget's pane is not
the default-active one.

**Required changes (would otherwise hard-fail — findings 1/2 above):**
- `tests/test_ui.py`'s `NumBoxFocus` class (`:638-736`, 9 tests, all
  routed through the shared `focus_and_settle()` helper at `:641-645`) —
  every one starts by focusing `self.ui.click_ms.entry`, a Clicking-pane
  widget, while `Hotkey` is the default-active tab. **Fix**: add
  `self.ui._set_content_tab("clicking"); self.root.update()` to the top of
  `focus_and_settle()` itself — one change, all 9 tests covered, since they
  all funnel through it. This is legitimate, not a loosened assertion: a
  real user must click the `Clicking` tab before an entry inside it can
  take real keyboard focus, and the test now does what a real user would
  do first.
- `BindAllBoundOnce.test_a_click_still_drops_focus_exactly_once_after_two_
  theme_changes` (`:2374-2384`) — calls `self.ui.click_ms.entry.focus_set()`
  directly (not via the shared helper). **Fix**: same one-line addition
  before that call.
- No other `event_generate`/`focus_set` call site in the file targets a
  Clicking/Eating/Updates-pane widget (confirmed by grep across the whole
  file): the Appearance-pane clicks (`SettingsNavigation:1919-1920`,
  `RowValueColumn:806-830` via `_appearance_segment`,
  `OverlappingAppearanceChanges:2461-2466`) all target `appearance_var`/
  `ui_scale_var`, which live in `appearance_pane` — the default-active
  Settings tab — so **none of these need any change**. The one
  `GameItem` click (`NumBoxFocus.test_a_game_item_still_selects`, `:718`)
  targets a sidebar item, never inside any pane, and is already covered by
  the `focus_and_settle()` fix above (it also calls that helper first).

**Recommended changes (would not fail, but would silently stop proving
what they claim — see edge case above and finding 4):**
- `RowValueColumn.test_offset_is_unchanged_when_the_card_stretches`
  (`tests/test_ui.py:787-796`) and
  `test_extra_width_becomes_trailing_margin_not_a_growing_gap` (`:798-804`)
  both resize `self.root` and then read geometry off `self.ui.click_ms`'s
  ancestors — a Clicking-pane widget, hidden by default. Per finding 4,
  the hidden card would not track the resize, so both assertions would
  keep passing but for a hollow reason: `control.winfo_x()` staying
  "unchanged" (test 1) is true either way (it never depended on stretch
  propagating — that is the actual fix, not an artifact), but
  `test_extra_width_becomes_trailing_margin_not_a_growing_gap`'s
  `card.winfo_width()` comparison would compare against a **stale,
  pre-resize** width and could not catch a real regression where the
  Clicking pane's own margin behavior broke while visible. **Fix**: add
  `self.ui._set_content_tab("clicking"); self.root.update()` immediately
  after `self.root.geometry("900x760"); self.root.update()` in both tests
  (before reading `winfo_width()`), restoring genuine coverage of the
  resize-while-visible case these tests were written for. Not required to
  keep the suite green; required to keep it meaningful — flagged for the
  developer/reviewer rather than silently left as latent hollow coverage.
- `test_control_sits_at_the_fixed_label_column_offset` (`:782-785`) and
  `test_random_jitter_hint_wraps_instead_of_overlapping_the_control`
  (`:832-859`) need **no change** — both read `grid`-based offsets/
  requested sizes (`winfo_x()` off a `grid`-managed column,
  `winfo_reqheight()`), which finding 3 confirms are computed correctly
  independent of the ancestor pane's mapped state.
- `test_ui_scale_row_never_overflows_its_card_at_any_scale_step`
  (`:806-830`) targets the Appearance pane (default-active) — no change.

**No change, argued:**
- `PerGameSettings` (`:202-241`) — `test_defaults_differ_per_profile`,
  `test_eating_panel_is_minecraft_only`, `test_values_are_kept_apart`,
  `test_survives_a_restart` all read/write via `.var.get()`/`.set()` and
  `.winfo_manager()` (a manager-registration query, unaffected by ancestor
  visibility per finding 3's own mechanism) — none touch focus or a real
  click. **Unaffected.**
- `EatingCardCanvas` (`:1517-1531`) — same reasoning; `eat_card`'s own
  pack/pack_forget cycle is driven by `_select()`, untouched by this
  feature, and `.winfo_manager()` reflects that directly regardless of
  `clicking_pane`'s own visibility.
- `CardResize` (`:1533-1552`) — targets the Hotkey card
  (`self.ui.apply_button.master.master.master`), the default-active pane;
  resizes and reads `winfo_width()` while genuinely visible throughout.
  **Unaffected**, and this is a second, independent reason `Hotkey` (not
  `Clicking`) is the better *default* pane even though the two
  `RowValueColumn` tests above need a tab switch either way: `CardResize`
  would need the same fix `RowValueColumn` needs if the default were
  flipped, trading one class of updates for another rather than reducing
  the total.
- `SettingsNavigation` (`:1847-1945`), `SettingsUpdates` (`:1946-2120ish`),
  `OverlappingAppearanceChanges` (`:2416-2467`),
  `QueuedNonResyncedUpdatesSurviveARebuild` (`:2627-2673`) — every
  interaction is either a direct Python call (`_set_update_state`,
  `_offer_update`, `_apply_appearance`, `_rebuild_ui`) or targets the
  default-active Appearance pane. **Unaffected.**
- No test in `test_hotkey.py`, `test_chords_slow.py`, or `test_updater.py`
  references `Row`, `Segmented`, `TabBar`, or any layout/tab constant
  (confirmed by grep) — this story's blast radius stays contained to
  `test_ui.py`, matching `docs/story.md`'s own note.

**New tests needed** (see Acceptance criteria): a new test class, e.g.
`TabBarNavigation(UITestCase)`, covering `TabBar` construction/click/
underline behavior and the pane-visibility contract for both pages.

## Acceptance criteria
- [ ] Given a freshly built app on a game page, when no tab has been
      clicked, then `Hotkey` is the active tab (`self.ui._content_tab ==
      "hotkey"`), `self.ui.hotkey_pane.winfo_manager() == "pack"`, and
      `self.ui.clicking_pane.winfo_manager() == ""`.
- [ ] Given the `Clicking` tab is clicked (a real `<Button-1>` on the
      `TabBar` at the `Clicking` label's own measured x-range, not a
      hand-picked pixel constant), when the click lands, then
      `self.ui.content_tab_var.get() == "clicking"`,
      `self.ui.clicking_pane.winfo_manager() == "pack"`, and
      `self.ui.hotkey_pane.winfo_manager() == ""` — switching tabs shows
      only that tab's content.
- [ ] Given either tab is active, when reading `self.ui.click_ms.var`/
      `self.ui.jitter_ms.var`/`self.ui.button_name`/`self.ui.hotkey_label`/
      `self.ui.apply_button`, then all exist and hold their expected values
      regardless of which pane is currently packed — hidden-pane widgets
      are never destroyed, only unpacked.
- [ ] Given the Settings page open with no tab yet clicked, then
      `Appearance` is active (`self.ui._settings_tab == "appearance"`),
      `self.ui.appearance_pane.winfo_manager() == "pack"`, and
      `self.ui.updates_pane.winfo_manager() == ""`, and `hasattr(self.ui,
      "update_button")` is `True` (built, just not the visible pane) —
      matching the existing `if not self._settings_open` contract in
      `_offer_update()`/`_set_update_state()` with no change to either.
- [ ] Given Settings open and `Updates` clicked, when an update check is
      then run (`self.ui.check_update()` → `_check_worker`/`_offer_update`/
      `_set_update_state`), then `self.ui.update_button`/
      `self.ui.version_label` reflect the new state exactly as today
      (`SettingsUpdates`'s existing coverage), proving the tab split adds
      no new gap in the updater's own visibility contract.
- [ ] Given a game with `profile["eating"]` true (Minecraft), when the
      `Clicking` tab is active, then `self.eat_section`/`self.eat_card`
      are packed (visible) below the Clicking card; given a game with
      `profile["eating"]` false, when `Clicking` is active, then both stay
      `pack_forget()`'d — unaffected by this feature, verified unchanged.
- [ ] Given an Appearance change (`self.ui._apply_appearance("light")`) or
      a UI-scale change while on either tab of either page, when the
      resulting `_rebuild_ui()` completes, then the same tab that was
      active before the rebuild is active after it, on the same page —
      active-tab state survives a rebuild exactly like `_settings_open`
      already does.
- [ ] Given the full suite (`DISPLAY=:99 .../venv/bin/python -m unittest
      discover -s tests -t .`) after this change, then it passes at the
      245-test baseline (`OK (skipped=5)`) plus this feature's new
      `TabBarNavigation` tests, with exactly the "Test impact" section's
      required (`NumBoxFocus`, `BindAllBoundOnce`) and recommended
      (`RowValueColumn`'s two resize tests) changes applied, and zero other
      existing tests modified. The known `Tcl_AsyncDelete` shutdown flake
      (~1 run in 4, exit 134, no summary) is pre-existing — re-run once, do
      not chase it.

## Open questions
- **Does the active tab survive switching games / opening Settings and
  coming back, or reset to the first tab each time?** Proceeding under
  "survives" (see §2) — it is the smaller diff (no reset logic needed),
  it matches `self._settings_open`'s own "just a flag, never reset by
  anything but its own toggle" precedent, and it is arguably the more
  useful behavior for someone tuning `Clicking` settings across several
  games in one sitting. The alternative (always reset to `Hotkey`/
  `Appearance` on every game switch or Settings entry) is a one-line
  change to `_select()`/`_show_settings()` if the owner prefers it — not a
  blocker, called out so it can be overridden before implementation if the
  assumption is wrong.
- **Should the now-possibly-redundant bare-word `section()` headers
  ("Clicking"/"Appearance"/"Updates") be dropped since the tab label above
  them already says the same word?** Deliberately left to `design.md` (see
  Non-goals) — this spec keeps every existing `section()` call verbatim,
  just relocated into its new pane frame.
- **Exact `TabBar` pixel constants** (`TAB_HEIGHT`, `TAB_GAP`,
  `TAB_PAD_BOTTOM`, `TAB_UNDERLINE_H`) are proposed starting points, not
  externally mandated — same status Feature 1's `ROW_LABEL_W`/
  `ROW_LABEL_GAP` had. If the ux-designer's/reviewer's visual pass finds
  the tabs cramped or the underline mis-sized against the reference
  screenshots, adjusting these four constants is a same-spec tweak.

## Risk / rollback notes
- Single new widget class + two small toggle methods + relocating existing
  widget-construction code into new parent frames (no construction call
  itself changes). Revert is: drop `TabBar` and the two `_set_*_tab`
  methods, un-nest the Hotkey/Clicking/Appearance/Updates card
  constructions back to `body` directly, drop the two new instance
  attributes.
- The main risk this spec identifies and mitigates is silent, hollow test
  coverage on a hidden pane (a test that still reports green without
  actually exercising the behavior it names) — addressed directly in
  "Test impact" above via the two `RowValueColumn` updates, rather than
  left for the reviewer to discover independently.
- `_sync_settings()`'s 200ms poll (`afk_clicker.py:2313`) is the least
  forgiving existing consumer of Clicking/Eating widgets and receives
  zero changes here — if a future change ever needs to special-case "only
  sync the visible tab," that is an explicit, separate decision, not a
  side effect of this feature.
