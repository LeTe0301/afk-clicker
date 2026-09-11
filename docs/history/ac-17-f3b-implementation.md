# Implementation: Move Updates into Settings (story #17, Feature 3b)

## Summary
Relocated `self.update_button` ("Check for updates"/install action) and
`self.version_label` (the version string, doubling as status/offer/error
text) out of the sidebar footer and into a new "Updates" section on the
Settings page, below Appearance (3a). The sidebar footer is now: games list
→ "Add current game" → divider → "Settings". `SettingsItem` gained a
`has_update` flag that renders "Settings · Update" in `ACCENT` so a user who
never opens Settings still learns an update is pending. A new
`self._update_text` tuple records the most recent `_set_update_state(...)`
call; `_set_update_state`/`_offer_update` now guard every widget touch on
`self._settings_open` and are replayed by `_build_ui()`'s tail whenever a
rebuild happens with Settings open, so an in-progress "Downloading… N%" (or
any other state) survives a theme switch instead of resetting to idle.

No updater logic changed: `check_update`, `_check_worker`, `install_update`,
`_install_worker`, `_quit_for_update`, `download_and_stage`,
`fetch_checksums`, and the swap script keep their bodies verbatim — only
`_set_update_state`/`_offer_update` gained the guard/record lines the
relocation itself requires (see "Changes by file").

