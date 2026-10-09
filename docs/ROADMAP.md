# Roadmap

Ordered by what a user notices, not by what is interesting to build. Nothing
here promises a date.

## Before 1.0.0

`1.0.0` means the UI and the on-disk settings format have stopped moving.
Until both are settled, the version stays in `0.x`.

- [x] **Settings schema version.** `settings.json` now carries a `"version"`
      key (`SETTINGS_VERSION` in `afk_clicker.py`). A file with no version key
      at all -- every one written before this change -- is treated as version
      0; `_run_settings_migrations()` carries it forward through
      `_SETTINGS_MIGRATIONS`, one function per version, before the games-shape
      filter runs (per this bullet's own original requirement: a migration
      must see the shape it actually expects, not whatever the defensive
      corruption filter already dropped). The one migration that exists today
      (v0 -> v1) is the promoted click_ms-510-becomes-650 rewrite that used to
      run unconditionally. The `hotkey` field (PR #4) stays unversioned by
      design: an older file simply lacks the key, and an unreadable blob
      degrades to no hotkey through `Hotkey.from_json` either way, with
      nothing a version number would add. Unblocks the macros tab below.
- [x] **Update integrity.** The updater downloads over HTTPS and executes the
      result. It now verifies the archive against the release's `SHA256SUMS`
      before extracting anything, refuses a release that publishes none, and
      refuses archive entries that escape the staging directory (#3, #11).
      Digests from the same release catch a corrupt or swapped asset, not a
      compromised release — that would need signing.
- [ ] **macOS verification.** Built and smoke-tested in CI, never run by a
      human. Accessibility permission, the unsigned-app first launch and the
      hotkey listener are all unverified on real hardware.
- [ ] **Game catalogue.** Minecraft is the only profile with grounded tuning.
      Others should come from measurement or from the user via "Add current
      game" — not from plausible-sounding guesses.
- [ ] **Detection cost.** The X11 path still walks the window tree every
      five seconds -- fine on a desktop, wasteful on a laptop battery.
      **Partially addressed (G#62):** the connection-setup cost (opening
      and closing a fresh Xlib connection on every single poll) is gone --
      one connection is now reused across calls. The walk itself, and its
      5s cadence, are unchanged; a full fix (event-driven detection instead
      of polling) was considered and deliberately deferred, since it would
      depend on window-manager cooperation Xvfb doesn't provide and would
      likely be untestable in this project's own CI.
- [x] **A Macros tab, configurable per game** (#15). A third tab beside
      Hotkey/Clicking, holding an ordered list of steps -- key down, key up,
      click, wait -- stored per game exactly as the clicker settings are
      (`Store`'s per-game `"macros"` list, schema-versioned per the bullet
      above), and fired by its own chord hotkey (`Hotkey`/`HotkeyRecorder`/
      `HotkeyWatcher`, unchanged -- one extra `HotkeyWatcher` per macro
      hotkey, armed/disarmed by `_arm_macro_hotkeys()` every time `_select()`
      switches games). `MacroRunner` tracks every key it presses and
      releases all of them in a `finally` on any exit path -- stopped,
      an exception, or reaching the end -- mirroring the click loop's own
      right-mouse-button release; sabotage-verified (`MacroRunnerReleases
      HeldKeys.test_a_deleted_finally_fails_this_test`). Deterministic
      only: no jitter presets, no randomised step ordering -- see
      "Explicitly not planned" below. Runs once per trigger, refusing a
      retrigger while the same macro is still running; does not pause the
      clicker -- the two run on independent threads sending input through
      the same `pynput` controllers, with no coordination between them
      beyond that. Left genuinely open, not resolved: a macro clicking or
      holding a button while the clicker (or its own eating pause) does
      the same thing at the same instant can interleave in ways nothing
      here accounts for; revisit if that proves to matter in practice
      rather than guessing at a coordination scheme now. Recording with
      real timings, not just an authored step list, stays open for later.
      Blocked on macOS by the same unresolved listener abort as the hotkey
      system itself.

## Later

- [x] **Per-game hotkeys** (G#57). The one global toggle hotkey became an
      optional, per-game value, stored on each game's own settings entry
      (`Store.game(id)["hotkey"]`) and re-armed on every real game switch
      (`_arm_toggle_hotkey()`, mirroring macros' own `_arm_macro_hotkeys()`)
      -- never falling back across games, and deliberately not torn down
      and rebuilt on a same-game theme/scale rebuild replay (the
      `_toggle_armed_for` guard; see `HotkeyListenerSurvivesRebuild`). An
      existing single top-level hotkey is carried into every already-
      configured game by the `SETTINGS_VERSION` 2 -> 3 migration, not just
      the one selected at the time. No cross-game collision validation --
      two games can share a chord, since only the selected one is ever
      armed. A capture still in flight when the user switches games is
      dropped by a generation counter (`_capture_gen`), and Record on the
      newly-selected game works immediately rather than waiting on the old
      capture thread.
- [x] **A visible click counter and session timer.** Shown in the header
      (`self.session_stats_label`), not the Clicking pane, so it costs no
      extra pane height. Counts only the click loop's own clicks (left/
      right/middle), not a macro's -- a macro is a separate, deterministic,
      user-authored sequence. Resets on each `start()`; frozen, not reset,
      at `stop()` so the last session's totals stay visible until the next
      `start()`.
- [x] **Import/export of a game profile** (G#60). Export writes the selected
      game's full stored dict (settings + macros + hotkey) to a JSON envelope
      via a native file dialog, atomic tmp-then-replace write mirroring
      `Store.save()`. Import always creates a new custom game via the
      existing `make_profile()` path -- never overwrites -- with numeric-
      suffixed name/id collisions, validated through a shared
      `_sanitize_game_entry()` helper also used by the normal settings-load
      path. Importing preserves `eat_mode` as a key but not its value (the
      existing per-game `_select()`/`_persist()` coercion forces it to
      `"off"` for any non-eating profile) -- deliberate, not a gap.
- [ ] Linux Wayland: not solvable in-process. Would need a portal-based
      global-shortcut integration, and only on compositors that implement it.

## Explicitly not planned

- **Randomised human-like movement paths.** The point of this tool is an AFK
  farm on a private server, not defeating anti-cheat on someone else's.
- **Anything that hides the program from the operating system.** That is the
  behaviour of malware, and it is what makes antivirus flag legitimate tools.
- **A second GUI toolkit.** See `TECHSTACK.md`.
