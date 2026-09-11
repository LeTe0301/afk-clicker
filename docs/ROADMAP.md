# Roadmap

Ordered by what a user notices, not by what is interesting to build. Nothing
here promises a date.

## Before 1.0.0

`1.0.0` means the UI and the on-disk settings format have stopped moving.
Until both are settled, the version stays in `0.x`.

- [ ] **Settings schema version.** `settings.json` has no version field, so a
      future format change has no migration path and would silently reset
      everyone's per-game values.
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
