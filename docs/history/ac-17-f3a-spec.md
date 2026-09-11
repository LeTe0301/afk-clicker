# Spec: Tab navigation + Settings tab (story #17, Feature 3a — rebuild mechanism + Appearance)

## Summary
Introduce the app-level Settings destination (reached from a new sidebar
entry) holding an Appearance control (System/Light/Dark), build the
`_build_ui()`/`_rebuild_ui()` in-place widget-tree rebuild mechanism the
story decided on so picking a theme repaints the window without a restart,
and persist the choice as a new `settings.json["appearance"]` key. Moving
the Updates section (`self.update_button`/`self.version_label`) out of the
sidebar and into Settings is **deliberately deferred to Feature 3b** (a
separate spec, written after this one ships and reviews clean) — see
"Split rationale" below.

## Goals
- A `self._build_ui()` method holding the rebuildable widget-construction
  body (header/sidebar/content), callable both from `__init__` (once) and
  from a new `self._rebuild_ui()` (on every Appearance change), with the
  survives-a-rebuild state enumerated in "Proposed approach" §2 intact.
- A sidebar "Settings" entry (bottom, below "Add current game") that swaps
  `self.content`'s body between the existing per-game form and a new,
  minimal Settings page; picking a game swaps back.
- A Settings page holding one control: Appearance, a `Segmented` (System /
  Light / Dark, reusing the existing `Segmented` widget class) that writes
  `settings.json["appearance"]`, resolves `"system"` against `detect_os_theme()`
  (memoized once per process, never re-detected), calls `set_active_theme()`,
  and triggers `self._rebuild_ui()` — all synchronously, no restart.
- `Store.__init__` gains `"appearance"` as a fourth known top-level key,
  defaulting to `"system"`, with a value-shape sanitiser matching the
  precedent already set for `"games"`.
- `__main__` reads the saved `appearance` (constructing `Store` earlier than
  it does today) instead of always calling `detect_os_theme()` unconditionally.
- The `_drain_ui` robustness fix required to make an in-place rebuild safe
  while the clicker keeps running (see §3).

## Non-goals
- **Moving `self.update_button`/`self.version_label` into Settings, or
  changing anything about the updater's own logic/text.** They stay exactly
  where and how they are today (sidebar bottom, `afk_clicker.py:1426-1431`).
  This is Feature 3b, a separate spec — see "Split rationale."
- UI scale (Feature 4).
- Any per-game tab row (Clicker | Macros) — that's `#13`. This spec *names*
  where it will go (inside `self.content`'s body header, once a game is
  selected — see §1) so 3b/Macros don't collide with what's built here, but
  builds none of it.
- Any change to `THEMES`'s values, Feature 1's shapes, or Feature 2's
  `detect_os_theme()` platform branches.
- A schema version for `settings.json` (story.md Decision 0 — this is one
  more additive, defaulted top-level key, the same shape as `"hotkey"`/
  `"selected"`/the Feature-1-era migration, not a shape change to an
  existing key).
- Live OS-change polling while "System" is active (story.md cross-cutting
  Decision — detection stays once-per-process).

## Split rationale (skill 11 — load-balanced decomposition)
The full Feature 3 as scoped by story.md (rebuild mechanism + Appearance +
moving Updates) spans: a new persistence key + sanitiser, a widget-tree
rebuild mechanism with real thread-safety implications for a *running*
clicker, a new content-pane view-switching mechanism, a new sidebar entry,
*and* relocating an existing feature's widgets with their own in-flight-
background-thread state. That is not one architectural layer so much as one
architectural layer (the rebuild mechanism, §2-3 below) plus a second,
independent, much smaller mechanical relocation (3b) that depends on the
first but adds no new mechanism of its own — moving `update_button`/
`version_label` into the Settings page 3a builds, resyncing their state
after a rebuild the same way §2 already resyncs the status pill, and
deleting them from the sidebar. Splitting keeps 3a's developer dispatch
(and the reviewer's testing pass) focused entirely on the one genuinely
risky new mechanism — the rebuild — without also re-verifying updater
behaviour that isn't changing. **3b's spec should be written by the next
product-manager iteration once this one is reviewed and approved**, not
drafted speculatively here.

## Background / current state

### Navigation today
`AfkAutoclicker.__init__` (`afk_clicker.py:1357-1450`) builds, once, in this
shape:
- `header` (not on `self`): title label + `self.status` (StatusPill).
- `shell` (not on `self`) → `self.side` (the sidebar, width `SIDEBAR_W`):
  `self.count_label` ("GAMES N"), `self.list_frame` holding one `GameItem`
  per `self.profiles` entry (tracked in `self.items`, keyed by game id), then
  "Add current game" (`Button`, unnamed on `self`), `self.update_button`
  ("Check for updates"), `self.version_label` (`v{__version__}`).
- a 1px `LINE` divider, then `self.content` (width `CONTENT_W`) →
  `self._build_content(s)` (`afk_clicker.py:1454-1518`), which builds the
  *per-game* form: `self.game_title`/`self.game_state`/`self.game_note`,
  a "Hotkey" card (shared, not per-game: `self.hotkey_label`,
  `self.apply_button`), a "Clicking" card (`self.click_ms`/`self.jitter_ms`/
  `self.autostop_min`/`self.button_name`), and an "Eating" card
  (`self.eat_section`/`self.eat_card_inner`/`self.eat_card`/`self.eat_mode`/
  `self.eat_every`/`self.eat_hold`) shown only when `profile["eating"]`.

`self.side` is a *games* list — nothing in it today represents a
non-game destination. Switching games (`self._select`, `afk_clicker.py:
1532-1566`) never rebuilds `self.content`'s widget tree; it only refills the
existing widgets' values (`self.click_ms.var.set(...)`, `eat_card.pack()`/
`pack_forget()`) and re-tags `GameItem.set_state(selected=...)`. Settings is
a structurally different form (Appearance, later Updates), not a refill of
the same fields, so reaching it needs a real content-pane swap, not a
`_select`-style refill.

