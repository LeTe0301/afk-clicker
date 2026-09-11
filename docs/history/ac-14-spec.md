# Spec: Number fields keep focus, and the window cannot be resized

## Summary
`NumBox` entries only drop their focus highlight on `<FocusOut>`, which Tk fires
solely when another widget takes focus — nothing else in this window ever does
that today — so a field stays focused and keeps eating keystrokes indefinitely
after being edited; separately, `AfkAutoclicker`'s window is hard-locked to one
fixed size (`resizable(False, False)` + an explicit `geometry()`), so it cannot
be resized at all. Both are fixed together as one ticket (Gitea `admin/afk-clicker#14`,
GitHub #16): fields become easy to defocus while staying fully typeable, and the
window becomes resizable with a sensible floor and no dead horizontal gutter.

## Goals
- A `NumBox` entry drops its focus highlight (wrap turns `LINE`) and releases
  keyboard focus when: the user clicks anywhere else in the window (background,
  a label, a card, the sidebar, a button, a segmented control), presses Enter,
  presses Escape, or the clicker starts (global hotkey fires while a field is
  focused).
- `Tab`/`Shift-Tab` traversal between fields is unaffected.
- Typing in a field, and every existing way its value reaches settings
  (per-keystroke persistence, the 200 ms snapshot used by the click loop),
  keeps working exactly as today.
- The window can be resized by dragging its edges/corner, with a minimum size
  below which it refuses to shrink further, and the content pane visibly uses
  extra width instead of leaving a blank strip.

## Non-goals
- No redesign of the card/row/canvas-widget layout. Buttons, the segmented
  control, `StatusPill` and `GameItem` stay fixed-pixel-size canvases, same as
  today.
- No "revert value on Escape". See Decision 2 below for why.
- No persisting window size or position across restarts.
- No change to vertical use of extra space beyond "don't clip": some blank
  space below the last card when the window is made taller than its content
  needs is expected and left alone (see Decision 3).
- No new dependency, no second GUI toolkit (`docs/TECHSTACK.md`).
- No settings-format change (`docs/ROADMAP.md`: no schema version exists yet).

## Background / current state
- `NumBox` (`afk_clicker.py:948-963`) wraps a `tk.Entry` in a 1px `wrap` Frame
  and only binds `<FocusIn>`/`<FocusOut>` (962-963) to recolour it between
  `ACCENT` and `LINE`. No other widget in the window ever takes focus on
  click — `Button` (758-804), `Segmented` (806-847), `GameItem` (897-926) and
  `StatusPill` (850-869) are all plain `tk.Canvas` subclasses bound only to
  `<Button-1>` for their own click action, with no focus-follows-click
  binding, and `Row`/`card`/labels are plain `tk.Frame`/`tk.Label`. So once a
  field is focused, nothing the user clicks besides another `Entry` ever fires
  `<FocusOut>` on it.
- A value reaches settings in exactly two ways, both already live/continuous,
  neither gated by blur:
  - Every `NumBox.var` (and every other settings var) has a
    `var.trace_add("write", ...)` (1122-1125) that calls `self._persist()` on
    *every keystroke*, which reads the raw `field.var.get()` text through
    `self._num()` (1312-1317, tolerant: clamps to a minimum, falls back to a
    default on anything that doesn't parse) and writes it to `self.store`.
  - `_sync_settings()` (1341-1362) re-reads the same vars through the same
    `_num()` every 200 ms into `self.settings`, the dict the click-loop thread
    actually reads.
  - There is no separate "committed" value anywhere — the live text *is* the
    source of truth, continuously clamped/validated at read time. See
    Decision 2.
- `AfkAutoclicker.__init__` (966-980): `root.resizable(False, False)` (974),
  then an explicit `root.geometry(f"{...}x{int(690 * s)}")` (979) sized from
  `SIDEBAR_W` (208) and `CONTENT_W` (452). The comment above it (975-978)
  explains the explicit geometry is needed because both panes disable
  geometry propagation, so nothing else tells the window how tall to be.
- Panes (1017-1046): `side` (1021-1023) is packed `side="left", fill="y"`
  (no `expand`), width frozen at `SIDEBAR_W * s` via `pack_propagate(False)`.
  `self.content` (1043-1046) is packed `side="left", fill="both", expand=True`,
  width frozen at `CONTENT_W * s`, also `pack_propagate(False)`. `shell`
  (1017-1018) itself is `fill="both", expand=True` under `header`.
- `start()` (1443-1460) is reached **only** through `toggle()` (1440-1441),
  which is the `callback` a `HotkeyWatcher` (343-367) invokes directly from
  the `pynput.keyboard.Listener` thread — never from the Tk main thread. Every
  other Tk touch inside `start()`/`stop()` already goes through `self._ui()`
  (e.g. `self._ui(self.status.set, ...)` at 1457-1458) per
  `docs/CODING-GUIDELINES.md`'s "only the main thread may touch Tk".

## Proposed approach

### Focus

**Decision 1 — how "click anywhere else" is implemented.**
Add one application-wide binding in `AfkAutoclicker.__init__`, right after
`root.protocol("WM_DELETE_WINDOW", self.on_close)` (980):

```python
root.bind_all("<Button-1>", self._maybe_drop_focus)
```

```python
def _maybe_drop_focus(self, event):
    # Only an Entry's own class binding should keep it focused on click --
    # every other click (background, a label, a card, the sidebar, a
    # Button/Segmented/GameItem canvas) drops it, so a field stops looking
    # and acting focused the moment you click away instead of only when Tk
    # happens to hand focus to something else.
    if not isinstance(event.widget, tk.Entry):
        self.root.focus_set()
```

Rejected alternatives:
- *Bind `<Button-1>` on the root/canvas backgrounds only.* Would miss labels,
  cards, the sidebar list and every button — exactly the set of widgets the
  ticket calls out as not currently taking focus. The `isinstance` check
  above is the narrowest binding that still covers all of them with one line,
  because `NumBox`'s `Entry` is the *only* `tk.Entry` anywhere in the module
  (verified: `grep -n "tk.Entry" afk_clicker.py` returns exactly one hit, the
  one in `NumBox.__init__`).
- *Return `"break"` from the handler.* Not needed and rejected: `bind_all`'s
  "all" bindtag fires last in Tk's per-widget bindtag order (widget → class →
  toplevel → all), *after* `Button`/`Segmented`/`GameItem`'s own `<Button-1>`
  handlers and after `Entry`'s own class binding that focuses itself on
  click. Returning `"break"` would risk suppressing something later in the
  chain for no benefit; not returning it lets every existing click handler
  keep firing unmodified, which is the whole point (must not break button/
  segmented/game-list clicks, per the ticket).
- *Track "the currently focused NumBox" explicitly and defocus by object
  identity.* More state than needed — `isinstance(event.widget, tk.Entry)` is
  already exact because there is nothing else to confuse it with.

Verified empirically (not just reasoned about) with a standalone script under
`DISPLAY=:99`, reproducing `NumBox`'s wrap/FocusIn/FocusOut pattern plus a
`Label` and a `Canvas` with its own `<Button-1>` binding, against exactly this
handler: clicking the label or the canvas drops focus and greys the wrap
while the canvas's own click still fires; clicking the entry (itself, or a
second entry) leaves/gives it focus normally. One environment quirk found
during that verification, which the reviewer will hit too: under Xvfb with no
window manager, a freshly created `tk.Tk()` never actually owns X input focus,
so `focus_set()` alone produces no `<FocusIn>`/`<FocusOut>` at all and
`focus_get()` reads `None` no matter what — `root.focus_force()` has to be
called once to make the toplevel genuinely own input focus before any
`focus_set()`-based assertion (in the app *or* in a test) will observe
anything. The app itself must keep using `focus_set()`, not `focus_force()`
— on a real desktop the window already owns input focus by the time a click
lands in it, and forcing focus is the aggressive, WM-stealing call, not the
normal one. The one-time `focus_force()` is a **test-setup** detail: cleanest
place for it is `UITestCase.setUp` (`tests/test_ui.py:34-39`), once, right
after `self.settle()` — every other existing test is unaffected by an
already-owned input focus, and every new focus test gets it for free instead
of repeating it.