## Changes by file
- `afk_clicker.py`
  - `SettingsItem`: new `has_update=False` constructor kwarg and matching
    `set_state(selected=None, has_update=None)` kwarg (`None` means
    "leave unchanged", same convention `GameItem.set_state` already uses).
    `_paint()` now renders "Settings · Update" in `ACCENT` when
    `has_update` is `True` (selected or not — that's the whole point of
    the indicator), otherwise the unchanged "Settings" in `INK`/`MUTED`.
  - `AfkAutoclicker.__init__`: added `self._update_text = ("Check for
    updates", True, None)` next to `self._pending = None` — a plain
    tuple, never reset by a rebuild, holding the args of the most recent
    `_set_update_state()` call regardless of whether Settings is open.
  - `AfkAutoclicker._build_ui(s)`:
    - Sidebar footer: removed the `update_button`/`version_label`
      construction lines and the stale "3a leaves this exactly where..."
      comment; the divider's comment now describes closing off one action
      button, not two. `self.settings_item` is now constructed with
      `has_update=(self._pending is not None)`, so a rebuild that happens
      while Settings is closed (an Appearance change on a game page, with
      an offer already pending) still shows the indicator correctly.
    - Tail: the previously-unconditional `if self._pending is not None:
      self._offer_update(...)` moved inside the `if self._settings_open:`
      branch (the widgets it touches only exist there now), followed by
      `self._set_update_state(*overlay)` where `overlay` is a snapshot of
      `self._update_text` taken *before* the `_offer_update()` replay call
      — see "Key decisions" for why the snapshot is necessary and not just
      belt-and-suspenders.
  - `AfkAutoclicker._build_settings(s)`: after the existing Appearance
    section/card, added `section(body, "Updates", s)` + a `card(body, s)`
    holding a `Row(up, "Version", s)` (a `tk.Label` in `row.control`,
    Consolas mono, matching `NumBox`'s existing font choice) and
    `self.update_button = Button(up, "Check for updates", self.
    check_update, s, width=CARD_INNER_W)` — same constructor shapes as the
    sidebar version, so `check_update`/`_set_update_state`/`_offer_update`
    needed no signature changes. Only idle defaults are set here; the
    actual current state is applied by `_build_ui()`'s tail right after.
  - `AfkAutoclicker._offer_update(tag)`: now records `self._update_text =
    (f"Install {tag}", True, None)` and unconditionally calls `self.
    settings_item.set_state(has_update=True)` (no guard needed —
    `settings_item` always exists), then returns early if `not self.
    _settings_open`. The widget-touching lines below that guard are
    byte-for-byte what the method already did.
  - `AfkAutoclicker._set_update_state(text, enabled=True, colour=None)`:
    now records `self._update_text = (text, enabled, colour)` and returns
    early if `not self._settings_open`. The widget-touching lines below
    that guard are byte-for-byte what the method already did.
  - `check_update`, `_check_worker`, `install_update`, `_install_worker`,
    `_quit_for_update`: **untouched** — confirmed via `git diff main`, no
    hunk overlaps their line ranges. The `[:40]` truncation stays exactly
    where it is (`_install_worker`'s two call sites).
- `README.md:23` — "**Check for updates** unten links" (bottom left)
  replaced with "**Settings → Updates → Check for updates**", matching the
  neighbouring "Aussehen" section's own "Settings → Appearance" phrasing.
- `tests/test_updater.py:190` — stale `afk_clicker.py:1376` line-number
  comment fixed to `afk_clicker.py:2069` (the truncation's real, unchanged,
  new location — a comment-only nit, no behaviour change).
- `tests/test_ui.py`
  - `InstallWorker`'s two tests: added `self.ui._show_settings()` +
    `self.root.update()` before `self.ui._pending = (...)` so `self.ui.
    update_button` exists before `_install_worker()`/`_drain()` run. Every
    existing assertion (`_button_text()`, `.update_button._enabled`) is
    unchanged, same attribute, same real widget.
  - `test_sidebar_has_a_settings_entry_plus_the_untouched_update_widgets`
    rewritten as `test_sidebar_no_longer_holds_the_update_widgets`: asserts
    exactly one `app.Button` and no extra `tk.Label` (beyond
    `count_label`) sit directly in `self.ui.side`, that `update_button`/
    `version_label` don't exist as attributes until Settings is opened,
    and that a fresh app's `settings_item.has_update` is `False`.
  - New `SettingsUpdates(UITestCase)` class:
    - `test_settings_page_builds_the_updates_section` — AC2: `update_button`/
      `version_label` exist as real `Button`/`tk.Label` after
      `_show_settings()`, default text "Check for updates".
    - `test_every_update_state_renders_on_the_settings_page` — AC3, a
      non-regression sweep driving `_set_update_state`/`_offer_update`
      directly with every real string `check_update`/`_check_worker`/
      `install_update`/`_install_worker` can produce (checking, no
      releases, up to date, GitHub unreachable, no build for this OS, both
      real truncated checksum messages, read-only folder, a generic
      install failure, the non-frozen "not a build" state, an offer, three
      download percentages, and restarting), asserting button text/
      enabled/fill and version-label text/colour for each.
    - `test_an_offer_marks_the_settings_row_while_a_game_page_is_open` —
      AC4: `_offer_update()` called with Settings never opened this
      session sets `settings_item.has_update` without raising, and the
      flag survives an Appearance rebuild and a game switch; opening
      Settings afterward replays the offer without a second check.
    - `test_downloading_state_survives_a_rebuild_with_settings_open` — AC6:
      a progress tick delivered from a real background thread via
      `self.ui._ui(...)` and drained with `_drain_ui()`, then a rebuild
      (`_apply_appearance`) — the **new** `update_button` shows
      "Downloading… 42%", disabled, not "Install v{tag}", and `self.ui.
      _pending`/`self.ui._update_text` are unchanged by the rebuild.
    - `test_set_update_state_with_settings_closed_does_not_raise` — AC (the
      §3 hazard): calling `_set_update_state` with Settings never opened
      doesn't raise, records `self._update_text`, and the text shows once
      Settings is opened.
  - `CapturesCallbackExceptions` stayed empty in every run (verified — see
    "How to verify locally").

## Key decisions / tradeoffs
- **Snapshot `self._update_text` before replaying `_offer_update()` in the
  tail (`_build_ui`, not `_offer_update` itself).** The spec's own §3
  pseudocode calls `_offer_update()` first, then `self._set_update_state
  (*self._update_text)`, reasoning that this reproduces "offer styling,
  then the latest text, overlaid." But `_offer_update()` itself
  unconditionally sets `self._update_text = (f"Install {tag}", True,
  None)` as its own first line (needed so a *live* offer — no rebuild
  involved — is correctly the newest state). Calling it during the tail's
  replay therefore clobbers whatever `self._update_text` held *before* the
  rebuild (e.g. `("Downloading… 45%", False, None)`) with the offer's own
  text, and the following `self._set_update_state(*self._update_text)`
  then reads that just-clobbered value — silently reverting a mid-download
  rebuild to "Install v{tag}" instead of preserving "Downloading… 45%".
  This was caught by
  `test_downloading_state_survives_a_rebuild_with_settings_open`, which
  failed against the literal spec pseudocode (manually reproduced with a
  throwaway script outside the repo before touching any code — see
  "Deviations from spec" below). The fix is a one-line local capture
  (`overlay = self._update_text`, taken before the `_offer_update()`
  replay call) so the final `_set_update_state(*overlay)` line applies the
  pre-rebuild state, not the offer-replay's own side effect. This changes
  nothing about `_offer_update`'s own body or its live-call behaviour —
  only the tail's local variable use.
- **Version label uses `Consolas`, no explicit cross-platform fallback
  code.** `design.md`'s Platform notes mention a `TkFixedFont` fallback on
  macOS/Linux, but no existing widget in this file (including `NumBox`,
  which already uses `("Consolas", ...)` directly for its numeric entries)
  implements that fallback in code — Tk substitutes a default font
  automatically when the named family is unavailable. Matched the existing
  convention rather than introducing a new fallback pattern for one label.
- **Button width `CARD_INNER_W`, no explicit padding math.** Mirrors the
  existing full-width-in-card pattern (`Segmented(self.eat_card_inner,
  ..., self.eat_mode, s)`, which also defaults to `width=CARD_INNER_W` and
  is packed directly into a card's inner frame, not inside a `Row`) rather
  than inventing new sizing.
- **Sidebar `SettingsItem._paint()` colours `ACCENT` whenever `has_update`
  is `True`, selected or not.** The orchestrator recomputed the design's
  contrast numbers with WCAG and found all four pairs pass comfortably
  (Deepslate: ACCENT/CARD_HI 5.45, ACCENT/CARD 6.25; Quartz: ACCENT/CARD_HI
  5.55, ACCENT/CARD 6.23) — no darkening of any colour was needed, and none
  is done here.

## Deviations from spec
- **The tail's replay order needed a local snapshot, not the spec's literal
  two-line pseudocode.** See "Key decisions" above for the full mechanism.
  The *behaviour* implemented matches the spec's own prose exactly (the
  "Mid-download" bullet under "Why replaying both, in this order, is
  correct — not redundant" describes precisely the end state this fix
  produces); only the literal code differs from the spec's inline snippet,
  because that snippet's ordering silently breaks its own stated guarantee
  (`_offer_update()` overwrites the very tuple the following line reads).
  Confirmed by writing the acceptance-criteria test first, watching it
  fail against the spec's literal pseudocode, then fixing the tail.
- **`design.md`'s State-coverage table's "Version label text" column is
  inaccurate for `GitHub unreachable`/`No build for OS`.** The table lists
  both as showing `"v{version}"` in the label while colour is `BAD`, but
  `_set_update_state`'s real, unchanged body is `self.version_label.config
  (text=text, fg=colour)` — whenever a colour is passed, the label's text
  becomes the *button's own status text*, not the bare version string
  (this is pre-existing sidebar behaviour, untouched by this spec, not a
  layout choice 3b introduces). Implemented and tested against the real,
  unchanged code path (`test_every_update_state_renders_on_the_settings_
  page`), not the design table's inaccurate placeholder — hard requirement
  1 (no updater logic changes) forecloses "fixing" `_set_update_state` to
  match the table instead.
- Did not darken `BAD` anywhere, per the orchestrator's corrected contrast
  numbers (all four pairs pass WCAG AA as-is) — `design.md`'s own
  "Deepslate BAD on CARD is at 4.30:1... darken if needed" caveat does not
  apply once measured correctly (recomputed: BAD/CARD is 5.22 on Deepslate,
  5.11 on Quartz). No contrast numbers were placed in any code comment.

## Known limitations
- No automatic update check exists (confirmed unchanged — `check_update`'s
  only caller remains the Settings page button's own `command=`); this was
  explicitly out of scope per the spec's non-goals.
- The mid-download-rebuild replay (both this feature's guard and 3a's own
  rebuild coalescing) is exercised here with a real background thread
  (`threading.Thread` + `self.ui._ui(...)` + `_drain_ui()`), not through
  the actual `download_and_stage(on_progress=...)` callback chain end to
  end — that chain itself is untouched updater logic already covered by
  `tests/test_updater.py` and `InstallWorker`'s existing tests; this
  feature's own tests isolate the UI-relocation concern instead of
  re-testing the download path.

## How to verify locally
```
DISPLAY=:99 <path-to-venv>/bin/python -m unittest discover -s tests -t .
```
221 tests, OK, 5 skipped (up from the 3a baseline of 216 OK/5 skipped: one
sidebar test rewritten in place, five new tests added in `SettingsUpdates`).

Probes re-run from the scratchpad used during this session (all pre-existing,
not part of this diff):
- `probe1_running_rapid.py`, `probe3_misc.py`, `probe4_break_coalescing.py`,
  `probe5_reentrant_card.py` — all still PASS unmodified.
- `probe2_queued_callbacks.py` — fails at `ui.update_button` on an
  unopened-Settings fresh app; this is the probe's own 3a-era premise (an
  unconditional sidebar `update_button`) being invalidated by exactly what
  this spec intentionally changes, the same category as the sidebar test
  that needed rewriting. Re-verified the probe's actual concern (a stale
  bound-method closure mixed into a post-rebuild queue drains without
  killing `_drain_ui`, and a real `on_close()` prints no `TclError`) still
  holds by running a scratch-only copy with one line added
  (`ui._show_settings(); root.update()` before capturing the old widget
  references) — PROBE2 parts A and B both PASS. That scratch copy was not
  left in the scratchpad or the worktree.

Screenshots (scratchpad only, `Store(<scratchpad tempdir>)`, `import
-window ... -crop`, nothing written to `~/.config` or the worktree):
- `f3b-settings-dark.png` — Settings page, Dark, idle: Appearance card
  unchanged, new Updates card below it with "Version v0.3.1" and "Check for
  updates".
- `f3b-offer-light.png` — Quartz (light), Minecraft's game page open, an
  offer driven via `ui._pending = (...)` + `ui._offer_update("v0.3.2")`:
  sidebar shows "Settings · Update" in ACCENT, `update_button`/
  `version_label` untouched (don't exist yet).
- `f3b-downloading-dark.png` — Settings page, Dark, an offer followed by
  `_set_update_state("Downloading… 42%", False)`: button disabled reading
  "Downloading… 42%", version label "v0.3.1 → v0.3.2" in ACCENT, sidebar
  "Settings · Update" indicator visible (selected, on CARD_HI).

## Updater functions — confirmed unchanged
`git diff main -- afk_clicker.py` hunks touch only: `SettingsItem`,
`AfkAutoclicker.__init__` (one new state line), `_build_ui` (sidebar footer
+ tail), `_build_settings` (docstring + new Updates section), `_offer_update`
(guard/record lines added, existing lines untouched), `_set_update_state`
(guard/record lines added, existing lines untouched). No hunk overlaps
`check_update`, `_check_worker`, `install_update`, `_install_worker`,
`_quit_for_update`, `download_and_stage`, `fetch_checksums`, or the swap
script — their bodies are byte-for-byte what they were on `main`.
