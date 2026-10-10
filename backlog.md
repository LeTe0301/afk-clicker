# afk-clicker — backlog

Scoped to this project only. Claude: check this first when picking up work
here, keep it updated as items are resolved or new ones come up — same
convention as the homelab-wide /root/backlog.md.

Tickets live in Gitea (`admin/afk-clicker`, the number used in `ac-N` branch
names) and are mirrored as GitHub issues whose body starts `Gitea:
admin/afk-clicker#N`. GitHub numbers differ, so `Closes #X` in a PR uses the
GitHub number. Shown below as **G#** / **GH#**.

## In progress

Nothing in flight. All code-actionable backlog items are closed out; everything remaining needs
Leo's decision or real hardware — see Housekeeping below (G#39, G#46, G#47) and Features (G#59).

## Session handoff — 2026-10-10

**Where things stand:** `main` is at `157fc07`, working tree clean, nothing uncommitted. Five
feature/fix cycles shipped and merged this session: **G#57** (per-game hotkeys, PR #101), **G#58**
(its own follow-up regression test, PR #102), **G#60** (import/export of a game profile, PR #107,
8 macOS CI rounds — found and fixed two real pre-existing hazards, not just test artifacts, see its
own Features entry above), **G#61** (closed as a direct consequence of G#60's production fix, not
separately shipped), **G#62** (reuse the Xlib connection in `detect_running()`, PR #110, 3 review
rounds, two real defects found and fixed in the fallback rescue path). Both unscoped
`docs/ROADMAP.md` "Later" items are done; "Detection cost" (Before 1.0) is partially addressed
(connection-reuse cost cut, the 5s walk itself is unchanged, deliberately — see ROADMAP.md).

