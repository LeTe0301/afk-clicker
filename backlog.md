# afk-clicker — backlog

Scoped to this project only. Claude: check this first when picking up work
here, keep it updated as items are resolved or new ones come up — same
convention as the homelab-wide /root/backlog.md.

Tickets live in Gitea (`admin/afk-clicker`, the number used in `ac-N` branch
names) and are mirrored as GitHub issues whose body starts `Gitea:
admin/afk-clicker#N`. GitHub numbers differ, so `Closes #X` in a PR uses the
GitHub number. Shown below as **G#** / **GH#**.

## In progress

Story G#24 / GH#36 (responsive layout and an icon-led minimal restyle) closed
2026-09-12: all five features merged — PR #37 (`db20af2`, row value column),
#40 (`5ab0196`, tab bar), #41 (`18c6f7c`, icon rail), #42 (`cb5900e`, vertical
fill), #43 (`06f5900`, flat restyle). Story-level end-to-end pass clean on `main`
at `0a6ce58`, 284 tests, CI green on all three platforms. Report:
`handoff/story-24-e2e.md`; screenshots in `handoff/story24-shots/`.

Story G#17 / GH#20 (themes that follow the system, and a Settings tab) closed
2026-09-11: features 1, 2, 3a, 3b and 4 merged (PRs #28–#31, #34), story-level
end-to-end pass clean on `main` at `0d6e784`. Report: `handoff/story-17-e2e.md`.

## Open

Bugs and residue:
- [x] **`Segmented` never calls `trace_remove`**, so a destroyed widget's trace stays
      registered on its variable. Found during story #24's end-to-end pass: writing to
      `appearance_var`/`ui_scale_var` after closing Settings (without reopening) hits
      the dangling trace of the destroyed `Segmented`. Confirmed by grep that **no code
      path in the app itself can reach this** — it needs an external caller holding a
      stale reference, which is why it has never surfaced in normal use or in the suite.
      Not a story #24 regression; it predates the story.
      **Partially resolved by G#27/ac-27** (`AfkAutoclicker._forget_traces()`): every
      trace on a Variable this UI still owns is swept on each rebuild, regardless of
      which widget registered it, so `Segmented`/`TabBar`'s own un-removed traces stop
      accumulating across repeated rebuilds. The mid-life window this item originally
      described — something external writing to the variable *between* a rebuild and
      the next close/rebuild, while a superseded `Segmented`'s dangling trace is still
      live — is **not** addressed; that needs the trace removed at rebuild time on the
      *old* widget specifically, which `_forget_traces()` deliberately does not
      attempt (see its own docstring and docs/history/ac-27-implementation.md).
      **Round 2 (PR #47) narrowed this further**: `_forget_traces()` was originally
      also called from `on_close()`, so the *final* generation's traces (whatever is
      live when the app actually closes) were swept too — that `on_close()` call was
      reverted after it was implicated (alongside the `bind_all` deletecommand below)
      in a macOS-only interpreter abort reproduced twice in CI
      (`Tcl_FindHashEntry on deleted table`, exit 134); see
      docs/implementation.md's "Round 2" section. So as of `ac-27`, only the
      rebuild-to-rebuild accumulation is fixed; the final generation's traces (a
      one-time leak, on every close, not a per-rebuild accumulation) are open again,
      same as before this ticket. Left open, narrowed to both windows.
