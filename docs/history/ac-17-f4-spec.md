# Spec: UI scale (story #17, Feature 4 — final feature of the story)

## Summary
Add a "UI scale" control to the Settings tab's Appearance card — four
discrete steps (90% / 100% / 115% / 130%) that multiply on top of the DPI
factor the app already computes, persisted as a new `"ui_scale"` key in
`settings.json`, applied through the same in-place rebuild mechanism
Feature 3 built for Appearance — no process restart, no new widget class,
no new rebuild path.

## Goals
- A second `Row` inside the existing Appearance card (below Theme), holding
  a 4-option `Segmented`: `90%`, `100%` (default), `115%`, `130%`.
- `self.s` (today: DPI factor alone) becomes DPI factor × the user's chosen
  step; every widget size/font/radius that already multiplies by `self.s`
  picks the new effective value up for free on rebuild — no per-widget
  changes needed anywhere outside `AfkAutoclicker.__init__`.
- The choice is persisted as `settings.json["ui_scale"]`, one of
  `"90"|"100"|"115"|"130"`, sanitized in `Store.__init__` exactly like
  `"appearance"` — anything else (missing key, wrong type, an old/foreign
  value) resolves to `"100"`.
- Changing UI scale rebuilds in place (`_rebuild_ui`), the same as
  Appearance, and updates `root.minsize()` to match the new effective size;
  the window **grows** if its current size is now below the new minimum,
  and is **never shrunk** by a scale change in either direction.
- A UI-scale change and an Appearance change fired in quick succession
  coalesce into exactly one rebuild, through the same
  `self._rebuilding`/`self._rebuild_wanted`/`self._rebuild_after_id` machinery
  Feature 3 already built and tested for Appearance alone.
- A running clicker (`self.worker`, `self.hk_listener`, the click-loop
  thread) survives a scale-triggered rebuild unharmed, the same
  already-proven guarantee Feature 3 relies on (none of that state lives in
  the widget tree — `AfkAutoclicker.__init__`, `afk_clicker.py:1477-1479`).