### The palette mechanism (Feature 1/2, unchanged by this spec)
`THEMES`/`_theme()`/`_ACTIVE` (`afk_clicker.py:71-91`) and `set_active_theme()`
(`94-119`): every widget reads `BG`/`CARD`/`ACCENT`/... as bare module
globals *at construction time*; `set_active_theme(name)` reassigns those
globals from `THEMES[name]`. Because Python resolves a bare global at call
time, reassigning before a widget is built is sufficient — this is exactly
why an in-place rebuild (destroy the widgets, call the construction code
again) picks up a new theme with no per-widget retheme method. `detect_os_
theme()` (`965-995`) never raises, resolving to `"dark"` on any failure.
`__main__` (`1980-1989`) today: `set_active_theme(detect_os_theme())`, then
builds `root`, then `AfkAutoclicker(root)`.

### `Store` (`afk_clicker.py:789-847`)
`self.data` starts as `{"games": {}, "hotkey": None, "selected": None}`;
`__init__` loads the file, then does `self.data.update({k: v for k, v in
loaded.items() if k in self.data})` — an unknown on-disk key is dropped, a
known key's on-disk value (of ANY shape/type) is accepted as-is. Two
existing narrow, commented, unconditional `if`s run after that: the
`"games"`-shape filter (drops non-dict entries) and the Minecraft
`click_ms == 510 → 650` migration. `ROADMAP.md`'s "Settings schema version"
item explicitly warns: *whatever versioned migration comes first must run
before that shape filter, or it discards old-format data as if corrupt* —
this spec adds no migration (nothing changes shape), only one more
defaulted key, so this ordering concern does not apply here, but the new
sanitiser must still sit in the same place/spirit as the `games` one so a
later migration author has one place to look, not two.

### Threading (`docs/CODING-GUIDELINES.md`)
"Only the main thread may touch Tk." The click loop (`loop()`, `afk_clicker.
py:1898-1957`) reads only `self.settings` (a plain dict snapshotted by
`_sync_settings`, `1756-1777`), `self.running`, `self.mouse`, `self.right_
held`, and hands every UI touch to `self._ui(fn, *args)` — `_ui_queue.put
((fn, args))`, drained on the main thread by `_drain_ui` (`1744-1754`) via
`root.after(40, ...)`. **Confirmed: `loop()` never reads a widget directly**,
so a widget-tree rebuild while `self.running` is `True` does not interrupt
clicking — the worker thread's inputs (`self.settings`, `self.running`) live
outside the widget tree entirely and are untouched by rebuild.

**The one real hazard** (why "confirm that from `loop`" matters): three call
sites inside `start()`/`stop()`/`loop()` (`afk_clicker.py:1873-1874, 1880-
1881, 1909, 1936, 1945-1946, 1955`) all do
`self._ui(self.status.set, "RUNNING", OK, ...)` — this resolves `self.status
.set` to a **bound method of whatever StatusPill object `self.status`
currently is, at the moment `_ui()` is called** (often on the worker
thread), and stores that bound method in the queue. This is different from
every other queued callback in the file (`self._offer_update`, `self._set_
update_state`, `self._mark_running`, `self._quit_for_update` — all bound
methods of `self`, which is never replaced; they look up `self.update_
button`/`self.status`/`self.items` **fresh, inside their own body, when
`_drain_ui` actually calls them** — always current, rebuild-safe by
construction). If a rebuild reassigns `self.status` to a new StatusPill
between one of these three `_ui(self.status.set, ...)` calls being enqueued
and `_drain_ui` actually invoking it, the queued call targets the *old,
now-destroyed* canvas. `StatusPill.set()` calls `self.itemconfig(...)` — on
a destroyed canvas this raises `tk.TclError`. `_drain_ui`'s current handling
of that (`1744-1754`):
```python
def _drain_ui(self):
    while True:
        try:
            fn, args = self._ui_queue.get_nowait()
        except queue.Empty:
            break
        try:
            fn(*args)
        except tk.TclError:
            return                      # window is going away
    self._timers.append(self.root.after(40, self._drain_ui))
```
treats **any** `TclError` as "the window itself is closing" and stops
rescheduling — correct for a real `on_close()`, wrong for a rebuild: one
stale `self.status.set` closure would permanently kill the drain loop (no
further status/update-button/game-list UI update would ever land again for
the rest of the run). This is a real, load-bearing correctness gap that
this spec's rebuild depends on closing — see §3.

