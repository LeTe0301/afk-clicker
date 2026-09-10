# Roadmap

Ordered by what a user notices, not by what is interesting to build. Nothing
here promises a date.

## Before 1.0.0

`1.0.0` means the UI and the on-disk settings format have stopped moving.
Until both are settled, the version stays in `0.x`.

- [ ] **Settings schema version.** `settings.json` has no version field, so a
      future format change has no migration path and would silently reset
      everyone's per-game values. **Blocks the macros tab** — see below.
- [ ] **Update integrity.** The updater downloads over HTTPS and executes the
      result. It should verify a checksum published with the release before
      swapping anything in.
- [ ] **macOS verification.** Built and smoke-tested in CI, never run by a
      human. Accessibility permission, the unsigned-app first launch and the
      hotkey listener are all unverified on real hardware.
- [ ] **Game catalogue.** Minecraft is the only profile with grounded tuning.
      Others should come from measurement or from the user via "Add current
      game" — not from plausible-sounding guesses.
- [ ] **Detection cost.** The X11 path walks the window tree every five
      seconds. Fine on a desktop, wasteful on a laptop battery.

## Next, once the schema version lands

- [ ] **A Macros tab, configurable per game** (#15). A second tab beside the
      clicker settings holding an ordered list of steps — key down, key up,
      click, wait — stored per game exactly as the clicker settings are, and
      fired by its own chord hotkey. The recorder already handles up to three
      keys with modifiers, so the trigger is solved; the sequence is not.

      It waits on the schema version deliberately. Adding a nested structure to
      `settings.json` without one turns a theoretical migration problem into
      everyone losing their macros the first time the format moves.

      Two things are settled before any of it is written. **Every key a macro
      presses is tracked and released on any exit path** — the click loop
      already releases the right mouse button in a `finally`, and a review
      round found the test covering that passed with the `finally` deleted; a
      macro holding a key when it stops is a stuck sprint or a dropped stack.
      And **macros stay deterministic**: no jitter presets aimed at looking
      human, no randomised step ordering. See what is refused below — a macro
      system is the obvious place for that rule to erode.

      Open: recording with real timings versus authoring a step list; whether a
      macro pauses the clicker the way eating does or runs alongside it, which
      would mean two threads sending input and the design has no answer for
      that yet. Blocked on macOS by the same listener abort as #7.

## Later

- [ ] Per-game hotkeys, once one global hotkey proves too coarse.
- [ ] A visible click counter and session timer.
- [ ] Import/export of a game profile, for sharing a known-good configuration.
- [ ] Linux Wayland: not solvable in-process. Would need a portal-based
      global-shortcut integration, and only on compositors that implement it.

## Explicitly not planned

- **Randomised human-like movement paths.** The point of this tool is an AFK
  farm on a private server, not defeating anti-cheat on someone else's. This
  covers the macros tab too: the interval jitter exists so the rhythm is not a
  metronome, not as evasion, and it stays where it is.
- **Anything that hides the program from the operating system.** That is the
  behaviour of malware, and it is what makes antivirus flag legitimate tools.
- **A second GUI toolkit.** See `TECHSTACK.md`.