## Non-goals
- Persisting window size/position — already out of `#14`'s scope, unchanged
  here (story.md's own Feature 4 non-goal).
- Per-monitor DPI re-detection at runtime, or re-reading `tk scaling` after
  startup — the DPI half of the factor is still read once, in `__init__`,
  same as today; only the user's chosen multiplier on top of it is new.
- A continuous slider, or more than 4 steps — see §1's rejected
  alternatives.
- A font-size floor/clamp helper threaded through all ~20 `int(base * s)`
  call sites — not needed at the chosen steps; see §3.
- Any change to `Segmented`, `Button`, `StatusPill`, or any other widget
  class's own code — they already take `s` as a plain multiplier and need
  nothing scale-specific.
- Any change to Appearance/theme behavior itself (Features 2/3) beyond the
  shared coalescing helper extracted in §2, which is a pure refactor of
  already-existing logic, not a behavior change.

## Background / current state

- `self.s = root.tk.call("tk", "scaling") / 1.333` — `afk_clicker.py:1445`,
  computed once in `AfkAutoclicker.__init__`, **before** `self.store` is
  assigned (`afk_clicker.py:1446`). Every widget built by `_build_ui(s)`
  and its helpers (`_build_content`, `_build_settings`, `Button`,
  `Segmented`, `StatusPill`, `GameItem`, `Row`, `NumBox`, `card()`,
  `section()`) takes this same `s` and multiplies every pixel width,
  height, padding, and font point size by it — confirmed by grep, no
  exception anywhere in the file.
- `minw, minh = int((SIDEBAR_W + 1 + CONTENT_W) * s), int(690 * s)` /
  `root.minsize(minw, minh)` / `root.geometry(f"{minw}x{minh}")` —
  `afk_clicker.py:1460-1462`, set **once**, inline in `__init__`, using the
  `s` computed two lines above. This is `#14`'s tuned-default-size
  mechanism; nothing today ever calls `minsize`/`geometry` a second time.
- `enable_dpi_awareness()` (`afk_clicker.py:189-205`) only affects Windows
  (`SetProcessDpiAwareness`); it runs once in `__main__`
  (`afk_clicker.py:2423`), before `Store()`/`Tk()` are constructed, and is
  untouched by this feature — it governs whether Windows itself upscales
  blurrily, not anything this spec's multiplier controls.
- The rebuild mechanism (`_build_ui(s)`: `1529-1650`; `_rebuild_ui()`:
  `1650-1737`) already does exactly what a UI-scale change needs: destroy
  every child of `root`, rebuild fresh from `self.s`. `self._rebuilding`/
  `self._rebuild_wanted`/`self._rebuild_after_id` (set in `__init__`,
  `1498-1503`) already coalesce repeated rebuild requests into at most one
  in-flight rebuild — proven today only for repeated Appearance changes
  (`tests/test_ui.py:2004-2027`, `OverlappingAppearanceChanges`).
- `_apply_appearance(value)` (`afk_clicker.py:1862-1908`) is this feature's
  direct precedent for "a Settings control that persists a value and
  requests a coalesced rebuild": save to `self.store`, apply the
  synchronous part of the change (`set_active_theme(resolved)`), then
  either mark `self._rebuild_wanted = True` (if `self._rebuilding`) or
  schedule `self.root.after_idle(self._rebuild_ui)` (if no rebuild is
  already pending) — never both.
- `_build_settings(s)` (`afk_clicker.py:1806-1860`): one `section()` +
  `card()` for "Appearance" (a single `Row` holding the Theme `Segmented`,
  `1827-1837`, plus a "System is currently…" hint label, `1843-1846`), then
  a second `section()`/`card()` for "Updates" (`1851-1860`).
- `Store.__init__` (`afk_clicker.py:802-835`): `self.data` starts as a
  fixed dict of known keys with defaults
  (`{"games": {}, "hotkey": None, "selected": None, "appearance": "system"}`,
  `804-805`); `self.data.update({k: v for k, v in loaded.items() if k in
  self.data})` (`816`) only ever pulls in keys that dict already defines,
  so an old file missing a key keeps that key's built-in default — no
  migration needed for a new additive key (story.md's Decision 0). Then a
  narrow, one-line sanitization per key follows the same shape: `appearance`
  is checked against `("system", "light", "dark")` and reset to `"system"`
  if it doesn't match (`834-835`).
- `Segmented.__init__(self, parent, options, variable, s, width=CARD_INNER_W,
  height=34)` (`afk_clicker.py:1195-1215`) already takes an arbitrary-length
  `options` list of `(value, label)` tuples and divides its own width evenly
  among them (`seg = self.w / len(options)`, `1211`) — a 4-option control
  needs zero changes to this class.
- `CONTENT_W = 452`, `SIDEBAR_W = 208`, `CONTENT_PAD = 16`, `CARD_R = 12`,
  `CARD_INNER_W = CONTENT_W - 2*CONTENT_PAD - 2*CARD_R = 396`
  (`afk_clicker.py:151-157`). The Theme `Segmented` inside the Appearance
  card's `Row` is built at an explicit `width=180` (`1837`), narrower than
  the full `CARD_INNER_W`, because it shares its `Row` with a text label —
  `Row` (`1401-1414`) packs a flexible label (`side="left", expand=True`)
  against a fixed-width control (`side="right"`), so the control's width is
  whatever is passed to the widget inside it, not the full card width.
  `Row`'s own label has no `wraplength`, so it needs enough leftover
  horizontal room next to whatever the control's width is — comfortably
  true here (see §1).
- The two other fixed-pixel controls the dispatch calls out — the
  `StatusPill` at `width=250` (`afk_clicker.py:1554`) and the two hotkey
  `Button`s at `width=124` (`1767-1768`) — are **not** in the Settings page
  at all (the pill is in the header, the buttons are on a game page's
  hotkey card), so they are not competing for room with the new
  `ui_scale` `Row`. They matter only as the widest fixed-pixel widths that
  exist anywhere in the file, for the "does anything clip at the largest
  step" analysis in §1.

## Proposed approach

### 1. The steps, the persisted key, and why nothing new clips

**Chosen: 4 explicit percentage steps — `90%`, `100%` (default), `115%`,
`130%`.**

A new module-level dict, placed right after `set_active_theme`
(`afk_clicker.py:94-120`) and before `resolve_appearance` (`122`) — grouped
with `THEMES` (`78-93`) as "a persisted enum key → the concrete value it
resolves to," the same category `THEMES` is already in, not with the
purely-dimensional constants at `151-157`:

```python
UI_SCALE_FACTORS = {"90": 0.9, "100": 1.0, "115": 1.15, "130": 1.3}
UI_SCALE_DEFAULT = "100"
```

`Store.__init__` (`802-835`) gains a fourth default,
`"ui_scale": UI_SCALE_DEFAULT`, in the dict at `804-805`, and a fourth
sanitization block mirroring `appearance`'s (`834-835`):
```python
if self.data["ui_scale"] not in UI_SCALE_FACTORS:
    self.data["ui_scale"] = UI_SCALE_DEFAULT
```
This is the identical shape Decision 0 in `docs/story.md` already blessed
for `"appearance"` — no schema version, no migration, a garbage/foreign/
missing value just becomes the default.

**Why percentages, not `Small/Default/Large`.** Every other Segmented
label set in this file names a discrete *mode* (`System/Light/Dark`,
`Left/Right/Mid`) where the words carry the full meaning. A size choice is
inherently a magnitude, and "Large" tells a user nothing about how much
bigger — "130%" does, and matches the vocabulary Windows' own Settings →
Display and every major browser already use for this exact control, so
nothing needs to be learned. Rejected as unnecessary translation of a
number the user already thinks in.

**Why 4 steps, not 3.** A single jump from 100% straight to "Large" risks
overshooting for someone who just wants a little more headroom — a
mid-point (115%) covers that case cheaply, at zero extra mechanism cost
(`Segmented` already handles arbitrary option counts). Not pushed further
than this — this is a product-feel call, not a constraint anything else in
the codebase forces; if the ux-designer or a later review wants 3 or 5
steps, changing `UI_SCALE_FACTORS`'s entries and the sanitization tuple is
the entire cost, and doesn't touch anything else in this spec.

**Why not a slider.** No continuously-draggable control exists anywhere in
this file (`Segmented` is the only selector); building one is a new widget
class with new hit-testing/drag-event code, for a use case (choosing a
comfortable size once) that a handful of fixed steps already serves. Also:
the acceptance criteria's "each step changes `self.s` to DPI × step"
language and the DPI-multiplication model both assume a small, known,
testable set of factors — a slider would need to either quantize back down
to discrete factors anyway (pointless extra layer) or make "the smallest/
largest step" open-ended (harder to reason about the floor/clipping
analysis below at all). Rejected.

**Why nothing needs individual clipping verification per step.** Every
fixed pixel dimension in this file — `StatusPill`'s `250`, the hotkey
`Button`s' `124`, `Segmented`'s own `width=`, `SIDEBAR_W`, `CONTENT_W`, the
`minsize`/`geometry` formula itself — is multiplied by the *same* `self.s`
at construction time (§ Background). That means the ratio between any two
on-screen elements' sizes is invariant under a scale change: at 130% every
one of those numbers is exactly 1.3× (times the DPI factor) what it is at
100%, together, including the window's own `minsize`. A layout that
doesn't clip at 100% therefore cannot newly clip at 130% **provided the
window itself is allowed to grow to the new `minsize`** — which is exactly
why §2 (not per-widget pixel-pushing) is where the real risk in this
feature lives. This is also why the dispatch's "check `CONTENT_W` and text
widths" concern reduces to one concrete, bounded check rather than a sweep
of every widget:

**The new `Row`'s width.** Place it inside the existing Appearance `card()`
(§5), sharing the same `396`px inner width (`CARD_INNER_W`) as the Theme
`Row` above it. Theme's 3-option `Segmented` uses an explicit `width=180`
(`60`px/option) next to a `Row` label ("Theme", 5 characters). The new
`Row`'s label ("UI scale" or similar — ux-designer's exact copy call, §5)
is comparably short, and `"90%"/"100%"/"115%"/"130%"` are narrower per-
character than `"System"` (the longest Theme label). Recommended default:
`width=220` (`55`px/option, slightly tighter than Theme's `60`px/option
since the percent labels are shorter) — comfortably inside the `396`px
inner width alongside a short label, at every scale step, by the
invariant-ratio argument above. Exact pixel value is the ux-designer's to
adjust; the structural point (an explicit `width=`, not the
`CARD_INNER_W` default, matching Theme's own pattern) is what this spec
fixes.

### 2. Applying it — `self.s`, the rebuild, and `minsize`/`geometry`

**`self.s` becomes DPI × step, and the DPI half needs its own name.**
`AfkAutoclicker.__init__` currently computes and stores only the combined
value (`afk_clicker.py:1445`). Split it:
```python
self.store = store if store is not None else Store()
self._dpi_s = root.tk.call("tk", "scaling") / 1.333  # 1.0 at 96 dpi
self.s = s = self._dpi_s * UI_SCALE_FACTORS[self.store.data["ui_scale"]]
```
**Ordering matters and must change**: today `self.s` (`1445`) is computed
*before* `self.store` is assigned (`1446`) — harmless today since `self.s`
never read `self.store`, but this feature's `self.s` needs
`self.store.data["ui_scale"]` to already exist. `self.store = store if
store is not None else Store()` must move above the `self._dpi_s`/`self.s`
lines. (In the real `__main__` path this is moot — `store` is already a
fully loaded, sanitized `Store` instance passed in, `afk_clicker.py:2436`
— but `AfkAutoclicker(root)` with no `store=` argument, and every test that
does the same, self-constructs one, so the ordering is a real correctness
requirement, not just tidiness.) Every other line in `_build_ui`/its
helpers keeps reading `self.s` exactly as today — this is the only call
site that changes what `self.s` *means*.

**`minsize`/`geometry` — extracted into a reusable method, called two
different ways.** Today the two lines (`1460-1462`) run exactly once,
unconditionally, in `__init__`, establishing the initial tuned window size
— that behavior must not change. Extract them into:
```python
def _apply_minsize(self, grow_only=False):
    minw, minh = int((SIDEBAR_W + 1 + CONTENT_W) * self.s), int(690 * self.s)
    self.root.minsize(minw, minh)
    if not grow_only:
        self.root.geometry(f"{minw}x{minh}")
        return
    cur_w, cur_h = self.root.winfo_width(), self.root.winfo_height()
    new_w, new_h = max(cur_w, minw), max(cur_h, minh)
    if (new_w, new_h) != (cur_w, cur_h):
        self.root.geometry(f"{new_w}x{new_h}")
```
`__init__` calls `self._apply_minsize()` (default `grow_only=False`) at
exactly the point the two inline lines are today (`1460-1462`) —
byte-identical first-launch behavior, still outside `_build_ui`, still a
one-time call alongside `title`/`resizable`/`protocol`/`bind_all`.

A UI-scale change calls `self._apply_minsize(grow_only=True)` — `minsize`
is always updated to the new floor (a WM-level constraint independent of
the widget tree, safe to update regardless of rebuild timing), but
`geometry()` is only invoked, and only per-axis, when the window's
*current actual* size is below the new minimum — this is what makes
"grows when needed, never shrinks the user's size" literal: picking a
smaller step never calls `geometry()` at all if the window is already
bigger than the new (smaller) `minsize`, and picking a bigger step only
grows whichever axis (width, height, or both) actually falls short, using
`max()` against the window's real current size rather than overwriting it
outright.

**Reading `winfo_width()`/`winfo_height()` needs a realized window.** Same
caveat `card()`'s own `_redraw()` already documents for `shell.winfo_width()`
(`afk_clicker.py:1305`) — before the window has ever been mapped/updated,
these can report a placeholder (`1`) rather than the real size. In
practice this method is only ever called on an already-running
`AfkAutoclicker` (the user is on the Settings page, clicking a control on
an already-realized window), so this is not a startup-ordering concern the
way it would be for `card()`'s reentrancy hazard — flagged for the
developer/tests only so a test that calls `self.ui._apply_ui_scale(...)`
programmatically without ever having pumped the event loop first knows to
call `self.root.update()`/`update_idletasks()` beforehand, same as every
other geometry-reading test in `tests/test_ui.py` already does
(`WindowResize`, `738-756`).

**`_apply_ui_scale(value)` — structurally parallel to `_apply_appearance`
(`1862-1908`):**
```python
def _apply_ui_scale(self, value):
    if value not in UI_SCALE_FACTORS:
        value = UI_SCALE_DEFAULT
    self.store.data["ui_scale"] = value
    self.store.save()
    self.s = self._dpi_s * UI_SCALE_FACTORS[value]
    self._apply_minsize(grow_only=True)
    self._request_rebuild()
```
The `value not in UI_SCALE_FACTORS` guard mirrors `Store.__init__`'s own
sanitization defensively — the `Segmented` this is wired to only ever
emits one of the four valid keys, but the same belt-and-suspenders shape
`_apply_appearance` doesn't currently need (its caller, `resolve_appearance`,
already tolerates any string) is cheap insurance here since an invalid
`self.s` would be a visibly broken window, not just a wrong color.

