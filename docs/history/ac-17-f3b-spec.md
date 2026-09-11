# Spec: Move Updates into Settings (story #17, Feature 3b)

## Summary
Relocate `self.update_button` ("Check for updates"/install action) and
`self.version_label` (`v{__version__}`, and the status/offer text they
double as) out of the sidebar footer and into a new "Updates" section on
the Settings page (below Appearance, which 3a already built). The sidebar
footer becomes: games list → "Add current game" → divider → "Settings".
No updater logic changes (checking, verification, staging, the swap
script are untouched) — this is a relocation of two widgets plus the
rebuild-safety and off-screen-signal work that relocation itself requires,
same shape as 3a's own split rationale.

## Goals
- Sidebar footer no longer builds `update_button`/`version_label`; only
  "Add current game", the divider, and the Settings entry remain below the
  games list.
- `_build_settings(s)` gains an "Updates" section/card below Appearance,
  building `self.update_button`/`self.version_label` with the exact same
  widget classes and constructor shapes used today — `check_update`,
  `_check_worker`, `install_update`, `_install_worker`, `_quit_for_update`,
  `_set_update_state`, `_offer_update` keep their current bodies almost
  verbatim (see §3 for the one necessary addition to the latter two).
- An update state set while Settings is open renders immediately, exactly
  as it does today in the sidebar.
- An update state set while Settings is **not** open (or not yet ever
  opened this session) never touches `self.update_button`/`self.
  version_label` — they may not exist, or may be stale references to a
  destroyed widget tree — and is instead remembered and replayed the next
  time `_build_settings(s)` runs (a fresh open, or a rebuild that happens
  while Settings is already open).
- A durable "update found" offer (`self._pending is not None`) is signalled
  on the sidebar's Settings row itself, so a user who never opens Settings
  this session still learns an update exists.
- The existing `_drain_ui`/`_ui()` contract — only `_drain_ui`, on the main
  thread, ever touches a widget; `_check_worker`/`_install_worker` only
  ever call `self._ui(fn, *args)` — is preserved unchanged.

## Non-goals
- Any change to `latest_release`/`is_newer`/`pick_asset`/`pick_checksums`/
  `fetch_checksums`/`download_and_stage`/`write_swap_script`/
  `_quit_for_update`'s subprocess logic, or to the swap script itself.
- Any change to the checksum error wording or ordering from #19
  (`afk_clicker.py:700-711`) — the `[:40]` truncation budget itself stays
  (see §2 for why, with rejected alternatives).
- A new `settings.json` key. Nothing here is persisted; "which update
  state is showing" is process-lifetime state only, same as today.
- An automatic update check at startup. Confirmed by grep: `check_update`
  is called from exactly one place today, the sidebar button's `command`
  (`afk_clicker.py:1556`) — there is no startup call to add scope-check
  against, and the dispatch is explicit that adding one is a behaviour
  change beyond this story. `check_for_update`/`check_update` stays
  click-triggered only.
- A "seen/dismissed" tracking state for the sidebar offer indicator (see
  §1 — rejected as unneeded mechanism).
- A two-line or wrap-length status layout, or widening the truncation
  budget past 40 characters (see §2).
- Macros (`#13`), UI scale (Feature 4), any further sidebar/navigation
  restructuring beyond removing the two widgets named above.

## Background / current state

### What 3a already built (this spec's starting point, all in `afk_clicker.py`)
- `SettingsItem` (`1358-1385`): the sidebar's one non-game row. No dot (a
  deliberate 3a design decision — design.md: "unlike GameItem... no dot,
  making it visually distinct from game rows"), just a rounded canvas +
  text + a `selected` bool driving `_paint()`. `set_state(selected=None)`
  is the only public entry point.
- Sidebar footer construction, inside `_build_ui(s)` (`1549-1575`): "Add
  current game" button, then `self.update_button` (`1556-1558`, a plain
  `Button(side, "Check for updates", self.check_update, s, ...)`), a 1px
  `LINE` divider (`1565-1566`), `self.settings_item = SettingsItem(...)`
  (`1570-1572`), then `self.version_label` (`1573-1575`, a `tk.Label`).
  The comment at `1551-1555` ("3a leaves this exactly where and how it is
  today... this is Feature 3b") is this spec's own cue — delete it along
  with the widgets it describes.
- `_build_ui(s)`'s tail (`1584-1609`): builds either `_build_settings(s)`
  or `_build_content(s)` + `_select(...)` depending on `self.
  _settings_open`, then — **unconditionally, because `update_button`/
  `version_label` are unconditionally built today** — `if self._pending is
  not None: self._offer_update(self._pending[0])` (`1594-1595`), then
  resyncs the status pill. This line's precondition (the widgets always
  exist) stops being true once they move into `_build_settings` — see §3.