Enter/Escape are bound directly on each `NumBox`'s `Entry`, next to its
existing `<FocusIn>`/`<FocusOut>` binds (`afk_clicker.py:962-963`):

```python
entry.bind("<FocusIn>", lambda e: wrap.config(bg=ACCENT))
entry.bind("<FocusOut>", lambda e: wrap.config(bg=LINE))

def _blur(e):
    e.widget.winfo_toplevel().focus_set()
entry.bind("<Return>", _blur)
entry.bind("<Escape>", _blur)
```

`winfo_toplevel()` is used instead of wiring a reference to `AfkAutoclicker`'s
`root` into `NumBox` (which today takes no such reference) — `NumBox` stays a
self-contained, reusable widget. Verified with the same kind of standalone
script: `event_generate("<Return>")`/`("<Escape>")` on a focused entry drops
focus and greys the wrap; the `StringVar` keeps its typed value either way.

**Decision 2 — defocusing does not revert or re-validate the value.**
There is no "commit" step to revert *from* — `_persist()` already writes the
live text on every keystroke via the var trace (1122-1125), and
`_sync_settings()` already re-reads the live text every 200 ms through the
tolerant, clamping `_num()` (1312-1317). Both already treat the field as a
live, continuously-validated source, never a value that becomes "final" only
at blur. Escape *reverting* to the value at focus-in would mean inventing a
new concept this codebase doesn't have anywhere else (a cached pre-edit
snapshot per field, compared against on blur) for a single control, which
`docs/CODING-GUIDELINES.md`'s validation model argues against: validation
already happens "at the point of use" (`_num`, called both by `_persist` and
by the click loop's settings snapshot), not at entry. So: Enter and Escape
both simply blur the field; the text already typed is exactly what was
already being persisted and clamped, unchanged by which key (or click) ended
the edit.

**Decision — clicker starting also drops focus.**
There is no in-window "Start" button; `start()` (1443-1460) is reached only
through the global hotkey, whose `HotkeyWatcher` callback runs on the
`pynput` listener thread, not the Tk main thread (see Background). So the
drop has to go through `_ui()` like every other Tk touch in `start()`/
`stop()`:

```python
def start(self):
    if self.running:
        return
    ...
    self.running = True
    self._ui(self.root.focus_set)
    self._ui(self.status.set, "RUNNING", OK, ...)
    ...
```

`self._ui(self.root.focus_set)` is enough — `_ui()` queues `(fn, args)` and
`_drain_ui` later calls `fn(*args)`; `root.focus_set` takes no arguments, so
no new wrapper method is needed.

### Resize

**Decision 3 — the resize model.**
Replace `afk_clicker.py:974-979`:

```python
root.resizable(True, True)
# Both panes still turn off geometry propagation to hold their tuned widths,
# so nothing tells the window how tall to start -- without an explicit size
# the body collapses to zero height and only the header shows. minsize keeps
# the window from ever being resized below the size the layout was tuned at,
# so nothing clips.
minw, minh = int((SIDEBAR_W + 1 + CONTENT_W) * s), int(690 * s)
root.minsize(minw, minh)
root.geometry(f"{minw}x{minh}")
```

No other line changes. Reasoning, verified empirically (not just read from
the pack docs) with a standalone script reproducing `shell`/`side`/`content`'s
exact pack calls under `DISPLAY=:99`: `side` is packed `fill="y"` only (no
`expand`), so it never changes width on resize — confirmed: after growing the
window from 660 to 1000 px wide, `side.winfo_width()` stayed exactly 208.
`self.content` is *already* packed `fill="both", expand=True` (1044) — the
only expanding slave in `shell` — so it already absorbs 100% of any extra
width the window gains: confirmed, `content.winfo_width()` went from 452 to
792 (= 1000 − 208), exactly the extra space, with zero pack-option changes.
So:
- **Which pane grows:** `self.content`. `side` stays pinned at `SIDEBAR_W`.
  This falls straight out of the pack options already in the file — nothing
  new to add.
- **Minimum size:** the exact size the layout ships at today
  (`(SIDEBAR_W + 1 + CONTENT_W) * s` wide, `690 * s` tall). It is already the
  size the layout was tuned against (including the taller Minecraft profile
  with the eating card visible), so reusing it as the floor guarantees
  nothing clips, with no new tuning. Verified: `root.geometry("50x50")`
  against this `minsize` left `winfo_width()`/`winfo_height()` at exactly
  `minw`/`minh` — Tk enforces it itself even with no window manager present
  (Xvfb), so this is reliably testable, not just true on a real desktop.
- **Does the content column stretch or stay capped and centered:** stretches,
  uncapped. Rejected: capping `self.content` at `CONTENT_W` and centering it
  with padding frames. That would require *adding* pack structure (new filler
  frames, or switching `content` from `pack` to `place`) for a cosmetic
  difference the ticket doesn't ask for, whereas letting it stretch needs
  zero new code — `fill="both", expand=True` is already there. Practical
  effect of stretching: `Row`'s label side (`text`, packed
  `side="left", fill="x", expand=True`, `afk_clicker.py:937-938`) gets more
  breathing room; `Row.control` (packed `side="right"`, no fill/expand,
  944-945) — where every `NumBox`/`Segmented` lives — stays pinned to its
  natural size on the right edge of the row, same as today. A two-button row
  like `btns` in the hotkey card (1086-1091, `Record` left / `Apply` right)
  will show a wider gap between the two buttons on a wide window; that is a
  pre-existing anchor-to-opposite-edges layout choice, not new dead chrome,
  and is left alone as a minor, expected cosmetic consequence rather than
  something this ticket re-architects.