**Shared coalescing helper — `_request_rebuild()`.** `_apply_appearance`'s
own tail (`1905-1908`) already contains the exact coalescing logic both
this method and `_apply_appearance` need:
```python
if self._rebuilding:
    self._rebuild_wanted = True
elif self._rebuild_after_id is None:
    self._rebuild_after_id = self.root.after_idle(self._rebuild_ui)
```
Extract this into `self._request_rebuild()` (a new, small method — moving
existing logic, not adding a new mechanism), and have both
`_apply_appearance`'s tail and `_apply_ui_scale`'s tail call it. This is
what makes "a scale change and a theme change fired quickly coalesce into
one rebuild" true **by construction**, exactly the same guarantee already
tested for repeated Appearance-only changes
(`tests/test_ui.py:2010-2027`) — no new state, no second flag, the same
`self._rebuilding`/`self._rebuild_wanted`/`self._rebuild_after_id` triple
now has two callers instead of one.

**Trace-registration order for the new `Segmented` — must match Theme's.**
`_apply_appearance`'s own docstring (`1871-1880`) explains why: Tcl fires a
variable's `write` traces most-recently-registered-first, and destroying
the `Segmented` mid-way through its own internal repaint trace (by
rebuilding synchronously) raises `TclError`. Theme avoids this because
`self.appearance_var.trace_add(...)` (`1848`) is registered *after* the
`Segmented(...)` call (`1836`) that registers the widget's own repaint
trace first — so Tcl fires `_apply_appearance` (added second) before the
`Segmented`'s own repaint (added first), and `_apply_appearance` itself
only ever defers the rebuild via `after_idle`, never rebuilds inline. The
new `ui_scale_var.trace_add(...)` must be registered the same way, after
its `Segmented` is constructed — same ordering, same reason, same safety
argument, not a new one.