- `_build_settings(s)` (`1757-1796`): one section ("Appearance") + one
  card holding the Theme `Segmented`. Its own docstring already names the
  seam: *"Feature 3b's Updates section goes below this... nothing built
  here yet, only the seam left open by this page existing at all."*
- The updater methods, unchanged shape today: `check_update` (`1944-1946`)
  → `_check_worker` (`1948-1966`, background thread) → `_offer_update`
  (`1968-1973`) or a terminal `_set_update_state` call for "no releases",
  "GitHub unreachable", "up to date", "no build for this OS". `install_
  update` (`1975-1982`) → `_install_worker` (`1984-2012`, background
  thread) → `_quit_for_update` (`2014-2021`) or a terminal `_set_update_
  state` call for a checksum/verification/read-only-folder failure. `_set_
  update_state(text, enabled=True, colour=None)` (`2023-2027`) always
  calls `self.update_button.set_text(text)`/`set_enabled(enabled)`; only
  touches `self.version_label` when `colour` is given (the idle/checking/
  progress states leave the version text alone; only a found offer, an
  error, or "up to date" pass a colour or otherwise want the label to
  change — `_offer_update` sets it directly, not through `_set_update_
  state`). Every call site already reaches these methods only via `self.
  _ui(fn, *args)` from a background thread, or a direct same-thread call
  from a `Button`'s own `command` — `_check_worker`/`_install_worker`
  never touch a widget directly today, and nothing here changes that.
- The `[:40]` truncation is **not** inside `_set_update_state` — it is
  applied at its two call sites in `_install_worker` (`2007`: `str(exc)
  [:40]` for a `ChecksumError`; `2010`: `f"Update failed: {exc}"[:40]` for
  any other exception). #19's own comment (`afk_clicker.py:701-704`)
  confirms the budget is deliberate and independent of the sidebar
  button's literal pixel width: *"The fixed words must come first: the
  status line keeps only the first 40 characters... and a real asset name
  is long enough on its own to push 'not listed in SHA256SUMS' past that
  budget if it leads the message instead of trailing it."*
- `_set_status`/`_drain_ui` (`2079-2092`, `2094+`): the pattern 3a's own
  spec (§3) and this dispatch point at for "resync after rebuild without
  binding a stale widget reference" — `_set_status` is looked up **fresh**
  by `_drain_ui` every time (a bound method of `self`, never of a specific
  StatusPill instance), and `_drain_ui` no longer treats every `TclError`
  as "the window is closing" (`2085-2091`) — a stale closure against a
  torn-down widget is dropped, draining continues. `_set_update_state`/
  `_offer_update` already follow the same "look up `self.update_button`
  fresh, inside the method body" shape — that part needs no change. What
  changes is that, post-move, the widgets they look up may not currently
  *exist* at all (not merely "stale") whenever Settings isn't open — a
  case `_set_status` never has to handle, since the header (and `self.
  status`) is unconditionally rebuilt every time. See §3.
- `SettingsItem`/`update_button`/`version_label` are all rebuilt from
  scratch on every `_rebuild_ui()` call (`1611-1687`, blanket `for w in
  self.root.winfo_children(): w.destroy()` then `_build_ui(self.s)` again)
  — nothing here changes that mechanism, this spec only changes *what* is
  (re)built where, and adds replay logic for state that isn't naturally
  reconstructed by rebuilding widgets fresh.
- No startup update check exists (confirmed by grep — the only caller of
  `check_update` is the button's own `command=self.check_update`,
  `1556`); `__main__` (`2345+`) never calls it.