- **Fixed-size canvases:** unchanged. `Button`, `Segmented`, `StatusPill`,
  `GameItem` keep their configured pixel width/height and whatever `pack`
  side they already use; none of them are touched.

This does **not** need splitting into a "part 1 / part 2" per skill 11 —
confirmed by the empirical check above that the width behavior needs zero
pack-option changes, only the three-line `resizable`/`minsize`/`geometry`
swap. If that check had come out the other way (content pane *not* already
absorbing extra width), the honest move would have been to say so here and
propose shipping focus first — it didn't.

**Decision 4 — no window size/position persistence across restarts.**
Confirmed, not argued otherwise: `docs/ROADMAP.md`'s "Settings schema
version" item explicitly flags that `settings.json` has no version field yet
and a format change today has no migration path. Adding a `window` key would
be exactly that kind of format change, for a feature the ticket doesn't ask
for. `on_close` (`~1545-1560`) and `Store` are left untouched.

## Affected areas
- `afk_clicker.py` only: `NumBox.__init__` (948-963), `AfkAutoclicker.__init__`
  (966-980), a new `_maybe_drop_focus` method, `start()` (1443-1460). One
  file, one architectural layer (the Tk UI) — no split needed.
- `tests/test_ui.py`: `UITestCase.setUp` (34-39, add one `focus_force()`
  line), plus new test classes/methods for focus and resize behavior.