### 3. Fonts — checked, no new floor added

The smallest font base anywhere in the file is `int(8 * s)`
(`section()`'s header labels at `1272`, the "System is currently…" hint at
`1846`, `count_label` at `1565`). At the smallest chosen step (`90%`,
factor `0.9`) and a DPI factor of `1.0` (`tk scaling == 1.333`, the
"1.0 at 96 dpi" baseline this file's own comment names, and what
`tests/test_ui.py:739`'s `s = self.ui.s` observes in this project's own
Xvfb CI environment today): effective `s = 0.9`, `int(8 * 0.9) =
int(7.2) = 7` — never `0`, still legible. No other base font size in the
file is smaller than `8`.

**No floor/clamp helper is being added.** Doing so would mean touching
all ~20 `int(base * s)` font call sites (or introducing a small `fs(base,
s)` wrapper and swapping every one of them over) for a failure mode that
doesn't occur at the steps this spec actually picks — exactly the kind of
speculative surface `_conventions.md` §3 warns against building ahead of a
real need. **Assumption this relies on, stated explicitly**: `self._dpi_s
>= 1.0` in practice — no Windows display configured below 100% scaling
(Windows' own UI doesn't offer that), and no Linux/X11 `Xft.dpi` set below
the 96dpi baseline this codebase already treats as "1.0". If a future
report shows a real display where `self._dpi_s < 1.0` combined with the
`90%` step produces an uncomfortably small or `0`-sized font, the fix is
the small wrapper described above, added then — not built speculatively
now.