## Proposed approach

### 1. Navigation shape — sidebar entry (app-level) vs. future per-game tabs

**Chosen: a "Settings" entry at the bottom of the sidebar**, below "Add
current game" (and, in this 3a-only state, still above the untouched
`update_button`/`version_label` — see "Interim sidebar layout" below).
Clicking it swaps `self.content`'s body to the Settings page; clicking any
`GameItem` while Settings is showing swaps back to the per-game form. The
Settings entry is **not** added to `self.profiles`/`self.by_id`/`self.items`
— it must never appear in `self.count_label`'s "GAMES N" count, never be
touched by `_rebuild_list()`/`_mark_running()`/`_poll_games()` (all of which
only ever iterate real games), and must not be selectable as `self.current`
(which stays a game id at all times, even while Settings is open — reopening
a game after Settings shows the same game you left, unchanged).

A new `self._settings_open` (bool, default `False`) tracks which body is
showing. `self._select(game_id, ...)` gains one new first step: if `self.
_settings_open` is `True`, set it `False` and rebuild `self.content`'s body
back to the per-game form before doing anything else it does today. A new
`self._show_settings()` mirrors that in the other direction: set `self.
_settings_open = True`, rebuild `self.content`'s body to the Settings page,
and visually deselect every `GameItem` (`item.set_state(selected=False)` for
all of `self.items`) the same way `_select` already deselects every item but
the current one. The Settings sidebar entry itself needs an analogous
"selected" visual state when `self._settings_open` is `True` — exact widget
class/visual treatment (a `GameItem`-alike canvas vs. a plain `Button` with
a highlight) is the ux-designer's call, not decided here; the structural
requirement is just: **exactly one of "a GameItem" or "the Settings entry"
reads as selected at any time**, using each widget's own existing
`set_state`-style API rather than a new mechanism.

**Rejected — segmented control in the header.** The header
(`afk_clicker.py:1401-1408`) holds the app title and `self.status`
(`width=250`) in a fixed-width bar that's already tuned to read as "the one
thing you read from across the room" (StatusPill's own docstring). Wedging
a 3-way control in there competes for that space, and — since the header is
global, not per-game — doesn't help the future per-game Macros tabs either;
two different tab mechanisms would still be needed in two different places,
so there's no shared-mechanism payoff to justify cramping the header.

**Rejected — a top-level tab row above `self.content`.** This is exactly
the shape reserved below for the *future per-game* (Clicker | Macros) row
`#13` asks for "beside the clicker settings." Using the same row shape for
the app-level Settings destination would either collide with that future
row (two tab rows stacked, unclear which is which) or force `#13` to
invent a second, different-looking mechanism to avoid the collision. Also,
semantically, Settings is not a peer of "Minecraft"/"Global" the way two
tabs of the *same* game's configuration are — it's a different kind of
destination, which the sidebar (already the single "pick where you're
looking" surface) expresses more honestly than a tab row of mixed peers.

**Where the future per-game tab row goes (named, not built):** inside
`self.content`'s body (`_build_content`'s `body` frame, `afk_clicker.py:
1456-1470`), directly below `self.game_title`/`self.game_state`/`self.
game_note` and above the "Hotkey" section — i.e. a `Clicker | Macros` row
scoped to *whichever game is currently selected*, appearing only in the
per-game form, never in the Settings page. This spec adds no code there;
it only reserves the seam so `#13` extends `_build_content` (or its
Feature-4-scale-aware successor) rather than restructuring the split
this spec introduces.

**Interim sidebar layout (3a only):** after this spec, the sidebar bottom
reads, top to bottom: games list → "Add current game" → **"Settings"
(new)** → "Check for updates" → version label. The last two are untouched
placeholders until 3b removes them and (per the dispatch's own item 4,
explicitly out of scope here) relocates them into the Settings page this
spec builds the shell for. This is a deliberate, temporary state, not an
oversight — flagged so the ux-designer and reviewer don't read it as one.

