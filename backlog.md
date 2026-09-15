# afk-clicker — backlog

Scoped to this project only. Claude: check this first when picking up work
here, keep it updated as items are resolved or new ones come up — same
convention as the homelab-wide /root/backlog.md.

Tickets live in Gitea (`admin/afk-clicker`, the number used in `ac-N` branch
names) and are mirrored as GitHub issues whose body starts `Gitea:
admin/afk-clicker#N`. GitHub numbers differ, so `Closes #X` in a PR uses the
GitHub number. Shown below as **G#** / **GH#**.

## In progress

**0.7.0 released 2026-09-15** (`v0.7.0` from `d008ad5`, run 34995512574): the update-log
prompt (PR #72), top-aligned panes (PR #68), the macOS Accessibility-permission fixes
(PR #73), saved-hotkey vocabulary validation (PR #74), the G#39 flake mitigation (PR #70).
`release/0.7.0` is merged back into `main` (`63b06f2`). Leo's own Windows copy was on 0.5.0,
whose in-app Install cannot work (G#35); he was pointed at the one-time manual unzip.
The first real in-app Windows update (0.6.0+ → next release) is still unverified.

**0.6.0 released 2026-09-15** (`v0.6.0` from `0d83eef`, run 34931395022): the
Clickwork name (PR #61), the Loop icon (PR #62) and the Windows install-update fix
(PR #65, G#35). `release/0.5.0` and `release/0.6.0` are both merged back into `main`.
Open check, only possible at the *next* release: a real Windows in-app update from
0.6.0 should close and reopen on the new version with no console flash and leave
`%APPDATA%\AFKFarmClicker\update.log` ending in `done`. Windows users on 0.5.0 or
earlier install 0.6.0 by hand once (said in the release notes).

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
- [x] **Fixed in 0.6.0 (G#35 / GH#63 — github: true, PR #65).** Under `DETACHED_PROCESS` the swap
      script stalled at its first `tasklist | find`; now `CREATE_NO_WINDOW`, `ping` for
      the wait, and a shipped `update.log`. Original report: **Windows: in-app Install
      closes the app and never comes back** (Leo,
      2026-09-13, 0.3.1 → 0.5.0). What he saw: at 100% the window closes, a black
      console window flashes and closes, the files are not replaced, and a
      double-click still starts 0.3.1. **Running the leftover
      `%TEMP%\apply-update.cmd` by hand from an interactive `cmd` then updated to
      0.5.0 correctly**, so the script's contents (tasklist wait, robocopy /MIR,
      start) are fine. The failure is in how `_quit_for_update()` launches it:
      `subprocess.Popen(["cmd", "/c", script], creationflags=DETACHED_PROCESS |
      CREATE_NEW_PROCESS_GROUP)`, right before `on_close()`. Linux 0.3.1 → 0.5.0 via
      the real frozen builds works end to end (verified under Xvfb). This code is
      identical in 0.3.1, 0.5.0 and `main`, so **every Windows user on an existing
      build hits this until they install a fixed build by hand**. Suspects, none
      confirmed yet: a console-less `cmd` giving its console children (`tasklist`,
      `find`, `timeout`, `robocopy`) each a new console, which explains the flash;
      `timeout` refusing to run without console input; the process tree being torn
      down with the parent. Next step: reproduce on the `windows-latest` CI runner
      with a frozen build, and log each script step to a file. Also: the script
      lands in `%TEMP%` itself, because `write_swap_script()` takes
      `dirname(dirname(staged))` and the Windows zip isn't flattened. **G#35 / GH#63**,
      shipped in 0.6.0 (PR #65). Leo also wanted the shipped script to keep a step log
      (`update.log` in the settings dir) — done, same PR; the in-app "send us the log"
      prompt was split out as G#36 / GH#64, now also done below.
- [x] github: true — no ticket (predates the ticketing rule) — **`Segmented` never calls `trace_remove`**, so a destroyed widget's trace stays
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
- [x] **Done 2026-09-15, PR #73 (combined with G#8/G#9 below).** G#5 / GH#7 — github: true — Applying
      a hotkey crashes the process on macOS without Accessibility permission. Needed no
      code change: already fixed by the commit that introduced `macos_input_permitted()`.
- [x] **Done 2026-09-15, PR #73.** G#8 / GH#10 — github: true — `registered_hotkey` claims a listener
      that is not running. Round 1 fixed the first-Apply case only; round 2 (caught by
      PR review, reproduced live) fixed a second Apply after an earlier successful one.
- [x] **Done 2026-09-15, PR #74.** G#7 / GH#9 — github: true — `from_json` checks shape but not
      vocabulary. Now `name in kb.Key.__members__`, char length 1..`MAX_CHAR_LEN` (8),
      non-bool vk in 0..`MAX_VK` (`0x1FFFFFFF`), and more than `MAX_CHORD` keys is
      rejected instead of truncated. `MAX_CHAR_LEN` is reasoned from pynput's darwin
      source, not a real Mac. Don't tighten `MAX_VK` to `0x0110FFFF`: XF86 media-key
      keysyms (`0x1008FFxx`) sit above that.
- [ ] G#40 / GH#75 — github: true — macOS flake: `Sidebar.test_running_dot_and_follow` read `running`
      as False on PR #74's first macOS leg (run 34989787219); the same commit's re-run
      was green. **Hit again on PR #76 (run 34996063044) — 2 of the last 7 macOS legs.** Suspected to be the same class as G#39: a periodic `_poll_games`
      scan landing inside the test's own `root.update()` after `settle()` only
      waited for the startup scan. Unconfirmed; details on the ticket.
- [x] **Done 2026-09-15, PR #73.** G#9 / GH#11 — github: true — macOS input-permission guard: residue
      from the review of PR #4 (5 small items: `selftest()`'s unconditional listener
      construction, a load-bearing comment, a corrected darwin hint string, a
      previously-self-skipping darwin test now exercised via a `find_library` patch).
- [x] **Done 2026-09-15, PR #76.** G#10 / GH#12 — github: true — Review residue: roadmap line, startup
      ordering, test hygiene, stale counts. The startup-ordering gap had already closed
      (since `54a3b65`, `_build_ui()` runs `_sync_settings()` before the hotkey restore),
      so it is documented, not moved. The stale counts were already corrected on GitHub.
- [x] **Done 2026-09-15, PR #77.** G#18 / GH#22 — github: true — Review residue from PR #21. The `bind_all`
      comment landed with PR #30; the test clicks the sidebar's real "Add current game"
      `Button` (round 1 built a throwaway one, missing that the sidebar stays viewable).
- [x] **Done 2026-09-15, PR #78.** G#21 / GH#32 — github: true — Review residue from the updater PRs. Hex check in
      `fetch_checksums`; `_safe_names` docstring (zipfile strips `..` itself, tar was the
      real hole); update-check results carry `_check_seq` and land via main-thread gates
      (`self._pending` was written from the worker); `Store.save()` returns a bool and the
      Appearance pane shows one "Couldn't save settings" notice. Three rounds: a crash
      opening Settings while saves fail (painting mid-rebuild), then a macOS-only SIGTRAP
      from a test that started a real pynput listener.
- [x] **Done 2026-09-15, PR #80.** G#22 / GH#33 — github: true — Warn when the Minecraft interval minus jitter drops
      below 650 ms. The jitter row's hint becomes "Java sweeps may miss" (INK bold, 550–649 ms)
      or "Java sweeps likely fail" (BAD bold, <550 ms). It sits in the jitter slot, not under
      Interval, because the Minecraft Clicking pane has ~0–1 px spare at `WINDOW_MIN_H` on
      Windows/macOS. Three rounds: placement/height (PR review), owner asked it to stand out
      more, and a floor test that could not fail.
- [ ] G#42 / GH#81 — github: true — The three older `WindowMinimumHeight` floor tests measure allocated, not
      required, heights, so they cannot detect a clipped pane. They are the only guard on
      `WINDOW_MIN_H = 620`. Use PR #80's reqheight+pady measure and sabotage-verify.
- [ ] G#41 / GH#79 — github: true — `Store.save` leaves `settings.json.tmp` behind when `os.replace` fails
      (e.g. Windows file lock). Harmless, small; found by PR #78's review.
- [x] **Done 2026-09-15, PR #72.** G#36 / GH#64 — github: true — Ask the person to send `update.log`
      (prefilled GitHub issue) when an in-app update didn't finish. Follow-up to G#35,
      which ships the log. Four review rounds: two design-doc contrast-arithmetic
      fixes, a theme/UI-scale change destroying the open dialog, the no-browser
      fallback clipping its own buttons at 100%, a macOS-only crash from an untracked
      `after_idle` handle (same class of bug as G#39, not the same bug), and a real
      command-injection finding — the GitHub release tag reached the swap script
      unvalidated, and a crafted tag could run a command. Fixed by validating the
      tag's shape before it's used at all.
- [ ] G#4 / GH#6 — github: true — The click interval measures 25–40 % slow on the macOS CI runner. Needs a real Mac.
- [ ] G#23 / GH#35 — github: true — macOS reports `_dpi_s` ~0.75, so the 90 % UI-scale step renders
      5 pt labels (6 pt at 100 %, which already ships). Not a regression; the spec's
      §3 assumption that `_dpi_s >= 1.0` was simply wrong about macOS. Decide whether
      to add the `fs(base, s)` floor across the ~20 font call sites, drop 90 % on
      low-DPI displays, or accept it. Only verifiable via CI — no real Mac here (G#4).
- [ ] G#39 / GH#69 — github: true — **RECURRED 2026-09-14** on PR #65's macOS leg (run 34906199873, commit
      `9aa7e81`, a diff touching only `tests/test_updater.py` and docs), same
      assertion: `'minecraft'` missing after a rebuild. So the `_poll_games` stub
      below does not close every path; something else still races the queued
      result on macOS. Tracked as **G#39 / GH#69**. The original entry:
      **`QueuedNonResyncedUpdatesSurviveARebuild...still_lands` macOS flake — fixed
      2026-09-13** (G#30 / GH#53, PR #58, `22815c9`). Failed four times, always on
      macOS, always passing on re-run — twice on diffs containing no executable code
      at all. Cause: `_rebuild_ui()`'s tail unconditionally restarts `_poll_games()`,
      so a second *real* OS scan races the test's fake one and overwrites
      `{"minecraft"}` with the runner's actual window state. Fixed by stubbing
      `_poll_games` to a no-op for that test. Two dead ends are recorded in
      `docs/history/ac-30-implementation.md` and worth reading before touching it:
      stubbing `detect_running` to the value the test queues blinds the guard
      entirely, and stubbing it to a *distinguishable* value fails 5/5 on correct
      code, because an instant stub makes the second scan land deterministically
      first.
      **Mitigated (PR #70), trigger unconfirmed.** `e60a6aa`+ closes a second,
      broader code-established gap the `_poll_games` stub above can't reach:
      `setUp()`'s own construction (not just a rebuild) starts a real scan and
      arms a 5000ms self-rescheduling timer that captured the *original*
      `_poll_games` before the stub ever exists, so a scan already in flight from
      `setUp()` could still land between the test's manual queue-put and its
      drain (`tests/test_ui.py`'s "Round 3" comment). The fix cancels that timer
      and joins the real poll thread (now failing loudly, not silently
      proceeding, if it's still alive after 5s) before the manual queue-put — see
      `docs/implementation.md`. This is real and sabotage-verified (two
      independently-designed sabotages, both 5/5 red; an independent race-class
      reproduction, old critical section red / new one green, 10/10 each) —
      **but that this was actually the trigger behind the real macOS recurrences
      above is NOT confirmed.** A dedicated diagnostic (draft PR #71, run
      34942811672) looped the fixed-for-Round-3 test 40x in isolation on macOS:
      0/40 failures, no poll thread ever alive at a manual queue-put, no periodic
      `_poll_games` firing inside the test, every real scan finishing well under
      0.5s (max 0.481s, median 0.162s) — nowhere near the ~5s stall this
      hypothesis needs. That's absence of the triggering condition in an isolated
      loop (the historical failures happened inside a loaded full-suite run, a
      different timing profile), not evidence against the mechanism itself, so
      this ships as a defensive closure of a real race path, not a claimed fix of
      G#39. Left open: **a recurrence with this fix in place means the periodic-
      timer/in-flight-poller hypothesis (H1) was not the (only) cause**, and the
      investigation should resume from the loaded-full-suite condition rather
      than re-deriving H1 from scratch.
      **Round 3 (PR #70 independent review, Finding #1, BLOCKER): also fixed in
      `afk_clicker.py` itself, a real production race, not just test exposure.**
      The Round 2 quiesce above only ever sees `self.ui._poll_thread`'s current
      value; `_poll_games()` (`afk_clicker.py:3093-3151`) overwrites that
      attribute on every call, including its own periodic reschedule, without
      joining whatever scan it just superseded. When an older scan is still
      stalled when a newer one starts — H1's own described trigger — the older
      scan's thread handle is orphaned and invisible to the test's quiesce; it
      can land later and silently clobber an already-applied result, with no
      diagnostic from the loud-fail path (reproduced directly against real
      production code by the reviewer, not just the test). This is a genuine
      product race (a live "what's running now" indicator can regress to stale
      data), so `_poll_games()` now stamps each call with a monotonically
      increasing sequence number, and a new `_apply_scan(seq, running)` gate
      drops any scan result older than the newest one already applied before
      calling `_mark_running()` (unchanged for every direct/non-scan caller).
      New dedicated test (`AnOlderScanResultDoesNotOverwriteANewerOne`) drives
      this through the real `_poll_games()`/`scan()` path and is sabotage-
      verified (disabling the sequence check fails it); the reviewer's own
      reproduction script now passes against the fixed code
      (`after_orphan_ok=True`), confirmed still failing against the Round 2 code
      first. The macOS-trigger hedge is unchanged by this round — still
      **`- [ ]` open, mitigated, trigger unconfirmed** — this closes a
      completeness gap the reviewer found in the fix itself, independent of
      whether H1 is ever confirmed as G#39's real-world cause.
- [x] github: true — no ticket (predates the ticketing rule) — **The test suite intermittently aborts at interpreter shutdown** —
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
- [ ] G#43 / GH#82 — github: true — **The trace-registration-order hazard is overclaimed in merged code and in the
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

- [ ] G#44 / GH#83 — github: true — **`TabBar` accepts a `height` it then ignores when repainting** — found by
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

- [ ] G#45 / GH#84 — github: true — **`_rebuild_ui()` does not cancel `_pane_fill_after_id`** the way it cancels
      `_rebuild_after_id` immediately above. Verified empirically harmless today —
      a pending pane fill landing across a rebuild does no damage — but it is an
      undocumented invariant rather than a guaranteed one, and the coalescing
      machinery it belongs to is new (PR #49 round 5). Worth either cancelling it
      for symmetry or writing down why it does not need cancelling.
- [x] **Done 2026-09-15, PR #68.** **G#37 / GH#66 — github: true — Pane content should sit directly under its tab bar, not in the middle of the
      page** (Leo, 2026-09-13, from screenshots of 0.5.0 on Windows, maximised). The
      Hotkey tab's Record/Apply card, the Clicking tab's cards and Settings →
      Appearance all float mid-page with a large empty band between the tabs and the
      first card. The content should start right below the tab it belongs to. This
      reverses story #24 feature 4's deliberate vertical centering (`FILL_TOP_SHARE =
      0.5`, `_request_pane_fill`/`_run_pane_fill` spacer frames). Treat it as a design
      change, not a bug, and check the window height floor (`WINDOW_MIN_H`) still
      holds with top alignment. The Macros tab branch (G#13, below) builds its
      settings on the same centered panes, so it needs the same change.
- [ ] **G#38 / GH#67 — github: true — UI scale should follow the window size** (Leo, 2026-09-13). Today it's a
      fixed Settings choice (90/100/115/130%). Leo wants it to scale with the window.
      Open design questions for the spec: replace the manual choice or make it an
      "Auto" option next to it, what the reference size is, whether it steps or
      scales continuously, and how it interacts with `WINDOW_MIN_H`, the rail
      collapse threshold and the per-rebuild cost of `_rebuild_ui()` during a drag
      resize.
- [ ] G#13 / GH#15 — github: true — Story: a Macros tab, configurable per game. Blocked on the settings schema version (ROADMAP). Rebase its branch first.
- [ ] G#12 / GH#14 — github: true — Calibration suite for the review agent. Rebase its branch first: it (and G#13's, which contains its `2bdf55f`) is stacked on `901f0a4`, whose FIFO tests fail on Windows.

Housekeeping:
- [ ] G#46 / GH#85 — github: true — **Delete merged remote branches** (Leo, 2026-09-13). As of
      2026-09-15, 15 branches on `github` are fully merged, listed on the ticket. Keep
      `feature/ac-12/…`/`feature/ac-13/…`; they are unmerged and tracked on G#12/G#13.
      Confirm the list with Leo before deleting.
- Lesson (not a backlog item): **A flake "fix" tends to work by blinding the test — sabotage-verify every
      one.** Three cases in two days, each caught only by deliberately breaking the
      product and checking the test still failed: a settling loop added to a *test*
      drove panes to a state the app never reached (289/289 green while a row was
      visibly clipped off-screen); `test_holding_does_not_repeat`'s quiet window fell
      inside `DEBOUNCE_S`, so debounce alone satisfied the assertion (sabotaged
      product: old test caught it 5/5, new test passed 10/10); and
      `QueuedNonResynced...` stubbed a dependency to the same value the test queues,
      so a dropped entry was indistinguishable from a delivered one (passed 3/3).
      Removing a flake means removing variation, and the test's own sensitivity is
      the easiest variation to remove. **The acceptance test is not "it stopped
      failing" but "it still fails when the product is broken."**
- Lesson (not a backlog item): **Anything matching on a command line matches the process doing the matching.**
      `pgrep -f` / `pkill -f` see the full command line **including the shell running
      them**, so `pkill -f foo.py` inside a `bash -c` containing that string SIGKILLs
      itself and leaves the target alive (hit twice on 2026-09-13, exit 144 both
      times). Collect PIDs first, then `kill -9` those. For waiting, prefer
      `tail --pid=<pid> -f /dev/null`, or `until ! pgrep -f "[f]oo" >/dev/null; do
      sleep 2; done` — and bracket **every** alternative: a loop whose pattern was
      `"[u]nittest ...\|fullsuite"` matched its own command line on the second
      alternative and spun for 15 hours, burning a core, noticed only from the host.
- Lesson (not a backlog item): **`ps` CPU and elapsed-time accounting is broken in this container.** Process
      ages read as ~130 years and `%CPU` shows ~0 even for a pegged core; a
      `/proc`-based age calculation comes out *negative*. To tell whether a process
      is working or hung, sample `utime+stime` from `/proc/<pid>/stat` twice a few
      seconds apart — zero delta with state `S` means blocked. Use `top` in the
      container, or ask the host session for cgroup figures, when real numbers matter.
- Lesson (not a backlog item): **"CI didn't run" usually means the PR is unmergeable, not that GitHub dropped
      it.** A `pull_request` run cannot be created while `mergeable_state` is
      `dirty`, and nothing in the runs list or check-runs API says so — it simply
      shows nothing. Two pushes and a close/reopen were spent before checking
      `mergeable` on PR #57 (2026-09-13). Check `mergeable_state` first.
- [ ] G#47 / GH#86 — github: true — **The GitHub token lacks `actions: write`**, which blocked four different
      things on 2026-09-13: approving the 0.5.0 release, re-running a failed job
      (four times, each costing an empty commit), `workflow_dispatch`, and a
      subagent's attempt to post a PR comment via `gh`. Reads work fine — the
      `pending_deployments` endpoint even reports `current_user_can_approve: true`,
      which is about the *user*, not the token's scope. Adding `actions: write`
      would remove all four.
- [ ] G#48 / GH#87 — github: true — **Stress-testing the suite needs two Xvfb displays, not one.** There is no
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
- Lesson (not a backlog item): **Unmapped-widget geometry passes on Linux and fails only on Windows.** On
      X11 a widget whose pane was packed then `pack_forget()`'d keeps returning its
      last real `winfo_rootx()`/`winfo_width()`; on Windows Tk returns 0 and 1 for
      the same unmapped widget. A test measuring a widget in a hidden pane therefore
      passes here on stale-but-plausible numbers and fails only on the Windows leg —
      `AssertionError: 1 not less than or equal to 0` is the signature. Distinguish
      `winfo_x()` (parent-relative, assigned at pack time, valid while unmapped)
      from `winfo_rootx()` (absolute screen position, not valid). Cost story #24
      feature 2 a CI round. Make the pane genuinely visible before measuring.
- Lesson (not a backlog item): **Xvfb has no window manager, so WM-driven events never fire locally.** Most
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
- [x] **Pipeline-doc references — resolved 2026-09-11** (G#25 / GH#38 — github: true, PR #39).
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
## Session handoff — 2026-09-13

**Where things stand:**
- `main` is at `6519786`, CI green on all three platforms, **293 tests**. Local
  checkout clean, on `main`. No worktrees beyond the repo itself.
- **Nothing is in flight.** No agents running, no tests running.
- **Release 0.5.0 is built and parked on the owner's approval** — see the Release
  item under Housekeeping. That is the only thing blocking a shipped release.

Merged since the last handoff, each after one in-depth review and green CI:

| PR | What | Merge |
|---|---|---|
| #49 | Window height floor, `690 * s` → `WINDOW_MIN_H = 620` (G#28) | `8ac6e35` |
| #51 | Review protocol: one in-depth pass, not ten rounds (G#29) | — |
| #52 | GC teardown fix — the interpreter-shutdown abort (G#27) | `08eb891` |
| #56 | GC regression guard + corrected class enumeration (G#31) | `6626fdd` |
| #58 | macOS queued-scan flake (G#30) | `22815c9` |
| #57 | `test_holding_does_not_repeat` flake (G#32) | `6519786` |

**All three known flaky tests are now fixed.** The merge path should stop costing
an empty commit every few PRs, and a release should no longer hit a coin-flip test
that only runs at release time.

**Process change (owner, homelab-wide):** a pull request gets **one in-depth
review pass**, not ten rounds. `docs/REVIEW-PROTOCOL.md` was reworded to match; its
ten lenses are that pass's checklist, and `ANOTHER ROUND` means the PR needs more
work and the *new* diff gets a fresh review — never re-reviewing the same diff.

**Next:** nothing is queued. The largest open items are G#13's Macros tab and
G#12's calibration suite (both need a rebase before they build), G#23's macOS DPI
decision, and the accumulated review residue. `docs/ROADMAP.md` has the plan.

**Workflow:**
1. product-manager → ux-designer → developer → reviewer, each reading the previous
   stage's `docs/*.md`.
2. An approved cycle is pushed and PR'd without asking.
3. The review agent gives each PR one in-depth critical pass per
   `docs/REVIEW-PROTOCOL.md`, re-deriving claims rather than trusting the cycle's
   own docs, and posts it on the PR.
4. Merge on a `MERGE` verdict **and** green CI on all three platforms. A red leg
   routes back to the developer — never merge through it.
5. After a fix lands post-verdict, ask the same reviewer for a fresh pass on the
   new diff rather than paying for a full re-review.
6. Archive the cycle's `docs/*.md` into `docs/history/` **after** CI is green, and
   before the next cycle overwrites them. Two conflicts this session came from
   skipping that.
7. **Ask about cutting a release after every merge** (owner's standing rule).

**Running tests here:** the README's `xvfb-run` needs `xauth`, which this container
lacks. Start `Xvfb :99` directly and use a venv with `pynput`:
`DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` — 293 tests on
`main`. The venv lives in the session scratchpad and does not survive a container
reset. Slow tests (`test_chords_slow`) need `AFK_SLOW_TESTS=1` and run **only on
releases**. Keep a second display for load loops — see Housekeeping.

**The lessons worth carrying, in order of how much they cost:**

1. *A green local run is not evidence for behaviour this box cannot produce.*
   CI's Windows and macOS legs caught **eleven** things the cycle reviews missed.
   Xvfb has no window manager, so it never clamps a window, never sends a post-map
   root `<Configure>`, and never arbitrates focus between processes.
2. *A flake fix tends to work by blinding the test.* Sabotage-verify every one —
   three cases in two days, detail under Housekeeping.
3. *Anything matching on a command line matches the process doing the matching.*
   Cost a 15-hour hot loop and two self-inflicted `pkill`s — detail under
   Housekeeping.
4. Design-doc contrast arithmetic has been wrong **four** times; recompute with the
   real WCAG formula and sanity-check the calculator against white/black = 21:1.
   The compound scale `_dpi_s * UI_SCALE_FACTORS[...]` **multiplies**, so the worst
   case is low-DPI *and* the 90% step together (`s = 0.675`). `int()` truncates.
5. A comment asserting a hazard is worth testing before trusting it. Three in this
   codebase claimed safety properties that were simply false.

## Session handoff — 2026-09-15 (continued)

Main is at `691c42a` (item 1 merged since, PR #74 → `c142eee`; item 2, PR #76 → `c2db91d`; item 3, PR #77 → `c1c7977`; item 4, PR #78 → `ffe3fc3`; item 5, PR #80 → `edd4975`; 0.7.0 cut from `b853890`). Everything below is queued, in the order to work it, one cycle
at a time (product-manager → developer → reviewer → PR → independent PR review →
merge), auto-continuing to the next after each merge unless told to stop:

1. ~~**G#7 / GH#9 — `from_json` checks shape but not vocabulary.**~~ **Done, PR #74.** Ticket text is
   essentially the spec already: `hasattr(kb.Key, name)` accepts non-key attributes
   (should be `name in kb.Key.__members__`); an empty `char` slides through to a
   `"Key None"` label; a bool `vk` (`isinstance(True, int)` is `True`) becomes
   `"Key True"`; a negative or 200-char `vk`/`char` renders verbatim; a 4-key payload
   is silently truncated (`records[:MAX_CHORD]`) rather than rejected — prefer
   `if len(raw) > MAX_CHORD: return None`.
2. ~~**G#10 / GH#12 — review residue grab-bag.**~~ **Done, PR #76.** ROADMAP.md's schema-version item
   should say hotkey is the first structured value `settings.json` ever carried;
   `AfkAutoclicker.__init__` arms the global listener before `_timers` exists / before
   `_sync_settings`/`_drain_ui` run (move it or document why it can't move);
   `test_malformed_input_yields_none` never actually exercises a `None` blob because
   of `blob if blob else {}`.
3. ~~**G#18 / GH#22 — missing Button click-away test**~~ **Done, PR #77.**, plus a one-sentence comment on
   `_maybe_drop_focus` noting `root.bind_all("<Button-1>", ...)` is interpreter-wide
   (fires in every future `Toplevel`, including the G#36 dialog).
4. ~~**G#21 / GH#32 — updater hardening residue.**~~ **Done, PR #78.** A hex check in `fetch_checksums`; a
   comment correction in `_safe_names` (zipfile has stripped `..` since 3.6.2, tar
   still needs the check); a test for the superseded-worker race in `check_update`;
   `Store.save()` swallowing `OSError` silently.
5. ~~**G#22 / GH#33 (GitHub mirror existed all along) — warn when the~~ **Done, PR #80.**
   Minecraft interval minus jitter drops below 650 ms.** Real feature, needs a
   ux-designer pass: a muted hint under the Interval row below 650, bad-colour below
   550. Java only (Bedrock has no sweep cooldown).
6. **G#23 / GH#35 — macOS `_dpi_s` ~0.75 renders 5pt labels at 90% UI scale.** Decide:
   an `fs(base, s)` floor across ~20 font call sites, drop 90% on low-DPI displays, or
   accept it. Only verifiable via CI, no real Mac here.
7. **G#4 / GH#6 — click interval measures 25–40% slow on macOS CI.** Investigation
   only; may end in "accept and document" rather than a code fix. Needs a real Mac to
   fully resolve.
8. **G#38 / GH#67 — UI scale follows the window size.** Leo's decisions already
   recorded as comments on both tickets (2026-09-15): add "Auto" next to the fixed
   90/100/115/130% steps, Auto is the default; continuous scaling, not snapping to
   steps; screen-relative reference. Spec must handle: debounce/settle rebuilds during
   a drag resize (a full `_rebuild_ui()` per pixel is too slow); a font-size floor and
   rounding for sizes between the tested steps; must not fight `WINDOW_MIN_H` or the
   icon-rail collapse threshold mid-drag.
9. **G#12 / GH#14 — calibration suite for the review agent** (ten planted features).
   Rebase its branch first — check what's stale on it before resuming.
10. **G#13 / GH#15 — Macros tab story.** Blocked on the settings schema version bump
    (ROADMAP) — resolve that first, then run as a `story` workflow (multiple
    features), the largest item on this list. Rebase its branch first.

**Housekeeping done this pass:** closed 5 stale Gitea tickets for already-merged work
(#33 rename, #34 icon, #35 Windows fix, #36 update-log dialog, #37 top-aligned panes)
and Story #24's own tracking issue (Gitea #24 / GitHub #36) — none of these had ever
been closed despite the work being merged days-to-hours earlier, because GitHub's
"Closes #N" only closes GitHub's own mirror, never the Gitea original. **Check this
every time a PR merges** — Gitea needs its own explicit close.

**0.7.0 was released later on 2026-09-15** (see top of file). Before that: `main` had PRs #68/#70/#72/#73 beyond 0.6.0,
none cut into a version. Always ask Leo before cutting a release.