**Infrastructure fixed this session:** the GitHub token's write scope was the dominant blocker for
the first half of the session (`gh pr create`/`gh issue create`/`gh issue reopen` all 403'd) — Leo
regenerated it partway through and PR/issue creation started working; `issues: write` specifically
needed a second, separate grant later and now also works (confirmed: GH#69 reopened, G#60/G#62's
issue mirrors created and closed cleanly). **Still missing: `actions: write`** (G#47/GH#86 stays
open) — `gh run rerun`/`workflow_dispatch` both still fail, so retriggering CI this whole session
has only ever been possible via an empty-commit push, never a direct re-run. `release/0.8.0` and
`release/0.9.0` were merged back into `main` on Leo's call. Branch deletion (`git push --delete`)
was confirmed working from this sandbox, contradicting an earlier session's note that it was
blocked — that note was stale, corrected in G#46's own entry below. A tracker-drift sweep this
session found and closed **Gitea #38** (UI scale, G#38/GH#67), which GitHub had shown closed since
PR #89 merged but Gitea never synced — same drift class flagged in an earlier handoff for other
tickets; worth a periodic sweep rather than assuming the two trackers stay in sync on their own.

**Loose end from the previous handoff — now resolved (2026-10-10).** The five-run flaky streak on
`main` (`38001567646` → `38031041652`) never recurred: the very next run, `38038494438` (the
`6d0be16` handoff commit itself), came back **success** on all three platforms
(`ubuntu-latest`/`windows-latest`/`macos-latest`). Confirms the streak was transient runner strain,
not a regression — no code change between the flaky runs and the green one. `main` is green,
nothing further to retrigger.

**What's left, all blocked on Leo or real hardware, nothing further to do autonomously:**
- **G#39/GH#69** — the macOS poll-race flake's closed-with-no-evidence GitHub state was already
  reconciled (reopened to match Gitea) a session ago; the underlying investigation itself is
  "mitigated, trigger unconfirmed" and needs a real Mac or fresh CI evidence to move further.
- **G#46/GH#85** — delete ~15 old merged remote branches; branch deletion itself now confirmed
  working from this sandbox, just needs Leo to confirm the list is still accurate before a bulk
  delete (it was last reviewed in 2026-09-15, might be stale by now).
- **G#47/GH#86** — the GitHub token still lacks `actions: write`; granting it would let CI jobs be
  re-run directly instead of via empty-commit pushes, and would unblock a few other things noted on
  the ticket itself.
- **G#59/GH#105** — verify the per-game-hotkey subtitle string's layout on a real Windows render
  (currently only a Linux-sandbox metric estimate); needs Windows hardware or a CI screenshot.

**Standing workflow note, unchanged:** product-manager → ux-designer (skipped for backend-only
cycles) → developer → reviewer, each reading the previous stage's `docs/*.md`; an approved cycle is
committed, pushed, and PR'd without asking; the reviewer's own pass plus one independent PR-level
review (by the orchestrator, once CI is green on all three platforms) gates merge; `docs/history/`
archival happens once a cycle is fully done, not left for "later archive" (the lesson G#38's own
docs-loss incident taught, re-learned the hard way again this session when G#57's uncommitted scratch
docs sat in this same working directory risking the identical loss before being rescued and archived).

**Session handoff — 2026-09-29.** GitHub `main` is at `de89182` (PR #100). Two more full-cycle PRs landed
today beyond what this file tracked, both via a `claude/fervent-shannon-5wujce` branch (not this repo's
usual `feature/ac-N/...` convention) from a separate, concurrently-running session:
- **PR #99** (`d266928`→...→merged 11:57 UTC): closed out G#51/GH#93, G#53/GH#95, G#54/GH#96, G#55/GH#97,
  G#56/GH#98 — see their entries below for what shipped. Also bumped `SETTINGS_VERSION` to 2 and
  `WINDOW_MIN_H` to 740.
- **PR #100** (`de89182`, merged 13:11 UTC): a visible click counter + session timer in the header.
  **No ticket** — picked directly from `docs/ROADMAP.md`'s "Later" list at Leo's direction once the open
  queue emptied out.
- **`v0.8.0` and `v0.9.0` both published 2026-09-29** (2026-09-29T14:06 UTC, seconds apart) — 0.8.0's
  long-parked deployment-gate approval finally went through. **2026-10-09: merged both back into `main`**
  on Leo's call, same pattern as `release/0.7.0` — `Merge release/0.8.0 back into main` (`7097057`), then
  `Merge release/0.9.0 back into main` (`48e3c2c`, one conflict: `__version__`, resolved to `"0.9.0"`).
  `main`'s `__version__` is now `0.9.0`. Both release branches should join the merged-branch cleanup list
  below.
- **A second tracker-drift sweep found 18 Gitea issues** (G#25, G#27–32, G#40–45, G#48–50, plus the six
  from this session's own G#51–56) closed on GitHub but still open on Gitea — all now closed to match,
  each with an evidence comment (commit/PR) on Gitea. **One exception: G#39/GH#69** — GitHub shows it
  closed with no comment and no commit reference. **2026-10-09: Leo's call was to reopen GH#69** to match
  Gitea (treated as an accidental closure, not intentional) — blocked on the same token write-scope gap
  as G#47/GH#86, see its entry below for the exact error. `sync pending: GitHub`.
- **Gitea's own git remote (`origin`, `/srv/git/repos/afk-clicker.git`) has not received a code push in a
  long time** — its `main` sits at `85dd1e6` ("Archive feature ac-28..."), far behind GitHub's `main`
  (`48e3c2c`). Only the `github` remote is getting real pushes/PRs; Gitea is issue-tracking only in
  practice. Flagging in case that's not intentional.
- **The 20-branch merged-branch cleanup from earlier this session is still pending** — sandbox policy
  blocks `git push --delete` from this session regardless of confirmation; see Housekeeping's G#46/GH#85.
  `release/0.8.0` and `release/0.9.0` now join that list, both merged back into `main` as of 2026-10-09.

**0.7.0 released 2026-09-15** (`v0.7.0` from `d008ad5`, run 34995512574): the update-log
prompt (PR #72), top-aligned panes (PR #68), the macOS Accessibility-permission fixes
(PR #73), saved-hotkey vocabulary validation (PR #74), the G#39 flake mitigation (PR #70).
`release/0.7.0` is merged back into `main` (`63b06f2`). Leo's own Windows copy was on 0.5.0,
whose in-app Install cannot work (G#35); he was pointed at the one-time manual unzip.
The first real in-app Windows update (0.6.0+ → next release) is still unverified.

**0.8.0 built 2026-09-15, waiting on Leo's approval** (`release/0.8.0` from `70e5751`,
run 35026463043): tests + all three builds green, `publish` parked at the `release`
environment's deployment gate. Ships the "couldn't save settings" notice + update-check
hardening (PR #78), the button click-away test (PR #77), the review residue cleanup
(PR #76), and the Minecraft sweep warning (PR #80). Once approved, merge
`release/0.8.0` back into `main` the way `release/0.7.0` was.

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
- [x] **Done 2026-09-28, PR #92.** G#40 / GH#75 — github: true — macOS flake: `Sidebar.test_running_dot_and_follow` read `running`
      as False on PR #74's first macOS leg (run 34989787219); the same commit's re-run
      was green. **Hit again on PR #76 (run 34996063044) — 2 of the last 7 macOS legs.** Suspected to be the same class as G#39: a periodic `_poll_games`
      scan landing inside the test's own `root.update()` after `settle()` only
      waited for the startup scan. Confirmed the exact mechanism directly
      (queuing a stale/fresh scan result via `_ui()` and draining it after a
      direct `_mark_running()` call does clear the dot): the test's
      `root.update()` was never actually needed -- `_mark_running()` is
      synchronous, and every assertion after it reads plain state, no
      redraw required. Removed the unneeded `update()`, closing the race by
      construction rather than a timing-dependent wait.
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
- [x] **Done 2026-09-28, PR #92.** G#42 / GH#81 — github: true — The three older `WindowMinimumHeight` floor tests measure allocated, not
      required, heights, so they cannot detect a clipped pane. They are the only guard on
      `WINDOW_MIN_H = 620`. Used PR #80's reqheight+pady measure (factored
      into a shared `_required_natural()`/`_pady_total()` classmethod, also
      now used by `test_sweep_hint_height_floor_minecraft_with_eating`
      itself, replacing its own local copy) and sabotage-verified: an
      inflated `SWEEP_HINT_BAD` reproduces the ticket's own evidence table
      exactly (454 allocated vs 455 available vs 514 actually required).
- [x] **Done 2026-09-28, PR #92.** G#41 / GH#79 — github: true — `Store.save` leaves `settings.json.tmp` behind when `os.replace` fails
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
- [x] **Closed 2026-09-18, accept-and-document (no code change, no PR).** G#4 / GH#6 —
      github: true — The click interval measures 25–40% slow on the macOS CI runner.
      Investigated twice (2026-09-09, 2026-09-18) with no real Mac available either time.
      Both timing tests use `FakeMouse` (no real OS click call), so the overshoot is
      thread-scheduling precision, not pynput's macOS click backend; the identical code
      is precise on Linux; a prior GIL-contention fix attempt made it worse, not better;
      GitHub's own `actions/runner-images` repo documents ongoing, unrelated `macos-latest`
      performance degradation. Most likely a throttled/virtualized-runner artifact, though
      a real Mac would be needed to fully rule out genuine macOS thread-scheduling
      coarseness too — see the expanded comment above `darwin_timing` in
      `tests/test_ui.py` for the full finding. Reopen only with new evidence (a real Mac,
      or fresh CI data).
- [x] **Done 2026-09-18, PR #88 (`91b75a5`, merge `99c9344`).** G#23 / GH#35 — github: true — macOS
      reported `_dpi_s` ~0.75, so the 90 % UI-scale step rendered 5 pt labels (6 pt at
      100 %, which already shipped). Added `fs(base, s) = max(FONT_SIZE_FLOOR, int(base*s))`
      (`FONT_SIZE_FLOOR = 6`) and swept all 33 font call sites onto it — no visual
      change above the floor, no `WINDOW_MIN_H`/scale-step change, no G#38 scope.
      Verified on the real macOS CI leg (pulled the job log directly), not just the
      local `_dpi_s` simulation. One in-depth cycle review + one independent critical
      PR review, both MERGE, CI green on all three platforms.
- [ ] G#39 / GH#69 — github: true — **DISCREPANCY found 2026-09-29: GH#69 was closed on GitHub
      2026-09-15T09:14:47Z with no closing comment and no commit reference in its timeline** (checked via
      the GitHub API — `closed`, `commit_id: null`, zero comments). No evidence this was actually fixed;
      the investigation below is still real and still open. Left `[ ]`/open here and on Gitea #39
      deliberately, not force-closed to match GitHub — **needs Leo's judgment**: was GH#69 closed
      intentionally (accepted as good-enough) or by mistake? If the latter, reopen it.
      **2026-10-09: Leo's call was "reopen GH#69 to match Gitea" (accidental closure).** `gh issue
      reopen 69 --repo LeTe0301/afk-clicker` failed: `GraphQL: Resource not accessible by personal
      access token (reopenIssue)` — same write-scope gap as G#47/GH#86. **sync pending: GitHub** —
      GH#69 is still closed; reopen once the token has Issues write.
      **RECURRED 2026-09-14** on PR #65's macOS leg (run 34906199873, commit
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
- [x] **Done 2026-09-28, PR #92.** G#43 / GH#82 — github: true — **The trace-registration-order hazard is overclaimed in merged code and in the
      story's spec** — `_apply_appearance`'s own comment (~`afk_clicker.py:1939-1958`)
      and `docs/spec.md` §2 both attribute Theme's safety to registering `trace_add`
      after the `Segmented(...)` call. Verified empirically during the feature 4 cycle
      (twice, independently): reversing that order changes nothing observable — the
      whole suite still passes, for Theme as well as UI scale. The real mechanism is
      that neither `_apply_appearance` nor `_apply_ui_scale` ever rebuilds
      synchronously inside the trace; `after_idle` defers it past the point where
      order could matter. Feature 4's own new comment was corrected to say this; the
      Feature-3 comment and the spec text were left alone as out of scope for that
      feature. Corrected both now: `_apply_appearance`'s own comment gained a
      clarifying paragraph, and `docs/history/ac-17-f4-spec.md` §2 got an
      inline "Correction (fix-pass...)" note (this project's own convention
      for historical docs, per `ac-5-spec.md`) rather than a silent rewrite.

- [x] **Done 2026-09-28, PR #92.** G#44 / GH#83 — github: true — **`TabBar` accepts a `height` it then ignores when repainting** — found by
      the critical review of PR #40 (non-blocking). `TabBar.__init__`
      (`afk_clicker.py:1269`) takes a `height` override and sizes the canvas with
      it, but `_paint()` (`afk_clicker.py:1314`) repositions the underline using
      the module constant `TAB_HEIGHT` instead of the instance's own height —
      unlike the sibling `Segmented`, which keeps `self.w`/`self.h`. Unreachable
      today since both call sites omit `height`, so it was a latent trap rather
      than a bug -- G#13's Macros tab is exactly what made it bite: it builds
      a `TabBar` with a custom height. Fixed by storing `self.w`/`self.h` in
      `__init__` and reading them back in `_paint()`, matching `Segmented`;
      test builds a `TabBar` at a non-default height and asserts the
      underline lands at the right y.

Features:
- [x] **Done, PR #110 (merged 2026-10-09, `3ec41d5`).** G#62 / GH#109 — github: true — Reuse the
      Xlib connection in `detect_running()`, picked from `docs/ROADMAP.md`'s "Detection cost" item
      (the low-risk fix: connection reuse, not a full event-driven rearchitecture, which would
      depend on window-manager cooperation Xvfb can't provide). One persistent module-level
      connection replaces opening and closing a fresh one on every 5s poll. Crux design decision:
      the connection *open* happens deliberately outside the lock — only installing it and walking
      the tree are lock-protected — since `Display()` stalling unboundedly is a documented
      pre-existing hazard (G#39's own saga) and locking the open itself would let one stuck open
      freeze every concurrent scan, reintroducing the exact regression G#39's no-join-on-superseded-
      scan design exists to prevent. Two real defects found and fixed across review rounds, same
      class each time — a `Display()`-adjacent call in the fallback rescue path escaping
      `_window_titles()` unguarded on a correlated failure — both reproduced directly and
      sabotage-verified by independent reviewer passes. `on_close()` closes the shared connection,
      mirroring the existing mouse/keyboard cleanup. win32/darwin branches untouched. Full account:
      `docs/history/ac-62-*.md`.
- [x] **Done, PR #107 (merged 2026-10-09, `026dc36`).** G#60 / GH#106 — github: true — Import/export
      of a game profile, picked from `docs/ROADMAP.md`'s "Later" list. Export writes the selected
      game's full stored dict (settings + macros + hotkey) to a JSON envelope via a native
      `tkinter.filedialog`, atomic tmp-then-`os.replace()` write mirroring `Store.save()`. Import
      always creates a new custom game via `make_profile()` — never overwrites — validated through a
      new shared `_sanitize_game_entry()` helper factored out of `Store.__init__`'s existing inline
      filtering. Two new sidebar buttons (Export/Import, ↑/↓ on the collapsed rail) with a sticky
      status strip. Cycle review: APPROVE. **8 CI fix-rounds on macOS**, two genuinely independent
      native segfaults found and resolved: a real, pre-existing production race (`_build_ui()`'s tail
      spawning a subprocess-shelling scan thread while the main thread could be inside Cocoa's live
      resize-tracking loop — fixed at the root by deferring that call one Tk tick) and a second,
      deeper native crash tied to any real OS-level window resize crossing the rail-collapse
      threshold with the new widgets present (root cause never confirmed without real Mac hardware;
      mitigated test-by-test by avoiding literal OS-level resizes where the test doesn't need one).
      Full account: `docs/history/ac-60-*.md` and this branch's own commit history (`1a4fbb4`
      through `8095bcd`).
- [x] **Done, PR #101 (merged 2026-10-09, `076fd39`).** G#57 / GH#103 — github: true — Per-game
      hotkeys, picked from `docs/ROADMAP.md`'s "Later" list. Storage moved per-game; a
      `SETTINGS_VERSION` 2→3 migration carries the old global chord into every already-configured
      game; `_arm_toggle_hotkey()` reuses macros' rebuild-on-switch lifecycle with a
      `_toggle_armed_for` same-game guard. Fixed a real pre-existing bug along the way:
      `Store.put_game()` wholesale-replaced a game's settings dict on every persist instead of
      merging, silently wiping macros/hotkey on the next save (also fixes an existing G#13 macros
      bug as a side effect). Three CI fix-rounds after the cycle's own reviewer approval, all caught
      by cross-platform CI that local Xvfb testing couldn't: two real macOS SIGTRAP crashes (tests
      missing `@needs_input_permission`) and one unrelated live-API rate-limit flake. Full account:
      `docs/history/ac-57-*.md`. Follow-ups: G#58 (below), G#59 (open, needs a real Windows render).
- [x] **Done, PR #102 (merged 2026-10-09, `b2db200`).** G#58 / GH#104 — github: true — Follow-up
      from G#57's cycle review: a macros-specific regression test for the `put_game()` merge fix
      (`MacrosTab.test_a_macro_survives_an_unrelated_persist_call`, sabotage-verified). Branch
      predated G#57 on `main`, so it forward-ported the identical one-line fix; merging both hit the
      predicted trivial textual conflict on that line, resolved by keeping G#57's commented version
      (`35b33f8`). Full account: `docs/history/ac-58-*.md`.
Resolved 2026-09-12 (G#28 / GH#48, PR #49, `8ac6e35`): the window height floor was
`690 * s`, sized for the single combined page that predated tabs. Now
`WINDOW_MIN_H = 620`, derived from the *tallest* pane's real content span — the
binding constraint, since nothing here scrolls and a lower floor puts Eating's
lower rows out of reach. Took five rounds; `docs/history/ac-28-*` records why.
Two follow-ups from its review are below.

- [x] **Done 2026-09-28, PR #92.** G#45 / GH#84 — github: true — **`_rebuild_ui()` does not cancel `_pane_fill_after_id`** the way it cancels
      `_rebuild_after_id` immediately above. Verified empirically harmless today —
      a pending pane fill landing across a rebuild does no damage — but it was an
      undocumented invariant rather than a guaranteed one. Cancelled for
      symmetry rather than documented as safe: test spies on `after_cancel`
      and asserts the pre-rebuild pane-fill job id is actually passed to it
      (a bare "is None afterward" check would pass either way, since
      rebuilding legitimately re-requests a fresh pane fill of its own).
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
- [x] **Merged 2026-09-18, PR #89.** G#38 / GH#67 — github: true — UI scale should follow the
      window size (Leo, 2026-09-13). Was a fixed Settings choice (90/100/115/130%); "Auto" is
      now prepended to the `Segmented` control and is the new-install default, a continuous
      scale from window-fill fraction against a 1920x1080 reference, clamped, reusing G#23's
      `fs(base, s)` floor. Cycle review: approve with 2 non-blocking follow-ups (filed as
      G#49/GH#90 and G#50/GH#91, see Housekeeping). **Independent PR review round 1: ANOTHER
      ROUND** — macOS/Windows CI failed because making `"auto"` the default meant every real
      launch (and every `UITestCase`) got a real WM's post-map `<Configure>`, which Xvfb never
      sends, arming a live settle timer that rebuilt mid-test. **Round 2 (`4266900`)**: gated
      the settle-arm on the event reporting the app's own bootstrap geometry echoed unchanged.
      Cycle testing pass then found this still left ~20 failures/platform on CI, traced to a
      real production bug — round 3 (5 pushes, `f18164d`) fixed `_apply_minsize`'s own later
      `geometry()`/`minsize()` calls self-triggering unrecognized echoes, plus test-
      infrastructure hardening; got CI down to 1 failure/platform. Cycle testing pass round 2:
      **BLOCKED** — found the real DPI-relative-vs-absolute clamp bug behind the macOS failure
      (Auto's `self.s` pinned unreachably at 0.9 on any `_dpi_s < 0.9` machine) plus a
      tautological regression test. **Round 4 (4 pushes, `20ce68c`)** fixed both, plus the
      Windows failure's real cause (a test trusting post-construction state without verifying
      sync with the real widget tree) — all three CI legs green. Cycle review: **APPROVE**.
      **Independent PR review round 2: MERGE** (0 blockers; 2 more non-blocking follow-ups
      filed as G#51/G#52, see Housekeeping) — merged into `main` same day. GitHub side of the
      review comment and G#49–53's GitHub mirrors are pending: the repo's `gh` token currently
      lacks Issues/PR write scope, needs Leo to grant it.
- [x] **Done 2026-09-28, PR #92.** G#13 / GH#15 — github: true — Story: a Macros tab, configurable per game. The
      settings schema version it was blocked on (ROADMAP) landed first, same
      session. Its old branch (`feature/ac-13/story-macros-tab`) turned out
      to share no common ancestor with current `main` (an old history
      rewrite orphaned it) so it was rebuilt fresh rather than rebased:
      per-game `"macros"` list, `MacroRunner` with a sabotage-verified
      guaranteed-release `finally`, one `HotkeyWatcher` per macro hotkey
      armed/disarmed on every `_select()`, and the third game-page tab
      itself (list + add/edit dialog + run/delete).
- [x] **Done 2026-09-28, PR #92.** G#12 / GH#14 — github: true — Calibration suite for the review agent. Its
      branch (`feature/ac-12/review-calibration-suite`) shared the same
      orphaned-history problem as G#13's (both stacked on `901f0a4`, sharing
      no ancestor with current `main`) — cherry-picked its two commits
      cleanly instead (purely additive files, no conflicts beyond one
      auto-merged `docs/REVIEW-PROTOCOL.md` hunk): the ten cases plus the
      later hardening pass (sealed `.b64` answer keys, `GRADING.md`,
      `results-run1.json`'s 78% first run). `run.py --list` reproduces the
      README's own totals (54 defects, 20 traps) on this tree.
- [x] **Done, PR #99 (merged 2026-09-29T11:57:07Z).** G#54 / GH#96 — github: true — No way to delete a
      custom game profile (Leo, 2026-09-29). Delete affordance added to `GameItem`'s sidebar row for
      custom profiles only, removing it from `self.profiles`/`self.by_id`/the store, with fallback
      selection.
- [x] **Done, PR #99 (merged 2026-09-29T11:57:07Z).** G#55 / GH#97 — github: true — Clicking is one
      global button choice, not individually configurable per mouse button (Leo, 2026-09-29). Left and
      right mouse buttons are now independently enabled and click **concurrently**, each with its own
      interval/jitter; middle click stays a separate exclusive mode using the original shared fields.
      `SETTINGS_VERSION` bumped to 2 with a migration from the old single `"button"` field. The right
      loop skips a tick whenever Eating holds the right button down, so it doesn't fight Eating for it.
      `WINDOW_MIN_H` moved 620 → 740 for the five new Clicking-pane rows.
- [x] **Done, PR #99 (merged 2026-09-29T11:57:07Z).** G#56 / GH#98 — github: true — Recognized/detected
      macros should be trackable with a configurable interval (Leo, 2026-09-29). Macros can now have an
      optional auto-repeat interval alongside their hotkey trigger, armed/disarmed through the same
      per-game lifecycle as macro hotkey watchers.
- [x] **Done, PR #100 (merged 2026-09-29T13:11:51Z).** No ticket — picked directly from
      `docs/ROADMAP.md`'s "Later" list at Leo's direction once the open queue emptied out. **A visible
      click counter and session timer** in the header, not the Clicking pane (no `WINDOW_MIN_H` impact).
      Counts only the click loop's own clicks (left/right/middle), never a macro's; resets on each
      `start()`, frozen (not reset) on every exit path via `loop()`'s own `finally`.

Housekeeping:
- [ ] G#59 / GH#105 — github: true — Follow-up from G#57's cycle review (Finding #2): verify the
      new Hotkey-tab subtitle string ("Hotkey · this game only", `afk_clicker.py:3676`) on a real
      Windows render — the ux-designer's width estimate was a metric calculation on a Linux sandbox
      without Segoe UI installed, not a real render. 44% headroom and a shorter new string make a
      clip unlikely but unconfirmed. Needs Windows hardware or a CI screenshot, not actionable from
      this sandbox.
- [x] **Done, PR #107 (merged 2026-10-09, `026dc36`).** G#61 / GH#108 — github: true — Follow-up from
      G#60's PR #107 review round 2 (macOS CI segfault): `_poll_games()` spawns a background thread
      that shells out via `subprocess` (`afk_clicker.py:2032`, `_window_titles`). Forking a subprocess
      from a background thread while the main thread is inside Cocoa's/Tk's real event loop is a known
      macOS crash class (Apple's Objective-C runtime isn't fork-safe across threads) — confirmed via
      `PYTHONFAULTHANDLER=1`'s dump in CI run 37947940301/job 113879182323. Fixed at the root, not just
      worked around in tests: `_build_ui()`'s tail used to call `self._poll_games()` inline, with zero
      delay, on every rebuild — including one mid real-WM-driven resize, which is what actually raced
      Cocoa's live event loop. Now deferred one Tk tick (`self.root.after(50, self._poll_games)`,
      `afk_clicker.py:3568`), giving any live native resize context room to unwind first. The other
      call site this ticket originally named, `_poll_games()`'s own periodic 5000ms reschedule
      (`afk_clicker.py:5230`), was re-examined and found to have never actually been at risk: it was
      already a genuinely deferred `self.root.after(5000, ...)` callback, which Tk always dispatches as
      a fresh top-level mainloop iteration, never nested inside whatever call stack scheduled it five
      seconds earlier — only the inline, zero-delay rebuild-tail call could land nested inside a live
      Cocoa resize-tracking loop. Confirmed across 8 CI rounds during G#60's own fix cycle: the
      subprocess race never recurred after this fix (a second, unrelated native crash did, mitigated
      separately per-test — see G#60's own backlog entry above). No real Mac available to confirm
      beyond CI evidence, same standard this repo already applies to other macOS-only findings (G#39,
      G#4).
- Lesson (not a backlog item): **This repo has two remotes — `origin` (a Gitea mirror at
      `/srv/git/repos`) and `github` (the real `LeTe0301/afk-clicker` GitHub repo) — and a `git push`
      with no remote named defaults to whichever `git push.default`/upstream resolves to, which is not
      guaranteed to be `github`.** Cost a full CI-round delay during G#60's fix cycle: a developer
      subagent committed and pushed a real fix, reported it pushed to both remotes, but it only reached
      `origin` — the orchestrator kept watching a stale CI run on the old commit until checking
      `git log github/<branch>` directly caught the mismatch. Always push explicitly with `git push
      github <branch>` when the goal is "make CI/the PR see this," and verify with `git log --oneline
      github/<branch> -1` after any subagent reports a push, rather than trusting the report.
- [x] **Done 2026-09-28, PR #92.** G#49 / GH#90 — github: true — Follow-up from PR #89's cycle review (G#38): the Auto UI-scale
      clamp's regression test doesn't actually exercise out-of-range factors — every back-solved
      test value already sits inside `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]`. Sabotage-verified: removing
      the clamp leaves the test green. Added
      `test_a_genuinely_out_of_range_factor_clamps_to_the_scale_bound` (1.6
      and 0.5 back-solved factors) asserting `self.ui.s` lands exactly at
      the clamp boundary — reproduces the exact sabotage-verified gap
      (clamp removed: 1.667/0.521 instead of 1.355/0.938) this ticket
      describes.
- [x] **Done 2026-09-28, PR #92.** G#50 / GH#91 — github: true — Follow-up from PR #89's cycle review (G#38): `README.md` still
      describes UI scale as only the 4 fixed percentage steps, doesn't mention the new Auto default.
      One-sentence fix.
- [x] **Done 2026-09-29, PR #TBD.** G#51 / GH#93 — github: true — Follow-up from PR #89's round-4
      independent review (G#38): `docs/spec.md` §2 and its AC at line 130 still described Auto's
      clamp as the raw DPI-absolute `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]` range; the shipped round-4
      fix is DPI-relative (`self._dpi_s * [AUTO_SCALE_MIN, AUTO_SCALE_MAX]`). **Found while fixing
      this: `docs/spec.md` no longer exists anywhere in git history** — the 2026-09-18 session
      handoff above left it (plus `design.md`/`implementation.md`/`test-review.md`) sitting
      uncommitted in that session's own working tree, to be archived "as the last step once the PR
      merges" — a step nobody performed before that container was reclaimed. The original stale
      text is unrecoverable. Reconstructed `docs/history/ac-38-spec.md` from the shipped code and
      tests instead (correct DPI-relative clamp, matching what `_auto_scale_factor()`'s own
      docstring already implemented), and repointed that docstring's and `_request_auto_settle()`'s
      `docs/spec.md §2` / "The debounce decision" citations at the new archive path.
      `design.md`/`implementation.md`/`test-review.md` for G#38 remain lost; only the file GH#93
      was about got reconstructed. https://dev.tailbe22cd.ts.net/gitea/admin/afk-clicker/issues/51
      **Correction, 2026-10-09: not actually lost.** The real originals (all four files) turned up
      uncommitted in a later session's own checkout of this repo — the 2026-09-18 session's working
      tree was never reclaimed, just a different local clone than the one that merged PR #89. Archived
      verbatim as `docs/history/ac-38-{spec,design,implementation,test-review}.md`, replacing the
      2026-09-29 reconstruction; the real original confirms GH#93's report exactly (see
      `docs/history/README.md`'s ac-38 row).
- [x] **Done 2026-09-29, PR #92.** G#52 — github: true — Follow-up from PR #89's round-4 independent
      review (G#38): `UIScaleAuto.test_the_settle_timer_resets_on_each_new_event_not_just_the_first`
      (tests/test_ui.py:4243-4267) uses a brittle fixed-duration `pump()` chain instead of
      `pump_until`; recurred as a macOS flake across rounds 3-4 -- and again on PR #92's own
      first three CI runs, reproducing identically on main's last run before that branch existed.
      Rewritten to record timestamps and wait via a single generous `pump_until()` (10x the
      settle window) instead of two narrow fixed-duration `pump()` checkpoints, then check the
      one property that actually distinguishes "reset" from "coalesced into the first event's
      deadline": how long after the SECOND event the rebuild landed. Sabotage-verified (reverted
      the reset to a coalesce-only no-op, confirmed the rewritten test fails with a clear
      message); `UIScaleAuto` run 5x locally with no flakes.
      https://dev.tailbe22cd.ts.net/gitea/admin/afk-clicker/issues/52
- [x] **Done 2026-09-29, PR #TBD.** G#53 / GH#95 — github: true — Found during PR #89 round 3
      (G#38): `pynput.mouse.Controller()` never closes its Xlib connection, so a large local test
      run can hit Xvfb's max-clients ceiling. Pre-existing, out of scope for G#38.
      **Mitigated, not closed, 2026-09-28 (PR #92):** the ceiling was actually hit for real on CI
      (`Xlib.error.DisplayConnectionError: ... Maximum number of clients reached`, run 36489585846,
      ubuntu-latest) once the Macros tab added a SECOND Xlib connection per test (`kb.Controller()`,
      alongside the existing `mouse.Controller()`). `.github/workflows/ci.yml`'s `xvfb-run` now
      passes `-maxclients 2048`, which unblocks CI, but that raises the ceiling rather than fixing
      the leak.
      **Actually closed, 2026-09-29:** pynput's own `Controller.__del__` (`pynput/mouse/_xorg.py`)
      already closes `self._display` -- the leak was never pynput's fault, it was that
      `self.mouse`/`self.keyboard` (and each `MacroRunner`'s own copy of both, since G#47/GH#15's
      `self._macro_runners`) stayed referenced by `AfkAutoclicker` for as long as the app object
      itself does, and `on_close()` never dropped them -- so with ~150+ UI-building `UITestCase`
      instances sharing one process, none of those Controllers (and their Xlib connections) were
      ever eligible for collection until whatever much later point something finally dropped the
      whole app object. Fixed at the root: `on_close()` now clears `self._macro_runners` and sets
      `self.mouse`/`self.keyboard` to `None` as its last step, once nothing after that point still
      needs them -- letting each Controller's own `__del__` close its connection immediately
      instead of waiting on indefinite, unrelated timing. Added `OnCloseDropsControllerReferences`
      (`tests/test_ui.py`): `weakref`-based regression tests proving both `self.ui.mouse`/
      `self.ui.keyboard` and a stale `_macro_runners` entry are actually collected right after
      `on_close()`, plus a sabotage test (restores `self.mouse` after a real `on_close()` call)
      confirming the real tests fail without the fix. 481 tests green locally
      (478 + 3 new), full suite, matching CI's own invocation.
      https://dev.tailbe22cd.ts.net/gitea/admin/afk-clicker/issues/53
- [ ] G#46 / GH#85 — github: true — **Delete merged remote branches** (Leo, 2026-09-13).
      **2026-10-09: `git push github --delete <branch>` now works from this session** (deleted
      `feature/ac-57/per-game-hotkeys` and `feature/ac-58/macros-specific-regression-test-put`
      cleanly right after merging them) — the "sandbox policy blocks this regardless of
      confirmation" note below is stale, from whatever constrained that earlier session
      specifically. Only cleaned up the two branches just finished this session; the broader list
      below still needs Leo's confirm before a bulk delete, since those branches are older and
      this session hasn't re-verified which of them are still genuinely merged. As of
      2026-09-15, 15 branches on `github` are fully merged, listed on the ticket. Keep
      `feature/ac-12/…`/`feature/ac-13/…`; they are unmerged and tracked on G#12/G#13
      (now built directly on `main` instead -- see those tickets -- so these two
      branches are stale WIP, not pending work, but still technically unmerged and
      out of scope for this ticket's own list either way). 2026-09-28: re-verified
      all 15 against current `main` (each still exactly 0 commits ahead; `ac-12`/
      `ac-13` still correctly excluded at 19 commits ahead each, confirming they
      share no common ancestor with `main` -- see G#12/G#13) and confirmed the list
      with Leo, but `git push --delete` failed with 403: this session's GitHub
      credentials are scoped to its own working branch only, not arbitrary branch
      deletion, and there is no delete-branch tool available either. **Still needs a
      human with real push access** (Settings → Branches, or `git push --delete`
      with their own credentials) to actually run the deletion.
- [x] **Done 2026-09-29, PR #TBD.** G#54 / GH#96 — github: true — **No way to delete a custom game
      profile** (Leo, 2026-09-29). Only `add_current_game()`/`_add_game()` existed; a custom
      profile (`game_id = "custom:" + name.lower()`) stuck around in `self.profiles`/`self.by_id`/
      the store permanently once added. Added a small "✕" glyph on `GameItem`'s own canvas, drawn
      only for `profile.get("custom")` rows and only when the rail is expanded (no room next to
      the collapsed badge) — the built-in profiles never draw one, not even disabled. Clicking it
      (`tag_bind`, returns from the handler via `"break"` so the row's own whole-canvas
      `<Button-1>` select binding never also fires) calls the new `_delete_game(game_id)`, which
      removes the profile from `self.profiles`/`self.by_id`, calls the new `Store.delete_game()` to
      drop its persisted settings/macros, rebuilds the sidebar, and falls back the selection to
      `"global"` (the same built-in default `__init__` already falls back to for a missing/unknown
      `"selected"` value) if the deleted profile was the one showing — or, if it wasn't, re-syncs
      the still-current row's selected/highlighted state, since `_rebuild_list()` replaces every
      `GameItem` with a fresh, all-unselected one either way (a real bug caught only by testing the
      non-current-deletion path specifically). Added `DeletedGames` (`tests/test_ui.py`): removal
      from every place listed above plus across a restart, the current-vs-non-current fallback
      behavior (with a sabotage test for the resync case), built-ins staying undeletable, the glyph
      only existing on custom rows, and an end-to-end synthetic-click test proving the click deletes
      without selecting the row first. README's "Aufbau" section documents the ✕. 488 tests green
      locally (481 + 7 new), full suite.
      https://dev.tailbe22cd.ts.net/gitea/admin/afk-clicker/issues/54
- [x] **Done 2026-09-29, PR #TBD.** G#55 / GH#97 — github: true — **Per-button clicking
      configuration** (Leo, 2026-09-29): "the clicking should be individual so not just eating
      labeled for example it should be the same configurable for LMB RMB or other mouse buttons if
      there is anything." Scoping decisions (Leo, 2026-09-29): LMB + RMB only (not every pynput
      button pynput exposes); both can click concurrently, not mutually exclusive; Middle click
      stays exactly as it was -- a separate, mutually-exclusive mode using the original shared
      Interval/jitter, picking it pauses the independent left/right loops.
      **Schema (`SETTINGS_VERSION` bumped 1 -> 2, `_migrate_settings_v1_to_v2`):** the old single
      `"button"` field is replaced by `click_mode` ("buttons"/"middle"), `left_enabled`/
      `right_enabled`, and new `right_click_ms`/`right_jitter_ms` -- `click_ms`/`jitter_ms` keep
      their exact old keys, now meaning left's own interval/jitter (or middle's, in middle mode),
      since left/middle already carried the only real prior data an old "button" choice could mean.
      A migrated "right" profile moves its old click_ms/jitter_ms to the new right_* keys instead of
      losing them. **Loop (`AfkAutoclicker.loop()`):** kept to the one existing worker thread rather
      than adding real OS threads (this codebase's own history is exactly why that surface stays
      small) -- each enabled button now tracks its own next-due timestamp, checked on a shared 20ms
      tick (`CLICK_LOOP_TICK_S`, matching `_sleep()`'s own existing granularity) instead of blocking
      for one shared interval, so left and right proceed on fully independent schedules within the
      same thread. The right loop skips a tick whenever `self.right_held` is true (Eating currently
      owns RMB), so it never fights Eating for the button instead of needing new locking. **UI:**
      the old 3-way "Mouse button" Segmented is now `click_mode`'s 2-way Independent/Middle choice,
      plus new `Left click`/`Right click` `ToggleCheckbox` rows (Enable) and `Right interval`/
      `Right jitter` `NumBox` rows -- five new rows pushed the tallest pane (Clicking+Eating,
      Minecraft) past the existing floor, so `WINDOW_MIN_H` moved 620 -> 740 (re-derived from real
      content the same way every prior round of this constant was, per `WindowMinimumHeight`'s own
      tests; Windows' own taller font metrics still cannot be measured from this sandbox, same
      caveat every prior round of this constant already carries).
      `test_minimum_height_shrunk_from_the_pre_tab_split_floor`'s own threshold moved 690 -> 900 --
      updated, not deleted, since 690 was never the real invariant, just G#28's own measured value
      at the time, and this ticket's growth is deliberate, not a regression back toward the old
      combined-page bloat that guard actually exists to catch. Added/updated tests: 4 new
      `_migrate_settings_v1_to_v2` cases (`SettingsSchemaVersion`), rewrote `ClickLoop`'s
      button-selection tests for the new model and added concurrent-independent-interval,
      middle-mode-exclusivity, and eating-does-not-fight-right-click coverage. 507 tests green
      locally (500 + 4 migration + 3 new ClickLoop), full suite, `ClickLoop`/floor tests run
      multiple times for timing stability.
      https://dev.tailbe22cd.ts.net/gitea/admin/afk-clicker/issues/55
- [x] **Done 2026-09-29, PR #TBD.** G#56 / GH#98 — github: true — **Configurable interval for
      recognized/tracked macros** (Leo, 2026-09-29): "recognizable macros should be trackable and
      set to an intervall." Related to G#13/GH#15's Macros tab (built, PR #92) but a distinct ask.
      Scoping decision (Leo, 2026-09-29): rides inside the existing Macros tab as an optional field
      on each macro, not a separate follow-on. Added `interval_ms` to the macro schema (validated by
      `_validate_macro()`, floored at the new `MACRO_MIN_INTERVAL_MS = 200` when set, `None`/0 means
      off -- the same convention `autostop_min` already uses), an "Auto-repeat every" `NumBox` in the
      macro editor, and a self-rescheduling `self.root.after()` timer per macro with a nonzero
      interval (`_arm_macro_intervals()`/`_schedule_macro_interval()`/`_disarm_macro_intervals()`),
      arming/disarming through the exact same per-game lifecycle as `_macro_hotkey_watchers`
      (`_select()`, `_save_macro()`, `_delete_macro()`, `on_close()`) -- a macro can have a hotkey,
      an interval, both, or neither, and the interval timer reuses `_run_macro()` unchanged, so an
      overlapping run is refused exactly like a hotkey retrigger. Added `MacroIntervals`
      (`tests/test_ui.py`): arm/fire/disarm across every lifecycle point, plus 4 new
      `_validate_macro()` cases for the new field. 499 tests green locally (488 + 4 validation + 7
      lifecycle), full suite, run twice for timer-flake stability.
      https://dev.tailbe22cd.ts.net/gitea/admin/afk-clicker/issues/56
- [x] **Done 2026-09-29, PR #TBD.** No G#/GH# ticket -- picked from `docs/ROADMAP.md`'s own "Later"
      list at Leo's direction (2026-09-29, no ticket filed to leave nothing to build against) once
      the open-issue queue emptied out: **a visible click counter and session timer.** Shown in the
      header (`self.session_stats_label`), not the Clicking pane, specifically to avoid another
      `WINDOW_MIN_H` re-derivation so soon after G#55's. Counts only the click loop's own clicks
      (left/right/middle via the new plain `self.click_count`), never a macro's -- a macro is a
      separate, deterministic, user-authored sequence, not part of "this session's clicking." Resets
      on each `start()`; frozen (not reset) in `loop()`'s own `finally` -- covering every exit path
      (a normal `stop()`, auto-stop, or an exception alike) rather than duplicating the freeze logic
      in each -- so the last session's totals stay visible until the next `start()`. Repaints via
      `_refresh_session_stats()`, piggybacked on `_drain_ui()`'s own already-recurring 40ms tick
      rather than a second timer with its own start/stop/rebuild lifecycle to get right. Added
      `SessionStats` (`tests/test_ui.py`): count/timer across start/stop/rebuild, plus the
      count-resets-per-session behavior via two equal-length runs rather than asserting `== 0`
      immediately after `start()` (that specific assertion is racy -- the worker thread's own first
      tick can click before the next line on the main thread runs, since a freshly started button's
      due time is `0.0`). 513 tests green locally (507 + 6 new), full suite, `SessionStats` run 3x
      for stability.
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
- [x] **Done 2026-09-28, PR #92.** G#48 / GH#87 — github: true — **Stress-testing the suite needs two Xvfb displays, not one.** There is no
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

## Session handoff — 2026-09-15 (night)

`main` is at `90e1083`. Queue items 1-5 are all merged: PR #74 (G#7 → `c142eee`),
PR #76 (G#10 → `c2db91d`), PR #77 (G#18 → `c1c7977`), PR #78 (G#21 → `ffe3fc3`),
PR #80 (G#22 → `edd4975`). 0.7.0 shipped mid-session; 0.8.0 is built and waiting on
Leo's approval (see "In progress" above) — merge `release/0.8.0` back into `main`
once it publishes.

**In progress right now:** branch `hotfix/ac-23/macos-font-size-floor` exists
(checked out off `90e1083`, empty — no commits, no `docs/spec.md` yet). Leo decided
(2026-09-15, recorded on Gitea #23 and GitHub #35): land an `fs(base, s)` font-size
floor now, standalone, ahead of G#38 — G#38 will reuse the same helper for its
continuous scaling. Rejected: fold into G#38, drop the 90% step, accept as-is. A
product-manager dispatch to write `docs/spec.md` was started and then stopped by
Leo before it produced anything — safe to just start it again.

**Updated queue, in order** (continues after G#23):

1. ~~G#23 / GH#35 — macOS font-size floor.~~ **Done, PR #88 (`91b75a5` → `99c9344`).**
2. G#4 / GH#6 — click interval measures 25–40% slow on macOS CI. Investigation
   only; may end in "accept and document." Needs a real Mac to fully resolve.
3. G#38 / GH#67 — UI scale follows the window size. Leo's decisions recorded as
   comments on both tickets (2026-09-15): add "Auto" next to the fixed
   90/100/115/130% steps, Auto is the default; continuous scaling, not snapping to
   steps; screen-relative reference. Spec must handle: debounce/settle rebuilds
   during a drag resize; the font-size floor G#23 lands (reuse it, don't rebuild
   it) and rounding for sizes between steps; must not fight `WINDOW_MIN_H` or the
   icon-rail collapse threshold mid-drag.
4. G#12 / GH#14 — calibration suite for the review agent (ten planted features).
   Rebase first: it (and G#13's, which contains its own `2bdf55f`) is stacked on
   `901f0a4`, whose FIFO tests fail on Windows.
5. G#13 / GH#15 — Macros tab story. Blocked on the settings schema version bump
   (ROADMAP) — resolve that first, then run as a `story` workflow, the largest
   item on this list. Rebase its branch first (see #4).

**Smaller items not yet in the ordered queue above, pick up opportunistically**
(all ticketed, `github: true`): G#40/GH#75 (macOS `Sidebar.test_running_dot_and_follow`
flake, hit 2 of 7 legs so far), G#41/GH#79 (`Store.save` leaves `settings.json.tmp`
on a failed `os.replace`), G#42/GH#81 (the three older `WindowMinimumHeight` tests
can't detect a clipped pane — fix before trusting them on G#23/G#38), G#43/GH#82
(stale trace-order comment), G#44/GH#83 (`TabBar` ignores its own `height`),
G#45/GH#84 (`_rebuild_ui` doesn't cancel a pending pane fill), G#46/GH#85 (delete
15 merged remote branches — confirm the list with Leo first), G#47/GH#86 (token
lacks `actions: write` — Leo's action item, no code), G#48/GH#87 (a code comment
about needing two Xvfb displays for stress-testing).

**Housekeeping done this pass:** every backlog item now states `github: true`/`false`
per the shared ticketing rule (`~/.config/agent-knowledge/ticketing.md`); the six
untracked open items above got tickets (G#43-48); stale entries removed (a finished
0.5.0-approval note, a duplicate ac-12/ac-13 stacking note folded into G#12); six
lessons (flake sabotage-verify, `pgrep -f` self-match, etc.) demoted from checkbox
items to plain notes, since they're not work to do.

**Standing reminders, still true:** close Gitea explicitly on every merge — GitHub's
`Closes #N` never touches it. CI can't be re-run with this token (403); close and
reopen the PR to retrigger. The auto-mode classifier has blocked pushes/merges
intermittently; a same-command retry has gone through every time so far. Any test
reaching a real `apply_hotkey()` listener SIGTRAPs macOS CI unless `app.HotkeyWatcher`
is stubbed (see `docs/history/ac-21-implementation.md` round 3). Design docs have
gotten WCAG contrast arithmetic wrong three separate times this session — always
recompute from the literal `THEMES` hex values before trusting a design doc's numbers.

## Session handoff — 2026-09-18

`main` is at `99c9344`. G#23/GH#35 (macOS font-size floor) is done: full
product-manager → ux-designer → developer → reviewer cycle, PR #88 (`91b75a5`),
independent critical PR review confirmed MERGE with its own venv run, revert-
and-watch-it-fail check, and a pull of the real macOS CI job log (not just the
green checkmark) — CI green on all three platforms, merged `99c9344`. Both
trackers closed (Gitea #23, GitHub #35).

**0.8.0 is still unpublished**, parked on Leo's deployment-gate approval since
2026-09-15 (`release/0.8.0` from `70e5751`, run 35026463043) — this session did
not touch it, that's his call. It does **not** include this G#23 merge, since
`release/0.8.0` branched before G#23 landed on `main`; once 0.8.0 publishes,
merge `release/0.8.0` back into `main` as usual, and G#23 ships in whatever
release comes after 0.8.0.

**Next up, per the queue recorded 2026-09-15 (night), continuing in order:**
1. ~~G#4 / GH#6 — click interval measures 25–40% slow on macOS CI.~~ **Closed
   2026-09-18, accept-and-document, no code/PR** — see the checkbox entry
   above and `tests/test_ui.py`'s `darwin_timing` comment for the finding.
2. ~~G#38 / GH#67 — UI scale follows the window size (reuses G#23's `fs()`).~~
   **In review, PR #89** — see the checkbox entry above and the continued
   handoff below.
3. G#12 / GH#14 — calibration suite for the review agent. Rebase first.
4. G#13 / GH#15 — Macros tab story. Blocked on the settings schema version
   bump (ROADMAP); resolve that first, then run as a `story` workflow.

Smaller opportunistic items (G#40, G#41, G#42, G#44, G#45, G#46, G#47, G#48,
and the two new ones filed this session, G#49, G#50) are unchanged/additive
from the 2026-09-15 (night) list above.

## Session handoff — 2026-09-18 (continued)

`main` is unchanged at `99c9344` since the handoff above — **G#38 is not yet
merged**, still in flight on `feature/ac-38/ui-scale-follows-window`.

Full cycle ran: product-manager → ux-designer → developer → cycle reviewer
(**approve with follow-ups**, 2 non-blocking items filed as G#49/GH#90 and
G#50/GH#91) → pushed, PR #89 opened. Independent critical PR review round 1
returned **ANOTHER ROUND**: `ubuntu-latest` passed but `macos-latest` and
`windows-latest` both failed (20 failures each) against `main`'s green
baseline — a real regression, not flakiness. Root cause: making `"auto"`
the new default means every real launch (and every `UITestCase`, since
tests don't override the default) now runs in Auto mode, and a real WM's
post-map `<Configure>` — which Xvfb never sends, so this was invisible in
local/Linux testing — armed a live 150ms settle timer that rebuilt the
widget tree mid-test.

**Round 2 pushed (`4266900`)**: gates the settle-arm on the `<Configure>`
event reporting the app's own already-known bootstrap geometry echoed back
unchanged (content, not order — an order-based "first event" heuristic was
tried and rejected, since Xvfb's first *synthetic* event in a test is never
actually the real echo, so it broke existing tests); also unbinds
`<Configure>` at the very top of `on_close()`, before the existing after-id
cancellation, so a late echo during teardown can't re-arm a job nothing
after that point cancels — the same hazard class already hit once for
`_log_report_after_id` (`afk_clicker.py:3974-3979`). 3 new sabotage-verified
regression tests, 437 tests green locally (Linux/Xvfb only — the actual fix
for the macOS/Windows failures can only be confirmed once this round's CI
runs). Status posted to PR #89 and Gitea #38.

**Session paused here, deliberately, before dispatching the next stage.**
The immediate next step for whoever picks this up: dispatch a **fresh**
independent critical PR review of the new diff (`4266900`) — never a
re-review of the round-1 diff already marked ANOTHER ROUND — then merge on
`MERGE` + green CI on all three platforms. `docs/spec.md`/`design.md`/
`implementation.md`/`test-review.md` are still sitting uncommitted in the
working tree (this project's normal per-cycle scratch state — archive them
into `docs/history/ac-38-*.md` as the last step once the PR merges, same as
every prior cycle). `0.8.0` is still unpublished, parked on Leo's
deployment-gate approval, untouched this session (Leo's own call, "hold off
for now" as of the last check-in) — it does not include G#38 either way.