### 2. The in-place rebuild — `_build_ui()` / `_rebuild_ui()`

Extract the **widget-construction body only** — not the one-time,
root-level setup, and not the one-time state initialization — into
`self._build_ui()`. Concretely, of `AfkAutoclicker.__init__`'s current body
(`afk_clicker.py:1357-1450`):

**Stays in `__init__`, runs exactly once, never re-run by a rebuild:**
- `self.root`, `self.s`, `self.store` assignment.
- `root.title/config/resizable/minsize/geometry/protocol` and
  `root.bind_all("<Button-1>", self._maybe_drop_focus)` — these configure
  `root` itself, which a rebuild never destroys (only its *children* are
  torn down), so none of this needs to (or should) run again. **`bind_all`
  in particular must not move into `_build_ui()`** — see the #18 note below.
- All the plain state assignments: `self.mouse`, `self.hotkey`, `self.
  registered_hotkey`, `self.hk_listener`, `self.running`, `self.worker`,
  `self.capture_thread`, `self.right_held`, `self.settings`, `self._pending`,
  `self._loading`, `self.profiles`, `self.by_id`, `self.current`, and the new
  `self._settings_open = False`, `self._os_theme` (see §4). None of these
  are Tk objects; rebuilding widgets must never reset any of them.
  `self._ui_queue` is the one exception — see below.