**Rounding can still collapse two adjacent sizes to the same integer**
(e.g. bases `8` and `8.5` both floor to `7` at `s = 0.9`) — this is an
existing, already-live property of `int(base * s)` at any non-integer `s`
(today's DPI-only scaling already produces this at odd DPI values), not a
new defect this feature introduces. Not guarded against.

### 4. Interaction with Appearance

Covered structurally by §2's `_request_rebuild()` extraction — both
`_apply_appearance` and `_apply_ui_scale` end by calling the same method,
so the existing `self._rebuilding`/`self._rebuild_wanted`/
`self._rebuild_after_id` coalescing (already proven for repeated Appearance
changes alone) applies identically to any interleaving of the two, with no
new code path to reason about.

### 5. Settings page layout — inside the Appearance card, not a new one

Add a second `Row` to the existing Appearance `card()` (`afk_clicker.py:
1828-1846`), directly below the Theme `Row`, before the "System is
currently…" hint label:
```python
row2 = Row(ap, "UI scale", s)          # exact copy: ux-designer's call
row2.pack(fill="x", pady=(int(8 * s), 0))
self.ui_scale_var = tk.StringVar(value=self.store.data["ui_scale"])
Segmented(row2.control,
          [("90", "90%"), ("100", "100%"), ("115", "115%"), ("130", "130%")],
          self.ui_scale_var, s, width=220).pack()
self.ui_scale_var.trace_add("write",
    lambda *_a: self._apply_ui_scale(self.ui_scale_var.get()))
```
(Registered after the `Segmented(...)` call, per §2's ordering
requirement.)

**Why inside the Appearance card, not its own section/card.** Every other
section on this page (Appearance's Theme, Updates' Version+button) holds a
substantive, multi-part control; a lone-`Row` "UI Scale" section would be
the only one-row card on the page, structurally inconsistent with the
page's established rhythm. "Appearance" as a heading already covers "how
the app looks," which a size choice is squarely part of, and there is no
non-visual reason to split it out — no separate persistence timing, no
separate rebuild path, nothing Feature 3's Updates split (`docs/spec.md`'s
own 3b rationale, now superseded by this file) needed to justify *its*
separation. Rejected as unneeded structure for a single control.

