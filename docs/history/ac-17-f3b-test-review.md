# Test & Review: Move Updates into Settings (story #17, Feature 3b)

## Scope
Everything in `docs/spec.md`'s acceptance criteria for 3b: the sidebar losing
`update_button`/`version_label`, the new Settings-page Updates section, the
`self._update_text` rebuild-replay mechanism, the guarded
`_set_update_state`/`_offer_update`, and the `SettingsItem.has_update`
off-screen sidebar signal. Reviewed against `git diff main` in
`/home/dev/projects/.worktrees/afk-clicker/ac-17` (uncommitted, branch at
`main` 5ba6b9d). Tree left exactly as found — nothing committed, nothing
fixed by this pass.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Sidebar footer: only "Add current game", divider, Settings entry; no `update_button`/`version_label` children | Automated | pass | `tests/test_ui.py::SettingsNavigation::test_sidebar_no_longer_holds_the_update_widgets` |
| 2 | `_show_settings()` builds real `update_button`/`version_label`, below Appearance, default "Check for updates" | Automated + manual (screenshot) | pass | `tests/test_ui.py::SettingsUpdates::test_settings_page_builds_the_updates_section`; `f3b-settings-dark.png` |
| 3 | Every update state (checking, no releases, unreachable, up-to-date, no-build, offer, downloading, checksum errors, read-only, generic error, not-a-build, restarting) renders identically to today when Settings open | Automated | pass | `SettingsUpdates::test_every_update_state_renders_on_the_settings_page`; also exercised via a real thread in reviewer's own `WholeJourney` probe |
| 4 | Offer signalled on Settings row while Settings never opened this session, no exception | Automated | pass | `SettingsUpdates::test_an_offer_marks_the_settings_row_while_a_game_page_is_open`; reviewer's `WholeJourney` step 1 |
| 5 | Offer pending, Settings closed, then opened → shows offer without a second `check_update()` | Automated | pass | `SettingsUpdates::test_an_offer_marks_...` (tail assertions); reviewer's `WholeJourney` step 3 |
| 6 | Offer + mid-download, rebuild while Settings open → new button shows "Downloading… N%", not "Install v{tag}"; `_pending` unchanged | Automated + regression-by-reversion | pass | `SettingsUpdates::test_downloading_state_survives_a_rebuild_with_settings_open`; **reverted the `overlay = self._update_text` snapshot fix in a scratch copy and watched this exact test fail** (`'Install v9.9.9' != 'Downloading… 42%'`), then restored |
| 7 | Checksum/generic install error truncated to 40 chars, retains "checksum" (checksum cases), button re-enabled | Automated | pass | `InstallWorker`'s two tests (now via `_show_settings()` first) + `test_every_update_state_renders_on_the_settings_page`'s coloured-state sweep |
| 8 | Hotkey card unchanged, still only on game pages | Regression (unchanged code path, full suite) | pass | `_build_content` has zero diff hunks; full suite green |
| 9 | `count_label`/`self.ui.items` unaffected | Regression | pass | `SettingsNavigation::test_games_count_excludes_the_settings_entry` (unchanged, still passes) |
| 10 | `README.md:23` no longer claims sidebar-bottom-left | Manual read | pass | `README.md:23` now reads "**Settings → Updates → Check for updates**", matching the established "Settings → Appearance" phrasing at `README.md:86` |
| 11 | Whole journey: check→offer (Settings closed)→game switch→open Settings→theme switch→install→close Settings mid-download→reopen→Restarting, via real `_check_worker`/`_install_worker` threads, network faked | Automated (reviewer-authored, real threads) | pass | scratchpad `reviewer_3b_test.py::WholeJourney::test_journey`; `CapturesCallbackExceptions` empty (test passed under `UITestCase.tearDown`'s own assertion) |
| 12 | Settings-row mark: stays set after a checksum error (per spec, `_pending` untouched by a retry-able failure) | Automated (reviewer-authored) | pass | `reviewer_3b_test.py::SettingsMarkEdgeCases::test_mark_stays_after_a_checksum_error` |
| 13 | Settings-row mark: does **not** clear on a fresh "up to date" result (current, unchanged code never clears it) | Automated (reviewer-authored) | pass (documents a real, spec-sanctioned quirk — see Findings) | `reviewer_3b_test.py::SettingsMarkEdgeCases::test_mark_does_not_clear_on_a_fresh_up_to_date_result` |
| 14 | Button's click binding after a rebuild — `check_update` vs `install_update`, no stale `command` from build time | Automated (reviewer-authored) | pass | `reviewer_3b_test.py::ButtonBindingAfterRebuild` (both cases) |
| 15 | `_settings_open` guard in `_set_update_state` actually prevents the `AttributeError` it claims to | Regression-by-reversion | pass | reverted the guard in a scratch copy, watched `test_set_update_state_with_settings_closed_does_not_raise` die with `AttributeError: 'AfkAutoclicker' object has no attribute 'update_button'` at the exact guarded line, then restored |
| 16 | 40-char checksum/verification message budget still leads with meaning at the new location | Manual (source read + existing test) | pass | `afk_clicker.py:706-711` unchanged (0 diff hunks in that range); truncation applied only at `_install_worker`'s two `[:40]` call sites, also unchanged |
| 17 | `probe2_queued_callbacks.py` failure is solely the 3a-era "unconditional `update_button`" premise | Manual (ran probe, then ran a one-line scratch variant) | pass | see Defect-check note below |
| 18 | Updater functions (`check_update`/`_check_worker`/`install_update`/`_install_worker`/`_quit_for_update`/`download_and_stage`/`fetch_checksums`/swap script) have zero logic changes | Manual (`git diff main` hunk audit) | pass | `git diff main -- afk_clicker.py` hunk list touches only `SettingsItem`, `__init__`, `_build_ui`, `_build_settings`, `_offer_update`, `_set_update_state` — no hunk overlaps line ranges 593-660 (`fetch_checksums`/`download_and_stage`) or 2008-2094 (`check_update`…`_quit_for_update`) |
| 19 | WCAG contrast of the code's actual (unchanged) hex values for every pair the diff relies on | Manual (independent sRGB-linearised recomputation from `afk_clicker.py:78-83`'s literal hex) | pass | see "Contrast verification" below — all four figures match the orchestrator-supplied ground truth to 2 decimal places |

