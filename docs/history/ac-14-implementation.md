# Implementation: Number fields drop focus, window is resizable (ticket #14)

## Summary
`NumBox` entries no longer hold focus indefinitely: clicking any other widget, pressing
Enter/Escape, or the clicker starting (even from the hotkey thread) now blurs a focused
field. The main window is resizable with a floor equal to today's fixed size, and the
existing pack layout already sends all extra width to the content pane with zero
layout changes needed.

## Root cause
N/A (feature ticket, not a bugfix) — see spec's "Background / current state" for why
`<FocusOut>` never fired: nothing else in the window ever took focus on click.

## Changes by file
- `afk_clicker.py:958-970` (`NumBox.__init__`) — bound `<Return>`/`<Escape>` on the
  entry to a `_blur` closure that calls `e.widget.winfo_toplevel().focus_set()`
  (matches `docs/design.md`'s `NumBox bindings` section, using `winfo_toplevel()`
  instead of wiring a `root` reference into `NumBox` so it stays self-contained).
  Also stored `self.wrap`/`self.entry` on the instance — previously both were local
  variables inside `__init__`; tests (and nothing else) need to reach the wrap's
  background color and the entry widget from outside.
- `afk_clicker.py:978-990` (`AfkAutoclicker.__init__`) — replaced
  `root.resizable(False, False)` + a bare `geometry()` call with
  `root.resizable(True, True)`, `root.minsize(minw, minh)`, then
  `root.geometry(f"{minw}x{minh}")` using the same `minw`/`minh` computed from
  `SIDEBAR_W`/`CONTENT_W`/`690 * s` that the old geometry string used inline.
  Updated the comment above it (previously explained only why an explicit geometry
  is needed; now also explains what `minsize` is for) per the spec's explicit
  instruction to keep it true. Added
  `root.bind_all("<Button-1>", self._maybe_drop_focus)` right after
  `root.protocol("WM_DELETE_WINDOW", self.on_close)`, exactly where the spec places it.
- `afk_clicker.py:1032` — `side = tk.Frame(...)` became `side = self.side = tk.Frame(...)`.
  Not in the spec's line-by-line diff, but the spec's own acceptance criteria and design
  doc both refer to "`self.ui.side` — or whatever attribute holds the sidebar frame" to
  assert it doesn't grow; there was no existing attribute for it (`side` was previously a
  bare local), so one line was added to expose it without any other change.
- `afk_clicker.py:1330-1337` — new `_maybe_drop_focus` method, placed next to `_num`
  (both are small per-value helpers used by the main-thread UI), implementing exactly
  the spec's Decision 1 handler and comment.
- `afk_clicker.py:1477` (`start()`) — added `self._ui(self.root.focus_set)` right
  before the existing `self._ui(self.status.set, ...)` call. `start()` is reached only
  through `toggle()`, which `HotkeyWatcher` invokes directly from the `pynput` listener
  thread (confirmed by reading `HotkeyWatcher`/`toggle()`/`start()` — no code path calls
  `start()` from the Tk main thread), so the drop is queued through the existing
  `_ui()`/`_drain_ui()` mechanism per `docs/CODING-GUIDELINES.md`'s "only the main
  thread may touch Tk", the same way every other Tk touch already inside `start()`/
  `stop()` does it.
- `tests/test_ui.py:34-46` (`UITestCase.setUp`) — added one `self.root.focus_force()`
  call after `self.settle()`, exactly as the spec calls out: under Xvfb with no window
  manager a freshly created `tk.Tk()` never actually owns X input focus, so
  `focus_set()`-based assertions see nothing without it. The app itself still only ever
  calls `focus_set()`.
- `tests/test_ui.py:385-511` — two new test classes, `NumBoxFocus` (9 tests) and
  `WindowResize` (4 tests), covering every acceptance criterion in `docs/spec.md`.
  `NumBoxFocus` reuses the existing `UITestCase`/`FakeMouse` fixtures and drives real
  Tk events (`event_generate`) rather than calling internals directly, per the existing
  file's own style (see `ClickLoop`, `HotkeyPersistence`). A small `_find_segmented_for`
  helper walks `self.ui.content`'s widget tree by `isinstance(widget, app.Segmented)`
  and `widget.var is variable` to locate the mouse-button segmented control without
  adding any new attribute to the app for it — `Segmented` instances are ordinary
  `winfo_children()` results, so no new production code was needed for this.

## Key decisions / tradeoffs
- Exposed `NumBox.wrap`/`NumBox.entry` and `AfkAutoclicker.side` as instance attributes
  purely so the acceptance-criteria tests can observe them (`wrap.cget("bg")`,
  `root.focus_get() is entry`, `side.winfo_width()`). This is a small, test-driven
  surface addition, not called out line-by-line in the spec's diff, but it's the
  minimal way to make the spec's own acceptance criteria (which reference exactly
  these things) actually assertable from a test using only the public `self.ui.*`
  surface the rest of the suite already relies on.
- Followed the spec's rejected-alternatives reasoning as-is: no `"break"` return from
  `_maybe_drop_focus`, no explicit "currently focused NumBox" tracking, no revert-on-
  Escape, no width-capping/centering of the content pane. All matched empirically by
  running the actual suite (see below), not just re-derived from the spec's reasoning.

## Deviations from spec
None. The `self.side` attribute addition is the only production-code line not spelled
out in the spec's "Affected areas" list, and it exists solely to make an acceptance
criterion the spec itself specifies (comparing sidebar width before/after resize)
testable — it does not change any behavior.

## Known limitations
- Matches the spec's own listed non-goals: no window size/position persistence across
  restarts, no capping/centering of the content pane on very wide windows (the growing
  gap in two-button rows like Record/Apply is accepted, per spec Decision 3 and its
  "Open questions" note).

## How to verify locally
From the worktree root (`/home/dev/projects/.worktrees/afk-clicker/ac-14`):

```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```

Result observed in this session: **97 tests, OK, skipped=5** (baseline was 84 tests,
OK, skipped=5; the 13 new tests in `NumBoxFocus` and `WindowResize` account for the
difference, no regressions).

To run just the new tests:
```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest tests.test_ui.NumBoxFocus tests.test_ui.WindowResize -v
```
All 13 pass.

Manual check (optional, on a real desktop with a window manager): run `python
afk_clicker.py`, click into a click-interval field, click a card background or a
sidebar game — the field's border should turn from accent-yellow back to the default
line color and stop accepting keystrokes; press Enter/Escape while focused for the same
effect without the typed value changing; drag the window's edge to confirm it resizes
and the right-hand content pane widens while the left sidebar stays a fixed width, and
that it refuses to shrink below its current default size.