**Left to the ux-designer**: the row's exact label text, whether a hint
line similar to "System is currently…" is warranted (recommendation: no —
there's no "detected" value to report the way Theme's System option has
one), and fine-tuning the `220`px width from §1.

## Affected areas
- `afk_clicker.py` only, one file, the same architectural layer every prior
  feature in this story touched (Tk UI):
  - New module-level `UI_SCALE_FACTORS`/`UI_SCALE_DEFAULT` (placed near
    `THEMES`, ~line 93).
  - `Store.__init__` (`802-835`): new `"ui_scale"` default key + one
    sanitization block, same shape as `appearance`'s.
  - `AfkAutoclicker.__init__` (`1443-1526`): reorder `self.store` before
    `self.s`; split `self.s` into `self._dpi_s` × the stored step; replace
    the inline `minsize`/`geometry` lines with a call to the new
    `_apply_minsize()`.
  - New methods: `_apply_minsize(self, grow_only=False)`,
    `_apply_ui_scale(self, value)`, `_request_rebuild(self)` (the last one
    also removes the duplicated tail logic from `_apply_appearance`,
    replacing it with a call to `_request_rebuild()`).
  - `_build_settings(s)` (`1806-1860`): new `Row` + `Segmented` +
    `self.ui_scale_var` inside the existing Appearance card.
  - No changes to `Segmented`/`Button`/`StatusPill`/any other widget class,
    `_build_content`, `_rebuild_ui`, `_show_settings`, `resolve_appearance`,
    `set_active_theme`, `THEMES`, or any updater/hotkey/click-loop code.
- `tests/test_ui.py`: new tests per Acceptance criteria below; no existing
  test's *expected* values change (existing Appearance/`WindowResize`
  tests all compute their expectations from `self.ui.s`/`self.root.minsize()`
  dynamically, not a hardcoded literal, so a `ui_scale` default of `"100"`
  — factor `1.0`, a no-op multiplier — leaves every one of them passing
  unmodified; confirmed by reading `WindowResize` at `738-756` and the
  `AppearanceThemeSwitch`/`OverlappingAppearanceChanges` classes).
- `README.md`: if it documents the Settings page's contents (worth a
  one-line mention of the new Scale control, mechanical, same class of fix
  Feature 3b made for its own Settings relocation) — the developer should
  check `README.md`'s current Settings/Appearance section and add a line
  if one exists; not a structural requirement of this spec either way.