**`probe2_queued_callbacks.py` failure — confirmed cause.** Ran it unmodified:
```
AttributeError: 'AfkAutoclicker' object has no attribute 'update_button'
```
at its own line 28 (`old_update_button = ui.update_button`), immediately after
constructing a fresh `AfkAutoclicker` with Settings never opened — exactly
3b's intended change (the widget no longer exists until Settings opens). Made
a scratch-only copy (`probe2_reviewer_check.py`, not left in the scratchpad or
worktree) adding `ui._show_settings(); root.update()` before that line; both
of the probe's real concerns — a mixed queue with one stale-bound closure
draining without killing `_drain_ui`, and a genuine close printing no
`TclError` — still PASS. Confirms the failure is solely the probe's own
invalidated premise, not a regression.

## Regression check
Full suite: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .`
→ **221 tests, OK, 5 skipped** (matches the developer's report). Also re-ran
`probe1_running_rapid.py`, `probe3_misc.py`, `probe4_break_coalescing.py`,
`probe5_reentrant_card.py` unmodified — all still PASS.

## Contrast verification (independent, from literal hex in `afk_clicker.py:78-83`)
sRGB-linearised WCAG relative luminance, computed by hand from `THEMES["dark"]`/`THEMES["light"]`, not from any doc's stated numbers:

| Pair | Deepslate | Quartz |
|---|---|---|
| ACCENT / CARD_HI (selected + has_update) | 5.45:1 | 5.55:1 |
| BAD / CARD (error version_label) | 5.22:1 | 5.11:1 |
| ACCENT / BG (unselected + has_update) | 6.79:1 | 5.21:1 |

All four match the orchestrator-supplied ground truth to two decimal places
and all clear 4.5:1 AA text contrast. `design.md`'s own contrast table
(5.18/4.94 for ACCENT/CARD_HI, "4.30 marginal" for Deepslate BAD/CARD) is
confirmed wrong, exactly as flagged going in — `docs/implementation.md`'s
recomputed numbers are the ones that check out, and no colour was darkened,
correctly (BAD/CARD passes as-is on both palettes).

## Spec coverage
Every acceptance criterion in `docs/spec.md` §"Acceptance criteria" maps to a
passing test above (table rows 1-10) — no gap. The three "Edge cases" this
dispatch called out for extra scrutiny (mark stuck/missed, button binding
after rebuild, journey across open/closed/switched) are covered by rows
11-14, none of which exist in the developer's own test file — added here to
close what would otherwise be an untested-but-implemented set of edges.

---

## Ten-round review (`docs/REVIEW-PROTOCOL.md`)

**Round 1 — Ticket fidelity: PASS.** Branch `feature/ac-17/...` matches
`{ab}-{ticket}` (`ac`-17, story #17, real Taiga ref). Diff is confined to
exactly what `docs/spec.md` describes — `SettingsItem`, one `__init__` line,
`_build_ui`'s footer/tail, `_build_settings`'s new section, the two guarded
methods, README, one test comment — no drive-by refactor, no `settings.json`
change, no dot indicator, no truncation-width change.

**Round 2 — Correctness: PASS.** Walked the tail's replay logic and the two
guards by hand; the one real bug (spec's own pseudocode clobbering
`self._update_text` by calling `_offer_update()` before reading it) was
already caught and fixed by the developer, and reverting the fix reproduces
it exactly (test case 6 above). No further failing input found — checked
`_pending is None` + no colour, `_pending` set + nothing since (idempotent),
mid-download, and install-error paths by hand against the tail's two-line
replay; all match spec's own worked examples.

**Round 3 — Threading and Tk safety: PASS.** No new thread. Every widget
touch inside `_offer_update`/`_set_update_state` remains reachable only via
`self._ui(...)` from a worker or a same-thread `Button` command / rebuild
tail — confirmed by grep (call sites unchanged) and by running a real
two-worker-thread journey (`_check_worker` + `_install_worker`, both spawned
by the real `check_update()`/`install_update()`) with `CapturesCallbackExceptions`
wired in; it stayed empty across open/close/switch/theme-change mid-flight.

**Round 4 — Naming/shadowing: PASS.** `has_update`, `_update_text`, `overlay`
— no collision with a builtin, import, or existing attribute.

**Round 5 — Untrusted input: PASS — nothing new to examine.** No new
disk/network parsing in this diff; it is pure UI-state plumbing.

**Round 6 — Tech stack conformance: PASS.** No new dependency, no build-flag
change.

**Round 7 — Cross-platform: CONCERN (documentation drift only, pre-existing
pattern).** `version_label` uses `("Consolas", ...)` unconditionally, same as
`NumBox` already does elsewhere in this file — matches existing convention,
not a regression 3b introduces. `design.md`'s "falls back to `TkFixedFont` on
macOS/Linux" claim was never implemented anywhere in the codebase (correctly
called out in `docs/implementation.md`'s Deviations section); flagging only
because the design doc itself still asserts behaviour that doesn't exist —
worth a design-doc correction, not a code fix.

**Round 8 — Tests: PASS, verified by reversion, not just reading.** Reverted
the `_update_text` snapshot fix → `test_downloading_state_survives_a_rebuild_with_settings_open`
dies with the exact wrong-value symptom the spec's own pseudocode would
produce. Reverted the `_settings_open` guard in `_set_update_state` →
`test_set_update_state_with_settings_closed_does_not_raise` dies with
`AttributeError` at the guarded line. Both restored exactly afterward (only
a scratchpad copy was ever edited — the worktree is untouched, confirmed by
`git status --short` showing the same four modified/five untracked files as
at the start).

**Round 9 — Comments and documentation: PASS, one nit.** Every new comment
explains why (the snapshot-before-clobber rationale at `afk_clicker.py`'s
tail, the guard rationale on both methods, the updated divider comment) —
none merely restate the code. `README.md:23` was updated and independently
verified correct German, matching the sibling "Settings → Appearance"
phrasing at `README.md:86`. **Nit:** `docs/design.md`'s contrast table and
font-fallback claim are both inaccurate (contrast numbers off, fallback code
that doesn't exist) — already flagged going into this review and already
worked around correctly in `docs/implementation.md`'s "Deviations from spec"
section; no code fix needed, just a design-doc correction for whoever reads
`design.md` next without the implementation doc's caveats alongside it.

**Round 10 — Roadmap/release readiness: PASS.** No `ROADMAP.md` item moved or
violated. No `settings.json` schema change. No version bump — consistent
with 3a's own precedent (`54a3b65` also shipped without touching
`__version__`), not a new inconsistency.

```
VERDICT: MERGE
BLOCKERS: 0
CONCERNS: 1
```

## Findings (most severe first)

### 1. `docs/design.md`'s contrast table and Consolas-fallback claim are inaccurate — should-fix (doc only, not code)
- File: `docs/design.md:376-385` (contrast table), `docs/design.md:236-241` (Platform notes fallback claim)
- Issue: the contrast numbers don't match the actual hex values (independently reverified above — real numbers are 5.45/5.22 Deepslate, 5.55/5.11 Quartz, all passing), and the claimed `TkFixedFont` fallback for non-Consolas platforms was never implemented anywhere in this codebase, on this label or any other.
- Failure scenario: a future reader of `design.md` alone (without `implementation.md`'s "Deviations" section) would believe Deepslate's error-state contrast is a marginal 4.30:1 needing a darker `BAD`, and would look for fallback font code on macOS/Linux that doesn't exist — wasted investigation, not a runtime bug. No action needed in this code; a design-doc correction is the fix, whenever `design.md` is next touched.

## Follow-ups (non-blocking)
- Correct `docs/design.md`'s contrast table and Platform-notes section per Finding 1, next time that document is edited.

## Overall verdict
**Approve** — testing pass clean (19/19 cases, full 221-test suite green, two
custom regression-by-reversion checks confirmed the two named safety
mechanisms are load-bearing), ten-round review clean (0 blockers, 1
non-blocking documentation nit). Ready to hand back to product-manager.