- [ ] G#5 / GH#7 — Applying a hotkey crashes the process on macOS without Accessibility permission.
- [ ] G#8 / GH#10 — `registered_hotkey` claims a listener that is not running.
- [ ] G#7 / GH#9 — `from_json` checks shape but not vocabulary.
- [ ] G#9 / GH#11 — macOS input-permission guard: residue from the review of PR #4.
- [ ] G#10 / GH#12 — Review residue: roadmap line, startup ordering, test hygiene, stale counts.
- [ ] G#18 / GH#22 — Review residue from PR #21. The `bind_all` comment is done; still missing: a test that a Button click drops a field's focus.
- [ ] G#21 / GH#32 — Review residue from the updater PRs: a hex check in `fetch_checksums`, the zip comment, the superseded-worker race test, and `Store.save` swallowing `OSError`.
- [ ] G#4 / GH#6 — The click interval measures 25–40 % slow on the macOS CI runner. Needs a real Mac.
- [ ] G#23 / GH#35 — macOS reports `_dpi_s` ~0.75, so the 90 % UI-scale step renders
      5 pt labels (6 pt at 100 %, which already ships). Not a regression; the spec's
      §3 assumption that `_dpi_s >= 1.0` was simply wrong about macOS. Decide whether
      to add the `fs(base, s)` floor across the ~20 font call sites, drop 90 % on
      low-DPI displays, or accept it. Only verifiable via CI — no real Mac here (G#4).
- [ ] **`QueuedNonResyncedUpdatesSurviveARebuild.test_a_mark_running_scan_result_queued_before_a_rebuild_still_lands`
      is flaky on macOS.** Failed on `main` at `5c32f3c` (a docs-only commit, so
      nothing in the diff could have caused it) and earlier during story #24
      feature 3, passing on the retry both times. Non-fatal — exit 1, not an abort.
      It is why `main` shows a red macOS leg at `5c32f3c`.
- [x] **The test suite intermittently aborts at interpreter shutdown** —
      `Tcl_AsyncDelete: async handler deleted by the wrong thread`, exit 134, and
      unittest's summary never prints, so a run that passed looks like a failure.
      Reproduced on clean `main` at roughly 1 run in 4 (and at a similar rate on the
      feature/ac-17 branch), so it predates the UI-scale work.
      **G#27/ac-27 investigated this at length** (see
      docs/history/ac-27-implementation.md) and confirmed the mechanism: a Tk
      `Variable.__del__` running off the main thread, because the underlying
      interpreter (and everything reachable from it — every Variable, every widget)
      was still referenced, past `on_close()`, by something the test/app never
      released. Found four concrete, previously-unknown instances of exactly this:
      `root.bind_all()`'s own command (`needcleanup=0`, `destroy()` never releases
      it), every un-removed variable trace surviving a rebuild (see the `Segmented`
      item above), an item left sitting in `self._ui_queue` after `on_close()`'s own
      `self.stop()` call queues one with nothing left to drain it, and
      `_poll_games()`'s scan thread holding `self` for the full duration of its
      `detect_running()` call (which can itself stall — seen directly, ~1 scan in a
      couple hundred, stuck opening its Xlib connection).
      **Round 2 (PR #47): fixing the first three on `on_close()` itself introduced a
      new, worse failure — a macOS-only interpreter abort** (`Tcl_FindHashEntry on
      deleted table`, exit 134) reproduced twice in macOS CI, in a test `main` passes
      cleanly, that could not be reproduced on Linux (60+ runs across three parties)
      or root-caused without macOS access (see docs/implementation.md's "Round 2").
      Of the three, only the `_ui_queue` drain (pure Python, no Tcl call) was kept in
      `on_close()`. Reverted, and open again: `bind_all()`'s own command is not
      released by `on_close()` (the `_button1_all_funcid` capture was reverted too,
      since nothing else used it); `_forget_traces()` is no longer called from
      `on_close()` either, so the *final* generation's variable traces (live at the
      moment the app actually closes) are not swept by anything, though the
      `_rebuild_ui()` call to the same function — which fixes traces accumulating
      *across* rebuilds — was kept, since the review that found the abort explicitly
      did not implicate it (the crashing test does zero rebuilds; the multi-rebuild
      test that exercises this call site three times passed clean on the same macOS
      CI run). `_poll_games()`'s fix (and its `on_close()` join) is pure Python and
      unaffected by round 2 — still fixed.
      **Not fully resolved even before round 2.** After the original four fixes, a full-suite run still reports
      the *same* off-main-thread `Variable.__del__` at roughly the same frequency
      (~55 of ~284 tests) as before — traced to a real, reproducible interaction
      where a *preceding* test that goes through `UITestCase.restart()` leaves some
      later test's `GameItem`/`SettingsItem`/`Button` widgets uncollected after a
      clean `on_close()` (confirmed via `_tclCommands is None` and `children == {}`
      on the widgets themselves — the Tcl-level cleanup this ticket's fixes target is
      not the gap here). `gc.collect()` reports 0 objects collected even retried over
      a 2s window, and `gc.get_referrers()` shows no external anchor, which is
      consistent with (but not proven to be) a reference held by `_tkinter.tkapp`
      itself — confirmed via `gc.is_tracked()` to not participate in cyclic GC at all,
      so any real reference it holds is invisible to graph-based diagnosis. Whether
      the *fatal* abort (as opposed to this always-benign, always-caught RuntimeError
      variant) is downstream of this same mechanism is unconfirmed: 20 back-to-back
      full-suite runs of unmodified `main` in the sandboxed environment this
      investigation ran in produced zero exit-134 aborts, only this benign variant —
      so the fatal escalation could not be reproduced on demand here at all, on
      either side of the fix. Minimal repro for whoever picks this up next:
      `python -m unittest tests.test_ui.PerGameSettings.test_survives_a_restart
      tests.test_ui.<any test that constructs+on_close()s a second UI in the same
      process>` and check `gc.get_referrers()` on a `weakref.ref()` taken before that
      second UI's `on_close()`.
      **Round 3 (ac-27, this ticket, GH#46 blocking PR #49) — resolved as a test-suite
      symptom, root leak(s) still open.** Round 1/2 both tried to make the leaks not
      exist (release specific references in `on_close()`); this round instead accepted
      that at least one leak (the round-2 residual above) cannot currently be
      eliminated, and targeted *which thread finalises the leaked `Variable`* instead —
      the actual, confirmed cause of both the benign `RuntimeError` and the fatal abort.
      Python's cyclic GC runs on allocation-count thresholds it hits on whatever thread
      is executing at that moment, including this app's own worker threads (the click
      loop, the hotkey listener); `tests/context.py` now calls `gc.disable()` for the
      whole suite, and `UITestCase.tearDown()`/`AppearanceThemeSwitch.tearDown()`
      explicitly `gc.collect()` right after each test's own `on_close()` — always on
      the main/test-running thread. Measured: an explicit `gc.collect()` added only to
      `tearDown()` with automatic collection left *on* did not move the benign
      `RuntimeError` count (~55–57/285, same as unmodified `main`, over 7 runs) —
      most occurrences happen mid-test, before any `tearDown()` runs, whenever the
      automatic collector happens to land on a worker thread. Disabling automatic
      collection collapsed it to 0/285 across 5 repeated full-suite runs (plus a
      isolated repro of the two tests originally named on GH#46, `HotkeyListenerSurvives
      Rebuild.test_listener_object_identity_is_unchanged_across_a_rebuild` and
      `ClickLoop.test_interval_is_honoured`, run together 1/1 clean). No production
      code touched — the app never creates more than one `Tk()` per process, so this
      leak-finalised-on-a-worker-thread pattern is specific to the test suite building
      and tearing down ~140 interpreters in one process. The underlying reference
      leaks this item's Round 2 left open (`bind_all`'s funcid, the final generation's
      variable traces, and the still-unidentified `restart()` interaction) are
      unaffected by this round and remain real — tracked under the `Segmented` item
      above and the `restart()` repro just above this note — but none of them can
      abort the suite anymore, since nothing is left to finalise them off the main
      thread. Full account: `docs/implementation.md`.
- [ ] **The trace-registration-order hazard is overclaimed in merged code and in the
      story's spec** — `_apply_appearance`'s own comment (~`afk_clicker.py:1939-1958`)
      and `docs/spec.md` §2 both attribute Theme's safety to registering `trace_add`
      after the `Segmented(...)` call. Verified empirically during the feature 4 cycle
      (twice, independently): reversing that order changes nothing observable — the
      whole suite still passes, for Theme as well as UI scale. The real mechanism is
      that neither `_apply_appearance` nor `_apply_ui_scale` ever rebuilds
      synchronously inside the trace; `after_idle` defers it past the point where
      order could matter. Feature 4's own new comment was corrected to say this; the
      Feature-3 comment and the spec text were left alone as out of scope for that
      feature. Worth a small separate pass so the next person isn't misled.

- [ ] **`TabBar` accepts a `height` it then ignores when repainting** — found by
      the critical review of PR #40 (non-blocking). `TabBar.__init__`
      (`afk_clicker.py:1269`) takes a `height` override and sizes the canvas with
      it, but `_paint()` (`afk_clicker.py:1314`) repositions the underline using
      the module constant `TAB_HEIGHT` instead of the instance's own height —
      unlike the sibling `Segmented`, which keeps `self.w`/`self.h`. Unreachable
      today since both call sites omit `height`, so it is a latent trap rather
      than a bug: feature 3, or ticket G#13's Macros tab, adding a `TabBar` with a
      custom height is what makes it bite.

Features:
Resolved 2026-09-12 (G#28 / GH#48, PR #49, `8ac6e35`): the window height floor was
`690 * s`, sized for the single combined page that predated tabs. Now
`WINDOW_MIN_H = 620`, derived from the *tallest* pane's real content span — the
binding constraint, since nothing here scrolls and a lower floor puts Eating's
lower rows out of reach. Took five rounds; `docs/history/ac-28-*` records why.
Two follow-ups from its review are below.

- [ ] **`_rebuild_ui()` does not cancel `_pane_fill_after_id`** the way it cancels
      `_rebuild_after_id` immediately above. Verified empirically harmless today —
      a pending pane fill landing across a rebuild does no damage — but it is an
      undocumented invariant rather than a guaranteed one, and the coalescing
      machinery it belongs to is new (PR #49 round 5). Worth either cancelling it
      for symmetry or writing down why it does not need cancelling.
- [ ] G#13 / GH#15 — Story: a Macros tab, configurable per game. Blocked on the settings schema version (ROADMAP). Rebase its branch first.
- [ ] G#12 / GH#14 — Calibration suite for the review agent. Rebase its branch first.

Housekeeping:
- [ ] Branches `feature/ac-12/…` and `feature/ac-13/…` are stacked on `901f0a4`, whose FIFO tests fail on Windows. They stay red on CI until rebased onto `main`.
- [ ] Release: `main` carries #19, #21, #24, #27, #28–#31, #37, #39, #40, #41 since v0.3.1. `release.yml` needs `__version__` to match the `release/x.y.z` branch, so bump it there (0.4.0 suggested, since Settings is new UI).
- [ ] The GitHub token in `~/.config/afk-clicker/gh-token` can't re-run Actions jobs (no `actions:write`). A flaky run needs a new push to go again.
- [ ] **Stress-testing the suite needs two Xvfb displays, not one.** There is no
      window manager, so X input focus is a single global resource:
      `UITestCase.setUp` (`tests/test_ui.py:74-79`) calls `root.focus_force()` to
      acquire it, and the moment a second Tk process does the same, the first
      one's `focus_get()` returns `None` and every focus assertion in it fails.
      Demonstrated directly during story #24 feature 2: process A held focus until
      the instant process B called `focus_force()`, then dropped to `None`; with B
      on a separate display, A never lost it. So when inducing load to chase a
      flaky focus test, run the load loop on `:98` and the test under scrutiny on
      `:99` — a shared display manufactures its own failures. Worth a comment
      beside `focus_force()` so the next person doesn't rediscover it.
- [ ] **Unmapped-widget geometry passes on Linux and fails only on Windows.** On
      X11 a widget whose pane was packed then `pack_forget()`'d keeps returning its
      last real `winfo_rootx()`/`winfo_width()`; on Windows Tk returns 0 and 1 for
      the same unmapped widget. A test measuring a widget in a hidden pane therefore
      passes here on stale-but-plausible numbers and fails only on the Windows leg —
      `AssertionError: 1 not less than or equal to 0` is the signature. Distinguish
      `winfo_x()` (parent-relative, assigned at pack time, valid while unmapped)
      from `winfo_rootx()` (absolute screen position, not valid). Cost story #24
      feature 2 a CI round. Make the pane genuinely visible before measuring.
- [ ] **Xvfb has no window manager, so WM-driven events never fire locally.** Most
      importantly it never generates the root-targeted `<Configure>` a real WM
      (macOS WindowServer, Windows) sends after mapping. Story #24 feature 3 shipped
      the same crash twice behind this: binding `<Configure>` before `__init__`'s
      first `_build_ui()` returned let a genuine WM resize reenter the rebuild
      mid-construction and die on `AttributeError: ... has no attribute 'click_ms'`
      — green on every Linux run, red on macOS CI. Note the first fix
      (`event.widget is self.root`) addressed a *different* hazard (spurious
      `<Configure>` from descendants, via bindtags), and reading a green suite as
      proof it fixed both is what cost the second round. For anything resize-,
      mapping- or focus-driven, ask what a real WM would do that Xvfb will not, and
      treat CI as the only evidence.
- [x] **Pipeline-doc references — resolved 2026-09-11** (G#25 / GH#38, PR #39).
      The real count was 44, not 39 — the original grep omitted `implementation`.
      40 now resolve into `docs/history/`; 4 cite sections in documents overwritten
      before anyone archived them and are documented as unrecoverable, with the
      near-misses that were considered and rejected recorded so nobody repeats the
      search. **The recurrence fix matters more than the cleanup**: archiving a
      cycle's own docs into `docs/history/` is now a required last step of that
      cycle's *reviewer approval* (`docs/history/README.md`), because the reviewer is
      the last stage to touch a worktree before the next cycle overwrites those files.
      Arguably belongs in the global pipeline description in `~/.claude/CLAUDE.md`
      too — left alone, as that's the owner's file.
## Session handoff — 2026-09-12 (end of session)

**Where things stand:**
- `main` is at `6c4de48`, CI green on all three platforms, **284 tests**. Local checkout clean; the `ac-24` worktree is on its branch at
  the merged state, clean.
- **Story G#24 / GH#36 is closed — all five features merged.** Nothing is in
  flight. There is no story queued behind it.

Merged this session, each after a critical ten-round PR review posted on the PR
and green CI on all three platforms:

| PR | Feature | Merge |
|---|---|---|
| #40 | 2 — horizontal tab bar (`Hotkey \| Clicking`, `Appearance \| Updates`) | `5ab0196` |
| #41 | 3 — icon rail; window minimum width rederived | `18c6f7c` |
| #42 | 4 — each tab pane fills its own leftover vertical space | `cb5900e` |
| #43 | 5 — flat restyle, sparing accent, sentence-case headers | `06f5900` |

(Feature 1, the row value column, merged as PR #37 / `db20af2` at the end of the
previous session.)

Story-level end-to-end pass: clean. `handoff/story-24-e2e.md`, screenshots in
`handoff/story24-shots/`.

Merged after the story closed: G#26 / GH#44 (PR #45, `6c4de48`) — the number in
every numeric input sat flush against the field's right border, since
`justify="right"` pins it to the entry's own edge and `pack`'s `ipadx` pads both
sides equally. A background-coloured spacer insets it without changing the
entry's character width, so feature 1's value column keeps its offsets.

**Next:** nothing is queued. The open items are in the sections above — the
largest are the `minh` window-floor question (a product decision, and the one
most visible to a user), G#13's Macros tab, and G#12's calibration suite. Both
of those last two need a rebase before they build.

**Workflow:**
1. product-manager → ux-designer → developer → reviewer, each stage reading the
   previous stage's `docs/*.md`.
2. An approved cycle is pushed and PR'd without asking.
3. The review agent gives each PR a critical ten-round review per
   `docs/REVIEW-PROTOCOL.md`, re-deriving claims rather than trusting the cycle's
   own docs, and posts it on the PR.
4. Merge on a `MERGE` verdict **and** green CI on all three platforms. A red leg
   routes back to the developer as a new round — never merge through it.
5. If a fix lands after a verdict, ask the same reviewer to verify the delta and
   re-issue rather than paying for a fresh ten-round pass.
6. Archive the cycle's `docs/*.md` into `docs/history/` **after** CI is green,
   not at reviewer approval — approval is not the last gate.

**Running tests here:** the README's `xvfb-run` needs `xauth`, which this
container lacks. Start `Xvfb :99` directly and use a venv with `pynput`:
`DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` — 284 tests on
`main`. The venv lives in the session scratchpad and does not survive a container
reset. Keep a second display (`:98`) for load loops — see Housekeeping.

**The one lesson this story is worth remembering for:** *a green local run is not
evidence for behaviour this box cannot produce.* CI's Windows and macOS legs
caught **eleven** things the cycle reviews missed, and they share that one shape.
Xvfb has no window manager, so it never clamps a window, never sends a post-map
root `<Configure>`, and never arbitrates focus between processes. Anything
resize-, mapping- or focus-driven is only really tested on CI.

Concretely, before asserting a pixel value, ask what else could legitimately
produce a different number elsewhere — the font, the screen, the DPI, the WM.
Prefer assertions true by construction: compare two things measured the same way,
or derive the expectation from what was actually measured, rather than comparing
one measurement against a constant or against a starting value you assumed the
platform would honour.

**Other lessons that cost a round each:**
- Tk prints callback exceptions instead of raising them. `UITestCase` records them.
- Design-doc contrast arithmetic has been wrong **four** times. Recompute with the
  real WCAG formula, and sanity-check the calculator against white/black = 21:1.
  The compound scale is `_dpi_s * UI_SCALE_FACTORS[...]` — the two **multiply**, so
  the worst case is low-DPI *and* the 90% step together (`s = 0.675`), not either
  alone. `int()` truncates, so `int(10 * 0.675)` is 6, not 7.
- A comment asserting a hazard is worth empirically testing before trusting it.
  Three in this codebase claimed safety properties that were simply false.
- Verify a stress-test harness before trusting its numbers. A load loop killed by
  PID rather than process group leaves an orphan hammering the display, which
  produced a fake 25% failure rate briefly reported as a real regression.
- A test written to prevent a latent-parameter bug can contain one. Two tests this
  story shipped passed in both the working and sabotaged states. **Sabotage every
  new test in both directions** before believing it.