- The hotkey-listener restore block (`saved = Hotkey.from_json(...); if
  saved is not None: self.hotkey = saved; self.apply_hotkey()`) — this
  *registers an OS-level global hotkey listener*. Re-running it on every
  rebuild would attempt to re-register while the existing `self.hk_listener`
  is still running, which is exactly the state Feature drift this spec must
  not introduce. Runs once, in `__init__`, after the *first* `_build_ui()`
  call (unchanged from today's ordering).

**Moves into `self._build_ui(s)`, re-run on every rebuild:**
- Everything from `header = tk.Frame(root, bg=CARD, ...)` through
  `self._build_content(s)` (today's `afk_clicker.py:1401-1439`) — header,
  `self.status`, `self.side`/sidebar contents (games list, "Add current
  game", the new Settings entry, and — 3a only — the untouched `update_
  button`/`version_label`), the divider, `self.content`, and either `self.
  _build_content(s)` (per-game form) or a new `self._build_settings(s)`
  (the Settings page), chosen by `self._settings_open`.
- A tail that restores what the *previous* widget tree showed:
  ```python
  if self._settings_open:
      self._build_settings(s)
  else:
      self._select(self.current, persist=False)
  # status pill starts hard-coded "OFF" in its own constructor -- resync it
  # to the real, unchanged self.running/self.registered_hotkey state.
  if self.running:
      self.status.set("RUNNING", OK,
                       self.registered_hotkey.label() if self.registered_hotkey else "")
  else:
      self.status.set("OFF", BAD,
                       self.registered_hotkey.label() if self.registered_hotkey else "")
  self._timers = []
  self._sync_settings()
  self._drain_ui()
  self._poll_games()
  ```
  (This is the same tail `__init__` runs today after its one-time hotkey
  restore, `afk_clicker.py:1446-1450` — moving it into `_build_ui()` means
  `__init__` and `_rebuild_ui()` both get it for free by calling the same
  method, rather than duplicating it.)

**`self._rebuild_ui()`** (new; called by the Appearance handler, §4):
```python
def _rebuild_ui(self):
    self._persist()                    # flush any in-progress field edit
                                        # before its widget is destroyed
    for job in self._timers:
        try:
            self.root.after_cancel(job)
        except tk.TclError:
            pass
    self._timers = []
    self._ui_queue = queue.SimpleQueue()   # drop any already-queued closure
                                            # bound to a widget about to be
                                            # destroyed (see the self.status.
                                            # set hazard above) -- losing an
                                            # in-flight, not-yet-drained status
                                            # update is harmless; the next
                                            # state transition re-queues one.
    for w in self.root.winfo_children():
        w.destroy()
    self._build_ui(self.s)
```
This directly satisfies every item in the dispatch's enumeration:
- **selected game**: `self._select(self.current, persist=False)` in `_build_
  ui`'s tail restores it into the freshly-built form widgets.
- **`running`**: never read or written by teardown/rebuild — the worker
  thread keeps clicking through the whole sequence, per §"Threading" above.
- **`registered_hotkey`/`hk_listener`**: untouched (not Tk objects); only
  their *display* (the status pill's hint text, `hotkey_label` inside the
  rebuilt hotkey card) is resynced from existing state, never re-registered.
- **`_ui_queue`**: intentionally replaced (see the fresh-queue comment
  above) as one of the two defenses against the stale-`self.status.set`
  hazard — the other is the `_drain_ui` fix in §3, which is the one that
  actually closes the hole (the queue swap alone narrows but does not
  eliminate the race — see §3).
- **`after()` jobs**: `_drain_ui`/`_sync_settings`/`_poll_games`'s existing
  chains are explicitly cancelled, then restarted fresh in `_build_ui`'s
  tail — exactly 3 live jobs after a rebuild, same as after `__init__`,
  never 6. (Directly gives the "count them" acceptance criterion below.)
- **`bind_all` from #14**: never called from `_build_ui()` at all (see
  above) — the single call in `__init__` binds to `root`, which survives
  every rebuild untouched, so nothing needs to (or may) re-bind it.
- **a pending update offer**: out of scope for 3a's Settings page (Updates
  isn't in it yet), but `update_button`/`version_label` still live in the
  sidebar, which **is** torn down and rebuilt by `_rebuild_ui()` (it's a
  child of `root`). `_build_ui`'s tail must therefore resync them too, the
  same way it resyncs the status pill: if `self._pending` is set, call
  `self._offer_update(self._pending[0])` again after rebuilding (cheap —
  it only sets text/colour on the freshly-built widgets); otherwise the
  freshly-constructed `Button(side, "Check for updates", ...)` already
  shows the correct idle state by construction. A `Checking…`/`Downloading…
  N%` transient (no durable state beyond the widget text) is not resynced —
  acceptable: it is momentary, and a background `_check_worker`/`_install_
  worker` thread keeps running regardless of the UI's state, so nothing is
  lost, only a mid-flight status line that reverts to idle until the next
  progress tick redraws it (which will now reach the *new* button, since
  `_set_update_state` looks up `self.update_button` fresh — see §3).

### 3. Required `_drain_ui` fix — the actual correctness fix, not just hygiene

The fresh-`_ui_queue` swap in `_rebuild_ui()` only removes *already-queued*
stale closures; a `self._ui(self.status.set, ...)` call from the worker
thread that happens to read `self.status` in the narrow window while
`_rebuild_ui()` is destroying/reconstructing widgets can still land a stale
bound method in the *new* queue. `_drain_ui` must stop treating every
`TclError` as "the window is closing":
```python
def _drain_ui(self):
    while True:
        try:
            fn, args = self._ui_queue.get_nowait()
        except queue.Empty:
            break
        try:
            fn(*args)
        except tk.TclError:
            if not self.root.winfo_exists():
                return                  # window is really going away
            continue                    # a rebuilt/destroyed widget's stale
                                         # closure -- drop it, keep draining
    self._timers.append(self.root.after(40, self._drain_ui))
```
This is a one-function, minimal-diff fix (no change to `loop()`/`start()`/
`stop()`'s `self._ui(self.status.set, ...)` call sites — restructuring
those to look up `self.status` fresh like every other queued callback does
would also close the hole, but touches six call sites for no behavioural
gain over the two-line fix above, so it's not proposed). Required for this
spec's "a running clicker survives a rebuild" acceptance criterion to hold
under a real race, not just in the common case where the timing happens to
not overlap.

### 4. Persistence — `settings.json["appearance"]`

`Store.__init__` (`afk_clicker.py:792-830`): add `"appearance"` to the
default-keys dict and a sanitiser immediately after the existing `"games"`
one, same shape/spirit:
```python
self.data = {"games": {}, "hotkey": None, "selected": None,
             "appearance": "system"}
...
if self.data["appearance"] not in ("system", "light", "dark"):
    self.data["appearance"] = "system"
```
This is additive-only (story.md Decision 0 — no schema version needed; a
missing key on an old file already defaults to `"system"` the same way a
missing `"hotkey"` already defaults to `None`), so it does not interact with
`ROADMAP.md`'s "must run before the shape filter" warning — nothing here
changes an existing key's shape.

**Naming note (deviation from story.md's draft):** story.md's own draft
acceptance criteria (Feature 3) call this key `"theme"`; the dispatch for
this spec calls it `"appearance"`. Using `"appearance"` here, deliberately:
it names the *user-facing setting* ("system"/"light"/"dark", surfaced under
a section literally labelled "Appearance"), distinct from `THEMES`/`_ACTIVE`/
`set_active_theme()`'s existing use of "theme" to mean a *concrete resolved
palette* (`THEMES["light"]`). Keeping the two words apart avoids a
`settings.json["theme"] = "system"` that isn't itself a valid `THEMES` key —
confusing next to `set_active_theme(name)`'s own docstring, which already
uses "theme" to mean exactly `"dark"`/`"light"`.

**Resolution + caching `detect_os_theme()`:** story.md's cross-cutting
Decision is explicit that detection runs once per process, not polled and
not re-run on demand. A small pure helper, beside `set_active_theme()`:
```python
def resolve_appearance(value, cached_os_theme=None):
    """"system"/"light"/"dark" -> a THEMES key. cached_os_theme, if given,
    is reused instead of calling detect_os_theme() again -- story.md:
    detection happens once per process, not on every resolution (including
    a mid-session re-pick of "System" in Settings)."""
    if value != "system":
        return value
    return cached_os_theme if cached_os_theme is not None else detect_os_theme()
```
`__main__` (`afk_clicker.py:1980-1989`), constructing `Store` earlier so the
saved value is available before the first widget is built:
```python
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    enable_dpi_awareness()
    store = Store()
    appearance = store.data["appearance"]
    os_theme = detect_os_theme() if appearance == "system" else None
    set_active_theme(resolve_appearance(appearance, os_theme))
    root = tk.Tk()
    if "Segoe UI" not in tkfont.families():
        root.option_add("*Font", "TkDefaultFont")
    AfkAutoclicker(root, store=store, os_theme=os_theme)
    root.mainloop()
```
`AfkAutoclicker.__init__` gains one new optional constructor parameter,
`os_theme=None` (default keeps every existing `AfkAutoclicker(root,
store=...)` test call site working unchanged — no test needs updating for
this alone), stored as `self._os_theme`. Mid-session, the Settings page's
Appearance handler:
```python
def _apply_appearance(self, value):
    self.store.data["appearance"] = value
    self.store.save()
    resolved = resolve_appearance(value, self._os_theme)
    if value == "system" and self._os_theme is None:
        self._os_theme = resolved   # memoize -- a later System pick this
                                     # session must not call detect_os_theme()
                                     # a second time
    set_active_theme(resolved)
    self._rebuild_ui()
```
wired from the Settings page's `Segmented` control:
```python
self.appearance_var = tk.StringVar(value=self.store.data["appearance"])
Segmented(page, [("system", "System"), ("light", "Light"), ("dark", "Dark")],
          self.appearance_var, s).pack(...)
self.appearance_var.trace_add("write",
    lambda *_a: self._apply_appearance(self.appearance_var.get()))
```
(placement/sizing inside the Settings page is the ux-designer's call).
`self.appearance_var` must itself be rebuilt fresh each time `_build_
settings(s)` runs (it lives on `self`, but the `Segmented` widget reading it
is destroyed/recreated each rebuild like everything else in `self.content` —
no special handling beyond what §2 already does for every other widget).

### 5. `_build_settings(s)` — minimal page (3a scope only)

A new method, structurally parallel to `_build_content(s)`, building into
`self.content` (same pattern: a padded `body` frame, `section()`/`card()`
helpers already used throughout the file — no new visual primitives). 3a's
content: a "Appearance" section heading and one card holding the `Segmented`
control described in §4. Nothing else — no Updates section yet (3b). Exact
copy/spacing/sizing is the ux-designer's call (`docs/design.md`, next
stage); this spec fixes only the structural requirement: this method's body
must be fully torn down/rebuilt the same way `_build_content`'s is (i.e., it
must not special-case itself out of `_rebuild_ui()`'s blanket `root.winfo_
children()` teardown).

### 6. Residue ticket — `bind_all("<Button-1>")` and the Settings page

`root.bind_all("<Button-1>", self._maybe_drop_focus)` (`afk_clicker.py:
1374`) is interpreter-wide (bound on the special `"all"` bindtag, not on any
one widget) and, per §2, stays a single call made once in `__init__`, never
re-issued inside `_build_ui()`/`_rebuild_ui()` — a rebuild's new widgets
(the Settings entry, the `Segmented` Appearance control, its card) are
automatically covered by the existing single binding with zero extra code,
exactly like every other non-`Entry` widget already is today. Add the
one-line comment at the `bind_all` call site itself, answering #18 directly:
```python
root.bind_all("<Button-1>", self._maybe_drop_focus)  # bound once, here --
    # NOT inside _build_ui(): root itself survives every rebuild, so
    # re-issuing this on each theme change would be a pointless duplicate
    # binding on an interpreter-wide tag (see #18) for a target that never
    # goes away.
```
No special-casing needed for the Settings page's own widgets: `Segmented`/
`Button`-family widgets are canvases, not `Entry`, so a click on the
Appearance control already drops focus like a click on any other button —
consistent with the sidebar and every existing card.

## Affected areas
- `afk_clicker.py` only, one architectural layer (Tk UI + its one `Store`
  key): `Store.__init__` (new key + sanitiser), `set_active_theme`'s
  neighbourhood (new `resolve_appearance()`), `AfkAutoclicker.__init__`
  (split into one-time setup + `self._build_ui()`), new `self._rebuild_ui()`,
  `self._build_settings()`, `self._apply_appearance()`, `self._show_
  settings()`, a first-step addition to `self._select()`, `self._drain_ui`
  (the `TclError`-handling fix), one new sidebar widget, `__main__`
  (constructs `Store` earlier, passes `os_theme` through). No other file.
- Data model: `settings.json` gains `"appearance": "system"|"light"|"dark"`
  (default `"system"`).
- No public interface change beyond `AfkAutoclicker`'s new optional
  `os_theme=` constructor parameter (backward compatible — every existing
  test call site is unaffected).

## Edge cases
- **A fresh install / no `appearance` key on disk**: `Store.__init__`
  defaults it to `"system"` — startup behaves exactly like today
  (`detect_os_theme()` decides), no behaviour change for anyone who's never
  opened Settings.
- **A garbage `appearance` value** (wrong type, typo, an old `"theme"`-style
  value if someone hand-edits the file, `null`, a number): sanitised to
  `"system"` in `Store.__init__`, same place/shape as the `"games"` filter —
  never reaches `resolve_appearance()`/`set_active_theme()` unvalidated.
- **Appearance changed while the clicker is running**: the click loop is
  unaffected (§ "Threading"); the running/stopped state and its status-pill
  display both survive the rebuild (§2's resync tail).
- **Appearance changed while a "Checking…"/"Downloading… N%" update is
  in-flight**: the background thread is unaffected (it's a plain thread, not
  tied to any widget); a queued mid-flight status text may land on a
  destroyed widget and get silently dropped by §3's fix (harmless — the
  worker keeps running); a durable "update found" offer (`self._pending`)
  is explicitly resynced post-rebuild (§2) so it is never lost.
- **Rapid repeated Appearance clicks** (System→Light→Dark→System before one
  rebuild finishes): `_rebuild_ui()` runs synchronously on the main thread
  inside one Tk callback per click — no two rebuilds can overlap (Tk is
  single-threaded/event-loop-driven), so each click's rebuild fully
  completes before the next click's handler can run.
- **Settings open across a game auto-select** (`_mark_running`'s "follow the
  game the first time it appears," `afk_clicker.py:1700-1714`, could fire
  while `self._settings_open` is `True`): `_select()`'s new first step
  (close Settings, rebuild to the per-game form) applies unconditionally,
  including when `_select` is invoked from `_mark_running` — the user
  looking at Settings when their game is detected is switched to that
  game's form, matching today's "follow the game" behaviour for any other
  trigger of `_select`. Not a new decision, just confirming the existing
  mechanism composes correctly with the new one.
- **Selecting a game that's already selected while Settings is open**: still
  closes Settings and shows that game's (already-current) form — `_select`
  doesn't special-case "same id," matching today's behaviour.
- **Permission boundaries**: none — Appearance/Settings introduce no new
  privileged operation; `detect_os_theme()`'s own permission story is
  Feature 2's, unchanged.
- **Platform differences**: none beyond what Feature 2 already handles —
  `resolve_appearance()`/`_apply_appearance()` are platform-agnostic; they
  only decide *when* to call the already-cross-platform `detect_os_theme()`.

## Acceptance criteria
- [ ] Given a fresh `Store` (no `settings.json` on disk), when constructed,
      then `store.data["appearance"] == "system"`.
- [ ] Given a `settings.json` with `"appearance": "light"` (or `"dark"`,
      `"system"`), when loaded, then `store.data["appearance"]` is that
      exact value.
- [ ] Given a `settings.json` with `"appearance": "sepia"` (or `null`, `42`,
      missing entirely), when loaded, then `store.data["appearance"] ==
      "system"`.
- [ ] Given the Settings page's Appearance control set to `"light"`, when
      applied, then `app.set_active_theme` has effectively made
      `THEMES["light"]` active — sample the same widgets Feature 2's
      `test_light_theme_reaches_every_sampled_widget` samples (`ui.root.
      cget("bg")`, `ui.eat_card_inner.cget("bg")`, `ui.apply_button.
      itemcget(ui.apply_button.shape, "fill")` after `set_enabled(True)`,
      `ui.click_ms.wrap.cget("bg")`) against `app.THEMES["light"]`, using
      the **new, rebuilt** widget references (`ui.apply_button` etc. must be
      the post-rebuild objects — asserts the rebuild actually replaced them,
      not that stale references happen to still resolve).
- [ ] Given Appearance set to `"light"`, when applied, then `settings.json`
      on disk contains `"appearance": "light"` (`Store.save()` was called).
- [ ] Given a game (e.g. `"minecraft"`) is selected, when Appearance is
      changed, then after the rebuild `ui.current == "minecraft"` and the
      per-game form (not the Settings page) is what's showing, with that
      game's field values intact (re-select `"minecraft"` is not required —
      the rebuild's own tail already restores it).
- [ ] Given the clicker is running (`ui.running is True`, `ui.start()`
      called) when Appearance is changed, then after the rebuild `ui.
      running is True`, the worker thread is still alive and still the
      *same* `threading.Thread` object (`ui.worker` identity unchanged —
      the rebuild never touches it), and the status pill shows "RUNNING"
      after the rebuild's resync.
- [ ] Given a hotkey is applied (`ui.registered_hotkey` set, `ui.hk_
      listener` running) when Appearance is changed, then after the
      rebuild `ui.hk_listener` is the **identical object** (`is`, not
      `==`) as before the rebuild, and `.running` is still `True` — the
      listener was never stopped/restarted.
- [ ] Given the app has just been rebuilt (any Appearance change), when
      counting live `after()` jobs via `ui._timers`, then there are exactly
      3 (matching a fresh `__init__`'s count), not 6 — proves the pre-
      rebuild jobs were cancelled, not merely added to.
- [ ] Given `root.bind_all("<Button-1>", ...)`'s registered command count
      (or equivalent — e.g. clicking a non-`Entry` widget still drops focus
      exactly once, not twice, after two Appearance changes), when Appearance
      is changed twice in a row, then focus-drop behaviour is unchanged
      (a click on the Settings page's Appearance control drops focus from
      any previously-focused `Entry` exactly as any other non-`Entry` click
      already does) — proves `bind_all` was not re-issued.
- [ ] Given `settings.json["appearance"] == "light"` on disk, when the app
      is relaunched (`restart()`-style: `on_close()` then a fresh `Store` +
      `AfkAutoclicker`, or exercising `__main__`'s logic directly), then the
      window opens already showing `THEMES["light"]` — no Settings visit
      needed.
- [ ] Given `appearance == "system"` and `detect_os_theme()` is stubbed
      (Feature 2's existing seam) to return `"light"`, when the app starts
      and the user then opens Settings and picks "System" again, then
      `detect_os_theme()` (the stub) is called **at most once** across the
      whole sequence — proves the mid-session "System" pick reuses the
      cached value rather than re-detecting.
- [ ] Given the sidebar after this feature, when inspected, then "Add
      current game", the new "Settings" entry, "Check for updates", and the
      version label are all present (3a does not remove the last two — see
      "Interim sidebar layout"), and clicking "Settings" shows the
      Appearance control while every `GameItem` shows unselected.
- [ ] Given the Settings page is open, when a `GameItem` is clicked, then
      the per-game form reappears (`ui._settings_open is False`) and the
      Settings sidebar entry shows unselected.
- [ ] Given the hotkey card (`Toggle`/`Record`/`Apply`), when this feature
      ships, then it is unchanged and still only reachable from a game's
      page, never from Settings — non-regression on "the global hotkey
      stays on the game pages."

## Open questions
None that block starting 3a — every navigation/persistence/rebuild
ambiguity the dispatch raised is resolved above with reasons and rejected
alternatives. Two things flagged for confirmation rather than silently
assumed:

1. **The `"appearance"` vs. story.md's draft `"theme"` key name** (§4) — my
   reasoning is in the spec; if there's a reason to prefer matching story.md
   verbatim instead, say so before the ux-designer/developer pick it up,
   since it's a one-word, easy-to-change-now, hard-to-change-after-users-
   have-a-`settings.json` decision.
2. **Whether 3b (moving Updates) should be scoped as its own spec
   immediately after this one ships**, or folded back into a single larger
   spec if 3a's review shows the rebuild mechanism landed with less
   complexity than expected. My recommendation is to keep them split
   regardless (skill 11) — flagging only because the split itself, not its
   contents, is a call the orchestrator/user might want to weigh in on.

## Risk / rollback notes
- The riskiest new mechanism is the rebuild (§2-3), specifically the
  `self.status.set` stale-closure race. The `_drain_ui` fix (§3) is small
  (one function, ~4 changed lines) and independently testable — if it
  turns out insufficient in practice (a race the acceptance criteria above
  don't catch), the documented fallback from story.md's own Open Questions
  is downgrading Appearance to "applies next launch" rather than live
  rebuild; that downgrade would delete `_rebuild_ui()`/`_build_ui()`'s
  reuse-from-`__init__` shape but keep `Store`'s `"appearance"` key and
  `resolve_appearance()` untouched.
- Additive persistence only: a pre-this-feature `settings.json` (no
  `"appearance"` key) behaves identically to one with `"appearance":
  "system"` explicitly set — no migration, nothing to corrupt on downgrade.
- Reverting is contained to `afk_clicker.py` (no other file, no schema
  version bump) — deleting the new methods/key/sidebar entry restores
  today's behaviour exactly, since nothing else in the file references them
  yet (mirrors Feature 2's own rollback note).
