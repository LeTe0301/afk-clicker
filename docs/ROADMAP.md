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
- [ ] **Detection cost.** The X11 path walks the window tree every five
      seconds. Fine on a desktop, wasteful on a laptop battery.
- [ ] **A Macros tab, configurable per game** (#15). A second tab beside the
      clicker settings holding an ordered list of steps -- key down, key up,
      click, wait -- stored per game exactly as the clicker settings are, and
      fired by its own chord hotkey (the recorder already handles up to three
      keys with modifiers). Every key a macro presses is tracked and released
      on any exit path (`finally`-based, mirroring the click loop's own right-
      mouse-button release). Macros stay deterministic: no jitter presets
      aimed at looking human, no randomised step ordering -- see "Explicitly
      not planned" below. Runs once per trigger, does not pause the clicker
      (no shared-thread answer needed yet since the two never send input at
      the same instant in the current design). Recording with real timings,
      not just an authored step list, stays open for later. Blocked on macOS
      by the same unresolved listener abort as the hotkey system itself.

## Later

- [ ] Per-game hotkeys, once one global hotkey proves too coarse.
- [ ] A visible click counter and session timer.
- [ ] Import/export of a game profile, for sharing a known-good configuration.
- [ ] Linux Wayland: not solvable in-process. Would need a portal-based
      global-shortcut integration, and only on compositors that implement it.

## Explicitly not planned

- **Randomised human-like movement paths.** The point of this tool is an AFK
  farm on a private server, not defeating anti-cheat on someone else's.
- **Anything that hides the program from the operating system.** That is the
  behaviour of malware, and it is what makes antivirus flag legitimate tools.
- **A second GUI toolkit.** See `TECHSTACK.md`.
