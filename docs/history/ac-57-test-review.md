# Test & Review: Per-game hotkeys (G#57)

## Scope
Tests and reviews the full diff against `docs/spec.md`'s acceptance criteria and
`docs/design.md`'s three named deviations: `afk_clicker.py` (storage migration,
per-game arm/disarm lifecycle, capture-generation guard, the `Store.put_game()`
merge fix) and `tests/test_ui.py` (13 new tests + 3 rewritten). Environment:
`Xvfb :99` + `/home/dev/.venvs/afk-clicker-test` (pynput + tkinter), this
repo's own documented convention.

## Test cases

| # | Criterion / case (docs/spec.md) | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Fresh store: `version==3`, no top-level `"hotkey"` | Automated | pass | `SettingsSchemaVersion.test_a_fresh_store_is_at_the_current_version` (pre-existing, reads `app.SETTINGS_VERSION`, now 3); structurally guaranteed — `Store.__init__`'s default dict no longer has a `"hotkey"` key (`afk_clicker.py:1696`) |
| 2 | v2, one game: chord carried over, still armed when selected | Automated | pass | `SettingsSchemaVersion.test_v2_hotkey_is_carried_into_the_one_configured_game` (storage); arming-after-restore exercised by `HotkeyPersistence.test_restored_and_armed_after_restart` (same mechanism, current-version data) |
| 3 | v2, several games: every game gets the chord | Automated | pass | `test_v2_hotkey_is_carried_into_every_configured_game` (3 games incl. a `custom:` id) |
| 4 | v2, `games` empty/absent: no crash | Automated + manual | pass | `test_v2_hotkey_with_no_games_configured_does_not_crash` (empty dict); absent-key case has no dedicated test, so I checked it by hand (see Findings #3) — confirmed no crash, `version==3`, `games=={}` |
| 5 | Corrupt per-game `"hotkey"` blob, one game only | Automated | pass | `test_a_corrupt_hotkey_blob_is_dropped_for_that_game_only` |
| 6 | Game A's chord doesn't fire while B selected; B shows "Not set" | Automated | pass | `PerGameHotkeys.test_a_game_with_no_hotkey_shows_not_set_after_switching_from_one_that_has` |
| 7 | Each game's own chord toggles only while selected (both directions) | Automated | pass | `PerGameHotkeys.test_each_games_own_hotkey_is_armed_only_while_selected` |
| 8 | Same chord on two games: no rejection, selected one toggles | Automated | pass | `PerGameHotkeys.test_same_chord_on_two_games_is_accepted_without_error` |
| 9 | Record on A, switch to B before release: capture discarded | Automated | pass | `test_a_stale_capture_result_is_dropped_after_a_real_game_switch` + the A→B→A case `test_a_stale_capture_result_is_still_dropped_after_switching_back` |
| 10 | Theme rebuild keeps `hk_listener` identity (same game) | Automated | pass | `HotkeyListenerSurvivesRebuild.test_listener_object_identity_is_unchanged_across_a_rebuild` — unmodified, re-ran it directly, green |
| 11 | `on_close()` stops the listener cleanly | Automated (indirect) | pass | No dedicated assertion exists for this pre-existing behavior (the code at `afk_clicker.py:5862` area is untouched by this diff); exercised incidentally by every test that calls `on_close()`/`restart()` with a listener armed (e.g. `test_restored_and_armed_after_restart`) without hanging or erroring. Pre-existing gap, not introduced here — see Findings #4 |
| 12 | No permission: no listener, `registered_hotkey` None, candidate survives | Automated | pass | `HotkeyPersistence.test_no_listener_is_started_without_permission`, `test_registered_hotkey_cleared_on_second_apply_without_permission` (unchanged, still green); switch-time equivalent at `PerGameHotkeys.test_arm_failure_on_switch_shows_help_text_and_enables_apply_for_retry` |
| 13 | Exercisable under Xvfb/CI | Automated | pass | Whole suite run under Xvfb this session (below) |
| 14 | `register_hotkey()` on new game not blocked by old game's capture (design dev. #2) | Automated | pass | `test_register_hotkey_on_a_new_game_is_not_blocked_by_the_old_games_capture` |
| 15 | Switching games discards an unapplied recorded candidate | Automated | pass | `test_switching_games_discards_an_unapplied_recorded_candidate` |
| 16 | `Store.put_game()` wholesale-replace bug (developer's flagged deviation) | Automated + manual revert | pass | See "Deviation verification" below |

## Deviation verification: `Store.put_game()` merge fix

Independently reproduced, root-caused, and verified — not taken on the developer's word.

1. **Reproduced the pre-fix bug directly.** Stashed the full diff, wrote a
   throwaway repro (`Store.game(id)["macros"] = [...]` then `ui._persist()`):
   `macros` went from `[{'fake': 'macro'}]` to `None` on disk after one
   unconditional `_persist()` call — confirms the bug is real and exactly as
   described, independent of this ticket.
2. **Reproduced the ticket's own named failure mode.** Same technique with a
   hotkey: `apply_hotkey()` then `on_close()` (which unconditionally calls
   `_persist()`, `afk_clicker.py:5952`) wiped the just-applied hotkey from
   disk on the pre-fix code, confirming deviation item 1's claim that this
   bug directly blocks G#57's own "Record → Apply → close" acceptance
   criterion, not just the pre-existing macros feature.
3. **Confirmed the fix resolves both**, on the real working tree, with the
   developer's actual diff restored.
4. **Checked every call site.** `put_game()` has exactly one caller in the
   whole codebase: `_persist()` (`afk_clicker.py:4440`), which only ever
   builds `values` from Clicking-tab fields (`click_ms`, `jitter_ms`, ...,
   optionally `_profile`). Nothing relies on `put_game()` clearing keys it
   doesn't itself manage — a non-custom game never had `_profile`, and a
   custom game's `"custom": True` (set once, in-memory, at creation;
   `afk_clicker.py:1863`) never toggles off, so `_profile` is written on
   every `_persist()` for that game id regardless of merge vs. replace. The
   only two tests calling `put_game()` directly
   (`test_put_game_returns_saves_own_result` et al., `tests/test_ui.py:576-588`)
   assert the boolean return value only, confirmed by reading them — the
   developer's claim here is accurate.
5. **Found an existing regression tripwire the developer didn't name.**
   Copied `afk_clicker.py` + `tests/` to an isolated scratch directory,
   reverted just the one-line fix there, and reran
   `HotkeyPersistence.test_restored_and_armed_after_restart` (pre-existing,
   unmodified) — it **fails** on the reverted code
   (`AssertionError: unexpectedly None` on `ui.registered_hotkey`), because
   that test's `restart()` helper calls `on_close()` → `_persist()` →
   `put_game()` on a game with an already-applied hotkey, the identical code
   path the macros bug uses. So "every fix lands with a test that fails
   without it" (`docs/CODING-GUIDELINES.md`) is actually satisfied — just not
   by a new test, and not by a macros-specific one. See Findings #1 for the
   gap that remains.

## Regression check

Full suite as run in this session (not just the developer's quoted numbers):

```
Xvfb :99 -screen 0 1280x1024x24 &
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest tests.test_ui
Ran 404 tests in 96.988s
OK
```

Confirmed against a stashed baseline (pre-diff): `Ran 391 tests ... OK` — so
404 = 391 pre-existing + 13 new, matching the developer's claim exactly (not
just trusted).

Also ran the **full discover**, matching `.github/workflows/ci.yml`'s actual
command exactly (the developer's own verification only ran `test_ui`, not
`test_hotkey.py`/`test_updater.py`):

```
DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .
Ran 526 tests in 99.050s
OK (skipped=10)
```

10 skips are the documented platform-only guards (macOS Accessibility,
Windows-only paths), expected on this Linux runner. No failures, no errors.

## Spec coverage

All acceptance criteria in `docs/spec.md` are implemented and tested — see the
test-case table above. Two minor gaps noted, neither blocking (see Findings).

## Findings (most severe first)

### 1. No test exercises the `put_game()` merge fix via the macros path specifically — should-fix
- File: `afk_clicker.py:1799` (`Store.put_game`)
- Issue: the fix is real, correct, and demonstrably covered by an existing
  test (`test_restored_and_armed_after_restart`, verified above by reverting
  the fix and watching it fail) — but only via the hotkey path. No test
  calls `_persist()` after a macro save the way `MacrosTab.test_save_macro_persists_and_arms_its_hotkey`
  does, then asserts the macro survives a *second*, unrelated `_persist()`
  call (switching tabs, `on_close()`, or editing a Clicking field). I
  confirmed by running `StoreMacroFiltering`/`MacrosTab` against the
  reverted fix: all 13 tests still pass, i.e. the macros side of this bug
  has zero direct regression coverage today.
- Failure scenario: a future change to `put_game()` that preserves the
  hotkey-survives-restart property (e.g. by special-casing `"hotkey"`) but
  reintroduces wholesale-replace for everything else would pass the full
  suite today and silently wipe macros again on the next persist.
- Calibration: this is a judgement call, not a hard rule violation — the
  shared function has one piece of real coverage, and macros/hotkey go
  through the identical `dict.update()` with no key-specific branching, so
  the risk is theoretical rather than a concrete gap in *this* diff's own
  acceptance criteria. Reasonable to take as a fast follow-up rather than a
  blocker on this ticket, which is scoped to hotkeys.

### 2. Subtitle wording accuracy and layout estimate not re-verified on a real Windows render — should-fix (pre-existing caveat, carried forward honestly)
- File: `afk_clicker.py:3676`, `docs/design.md`'s "Layout verification"
- Issue: both `docs/design.md` and `docs/implementation.md` already flag
  this themselves (metric estimate on a Linux sandbox without Segoe UI) —
  not a new gap I'm introducing, just confirming it's accurately disclosed
  rather than quietly assumed solved. I did not attempt to re-derive the
  font metrics myself since no Windows renderer is available here; the
  estimate's margin (44% headroom, old string wider than the new one) makes
  a real regression unlikely, so this is correctly scoped as a follow-up,
  not a blocker.

### 3. `data["games"]` entirely absent during v2→v3 migration has no dedicated test — nit
- File: `afk_clicker.py:1639` (`_migrate_settings_v2_to_v3`)
- Issue: only the empty-dict `games` case is tested
  (`test_v2_hotkey_with_no_games_configured_does_not_crash`); the
  key-entirely-missing case is handled by the same `isinstance(games, dict)`
  guard but untested directly in the suite.
- Verified by hand (not inferred): wrote a one-off script loading
  `{"version": 2, "hotkey": {...}}` with no `"games"` key at all through the
  real `Store` — result: `version == 3`, `games == {}`, no exception. Safe,
  just untested. Nit — the guard is identical to the already-tested branch
  and the code path is a two-line `isinstance` check with no new logic.

### 4. "`on_close()` stops the listener cleanly" (spec AC) has no dedicated assertion — nit
- File: `afk_clicker.py:5952` area (unchanged by this diff)
- Issue: `docs/spec.md` itself calls this "existing on_close coverage,
  unaffected by the per-game change" — but no test in the suite, before or
  after this diff, asserts `hk_listener.stop()` was actually called /
  `hk_listener is None` purely as a result of `on_close()`. It's exercised
  incidentally (every restart-based test calls `on_close()` without
  hanging), which is weak but non-regressing evidence. Pre-existing gap,
  not introduced by G#57 — flagging for visibility only, per the spec's own
  framing of this AC as "unaffected," which I independently confirmed by
  grepping: `on_close()`'s hotkey-stopping line is byte-identical before and
  after this diff.

## Follow-ups (non-blocking)
- A macros-specific `_persist()`-survives-a-second-save regression test
  (Finding #1) — cheap, same technique already proven for hotkeys in this
  same test file.
- Confirm the new subtitle string's width on an actual Windows render at
  some point (Finding #2) — carried-forward caveat, not new to this cycle.

## Overall verdict
**Approve, with follow-ups.** All acceptance criteria in `docs/spec.md` are
implemented, match `docs/design.md`'s three named (and pre-approved)
deviations exactly as I traced line-by-line against the diff, and are
covered by tests I ran myself under Xvfb (404/404 in `test_ui`, 526/526 in
the full `discover` matching CI's own command, both green; baseline
confirmed at 391 via `git stash`). The developer's reported numbers check
out exactly. The flagged `Store.put_game()` deviation is a correct,
necessary, minimally-scoped root-cause fix with exactly one call site — I
reproduced the pre-fix bug twice (once for macros, once for the ticket's own
hotkey criterion), confirmed the fix resolves both, and found that an
existing unmodified test already regression-tests it via the hotkey path
(verified by reverting the fix and watching that specific test fail). No
must-fix findings. The two should-fix items (macros-specific test gap, the
carried-forward Windows-render caveat) are reasonable to take as follow-ups
rather than blockers on this ticket's own scope.
