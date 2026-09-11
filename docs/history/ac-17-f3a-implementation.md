# Implementation: Settings destination + Appearance control (story #17, Feature 3a)

## Summary
Split `AfkAutoclicker.__init__` into one-time root setup plus a rebuildable
`self._build_ui()`, added `self._rebuild_ui()` so picking a theme (or opening/
closing Settings) repaints/reshapes the window in place with no restart, added
a Settings sidebar entry + page holding an Appearance `Segmented` (System /
Light / Dark), and persisted the choice as `settings.json["appearance"]`.
Fixed the `_drain_ui` permanent-death bug the spec called out (a stale
`self.status.set` bound method raising `TclError` used to kill the drain loop
forever) by (a) routing every status-pill update through a fresh-lookup
`self._set_status` method instead of a captured bound method, and (b) making
`_drain_ui` tell "the window is closing" apart from "one stale closure" and
keep draining either way. Moving Updates into Settings is explicitly out of
scope (3b).

## Changes by file
- `afk_clicker.py`
  - `Store.__init__`: added `"appearance": "system"` to the default-keys
    dict and a sanitiser (`not in ("system", "light", "dark") -> "system"`)
    placed right after the existing `"games"` shape filter.
  - `resolve_appearance(value, cached_os_theme=None)`: new pure helper next
    to `set_active_theme()` — `"system"` resolves to `cached_os_theme` if
    given, else calls `detect_os_theme()`; anything else passes through.
  - `SettingsItem(tk.Canvas)`: new widget, structurally a `GameItem` minus
    the running-state dot (nothing to run) and with no profile behind it —
    `on_click()` takes no id.
  - `AfkAutoclicker.__init__`: now takes an optional `os_theme=None` param
    (stored as `self._os_theme`). Keeps only true one-time root setup —
    `root.title/resizable/minsize/geometry/protocol`, the single
    `root.bind_all("<Button-1>", ...)` (now carries the one-line "bound
    once, here" comment Gitea #18 asked for) — and every non-Tk state
    assignment (`self.running`, `self.worker`, `self.hk_listener`,
    `self.registered_hotkey`, `self.profiles`, `self.store`, the new
    `self._settings_open = False`). Calls `self._build_ui(s)` once, then
    (unchanged relative order of "runs once") restores a saved hotkey.
  - `AfkAutoclicker._build_ui(s)`: new — the widget-construction body
    (header, sidebar incl. the new Settings entry, content pane) plus the
    tail that restores the previous view (`_build_settings` or `_select`),
    resyncs the status pill and a pending update offer, resets `_timers`,
    and restarts the three `after()` chains. Called from `__init__` and
    from `_rebuild_ui()`.
  - `AfkAutoclicker._rebuild_ui()`: new — `_persist()`, cancel every job in
    `_timers`, replace `_ui_queue`, destroy every child of `root`, call
    `_build_ui(self.s)` again.
  - `AfkAutoclicker._build_settings(s)`: new — the Settings page (title,
    "Appearance" section, one card with a "Theme" `Row` + 3-way `Segmented`
    + a static OS-theme hint line), structurally parallel to
    `_build_content(s)`.
  - `AfkAutoclicker._apply_appearance(value)`: new — saves to the store,
    resolves + applies the palette, memoizes `self._os_theme` on a first
    "System" pick, then defers the rebuild via `root.after_idle` (see
    "Key decisions" — not a literal-spec deviation of outcome, only of
    scheduling).
  - `AfkAutoclicker._show_settings()`: new — opens the Settings page (no-op
    if already open).
  - `AfkAutoclicker._select()`: gained one new first step — if Settings is
    open, close it and rebuild before doing anything else it already did.
  - `AfkAutoclicker._drain_ui()`: a `TclError` now checks
    `self.root.winfo_exists()` — only a real "window is closing" stops the
    loop; anything else (a stale, rebuilt-away closure) is dropped and
    draining continues.
  - `AfkAutoclicker._set_status(text, color, hint="")`: new — resolves
    `self.status` fresh at call time, matching `_offer_update`/
    `_set_update_state`/`_mark_running`'s existing pattern. All six
    `self._ui(self.status.set, ...)` call sites in `start()`/`stop()`/
    `loop()` now read `self._ui(self._set_status, ...)`.
  - `__main__`: constructs `Store()` before `set_active_theme`, reads the
    saved `appearance`, calls `detect_os_theme()` only when it's `"system"`,
    passes `store=` and `os_theme=` into `AfkAutoclicker`.
- `tests/test_ui.py` — 22 new tests (184 → 206; see "How to verify locally").

**Round 2** (see the "Round 2" section below for the full rationale):
- `afk_clicker.py`
  - `AfkAutoclicker.__init__`: new `self._rebuild_after_id = None`.
  - `AfkAutoclicker._apply_appearance()`: coalesces — only schedules
    `root.after_idle(self._rebuild_ui)` if none is already pending.
  - `AfkAutoclicker._rebuild_ui()`: cancels/clears `self._rebuild_after_id`
    at the top of the call, absorbing any pending idle rebuild.
  - `card()`'s `_redraw()`: bails out via `shell.winfo_exists()` both at
    entry and right after `inner.update_idletasks()`.
  - `_build_ui()`: sidebar gained a 1px `LINE` divider between "Add current
    game" and the Settings entry.
- `tests/test_ui.py` — 5 new tests: `OverlappingAppearanceChanges` (4),
  `QueuedStatusSurvivesARebuild` (1); plus a new `CapturesCallbackExceptions`
  mixin wired into `UITestCase`, `AppearanceThemeSwitch`, and
  `StartupHonoursSavedAppearance` (206 → 211; see "How to verify locally").
- `docs/design.md` — sidebar wireframe + "Sizes and positioning" section
  updated for the new divider.

**Round 3** (see the "Round 3" section below for the full rationale —
addresses `docs/test-review.md`'s Round 2 review Findings #1/#2/#3):
- `afk_clicker.py`
  - `AfkAutoclicker.__init__`: new `self._rebuilding = False`,
    `self._rebuild_wanted = False`.
  - `AfkAutoclicker._rebuild_ui()`: body now wrapped in `try/finally`
    around `self._rebuilding = True`/`False`; the `finally` schedules
    exactly one follow-up rebuild if `self._rebuild_wanted` was set during
    the call.
  - `AfkAutoclicker._apply_appearance()`: while `self._rebuilding` is
    True, only sets `self._rebuild_wanted = True` instead of scheduling a
    fresh `after_idle` job.
- `tests/test_ui.py` — 2 new tests: `ReentrantAppearanceChangeDuringRebuild`
  (1, Finding #1) and `CardShell::test_redraw_bails_out_once_its_shell_is_
  destroyed` (1, Finding #2); `CardShell` also gained
  `CapturesCallbackExceptions` (211 → 213; see "How to verify locally").
- `README.md` — `### Aussehen` section (Finding #3) updated to describe the
  in-app Settings → Appearance control.
- `/tmp/.../scratchpad/probe5_reentrant_card.py` (reviewer's own probe, not
  part of this diff) — fixed a latent bug in its own success-path print
  statement (`ui.appearance_var` referenced without ever opening Settings,
  never previously reached because the probe always crashed first) so it
  can actually report PASS/FAIL once the crash itself is fixed.

## Key decisions / tradeoffs
- **`root.config(bg=BG)` moved into `_build_ui()`, not left one-time in
  `__init__` as the spec's §2 bullet literally lists it.** `root` itself is
  never destroyed by a rebuild, so its background is the one piece of
  "root configuration" that *is* theme-dependent and therefore must be
  reapplied every rebuild — confirmed by TDD: the acceptance criterion
  itself samples `ui.root.cget("bg")` against the new palette after a
  switch, which fails if `root.config(bg=BG)` only runs once.
  `title`/`resizable`/`minsize`/`geometry`/`protocol`/`bind_all` are
  genuinely theme-independent and stayed exactly where the spec put them.
  See "Deviations from spec".
- **`_apply_appearance()`'s rebuild is deferred one tick via
  `root.after_idle(self._rebuild_ui)`, not called inline as the spec's code
  sample shows.** Found via TDD: `appearance_var` carries two "write"
  traces — `Segmented`'s own built-in repaint (registered when the control
  is built) and the new `_apply_appearance` trace (registered after).
  Tcl invokes a variable's traces most-recently-added-first, so clicking a
  segment fires `_apply_appearance` *before* `Segmented`'s own repaint
  trace. Calling `_rebuild_ui()` inline there destroys the very canvas
  whose repaint trace is still queued to run next, which then raises
  `TclError` trying to redraw a widget that no longer exists (an uncaught
  exception inside a Tk trace callback — Tkinter prints it and swallows it,
  so nothing failed loudly, but it's a real defect). `after_idle` lets every
  trace on the current click finish against the still-live old tree first;
  the actual rebuild runs a moment later, once the event has fully
  unwound. `_show_settings()`/`_select()`'s own rebuild calls are *not*
  deferred — they're driven by a plain single `<Button-1>` binding
  (`SettingsItem`/`GameItem`), not a second trace on the same variable, so
  there's no competing callback to race.
- **`_select()`'s Settings-closing branch reuses the one general
  `_rebuild_ui()` rather than a narrower "rebuild just `self.content`"
  primitive.** The spec never defines a second, lighter rebuild mechanism,
  and reusing the one already built for Appearance keeps the surface area
  to one rebuild path total (skill: minimal new surface). The cost is a
  full header+sidebar+content rebuild on every "leave Settings by clicking
  a game" click, not just a content-pane swap — acceptable, this is a rare
  navigation action, not something in a hot loop, and ordinary game-to-game
  switching (`_select` when Settings was never open) is untouched, still
  the cheap in-place refill it always was.
- **`_build_ui`'s content step is one `if self._settings_open: _build_settings(s) else: _build_content(s); self._select(self.current, persist=False)`**,
  not two separate call sites as a very literal reading of the spec's two
  code blocks (§2's "moves into `_build_ui`" bullet and its "tail" bullet)
  might suggest. `_select()` fills values into widgets `_build_content()`
  already built (`self.click_ms.var.set(...)` etc.), so it cannot run
  without `_build_content()` having run first; the spec's own tail snippet
  omitting that call is read here as shorthand, not as two separate
  `_build_settings()` invocations.
- **Sidebar item width/placement**: `SettingsItem` reuses `GameItem`'s
  default width (`SIDEBAR_W - 16`) and sits between "Add current game" and
  "Check for updates", exactly where `docs/design.md`'s wireframe puts it.
- **Appearance `Segmented` width is 180, not `CARD_INNER_W`** as
  `docs/design.md`'s sizing table states. `CARD_INNER_W` is the *card's*
  full inner width; placed inside a `Row`'s right-hand control area (next
  to the "Theme" label, the only layout this file's `Row`/card pattern
  supports for a labelled control), a `CARD_INNER_W`-wide `Segmented` would
  overrun the label. Used the same width as this file's only other 3-option
  `Segmented`-in-a-`Row` ("Mouse button" in the Clicking card) instead —
  convention match over the design doc's literal number, which doesn't fit
  the container it's specified into. See "Deviations from spec".
- Hint text (`"System is currently {theme}"`) is computed once by
  `_build_settings()`, lazily filling `self._os_theme` via `detect_os_theme()`
  if nothing has needed it yet (e.g. the saved appearance was `"light"`/
  `"dark"` at startup, so `__main__` never detected the real OS theme) —
  still at most once per process, just deferred to the first actual need
  (startup's "System" resolution, or the first Settings page view,
  whichever comes first) rather than always eagerly at startup.

## Deviations from spec
- `root.config(bg=BG)` was moved from `__init__` into `_build_ui()` (see
  "Key decisions" above) — the spec's §2 bullet lists `root.config` among
  the calls that "stay in `__init__`, run exactly once, never re-run by a
  rebuild," which is correct for `title`/`resizable`/`minsize`/`geometry`/
  `protocol` but not for the `bg=BG` part specifically, since `BG` is a
  theme-dependent global and `root` is the one widget in the tree a rebuild
  never reconstructs. Verified against the spec's own acceptance criterion,
  which samples `ui.root.cget("bg")` post-switch.
- `_apply_appearance()`'s call to `_rebuild_ui()` is deferred via
  `root.after_idle(...)` instead of called inline, for the trace-ordering
  reason above. The externally-observable outcome (rebuild happens, in
  response to that Appearance change, before the next user-visible event)
  is unchanged; only the exact tick it runs on shifted by one Tk idle pass.
- Appearance `Segmented`'s width is 180 (matching the "Mouse button"
  precedent) rather than `docs/design.md`'s stated `CARD_INNER_W` — the
  latter doesn't fit inside a `Row`'s control area alongside the "Theme"
  label. Visual result: a right-aligned 3-segment control next to its
  label, matching every other labelled `Segmented` in this file.

## Known limitations
- **Fixed in Round 2** (see below): rapid repeated Appearance clicks used to
  queue multiple idle callbacks and raise an uncaught `TclError` — see
  `docs/test-review.md` Defect 1 and the "Round 2" section.
- `ui._timers` is (unchanged from before this feature) an ever-growing log,
  not a "currently pending" list — each of the three self-rescheduling
  `after()` jobs appends a fresh id every time it fires, and old,
  already-fired ids are never trimmed except by `_rebuild_ui()`'s full
  reset or `on_close()`'s cancel loop. "Exactly 3" only holds in the instant
  right after a rebuild, before any of the three has fired again — the new
  tests account for this; a future reader relying on `len(ui._timers)` at
  an arbitrary moment should not expect it to mean "currently pending."

## How to verify locally
```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
Result: **213 tests, OK, skipped=5** (baseline before this feature: 184;
Round 1 added 22 (→206); Round 2 added 5 more — `OverlappingAppearanceChanges`
(4) and `QueuedStatusSurvivesARebuild` (1) (→211); Round 3 added 2 more —
`ReentrantAppearanceChangeDuringRebuild` (1) and `CardShell::test_redraw_
bails_out_once_its_shell_is_destroyed` (1) (→213) — all passing, no
existing test's assertions changed; stable across repeated runs).

Reran the reviewer's probe scripts (`probe1_running_rapid.py`,
`probe2_queued_callbacks.py`, `probe3_misc.py`, `probe4_break_coalescing.py`,
`probe5_reentrant_card.py`, all in the scratchpad) after Round 3 — clean
output from all five, no `TclError`/uncaught-exception line from any of
them (see "Round 3" below for `probe4`/`probe5` specifically, and for the
one probe5 script-only bug fixed along the way). `probe4`'s own output
includes some `Exception ignored in: <function Variable.__del__ ...>
RuntimeError: main thread is not in main loop` noise between its three
sub-probes — this is CPython finalizing `tkinter.Variable` objects from an
earlier sub-probe's already-destroyed `Tk()` instance during garbage
collection, a well-known benign Tkinter/interpreter-shutdown-ordering
artifact that never goes through `report_callback_exception` and isn't
part of any PASS/FAIL check; `probe4`'s own exit code is 0
(`PROBE4 ALL PASS`).

Screenshots (`Store(<scratchpad tempdir>)`, `import -window <id> -crop
<w>x<h>+0+0`; nothing written to `~/.config` or the worktree — script run
from the scratchpad, not committed):
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f3-settings-dark.png`
  — Settings page open, Deepslate, "System" selected, hint reads "System is
  currently dark".
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f3-settings-light.png`
  — after picking "Light": Quartz, page still open, "Light" now selected.
- `/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/f3-game-light.png`
  — Minecraft selected (Settings closed), Quartz.

## `self.<widget>` attributes rebuilt by `_build_ui()`
Always (header/sidebar, every `_build_ui()` call): `self.status`,
`self.side`, `self.count_label`, `self.list_frame`, `self.items` (dict,
repopulated by `_rebuild_list()`), `self.settings_item`, `self.update_button`,
`self.version_label`, `self.content`.

Per-game form only (`self._settings_open is False`, via `_build_content`):
`self.game_title`, `self.game_state`, `self.game_note`, `self.hotkey_label`,
`self.apply_button`, `self.click_ms`, `self.jitter_ms`, `self.autostop_min`,
`self.button_name`, `self.eat_section`, `self.eat_card_inner`,
`self.eat_card`, `self.eat_mode`, `self.eat_every`, `self.eat_hold`.

Settings page only (`self._settings_open is True`, via `_build_settings`):
`self.appearance_var` (plus lazily filling `self._os_theme`, plain state,
not a widget, if it was still `None`).

Never rebuilt (assigned once in `__init__`, survive every rebuild):
`self.root`, `self.s`, `self.store`, `self.mouse`, `self.hotkey`,
`self.registered_hotkey`, `self.hk_listener`, `self.running`, `self.worker`,
`self.capture_thread`, `self.right_held`, `self.settings`, `self._pending`,
`self._loading`, `self._settings_open`, `self.profiles`, `self.by_id`,
`self.current`, `self._os_theme` (only ever mutated in place, never
reassigned by a rebuild).

## `after()` chains and how they restart
- `_drain_ui` (40 ms) — cancelled in `_rebuild_ui()` via
  `root.after_cancel` over every id in `self._timers`, `self._timers`
  reset to `[]`, restarted once by `_build_ui()`'s tail calling
  `self._drain_ui()` (which reschedules itself).
- `_sync_settings` (200 ms) — same cancel/reset, restarted by
  `_build_ui()`'s tail calling `self._sync_settings()`.
- `_poll_games` (5000 ms, plus a fresh background scan thread each fire) —
  same cancel/reset, restarted by `_build_ui()`'s tail calling
  `self._poll_games()`.
- New, one-shot, not part of the `_timers` chain: `root.after_idle(self._rebuild_ui)`
  inside `_apply_appearance()`. **Round 2:** now tracked in
  `self._rebuild_after_id` and coalesced — at most one is ever pending, and
  whichever call actually runs `_rebuild_ui()` (the idle callback itself, or
  an inline call from `_show_settings()`/`_select()`) cancels/absorbs the
  other via `root.after_cancel` at the top of `_rebuild_ui()`. Also
  cancelled by `on_close()` if still pending when the window closes, same
  `after_cancel`/`except tk.TclError` pattern as the `self._timers` loop
  right above it in `on_close()`. See "Round 2" below.

## Round 2 (test-review.md Defect 1 + UX fix)

`docs/test-review.md` blocked the first round on Defect 1 (an uncaught
`TclError` from overlapping Appearance rebuilds) and a Round-8 coverage gap
on the `_set_status` indirection, plus a non-blocking UX concern on the
sidebar. All three addressed here; also see the confirmed call chain below.

### Defect 1: overlapping rebuilds

**Confirmed root cause (not just the reviewer's read of the traceback).**
Reproduced with a minimal two-`after_idle`-job script and confirmed via
`print()` instrumentation: `root.update()` drains queued idle jobs in FIFO
order, but if a job **calls `update_idletasks()` while it is still
running** (exactly what `card()`'s `_redraw()` does via
`inner.update_idletasks()`, `afk_clicker.py` `card()`), that
`update_idletasks()` call **reentrantly runs any other already-queued idle
job** before returning control to the interrupted one. Concretely: two
Appearance picks before the first idle rebuild fires queue **two**
`after_idle(self._rebuild_ui)` jobs. `root.update()` starts the first
`_rebuild_ui()`; partway through building the tree, a `card()` call's
`_redraw()` calls `inner.update_idletasks()`, which reentrantly runs the
**second** still-pending `_rebuild_ui()` — destroying every widget the
first (still-running, outer) rebuild had already built, including the
`shell` canvas the outer `card()`/`_redraw()` call is still holding a
reference to. Control returns to the interrupted `_redraw()`, which then
calls `shell.winfo_width()` on that now-destroyed canvas → `TclError: bad
window path name`, uncaught, printed by Tk's default
`report_callback_exception` and swallowed. Confirmed via
`probe1_running_rapid.py` before any fix: 4 such tracebacks, one per
`_apply_appearance()` call beyond the first in a 5-call burst.

**Fix, two layers, both requested:**
- **(a) Coalesce** (`afk_clicker.py` `__init__`, `_apply_appearance()`,
  `_rebuild_ui()`): a new `self._rebuild_after_id` holds the one pending
  `after_idle(self._rebuild_ui)` job, if any. `_apply_appearance()` only
  schedules a new one if `self._rebuild_after_id is None` — the theme
  itself is still applied synchronously on every call
  (`set_active_theme(resolved)`), so whichever choice was latest when the
  one pending rebuild finally runs is exactly what it rebuilds against;
  nothing further needs to be remembered. `_rebuild_ui()` cancels/clears
  `self._rebuild_after_id` at its own top, before doing anything else. This
  handles both directions: the idle callback firing normally cancels
  itself (a harmless no-op `after_cancel` on an already-fired id, guarded
  by `except tk.TclError`), and an **inline** call from
  `_show_settings()`/`_select()` while an idle rebuild is still pending
  cancels that pending job and does the (single) rebuild right now instead
  — the "absorb" option from the two offered in the dispatch, chosen over a
  second explicit guard in `_show_settings()`/`_select()` because it keeps
  the invariant ("at most one `_rebuild_ui()` call ever in flight or
  pending") enforced in exactly one place regardless of which caller
  triggers it, rather than duplicating the guard at every call site.
- **(b) Robust `<Configure>` handler** (`card()`'s `_redraw()`,
  `afk_clicker.py`): added `if not shell.winfo_exists(): return` both at
  entry (a torn-down card fielding a stale/late `<Configure>`) and again
  right after `inner.update_idletasks()` (in case *that specific* call
  reentrantly runs another idle job that tears the card down — defense in
  depth on top of (a), which should already prevent this from happening at
  all once only one rebuild is ever pending).

**Tests added** (`tests/test_ui.py`, class `OverlappingAppearanceChanges`,
all inheriting `UITestCase`'s stderr-safety-net — see below): two rapid
`_apply_appearance()` calls before draining; five rapid calls, asserting
they coalesce into **exactly one** `_rebuild_ui()` call (via a counting
wrapper); two real `<Button-1>` events on the actual Appearance `Segmented`
via `event_generate`, back to back with no `root.update()` in between
(mirrors the dispatch's own physically-plausible-fast-double-click repro);
and `on_close()` racing a still-pending idle rebuild.

**Tracebacks now caught, not just eyeballed.** Added
`CapturesCallbackExceptions`, a small mixin (`tests/test_ui.py`) that
installs `root.report_callback_exception = <recorder>` and fails the test
if anything landed there. Chosen over a raw `contextlib.redirect_stderr`
because it only ever catches genuine Tk callback exceptions dispatched
through Tk's own error-reporting hook — the exact mechanism that swallowed
Defect 1 in the first place — rather than any unrelated text a test
happens to print to stderr. Wired into `UITestCase.setUp`/`tearDown` (so
every UITestCase-derived test gets it, not just the new ones — a small
superset of "the existing rebuild test classes" the dispatch named, cheap
and centralizing the fix in one base class rather than six), plus
`AppearanceThemeSwitch` and `StartupHonoursSavedAppearance` directly, since
neither subclasses `UITestCase` (each builds its own `root`/`ui` in
`setUp`/per-test rather than reusing the shared harness).

### Round-8 coverage gap: `_set_status`'s fresh-lookup indirection was untested

Added `QueuedStatusSurvivesARebuild` (`tests/test_ui.py`). Every existing
rebuild test only ever lands a plain RUNNING/OFF status update — exactly
what `_rebuild_ui()`'s own boolean resync (`if self.running: ... else:
...`) already writes, so a revert of the indirection at all 6
`start()`/`stop()`/`loop()` call sites was invisible: the resync happened
to already agree. `EATING` is never written by the resync, so it's the one
state that can prove the *queued* update — not the resync — is what
produced the final pill text.

The test drives `loop()`'s real EATING branch (not a hand-built queue
tuple, unlike `DrainUiSurvivesAStaleClosure`) and times it, via a
`StatusPill.__init__` monkeypatch, to fire from **inside**
`_rebuild_ui()` — after `self._ui_queue` has already been swapped to a
fresh queue but before `self.status` is reassigned to the new pill. That
is the exact narrow window `_set_status`'s own docstring names as the real
hazard (`_rebuild_ui()`'s queue swap is documented, intentional, and drops
anything queued *before* that swap — so the only way for an update to
survive to be drained *and* still be able to target a stale pill is to
land in this specific window). A worker thread is started for real from
inside that monkeypatch, polled (plain `right_held` attribute checks, no
`root.update()`) until it has enqueued the `EATING` update and is
blocked in its own interruptible `_sleep()`, then released. `eat_every` is
kept at its enforced UI minimum (5s) and a fake, monotonically-advancing
`time.monotonic()` (patched only for `afk_clicker`'s own module reference,
restored after) is used so the test doesn't block for 5 real seconds.

Confirmed failing on revert: reverted all 6
`self._ui(self._set_status, ...)` call sites to
`self._ui(self.status.set, ...)` directly in `afk_clicker.py`
(`sed`-scripted, diff-verified byte-identical restore afterward), ran just
this test — `AssertionError: 'OFF' != 'EATING'` (the stale bound method
targets the destroyed old pill, raises `TclError`, gets dropped by
`_drain_ui`'s existing guard, and the pill is left at whatever the resync
wrote). Restored, reran the full suite — green again.

### UX: sidebar divider

Added a 1px `LINE`-colored horizontal divider (`afk_clicker.py`
`_build_ui()`, sidebar section), `padx=14*s` (matching the "GAMES" label's
own inset), `pady=(4*s, 8*s)`. Addresses the reviewer's non-blocking
CONCERN: the three sidebar rows used to read as one stack of similar pill
buttons; the divider separates the two actions from "Settings" (a
persistent-selection navigation destination). `docs/design.md`'s sidebar
wireframe and "Sizes and positioning" section updated to match.
Screenshots retaken (`f3-settings-dark.png`, `f3-settings-light.png`,
`f3-game-light.png`, same scratchpad script as before).

**Correction (same Round 2, before handoff):** the first pass packed the
divider between "Add current game" and "Settings", leaving "Check for
updates" below Settings — Settings still sat between the two action
buttons, the exact problem the divider was meant to fix. Fixed the pack
order in `_build_ui()` so both action buttons are packed together first
("Add current game" then "Check for updates"), *then* the divider, *then*
the Settings entry, *then* the version label — matching
`docs/design.md`'s wireframe order top to bottom. `docs/design.md`'s
wireframe and "Sizes and positioning" section updated again to state this
order explicitly. Screenshots retaken a second time to confirm.

### `on_close()` now cancels a still-pending idle rebuild job

**Correction (same Round 2, before handoff).** Originally left as "out of
scope, pre-existing" (see below for the original reasoning) since the
reviewer had classified it as unreachable through a real `mainloop()`.
Per follow-up: it is one line to make it impossible outright regardless,
so `on_close()` (`afk_clicker.py`) now cancels `self._rebuild_after_id`
via `root.after_cancel` (guarded by `except tk.TclError`, same pattern as
the existing `self._timers` cancellation loop right above it) if one is
still pending, right after that loop.

Reran `probe3_misc.py`'s `close_races_idle_rebuild()` afterward: the raw
Tcl-level `invalid command name "..._rebuild_ui"` line is gone, output is
clean (`PROBE3a/3b/3c PASS`, no extra lines).

Extended `test_on_close_between_an_appearance_change_and_its_idle_rebuild`
(`OverlappingAppearanceChanges`) to assert this directly: captures
`self.ui._rebuild_after_id` right after `_apply_appearance()`, hooks
`self.ui._release_right` (the real `on_close()`'s last call before
`root.destroy()` — the last point `root.tk.call("after", "info")` can
still be queried at all) to record the live "after info" set at that
exact moment, then asserts the captured job id is not in it. This proves
the cancellation happens strictly before `destroy()`, not just
"eventually" or "by luck of ordering."

Original reasoning, for context (superseded by the above, not deleted
since the "why it was previously believed unreachable" analysis is still
correct and useful): this was the **same** failure mode
`docs/test-review.md`'s "Investigated, not a defect" section already
found and reproduced against the pre-Round-2 code, unrelated to Round 2's
Defect-1 changes (`on_close()` had never cancelled this one-shot idle job,
only `self._timers`' three self-rescheduling jobs). It bypasses both
`redirect_stderr` and `report_callback_exception` (a raw Tcl interpreter
error — the Python command backing the idle job has already been
deregistered by `root.destroy()`, so there's no Python exception object
for either mechanism to see), and per the reviewer's own finding was not
reachable through a real `mainloop()` (which exits before servicing a
stale idle callback) — only through a test's own manual extra
`root.update()` call after `destroy()`. That analysis of *why* it was
unreachable in practice still holds; cancelling the job explicitly simply
removes the possibility outright rather than relying on that ordering
argument.

## Round 3 (test-review.md Round 2 review — Findings #1, #2, #3)

The Round 2 review approved 3a ("Approve with follow-ups") with three
should-fix findings, none blocking. All three addressed here, still no
commit.

### Finding #1: the coalescing invariant was false under reentrancy

**Confirmed exact repro** via the reviewer's `probe5_reentrant_card.py`
before any Round 3 change: patches the module-level `card()` so that,
right after the *first* of `_build_content()`'s three `card()` calls
returns, it synchronously calls `ui._apply_appearance("dark")` — simulating
a synchronous internal caller re-entering `_apply_appearance()` while
`_rebuild_ui()` is still on the stack, mid-`_build_content()`. Result
before the fix: `_tkinter.TclError: bad window path name` at
`Row(cl, "Interval", s)` — `afk_clicker.py:1726` in `_build_content()` —
exactly the crash site `docs/test-review.md`'s Finding #1 named.

**Root cause, as the reviewer's finding already pinned down:**
`_rebuild_ui()` clears `self._rebuild_after_id` to `None` at its own top,
*before* its body runs. Round 2's coalescing guard in `_apply_appearance()`
(`if self._rebuild_after_id is None: schedule`) only ever prevented a
*second pending* rebuild from being scheduled while the *first* was
merely waiting to run — it said nothing about a rebuild *already running*.
A call to `_apply_appearance()` from inside that running rebuild's own
call stack sees `_rebuild_after_id is None` (cleared at the top, same as
any other time) and schedules a **fresh** `after_idle(self._rebuild_ui)`
job. A later `card()` call in the *same*, still-running outer rebuild then
calls `inner.update_idletasks()`, which — as confirmed experimentally in
Round 2 already (a two-`after_idle`-job script where a job calling
`update_idletasks()` mid-execution reentrantly runs another
already-queued idle job before returning) — reentrantly services that
fresh job, running a second `_rebuild_ui()` that tears down every widget
the first, still-in-progress rebuild is holding local references to.

**Fix (`afk_clicker.py`):**
- `AfkAutoclicker.__init__`: two new flags, `self._rebuilding = False`
  (true for the duration of `_rebuild_ui()`'s own body) and
  `self._rebuild_wanted = False` (a rebuild was requested while
  `_rebuilding` was true, and hasn't been scheduled yet).
- `_rebuild_ui()`: the body (everything after the existing
  `_rebuild_after_id` cancel-at-top logic) is now wrapped in
  `self._rebuilding = True` / `try` / `finally: self._rebuilding = False`.
  The `finally` block also checks `self._rebuild_wanted`: if set, clears
  it and schedules exactly one follow-up
  `self._rebuild_after_id = self.root.after_idle(self._rebuild_ui)`.
- `_apply_appearance()`: the scheduling guard is now
  `if self._rebuilding: self._rebuild_wanted = True elif
  self._rebuild_after_id is None: schedule`. While a rebuild is running,
  a reentrant call only records that a follow-up is wanted — it never
  touches `after_idle`/`_rebuild_after_id` at all, so there is nothing for
  a later `card()` call in the same still-running rebuild to reentrantly
  service. The theme itself is still applied synchronously above this
  guard on every call (`set_active_theme(resolved)`), so "records the
  latest choice" needed nothing extra — only the *scheduling* decision
  needed gating.

This makes the docstring's invariant ("at most one rebuild is ever in
flight or pending") actually true: previously it only held for "pending";
now it holds for "in flight" too.

**Test added:** `ReentrantAppearanceChangeDuringRebuild` (`tests/test_ui.py`)
patches the module-level `card()` the same way `probe5_reentrant_card.py`
does (`_build_content()`'s three sequential `card()` calls give a
second/third call, inside the same still-running rebuild, something to
reentrantly service) — right after the first `card()` call returns, it
calls `self.ui._apply_appearance("dark")`. A counting wrapper around
`_rebuild_ui()` asserts **exactly 2** total rebuild calls happen (the one
"light" itself queued, plus exactly one follow-up), the final theme
matches the last choice (`"dark"`), and `CapturesCallbackExceptions`
stayed empty.

**Confirmed red on revert:** reverted `_apply_appearance()`'s guard back to
its Round 2 form (`if self._rebuild_after_id is None: schedule`, dropping
the `self._rebuilding` branch) directly in `afk_clicker.py`. Ran just this
test: fails with the same `TclError: bad window path name` at
`Row(cl, "Interval", s)` `probe5` demonstrated, caught by
`CapturesCallbackExceptions` and reported via `tearDown`'s
`_assert_no_callback_exceptions()`. Restored (`diff`-verified
byte-identical), reran — green again.

**`probe5_reentrant_card.py` printed clean after the fix** — with one
side note: fixed a latent, previously-unreached bug in the probe script's
own final `print(...)` line, which referenced `ui.appearance_var.get()`
unconditionally even though the probe never opens Settings (it injects
into `_build_content()`, not `_build_settings()`) — before the fix this
line was never reached (the crash always happened first), so the bug was
invisible until the crash itself was fixed. Guarded it the same way
`probe4_break_coalescing.py`'s own `probe_a()` already does
(`getattr(ui, "appearance_var", None) and ui.appearance_var.get()`).
`probe4_break_coalescing.py` (all three of its own sub-probes: a
mid-rebuild `_apply_appearance()` injection, `_show_settings()`/`_select()`
absorbing a pending idle job then a second change landing, and a
50-step seeded fuzz of interleaved appearance/select/settings/start/stop/
pump actions) also passes clean, unchanged by this fix (it already passed
before Round 3, since none of its shapes hit the reentrancy window the
same way `probe5` does — included here since the dispatch asked for all
five probes' output).

### Finding #2: `card()`'s `winfo_exists()` guards had zero direct test coverage

**Confirmed the gap first,** per `docs/REVIEW-PROTOCOL.md` Round 8's own
question: removed both guard lines from `card()`'s `_redraw()` in memory,
ran the full 213-test suite — still green (matches the reviewer's own
finding). Restored, `diff`-verified byte-identical.

**Test added:** `CardShell::test_redraw_bails_out_once_its_shell_is_
destroyed` (`tests/test_ui.py`). Since `card()`'s `_redraw` closure isn't
exposed by `card()`'s own return value (only `inner` is), the test
temporarily monkeypatches `tk.Canvas.bind` (not `card()` itself — no
production code changed for testability) while calling `app.card(...)`,
capturing the exact `_redraw` function `card()` binds to `<Configure>`.
It then destroys the card's `shell` (`inner.master`), and dispatches the
captured `_redraw` through Tk's own callback machinery
(`self.root.after_idle(redraw)`, not a bare Python call — a bare call
would just raise straight into the test rather than exercising
`report_callback_exception`, the actual mechanism a real late/stale
`<Configure>` callback would go through) once `shell` no longer exists.
Asserts `CapturesCallbackExceptions` stays empty. `CardShell` (previously
a plain `unittest.TestCase`) now mixes in `CapturesCallbackExceptions` too,
same pattern as Round 2's other non-`UITestCase` classes.

**Confirmed red on revert:** removed both `if not shell.winfo_exists():
return` guard blocks from `card()`'s `_redraw()` directly in
`afk_clicker.py`. Ran just this test: fails with
`_tkinter.TclError: bad window path name` from `shell.winfo_width()`,
caught by `CapturesCallbackExceptions`. Restored (`diff`-verified
byte-identical against the Round 3 baseline), reran — green again.

### Finding #3: README's "Aussehen" section was stale

`README.md`'s `### Aussehen` section (German, pre-existing, not part of
this feature's original diff — `docs/spec.md` scoped 3a to `afk_clicker.py`
only, so this was a genuine gap nobody's spec routed to) described only
the pre-3a behavior: OS theme read once at startup, no in-app override.
Rewrote the paragraph to also describe the new in-app control, keeping
the same casual German register and the same convention the rest of the
README already uses for literal UI text (bold, untranslated — e.g.
**Add current game**, **Record**, **Apply**): the app's actual UI labels
are English throughout (checked directly in `afk_clicker.py`: the sidebar
entry and page title are literally `"Settings"`, the section label is
`"Appearance"`, the row label is `"Theme"`, the `Segmented` options are
`"System"`/`"Light"`/`"Dark"`) — not the placeholder "Einstellungen →
Darstellung" the dispatch's own wording guessed at. New paragraph: the
window follows the system's light/dark mode by default (Windows, macOS,
GNOME), read once at startup; under **Settings → Appearance** it can be
fixed to **Light** or **Dark**, or set back to **System**, and the change
applies immediately, no restart; other Linux desktops, or an unreadable
system setting, still get the dark theme when **System** is selected.

### Verification

Full suite: `DISPLAY=:99 .../python -m unittest discover -s tests -t .` →
**213 tests, OK, skipped=5** (211 → 213, the two new tests above).

All five probes reran clean post-fix:
- `probe1_running_rapid.py`: `PROBE1 PASS`
- `probe2_queued_callbacks.py`: both parts `PASS`, stderr empty
- `probe3_misc.py`: `PROBE3a/3b/3c PASS`
- `probe4_break_coalescing.py`: `PROBE4a/4b/4c PASS`, `PROBE4 ALL PASS`
  (exit code 0); benign GC-finalizer noise between sub-probes, not a
  failure (see "How to verify locally" above)
- `probe5_reentrant_card.py`: `PROBE5 PASS` (after fixing its own
  script-only `appearance_var` bug, see Finding #1 above)