- No data model change beyond the one new `settings.json` top-level key.
  No new public interface beyond `_apply_minsize`/`_apply_ui_scale`/
  `_request_rebuild` (new methods, no existing signature changes).

## Edge cases
- **A `settings.json` with no `"ui_scale"` key** (every pre-this-feature
  file, including a real v0.3.1 file): `Store.__init__`'s default fills it
  as `"100"` before any sanitization runs — behavior identical to today's
  DPI-only scaling (factor `1.0`).
- **A garbage `"ui_scale"` value** (wrong type, an old draft's different
  naming, a value outside the four keys, e.g. a hand-edited `"120"`):
  sanitized to `"100"` in `Store.__init__`, same as a garbage `"appearance"`
  already is.
- **A UI-scale change while the window has been manually resized larger
  than any `minsize`** (`#14`'s resizability): `_apply_minsize(grow_only=
  True)`'s `max(cur, new_min)` never shrinks below the user's actual
  current size in either direction — picking a smaller step after
  manually maximizing the window leaves the window exactly where the user
  put it.
- **A UI-scale change while the window is still at its just-launched
  minimum size** and the user picks a bigger step: both dimensions grow to
  the new `minsize` exactly (the "grows when needed" case).
- **A UI-scale change and an Appearance change fired back-to-back with no
  pump between them** (the real interaction §4 exists for): coalesce into
  one rebuild via the shared `_request_rebuild()` — both the theme and the
  scale in effect when the (single) rebuild finally runs are whichever was
  most recently set, same "latest choice wins, nothing lost" guarantee
  `_apply_appearance`'s own docstring already describes for repeated
  Appearance changes alone (`1882-1889`).
- **A UI-scale change fired while a rebuild is already running**
  (reentrant case, same shape as `_apply_appearance`'s own documented
  hazard at `1891-1904`): `_request_rebuild()` sees `self._rebuilding` and
  only sets `self._rebuild_wanted`, never schedules a second `after_idle`
  job inline — the exact protection `_rebuild_ui`'s `finally` block
  already provides, now shared by both callers.
- **A running clicker (`self.worker` mid-click-loop, `self.hk_listener`
  registered) during a scale-triggered rebuild**: unaffected — none of
  that state lives in the destroyed/rebuilt widget tree (§ Background),
  the identical guarantee already proven for Appearance changes.
- **`CapturesCallbackExceptions`**: every new code path here (`Segmented`
  click → trace → `_apply_ui_scale` → `_apply_minsize`/`_request_rebuild`
  → eventual `_rebuild_ui`) runs through the same Tk callback/trace/
  `after_idle` machinery already covered by this harness in every existing
  Appearance test — no new thread, no new place an exception could escape
  uncaught.
- **Platform differences**: none — `self._dpi_s`'s source
  (`root.tk.call("tk", "scaling")`) is already cross-platform and
  untouched; `enable_dpi_awareness()` (Windows-only, `189-205`) is
  unchanged.
- **Permission boundaries**: none — a local, unprivileged UI preference,
  same category as `appearance`.

## Acceptance criteria
- [ ] Given each of the four `ui_scale` values (`"90"`, `"100"`, `"115"`,
      `"130"`), when `self.ui._apply_ui_scale(value)` is called, then
      `self.ui.s == self.ui._dpi_s * UI_SCALE_FACTORS[value]`.
- [ ] Given a UI-scale change, when it applies, then a sampled widget's
      pixel size and font scale accordingly — e.g. `self.ui.status.w ==
      int(250 * self.ui.s)` (the header `StatusPill`, rebuilt fresh) and
      the Theme `Segmented`'s own `font` size on one of its text items
      reflects `int(9 * self.ui.s)`.
- [ ] Given `self.root.minsize()` before and after a UI-scale change, then
      it updates to `(int((SIDEBAR_W + 1 + CONTENT_W) * self.ui.s),
      int(690 * self.ui.s))` every time.
- [ ] Given the window is at its current `minsize` and a bigger step is
      picked, when the change applies, then `self.root.winfo_width()`/
      `winfo_height()` grow to (at least) the new `minsize`.
- [ ] Given the window has been manually resized larger than any
      `minsize` (`self.root.geometry("1000x900")` then `self.root.update()`,
      matching `WindowResize`'s own existing pattern at `746-747`), when
      any UI-scale change (bigger or smaller) is applied, then
      `self.root.winfo_width()`/`winfo_height()` are unchanged — never
      shrunk.
- [ ] Given a `ui_scale` choice other than the default, when
      `self.ui.store.save()` has run and `self.restart()` (the existing
      test helper, `tests/test_ui.py:149-154`) is called, then the new
      `self.ui.s`/`self.ui.ui_scale_var.get()` reflect the persisted
      choice with no Settings visit needed — the relaunch case.
- [ ] Given a garbage on-disk `"ui_scale"` value (write it directly into
      the test's `settings.json` file, matching
      `test_a_missing_appearance_key_defaults_to_system`'s own technique
      at `tests/test_ui.py:1500-1505`), when a fresh `Store`/`AfkAutoclicker`
      loads it, then `self.ui.store.data["ui_scale"] == "100"` and
      `self.ui.s == self.ui._dpi_s`.
- [ ] Given a UI-scale change and an Appearance change fired with no pump
      between them (either order), when the event loop is pumped once,
      then exactly one rebuild ran (same counting-wrapper technique as
      `test_five_rapid_appearance_changes_coalesce_into_exactly_one_rebuild`,
      `tests/test_ui.py:2010-2027`, generalized to interleave
      `_apply_ui_scale` calls), and the final rendered state reflects both
      the last-picked scale and the last-picked theme.
- [ ] Given the clicker is running (`self.ui.start()`/a real worker thread,
      matching `test_starting_from_a_background_thread_drops_focus`'s setup
      at `tests/test_ui.py:718-731`) when a UI-scale change applies, then
      `self.ui.running`/`self.ui.worker` are unaffected and the click loop
      is not interrupted.
- [ ] Given any of the above scenarios, when the test's `tearDown` runs
      (`UITestCase.tearDown`, `81-86`), then `CapturesCallbackExceptions`
      reports zero uncaught callback exceptions.

## Open questions
None that block starting. One flagged for confirmation rather than
silently assumed:

1. **The exact step values (90/100/115/130) and count (4).** My
   recommendation is firm with the reasoning in §1, but it's a product-feel
   call, not one forced by the code — if 3 steps, different percentages, or
   named steps are preferred instead, that's a one-dict change
   (`UI_SCALE_FACTORS` + its sanitization tuple + the `Segmented` options
   list in §5) and doesn't otherwise touch this spec's structure.

## Story completion

This is the story's last feature. Once it's reviewed and approved,
`workflows/story.md` calls for one final end-to-end pass over the whole
story before it's marked complete. That pass must cover, together, not
feature-by-feature in isolation:

- **On a fresh install (no `settings.json` at all)**: the app opens with
  Deepslate/Quartz shapes (Feature 1), the OS-detected theme applied
  (Feature 2, `"appearance": "system"` default), the Settings tab reachable
  with Appearance (Theme + the new Scale control) and Updates both present
  and functional (Feature 3), and `ui_scale` defaulting to `100%` (this
  feature) — a single walkthrough exercising every tab, every Settings
  control, and the hotkey card (still only reachable from a game page),
  confirming nothing from any one feature regressed another.
- **On a `settings.json` carried over from v0.3.1** (this project's actual
  pre-story version, `afk_clicker.py:495` — i.e. a file holding only
  `"games"`/`"hotkey"`/`"selected"`, no `"appearance"`, no `"ui_scale"`):
  the same walkthrough, confirming both new keys' absence resolves to
  their documented defaults (`"system"`, `"100"`) with no migration step,
  no crash, and no visibly different behavior from the fresh-install case
  above at the same OS theme.
- **Combined Theme + Scale changes, from Settings, in the same session, on
  both file states above**: at least one Theme change and one Scale change,
  in both orders, confirming the coalesced-rebuild guarantee and the
  correct final rendered state (§4 of this spec) hold end-to-end, not just
  in the isolated tests each feature's own spec added.
- **A running clicker throughout**: start the clicker before opening
  Settings, make Theme/Scale/Updates-adjacent changes while it runs,
  confirm it's never interrupted — the cumulative version of the
  per-feature "a running clicker survives" checks.
- **`CapturesCallbackExceptions` clean across the whole walkthrough**, not
  just within each feature's own test class.