### Tests referencing what's moving
- `tests/test_ui.py`'s `InstallWorker` class (`529-598`): calls `self.ui.
  _install_worker()` directly (inline on the test thread — safe, since it
  never touches Tk except via `self._ui()`) and reads `self.ui.update_
  button.itemcget(self.ui.update_button.label, "text")` (`549-550`) and
  `self.ui.update_button._enabled` (`569`, `598`). Both tests set `self.
  ui._pending` directly first.
- `tests/test_ui.py` around `1548-1560`: `test_sidebar_has_a_settings_
  entry_plus_the_untouched_update_widgets` asserts `self.ui.update_button`/
  `self.ui.version_label` exist in the sidebar unconditionally, right next
  to `self.ui.settings_item` — this test's entire premise ("untouched")
  is what 3b changes; it needs rewriting, not just a reference update (see
  §4).
- `tests/test_updater.py:190` has a comment citing `afk_clicker.py:1376`
  for `_install_worker`'s truncation — a stale line-number reference to
  fix as a nit (no attribute reference there; the file's tests are all
  pure unit tests of module-level helpers, none touch `self.ui.update_
  button`).

## Proposed approach

### 1. Sidebar footer — remove the two widgets, add an offer indicator

In `_build_ui(s)`, delete `self.update_button = Button(side, "Check for
updates", ...)` (`1556-1558`), its preceding comment (`1551-1555`), and
`self.version_label = tk.Label(side, text=f"v{__version__}", ...)`
(`1573-1575`). The divider (`1565-1566`) and `self.settings_item = ...`
(`1570-1572`) stay exactly as they are, positionally: sidebar footer
becomes games list → "Add current game" → divider → Settings entry.
Update the divider's own comment (currently explains separating "the two
action buttons above" from Settings) to reflect there is now only one
action button above it.

**Sidebar offer indicator (decision — the dispatch's "minimal honest
signal").** `SettingsItem` gains one more piece of state, `has_update`
(bool, default `False`): a new constructor keyword (`SettingsItem(parent,
on_click, s, has_update=False, ...)`), stored on `self`, and `set_state`
gains a matching keyword (`set_state(self, selected=None, has_update=
None)`, same "`None` means leave unchanged" convention `GameItem.set_
state` already uses). `_paint()` renders the row's text as `"Settings"`
when `has_update` is `False`, or a variant reading the update exists (e.g.
`"Settings · Update"` — exact copy/colour is the ux-designer's call, not
fixed here) when `True`.

Two ways `has_update` gets set, covering both trigger shapes:
- **At construction**, inside `_build_ui(s)`: `self.settings_item =
  SettingsItem(side, self._show_settings, s, has_update=(self._pending is
  not None))` — correct immediately after any rebuild, including one
  triggered while Settings is *closed* (an Appearance change on a game
  page, with an offer already pending from an earlier Settings visit).
- **Live, with no rebuild involved**: `_offer_update(tag)` (§3) additionally
  calls `self.settings_item.set_state(has_update=True)` unconditionally,
  every time it runs — `self.settings_item` is unconditionally present in
  the sidebar (unlike `update_button`/`version_label`), so this needs no
  guard. This is what makes an offer found while sitting on a game page,
  with no rebuild in sight, visible without waiting for one.

No explicit "clear" path is added: `self._pending` itself is never reset
to `None` except by a successful install (which restarts the process), so
the indicator persisting until then matches `self._pending`'s own existing
lifetime — nothing new to get out of sync.

**Rejected — reintroduce a coloured dot, like `GameItem`'s running dot.**
`design.md`'s own prior, reviewed decision for `SettingsItem` was explicit:
*"No dot/indicator: Unlike GameItem rows... making it visually distinct
from game rows."* Walking that back needs a real reason; a text-label
change signals the same thing without contradicting a decision 3a's
review already approved.

**Rejected — a hint near the header/title instead of on the Settings
row.** The header is already-tuned, shared real estate (`self.status`'s
own docstring: "the one thing you read from across the room") — 3a's own
spec already rejected wedging a segmented control there for exactly this
crowding reason (its §1 "Rejected — segmented control in the header").
Putting an update hint there reopens the same problem for a different
control, and it's semantically about the clicker's running state, not an
app-level settings destination.

**Rejected — a "seen" flag that dismisses the indicator once Settings has
been opened.** Not requested by any acceptance criterion, and it's new
state to keep consistent with `self._pending`'s own lifetime for no
concrete benefit — `self._pending is not None` is already an honest,
correct signal on its own; tracking "has the user looked yet" is
speculative complexity this spec doesn't need (`_conventions.md` §3).

### 2. The Settings page's Updates section — layout and the truncation budget

In `_build_settings(s)`, after the existing Appearance section/card
(`1774-1796`), add a second section using the same `section()`/`card()`/
`Row()` helpers already in use (no new visual primitives):

```python
section(body, "Updates", s)
up = card(body, s)
row = Row(up, "Version", s)
row.pack(fill="x")
self.version_label = tk.Label(row.control, text=f"v{__version__}", bg=CARD,
                              fg=MUTED, font=("Segoe UI", int(9 * s)))
self.version_label.pack()
self.update_button = Button(up, "Check for updates", self.check_update, s,
                            width=CARD_INNER_W... )  # exact sizing/placement:
                                                       # ux-designer's call
self.update_button.pack(pady=(int(8 * s), 0))
```
(Placement inside the card, spacing, and exact widths are the ux-
designer's call, same as 3a's Appearance card — the structural requirement
this spec fixes is just: both widgets are constructed here, as a `Button`
and `tk.Label` respectively, with the same names (`self.update_button`,
`self.version_label`) and the same constructor shapes they have today, so
`check_update`/`_set_update_state`/`_offer_update` need no signature
changes.) Do **not** populate either widget with any dynamic status text
inline here beyond the idle defaults shown above — the actual current
state (idle, checking, downloading, an offer, an error) is applied
immediately after `_build_settings(s)` returns, by `_build_ui(s)`'s tail
(§3), exactly mirroring how 3a's tail already resyncs the status pill
right after the per-game/Settings body is built.

**Does the truncation stay?** `CONTENT_W` is `452` (`afk_clicker.py:152`);
even after the card's own padding and the "Version" row's label, there is
comfortably more horizontal room than the sidebar's `SIDEBAR_W - 28 = 180`
px button ever had — so no, there's no *forced* reason to keep truncating.
**Decision: keep the existing `[:40]` truncation exactly as it is, at its
two existing call sites in `_install_worker` — do not widen, relocate, or
remove it.**

Reasons:
- story.md's Feature 3 line for this move is explicit: "reusing `_set_
  update_state`/`_offer_update`/`check_update` unchanged... a pure
  relocation of the widgets, not new update logic." The 40-character
  budget is part of the *text* `_install_worker`'s error handling
  produces, which is squarely the "verification" logic the dispatch says
  not to touch.
- #19 hand-ordered the checksum messages ("fixed words must come first")
  specifically around this cutoff (`afk_clicker.py:701-704`). Changing the
  cutoff without re-validating that ordering is still the right shape is
  a real correctness risk (a message that reads fine at 40 chars could
  read worse, not better, cut at some other length) for no requirement
  actually asking for it.
- A consistently terse, one-line status voice regardless of *where* it's
  shown is a legitimate design choice on its own merits, not just a
  constraint being worked around — matches every other status line in
  this file (`_set_status`'s own `str(exc)[:32]` cap at `afk_clicker.py:
  2306`, for the click-loop's error state, uses the same "short and
  legible over complete" logic).

**Rejected — remove truncation only for the Settings placement** (e.g. a
`sidebar=True`/budget parameter threaded through `_install_worker`).
Rejected: this *is* touching updater logic/text, which the dispatch rules
out, for a cosmetic upside ("headroom exists") with no acceptance
criterion behind it, and it reopens #19's wording without a concrete
complaint driving the change.

**Rejected — a two-line/wrapped status layout.** New layout complexity
(dynamic height, `wraplength` handling) for a `tk.Label` that has never
been more than one line, solving a problem ("40 chars reads cramped") that
no acceptance criterion or prior review flagged as real. If a future pass
finds real user confusion from truncated text, that is a smaller, focused
follow-up on its own — not something to build speculatively here.

### 3. Rebuild- and visibility-safety — `_update_text`, guarded `_set_update_state`/`_offer_update`

**The problem this section solves:** once `update_button`/`version_label`
only exist while `self._settings_open` is `True`, three things that were
previously always safe stop being so:
1. A background worker's queued callback (`self._ui(self._set_update_
   state, ...)` or `self._ui(self._offer_update, ...)`) can land via `_
   drain_ui` at a moment when Settings isn't open — `self.update_button`
   either doesn't exist yet (never opened this session: `AttributeError`)
   or is a stale reference to an already-destroyed widget from the last
   time Settings *was* open (`TclError`, same shape as the hazard 3a's §3
   fixed for `self.status`).
2. A rebuild (`_rebuild_ui()`, e.g. from an Appearance change) that
   happens *while Settings is open and a check/download is mid-flight*
   destroys and reconstructs `update_button`/`version_label` from scratch,
   which resets them to their idle defaults — losing the in-progress
   text ("Checking…", "Downloading… 45%") and any found offer, unless
   something replays the current state onto the freshly built widgets.
3. `install_update`'s in-progress state ("Downloading… N%") must survive a
   rebuild *without reverting to the "Install v{tag}" offer state* it grew
   out of — `self._pending` stays set for the whole download (it's read,
   never cleared, by `_install_worker`, `1985`), so a naive "replay the
   offer if `self._pending`" would incorrectly show "Install v{tag}"
   again mid-download after a rebuild.

**The fix — one new piece of state, plus a guard, plus a two-step replay
that reproduces today's own layering:**

`AfkAutoclicker.__init__` gains `self._update_text = ("Check for updates",
True, None)` alongside `self._pending = None` (`1469`) — a plain tuple,
not a Tk object, so (like `_pending`) it is never reset by a rebuild; it
is the args of the most recent `_set_update_state(text, enabled, colour)`
call, always kept current regardless of whether Settings is open.

`_set_update_state` becomes:
```python
def _set_update_state(self, text, enabled=True, colour=None):
    self._update_text = (text, enabled, colour)
    if not self._settings_open:
        return
    self.update_button.set_text(text)
    self.update_button.set_enabled(enabled)
    if colour:
        self.version_label.config(text=text, fg=colour)
```
`_offer_update` becomes:
```python
def _offer_update(self, tag):
    self._update_text = (f"Install {tag}", True, None)
    self.settings_item.set_state(has_update=True)
    if not self._settings_open:
        return
    self.update_button.set_text(f"Install {tag}")
    self.update_button.set_primary(True)
    self.update_button.set_enabled(True)
    self.update_button.command = self.install_update
    self.version_label.config(text=f"v{__version__} → {tag}", fg=ACCENT)
```
(`self._pending` itself continues to be set by `_check_worker`, `1965`,
exactly as today — `_offer_update` doesn't touch it.)

`_build_ui(s)`'s tail (`1584-1609`) changes its unconditional `if self.
_pending is not None: self._offer_update(self._pending[0])` (`1594-1595`)
to run, and be followed by a second replay step, **only when Settings is
the body that was just built**:
```python
if self._settings_open:
    self._build_settings(s)
    if self._pending is not None:
        self._offer_update(self._pending[0])
    self._set_update_state(*self._update_text)
else:
    self._build_content(s)
    self._select(self.current, persist=False)
```

**Why replaying both, in this order, is correct — not redundant.** This
reproduces the exact layering that already happens today, live, without
any rebuild: `_offer_update` sets the button's *styling* (primary,
`command=install_update`) and the version label's arrow text; a later
`_set_update_state` call (idle default, "Checking…", "Downloading… N%",
or an error) only ever overwrites *text*/*enabled*, never touches `primary`
or `command`. Replaying `_offer_update` first, then unconditionally
overlaying `_update_text`, puts the freshly rebuilt widgets through the
identical two-layer history the original widgets went through:
- **No offer yet, e.g. "Checking…" mid-flight**: `self._pending is None`,
  so only the `_update_text` overlay runs — button shows "Checking…",
  disabled, no special styling. Matches today.
- **Offer found, nothing since**: `_offer_update` runs (button becomes
  "Install v{tag}", primary, `command=install_update`); `_update_text` was
  set to the identical `(f"Install {tag}", True, None)` by that same call
  (see its new first line above), so the overlay reapplies the same text —
  idempotent, correct.
- **Mid-download** (`install_update` was clicked, `_install_worker`'s
  progress callback last set `_update_text = ("Downloading… 45%", False,
  None)`, while `self._pending` is still the same tag/asset/release):
  `_offer_update` replay first restores "Install v{tag}" styling
  (primary=True, command=install_update — an internal detail, invisible
  once overlaid), then the `_update_text` overlay immediately overwrites
  the *text* to "Downloading… 45%" and disables the button — the final
  rendered state is "Downloading… 45%", disabled, still accent-coloured
  from the offer styling underneath, exactly matching what the button
  already looks like today mid-download without any rebuild involved
  (nothing in the current, non-rebuilt code path resets `primary` either).
- **An install-time error** (checksum mismatch, read-only folder, generic
  exception): same shape as mid-download — `_pending` is still set (the
  button stays enabled so the user can retry), `_update_text` holds the
  truncated error text/colour, and the two-step replay reproduces
  "error text on an accent-styled, re-enabled button" exactly.

**Worker threads still never touch a widget.** `_check_worker`/`_install_
worker` are unchanged: every UI-facing call is still `self._ui(self._set_
update_state, ...)` or `self._ui(self._offer_update, ...)`, queued and
only ever invoked by `_drain_ui` on the main thread. The new `if not self.
_settings_open: return` guard, and the `self.settings_item.set_state(...)`
call, both execute inside that same main-thread `_drain_ui` invocation —
no new thread ever touches Tk, and `self._settings_open` itself is only
ever mutated on the main thread (`_select`/`_show_settings`), synchronously
followed by the rebuild that acts on it, so there is no window where a
queued callback observes a `self._settings_open` that doesn't match
whether the widgets it's about to touch actually exist (same reasoning
3a's spec already relied on for `self._rebuilding`/`self._rebuild_wanted`
not racing against `_drain_ui`).

### 4. Tests

- **`tests/test_ui.py`'s `InstallWorker` class (`529-598`)**: add one
  setup line before `self.ui._pending = (...)` in both test methods —
  `self.ui._show_settings()` (then whatever this file's existing pump
  helper is — e.g. `self.root.update()`/`self.pump(...)`, matching the
  pattern already used elsewhere in this class's `UITestCase` base) — so
  `self.ui.update_button` exists before `_install_worker()`/`_drain()` run.
  `_button_text()` (`549-550`) and every assertion on `self.ui.update_
  button._enabled` (`569`, `598`) stay exactly as written, same attribute
  name, same real widget — not weakened, since Settings is now genuinely
  open, the same state a user would actually see.
- **`test_sidebar_has_a_settings_entry_plus_the_untouched_update_widgets`
  (`~1548-1553`)**: rewrite, not just patch — its premise is gone. Replace
  with an assertion that the sidebar (`self.ui.side`'s direct children, or
  simply: before `_show_settings()` is called) does **not** hold `update_
  button`/`version_label`, and that `self.ui.settings_item.has_update is
  False` on a fresh app with no prior update activity. Rename it to drop
  "untouched" (e.g. `test_sidebar_no_longer_holds_the_update_widgets`).
- **New test — Settings shows the Updates section**: after `self.ui.
  _show_settings()`, `self.ui.update_button`/`self.ui.version_label` exist,
  are real `Button`/`tk.Label` instances, and the button's default text
  reads "Check for updates".
- **New test — offer signalled on the Settings row while a game page is
  open**: with Settings closed (default), drive `_check_worker`'s offer
  path (mock `latest_release`/`is_newer`/`pick_asset` the way existing
  updater tests already do, or set `self.ui._pending` directly and call
  `self.ui._offer_update(tag)` inline the same way `InstallWorker` already
  calls `_install_worker()` inline) and assert `self.ui.settings_item.
  has_update is True` without ever having opened Settings, and without
  raising (covers the `AttributeError`/`TclError` hazard in §3 directly).
- **New test — state survives a rebuild mid-download**: open Settings,
  set `self.ui._pending` and call `self.ui._offer_update(tag)`, then call
  `self.ui._set_update_state("Downloading… 45%", False)` (simulating an
  in-flight progress tick), then trigger a rebuild (`self.ui._rebuild_ui()`
  directly, or through `_apply_appearance` the way `test_system_
  appearance_detects_at_most_once...` at `~2047` already does), then
  assert the **new**, post-rebuild `self.ui.update_button` (object
  identity will differ — same pattern the Appearance acceptance criteria
  in `docs/spec.md` of 3a already required for `ui.apply_button` etc.)
  shows "Downloading… 45%", disabled, and `self.ui._pending`/`self.ui.
  _update_text` are unchanged by the rebuild.
- **`tests/test_updater.py:190`**: fix the stale `afk_clicker.py:1376`
  line-number comment to point at wherever `_install_worker`'s truncation
  ends up after the move (a nit, no behaviour change).

## Affected areas
- `afk_clicker.py` only, one file, the same single architectural layer 3a
  already established (Tk UI): `AfkAutoclicker.__init__` (one new `self.
  _update_text` state tuple), `_build_ui` (sidebar footer trims two
  widgets, tail gains the guarded two-step Updates replay), `_build_
  settings` (new "Updates" section/card), `_set_update_state`/`_offer_
  update` (record `_update_text`, guard on `self._settings_open`, `_offer_
  update` also signals `self.settings_item`), `SettingsItem` (`has_update`
  constructor kwarg + `set_state` kwarg + `_paint()` text branch). No
  change to `Store`, `settings.json`, `check_update`/`_check_worker`/
  `install_update`/`_install_worker`/`_quit_for_update`'s bodies beyond
  what's already covered above (call sites unchanged; only the two methods
  they call into gain the guard/record lines).
- `tests/test_ui.py` (`InstallWorker` class, the Settings-sidebar test
  around `1548`, new tests per §4), `tests/test_updater.py` (one comment
  line-number fix, no behavioural change).
- `README.md:23` — "Ab dann aktualisiert sich das Programm selbst: **Check
  for updates** unten links" ("...bottom left") becomes false once the
  button moves; update to point at Settings → Updates (small, mechanical,
  same kind of fix 3a already made to the neighbouring "Aussehen" section
  for the Appearance control, and the fix `docs/test-review.md`'s Finding
  #3 recommended folding into 3b).
- No data model or persisted-schema change. No new public interface beyond
  the two new-but-optional `SettingsItem` constructor/method keywords
  (backward compatible — no other call site passes `has_update`).

## Edge cases
- **Offer found while Settings is already open**: unchanged from today —
  `_offer_update` runs its widget-touching branch immediately (§3).
- **Offer found while a game page is open**: `self.settings_item.set_
  state(has_update=True)` fires immediately (§1/§3); `update_button`/
  `version_label` are untouched (don't exist yet) and correctly replay
  once Settings is opened (`_build_settings` + the tail's replay, §3).
- **Rebuild (Appearance change) while Settings is open, mid-"Checking…"**
  (no offer yet): `_update_text` replay alone restores "Checking…",
  disabled — the background `_check_worker` thread is unaffected by the
  rebuild and will land its eventual result on the new widgets via the
  same guarded `_set_update_state`/`_offer_update`, since `self._settings_
  open` is unchanged across the rebuild.
- **Rebuild while Settings is open, mid-download**: both-step replay (§3)
  restores "Downloading… N%", disabled, accent-styled — not "Install v
  {tag}".
- **Rebuild while Settings is closed, offer pending**: `_build_content`
  runs (not `_build_settings`); the tail's Updates replay is skipped
  entirely (guarded on `self._settings_open`); the sidebar's fresh `
  SettingsItem` is constructed with `has_update=(self._pending is not
  None)` directly (§1), so the indicator is still correct without needing
  the replay path.
- **Rebuild while Settings is closed, no pending offer**: nothing to
  replay, `self.settings_item.has_update` is `False` — matches a fresh
  `__init__`.
- **Rapid repeated Appearance clicks while a check/download is in
  flight**: unaffected by this spec — 3a's existing `self._rebuilding`/
  `self._rebuild_wanted`/`self._rebuild_after_id` coalescing already
  guarantees at most one rebuild runs at a time (`_rebuild_ui`'s own
  docstring, `1611-1655`); this spec adds no new rebuild-triggering path.
- **A checksum/verification/generic install error, post-move**: text and
  ordering unchanged from #19 (§2); still readable at 40 characters,
  still lands via the same guarded `_set_update_state` call, still leaves
  `self._pending` set so retry (clicking "Install v{tag}" again) works
  the same way it does today.
- **A non-frozen dev run** (`install_update`'s `"Run \`git pull\` — not a
  build"` branch, `1976-1980`): unaffected logic-wise; renders correctly
  through the same guarded `_set_update_state` call whether Settings is
  open at the moment of the click (always true here, since clicking the
  button requires it to exist) or not.
- **Permission boundaries**: none new — no new privileged operation is
  introduced by relocating two widgets or adding a boolean flag.
- **Platform differences**: none — `_quit_for_update`'s win32/POSIX branch
  (`2016-2020`) is untouched; only the on-screen location of the trigger/
  status changes.

## Acceptance criteria
- [ ] Given a freshly built sidebar, when inspected, then it holds "Add
      current game", a divider, and the Settings entry only — no `update_
      button`/`version_label` are children of `self.side`.
- [ ] Given `self.ui._show_settings()`, when the Settings page is built,
      then `self.ui.update_button`/`self.ui.version_label` exist as real
      `Button`/`tk.Label` instances inside `self.ui.content`, positioned
      below the Appearance section, and `self.ui.update_button`'s text
      reads "Check for updates" on first open with no prior activity.
- [ ] Given every update state `check_update`/`_check_worker`/`install_
      update`/`_install_worker` can produce today (checking, no releases,
      GitHub unreachable, up to date, no build for this OS, an offer
      found, downloading at some percent, a checksum error, a generic
      install error, read-only folder, a non-frozen "not a build" click,
      restarting), when Settings is open and that state is set, then it
      renders on `self.ui.update_button`/`self.ui.version_label` exactly
      as it does today in the sidebar (same text, same enabled/disabled,
      same colour where applicable) — a non-regression sweep, not a new
      behaviour.
- [ ] Given `self.ui._pending` is set (an offer found) via `self.ui.
      _offer_update(tag)`, when a game page is showing (Settings never
      opened this session), then `self.ui.settings_item.has_update is
      True` and no exception is raised — proves the off-screen signal
      path is safe and correct.
- [ ] Given `self.ui._pending` is set with Settings closed, when `self.ui.
      _show_settings()` is then called, then `self.ui.update_button`/
      `self.ui.version_label` show the offer ("Install v{tag}", primary,
      version label reading "v{current} → v{tag}") without needing a
      second `check_update()` call.
- [ ] Given Settings is open with an offer found and a download in
      progress (`self.ui._set_update_state("Downloading… 45%", False)`
      called after `self.ui._offer_update(tag)`), when a rebuild happens
      (`self.ui._rebuild_ui()` or an Appearance change), then the **new**
      `self.ui.update_button` shows "Downloading… 45%", disabled — not
      "Install v{tag}" — and `self.ui._pending` is unchanged.
- [ ] Given a `ChecksumError`/generic exception is raised inside `_install_
      worker` (mocked, same technique `InstallWorker`'s existing tests
      already use), when the resulting text reaches `self.ui.update_
      button`, then it is truncated to 40 characters, still contains
      "checksum" (case-insensitive) for a checksum failure, and `self.ui.
      update_button._enabled is True` (re-enabled for retry) — a direct
      repeat of the two existing `InstallWorker` assertions, now reached
      via `self.ui._show_settings()` first.
- [ ] Given the hotkey card (`Toggle`/`Record`/`Apply`), when this feature
      ships, then it is unchanged and still only reachable from a game's
      page — non-regression on "the global hotkey stays on the game
      pages," same check 3a's own acceptance criteria already ran.
- [ ] Given `self.ui.count_label`'s "GAMES N" text and `self.ui.items`,
      when this feature ships, then both are unaffected by the sidebar
      footer change (the games list itself is untouched) — non-regression
      repeat of 3a's own "games count excludes the settings entry" check.
- [ ] Given `README.md:23`, when read after this change, then it no
      longer claims "Check for updates" is at the sidebar bottom left.

## Open questions
None that block starting. Two things flagged for confirmation rather than
silently assumed, both already resolved above with reasons — raised only
in case there's a reason to prefer differently before the ux-designer/
developer pick this up:

1. **Sidebar indicator copy/styling** ("Settings · Update" vs. some other
   wording, colour choice) is deliberately left to the ux-designer per the
   dispatch — flagging only that the *mechanism* (a boolean `has_update` on
   `SettingsItem`, not a dot) is fixed by this spec, not the exact text.
2. **Keeping the 40-character truncation unchanged** (§2) is the
   recommendation; if there's a concrete reason to widen it now that
   Settings has more room, that's a one-call-site change (`_install_
   worker`'s two `[:40]` slices) and does not otherwise affect this
   spec's structure — worth raising only if it matters enough to reopen
   #19's message wording alongside it.

## Risk / rollback notes
- The riskiest new mechanism is the guarded replay in `_set_update_state`/
  `_offer_update` (§3) — if the two-step replay ordering turns out to miss
  a state combination the acceptance criteria don't cover, the safe
  fallback is the same one 3a's own spec named for its rebuild mechanism:
  simplify to "reopening Settings always shows idle 'Check for updates',
  a live check re-run if truly needed" and drop the mid-flight-state
  replay, keeping only the durable-offer (`self._pending`) replay and the
  sidebar indicator — a strictly smaller, still-correct-if-less-nice
  degradation, not a redesign.
- Everything here is contained to `afk_clicker.py` (plus the one `README.
  md` line and test files) — no schema, no persistence, nothing else in
  the codebase references `update_button`/`version_label`/`SettingsItem`
  outside what's listed under "Affected areas," so reverting is a matter
  of restoring the sidebar construction and deleting the Updates section/
  guard lines, same low-blast-radius shape as 3a's own rollback note.
- `self._pending`/`self._update_text` are both plain, non-Tk instance
  state — nothing about this spec risks corrupting `settings.json` or any
  on-disk state; worst case on a bug here is a stale or missing status
  display, never a failed update or a lost verification step.
