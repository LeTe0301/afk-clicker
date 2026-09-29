# Spec: UI scale follows the window size (G#38 / GH#67)

> **Reconstruction note (2026-09-29, GH#93/G#51):** This project's convention
> is a per-cycle scratch file at `docs/spec.md`, written before the
> corresponding code, archived here under `docs/history/ac-NN-spec.md` as the
> last step once the PR merges (see e.g. `ac-37-spec.md`). For this ticket
> that archive step was never done: the 2026-09-18 session handoff (see
> `backlog.md`) left `docs/spec.md`/`design.md`/`implementation.md`/
> `test-review.md` sitting **uncommitted** in that session's local working
> tree, "to archive... as the last step once the PR merges, same as every
> prior cycle" — but the session that eventually merged PR #89 did not carry
> those files over, and the ephemeral container they lived in is gone. The
> original pre-implementation text (including the stale DPI-*absolute* clamp
> description GH#93 reported) is not recoverable. What follows is a
> **reconstruction from the shipped code and tests**, describing what `main`
> actually does today — correct as of PR #89 (`e881e40`) plus its round-4
> follow-up (PR #92, `8ea76a8`) — not a recovered original. `design.md`,
> `implementation.md`, and `test-review.md` for this ticket remain lost; only
> this file is being reconstructed, since GH#93 is specifically about §2's
> clamp description and several shipped code comments (`afk_clicker.py`)
> cite "docs/spec.md §2" and "docs/spec.md 'The debounce decision'" by name.

## Summary
Auto is a new UI-scale mode (`ui_scale = "auto"`, now the default for new
installs) that derives `self.s` continuously from the window's own pixel
dimensions, instead of snapping to one of the four fixed steps (90/100/115/
130%). It reuses the fixed steps' existing scale-dependent layout throughout
the app unchanged — only how `self.s` is *computed* changes.

## §2: Computing Auto's scale factor

`AfkAutoclicker._auto_scale_factor(width, height)` (`afk_clicker.py:3018`):

1. Computes an area-based fill fraction against the display,
   square-rooted so it scales roughly linearly with window size the way the
   fixed percentage steps do: `fill = sqrt((width * height) / (screen_w *
   screen_h))`.
2. Divides by `AUTO_REFERENCE_FILL` (a calibration constant) so a typical
   desktop window lands at parity with today's fixed "100%" step.
3. **Clamps the result to `self._dpi_s * [AUTO_SCALE_MIN, AUTO_SCALE_MAX]`
   — a DPI-*relative* range, not the raw `[AUTO_SCALE_MIN, AUTO_SCALE_MAX] =
   [0.9, 1.3]` literals.** This is the same DPI-relative range every fixed
   step's own `self.s` already covers (`self._dpi_s *
   UI_SCALE_FACTORS[value]`), and is what prevents a shrink/grow feedback
   runaway.

`width`/`height` are real window pixel dimensions, which already carry
`self._dpi_s` baked in (the window's own geometry is always sized off
`self.s`, itself `self._dpi_s * something`) — so the raw fill/
`AUTO_REFERENCE_FILL` ratio already lands close to `self._dpi_s` for a
window at its "100%-equivalent" fill, with no separate multiplication
needed before the clamp.

**Why DPI-relative, not DPI-absolute (round 4, PR #89 review, Defect 1):**
an earlier version of this fix clamped to the raw `[AUTO_SCALE_MIN,
AUTO_SCALE_MAX]` literals. On a real low-DPI display (`self._dpi_s < 0.9` —
an ordinary non-Retina headless-VM value, not just a CI artifact, measured
around `~0.75` on macOS CI), that pinned Auto's `self.s` at the raw `0.9`
floor: unreachable-below, and *larger* than even the fixed "100%" step
would give on the same hardware. A tempting-looking alternative — clamp the
raw ratio to the plain `[MIN, MAX]` range and *then* multiply by
`self._dpi_s` — was considered and rejected: it double-counts
`self._dpi_s`, since it is already embedded in `width`/`height`. Verified
concretely against the macOS CI repro values before shipping the
`self._dpi_s * [AUTO_SCALE_MIN, AUTO_SCALE_MAX]` form. Covered by
`tests.test_ui.UIScaleAuto.test_auto_is_not_floored_at_the_raw_clamp_on_a_low_dpi_display`.

## The debounce decision

Auto mode arms a real-time (not `after_idle`) 150ms settle timer
(`AUTO_SETTLE_MS`, `_request_auto_settle()`/`_on_auto_settle()`) on a live
window resize, deliberately **not** reusing `_request_rebuild()`'s
`after_idle` coalescing: `after_idle` fires the next time Tk's event loop is
idle, which during a live OS-level drag is typically between every single
native resize callback, not after the drag as a whole settles. The timer
uses the same single-slot cancel-or-schedule shape as
`_rebuild_after_id`/`_pane_fill_after_id` (`_auto_settle_after_id`), and is
cancelled the same way in `on_close()`. Once the timer fires,
`_on_auto_settle()` hands off into the existing coalesced-rebuild machinery
unchanged — this mechanism only changes *when* a rebuild gets requested,
never *how* it's run.

The settle-arm itself is gated on the window's `<Configure>` event reporting
the app's own already-known bootstrap geometry echoed back unchanged
(content, not order — a real window manager's post-map `<Configure>`, which
Xvfb never sends, would otherwise arm a live settle timer mid-test on every
`UITestCase`).

## Acceptance criteria (§2, corrected)
- [x] Given a window at any size, when Auto mode computes its scale factor,
      then the result is clamped to `self._dpi_s * [AUTO_SCALE_MIN,
      AUTO_SCALE_MAX]` — **not** the raw `[AUTO_SCALE_MIN, AUTO_SCALE_MAX] =
      [0.9, 1.3]` literals — so the clamp's bounds move with the display's
      own DPI scaling exactly as every fixed step's bounds already do.
- [x] Given a real low-DPI display (`self._dpi_s < 0.9`), when Auto computes
      its factor, then the result is **not** floored at the raw `0.9`
      literal, and can land below it, matching what the fixed "100%" step
      would give on the same hardware.
- [x] Given a live window resize, then a rebuild is requested only after the
      configured settle window, not on every intermediate `<Configure>`
      event, via `_auto_settle_after_id`'s cancel-or-schedule timer.

## Related
- `README.md`'s "Aussehen" section (GH#91/G#50) documents Auto's 90–130%
  clamp for end users.
- `tests/test_ui.py`'s `UIScaleAuto` class covers this behavior, including
  the sabotage-verified regression test for the DPI-relative clamp
  (`test_a_genuinely_out_of_range_factor_clamps_to_the_scale_bound`, added
  under G#49/GH#90) and the settle-timer debounce tests (rewritten under
  G#52/GH#94, see `ac-38-spec.md`'s reconstruction note above for why this
  file exists at all).