- No data model, schema, or API changes.

## Edge cases
- **Clearing a field entirely, then clicking away.** `_num()` already
  falls back to a default on unparseable/empty text (verified by the
  existing `NumericClamping` tests); defocusing doesn't add a second path
  that needs its own handling.
- **Clicking the 1px `wrap` border itself, not the `Entry` inside it.** `wrap`
  is a `Frame`, not an `Entry`, so a click that lands exactly on that 1px
  padding defocuses too. Accepted as part of "click anywhere else" rather
  than special-cased — the target is a few pixels wide and the behavior
  (defocus) is the same one the ticket asks for everywhere else.
- **Switching focus directly from one `NumBox` to another by clicking into
  it.** Handled by `Entry`'s own class binding (fires before the `"all"`
  bindtag), not by `_maybe_drop_focus` — the `isinstance` check skips it.
- **The global hotkey firing while a field is mid-edit.** Covered by the
  `start()` change; the defocus is queued through `_ui()` like every other
  cross-thread Tk touch, so it lands within one `_drain_ui` tick (≤40 ms),
  the same latency every other hotkey-triggered UI update already has.
- **Tab traversal.** Untouched — no new binding on `<Tab>`/`<Shift-Tab>`,
  and `_maybe_drop_focus` only binds `<Button-1>`.
- **Shrinking below `minsize`.** Tk clamps it itself (verified under Xvfb
  with no window manager present, so this holds in the review environment
  too, not just on a real desktop).
- **Growing very wide (e.g. an ultrawide/multi-monitor drag).** `self.content`
  stretches unbounded; no `maxsize` is set, matching "use the extra space".
- **Switching game profiles at different window sizes** (e.g. Minecraft's
  taller eating card vs. Global's shorter form). Unaffected by this change —
  panel visibility toggling (`_select`, 1139-1173) is untouched, and
  `minsize` is tuned to the taller (Minecraft) case, same as the current
  fixed geometry already is.
- **Cross-platform.** `resizable`/`minsize`/`geometry` and `bind_all` are
  plain, platform-uniform Tk/Tcl calls — no `sys.platform` branch is needed
  or added.

## Acceptance criteria
- [ ] Given a `NumBox` entry has focus (its `wrap` is `ACCENT`), when
  `<Button-1>` is delivered to a different, non-`Entry` widget (a game-title
  label, a card's background `Frame`, a `GameItem` in the sidebar, a `Button`
  or `Segmented` canvas), then `root.focus_get()` is no longer that entry and
  `wrap.cget("bg") == LINE`.
- [ ] Given the same setup, when `<Button-1>` is delivered to the focused
  entry itself, or to a *different* `NumBox`'s entry, then a `tk.Entry`
  (not the toplevel) ends up with focus — normal click-to-edit and
  click-to-switch-fields both still work.
- [ ] Given a `NumBox` entry has focus, when `<Return>` is delivered to it,
  then focus leaves the entry, its `wrap` turns `LINE`, and `entry.var.get()`
  is unchanged (no revert).
- [ ] Same as above for `<Escape>`.
- [ ] Given a `NumBox` entry has focus, when `self.ui.start()` runs (called
  directly, or from a background thread the way the real hotkey does) and the
  UI queue is drained (one `pump`/`root.update()` past 40 ms), then focus is
  no longer on that entry and its `wrap` is `LINE`.
- [ ] Given focus on some widget, when `<Tab>` fires, focus moves to another
  widget without error (traversal is not broken) — a non-regression check,
  not a pinned specific order.
- [ ] Clicking a `Segmented` control still changes its bound variable (e.g.
  the mouse-button segmented control), and clicking a `GameItem` still calls
  `_select` — non-regression checks that `_maybe_drop_focus` doesn't swallow
  or reorder existing click handling.
- [ ] After `AfkAutoclicker.__init__`, `root.resizable()` reports both axes
  resizable (Tcl `(1, 1)`), where today it reports `(0, 0)`.
- [ ] After `AfkAutoclicker.__init__`, `root.minsize()` returns
  `(int((SIDEBAR_W + 1 + CONTENT_W) * s), int(690 * s))`, not Tk's unset
  default of `(1, 1)`.
- [ ] Given the window at its default geometry, when
  `root.geometry("1000x900")` is applied and the display updates, then
  `self.ui.content.winfo_width()` is greater than it was before (grows to
  fill the extra width) while `self.ui.side` — or whatever attribute holds
  the sidebar frame — stays at its original width, unchanged.
- [ ] Given the window at its default geometry, when
  `root.geometry("50x50")` is applied and the display updates, then
  `root.winfo_width()`/`winfo_height()` do not go below the configured
  `minsize`.

## Open questions
None blocking. One assumption worth a human glance, not a blocker: Decision 3
treats the growing gap in two-button rows (e.g. `Record`/`Apply` in the
hotkey card) on a very wide window as an acceptable, pre-existing consequence
rather than something to fix — flagging it in case the answer is "actually
cap the content width after all," which would be a one-line change
(`content.pack(..., expand=False)` plus centering) if wanted, not a
re-architecture.

## Risk / rollback notes
- Both changes are additive/local: a new `bind_all` handler, two new
  per-`Entry` key bindings, one `_ui()` call added to `start()`, and a
  three-line swap of `resizable`/`geometry` calls. Nothing existing is
  removed except the `resizable(False, False)` line itself.
- If `_maybe_drop_focus` ever turns out too broad in practice (something
  legitimately needs to keep focus through a stray click, which nothing in
  this window currently does), the fix is narrowing the `isinstance` check,
  not architectural — low blast radius.
- Rollback is a straight revert of the diff in `afk_clicker.py`; no data
  migration, no settings-format change, nothing else depends on either
  change.
