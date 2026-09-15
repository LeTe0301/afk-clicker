# docs/history/

Archived docs from past pipeline cycles (product-manager -> ux-designer ->
developer -> reviewer, plus an independent PR-review pass). Each cycle's
`docs/spec.md`/`docs/design.md`/`docs/implementation.md`/`docs/test-review.md`
(and, for a story, its `docs/story.md`) is scratch that lives only in a
worktree and is never committed to `main` — it gets overwritten by the next
cycle that reuses the same working directory. That's a problem the moment
code carries a comment like "see docs/spec.md §2" or "docs/test-review.md
Finding #1": which document, from which cycle, is not answerable from `main`
alone.

This directory exists so those comments have something durable to point at.
When a cycle's doc is worth citing from a comment, it is copied here
**verbatim** — not edited, reformatted, or "corrected" to match what shipped.
The value of an archived doc is that it records what was actually decided or
found *at the time*, including rejected alternatives, defects that were later
fixed, and things a later cycle superseded. Treat every file here as a
historical snapshot, not living documentation.

`spec.md`, `story.md`, `design.md`, `implementation.md`, and `test-review.md`
are all in scope — whichever of a cycle's own docs a comment actually cites.
A cycle's own PR-review round documents (from `handoff/pr-reviews/`, an
independent review pass distinct from the cycle's own `test-review.md`) are
archived too, but **only when a comment specifically cites a finding that
lives there and nowhere else** — see "PR-review docs" below.

## Naming

`docs/history/<ticket>[-f<N>]-<type>.md`, where `<ticket>` is the repo's own
`ac-<gitea-ticket-number>` identifier — the same one already used for branch
names (`feature/ac-17/...`) and worktree directories (`ac-17-f3a`), and
`<type>` is `spec`, `story`, `design`, `implementation`, or `test-review`. A
multi-feature story appends `-f<N>` (or `-f<N><letter>` when a feature itself
split further, e.g. `-f3a`/`-f3b`) for each feature's own docs; a
single-feature ticket has no `-f<N>` (e.g. `ac-3-spec.md`). The story's own
breakdown doc is `<ticket>-story.md` (no `<type>` suffix needed — there's only
one kind of story doc).

This reuses the identifier scheme the repo already has everywhere else
(worktree names, branch names, the `archive/` folder these were pulled from)
instead of inventing a second numbering system — a future story adds files
the same way today's did, and the name alone says which ticket, which feature
within it, and which kind of document a file is.

### PR-review docs

**Extension to the scheme above**, added when a comment turned out to cite a
PR-review finding rather than the cycle's own `test-review.md` (some code
comments say "docs/test-review.md's PR-review Finding #N" — worded as if it
were the cycle doc, but the finding in question is only in the PR-review
round document, not in the cycle's own `test-review.md`). These are named
`<ticket>[-f<N>]-pr<PR#>-review[-r<round>].md`, e.g.
`ac-17-f3a-pr30-review.md` (PR #30's first review round; a later round would
be `-r2`/`-r3`, matching the source filenames' own `-r2`/`-r3` suffixes).

This type is added on demand, one file at a time, only when a specific
comment's citation was verified to require it — not archived speculatively.
"Archive it in case something someday cites it" is exactly backwards for
`handoff/pr-reviews/`: unlike a cycle's own four docs (which are always
worth keeping once anything in the cycle is cited), a PR can accumulate
several review rounds where most of the content duplicates or supersedes the
last, so pulling in every round for a cycle nobody happens to cite from would
add clutter without a documented reason to keep it current.

## Going forward

**This directory only cleans up a backlog — on its own it does not stop the same problem recurring.**
Nothing in this repo's tooling currently prevents the *next* cycle from overwriting a worktree's
`docs/spec.md`/`design.md`/`implementation.md`/`test-review.md` (and `story.md`, for a story) before anyone
copies them out. `git log --all` on any of these paths in a per-cycle worktree returns nothing — they have
never been committed, on any branch, at any point — so once a cycle's docs are overwritten, the content is
gone. Left unaddressed, every future cycle regenerates the exact "N unresolvable references" outcome this
directory was created to fix.

**Concrete convention: archiving a cycle's own docs into `docs/history/` under this file's naming scheme is a
required last step of that cycle's own reviewer approval.** The reviewer copies the cycle's `spec.md`/
`design.md`/`implementation.md`/`test-review.md` (and `story.md`, for a story) into `docs/history/` and
updates this README's table as part of writing its own `docs/test-review.md` verdict, *before* handing
control back to product-manager for the next cycle. This is the right point in the pipeline because:

- it's the **last stage to touch the worktree** before a subsequent cycle's product-manager/developer
  overwrite the same `docs/*.md` files;
- it's already the stage that **reads and validates** those documents' final content, so archiving them is
  near-zero additional cost, not a new investigation;
- it removes the failure mode entirely, rather than requiring some later cycle's developer to reconstruct
  lost context via `git blame` and cross-referencing PR reviews (as this ticket's own `docs/implementation.md`
  had to do for the references that predate this convention).

Absent this step (or an equivalent one written into the pipeline's own global conventions), the same
unrecoverable-reference outcome will recur for every story after this one.

## Current contents

| File | Cycle |
| --- | --- |
| `ac-3-spec.md`, `ac-3-test-review.md`, `ac-3-implementation.md` | ac-3 — updater checksum verification |
| `ac-14-spec.md`, `ac-14-design.md`, `ac-14-test-review.md`, `ac-14-implementation.md` | ac-14 — number fields focus/window resize |
| `ac-15-spec.md`, `ac-15-test-review.md`, `ac-15-implementation.md` | ac-15 — Minecraft default interval sweep |
| `ac-19-implementation.md` | ac-19 — focus test races on macOS (hotfix; no spec/design/test-review archived — the developer's own implementation notes are the only doc that exists for this cycle) |
| `ac-17-story.md` | Story #17 — themes that follow the system, and a Settings tab (full breakdown) |
| `ac-17-f1-spec.md`, `ac-17-f1-design.md`, `ac-17-f1-test-review.md`, `ac-17-f1-implementation.md` | Story #17, Feature 1 — theme data + Quartz shape language |
| `ac-17-f2-spec.md`, `ac-17-f2-test-review.md`, `ac-17-f2-implementation.md` | Story #17, Feature 2 — OS light/dark detection (no design.md exists for this cycle) |
| `ac-17-f3a-spec.md`, `ac-17-f3a-design.md`, `ac-17-f3a-test-review.md`, `ac-17-f3a-implementation.md`, `ac-17-f3a-pr30-review.md` | Story #17, Feature 3a — tab navigation + Settings tab (rebuild mechanism + Appearance) |
| `ac-17-f3b-spec.md`, `ac-17-f3b-design.md`, `ac-17-f3b-test-review.md`, `ac-17-f3b-implementation.md` | Story #17, Feature 3b — move Updates into Settings |
| `ac-17-f4-spec.md`, `ac-17-f4-implementation.md` | Story #17, Feature 4 — UI scale (no design/test-review in the source archive; `implementation.md` was pulled from the live `ac-17` worktree, not `handoff/`, since this cycle was never snapshotted there — see the implementation write-up's "Live-worktree source" note) |
| `ac-24-story.md` | Story #24 — full breakdown (5 features) |
| `ac-24-f1-spec.md`, `ac-24-f1-design.md`, `ac-24-f1-test-review.md`, `ac-24-f1-implementation.md` | Story #24, Feature 1 — Row value-column alignment. Archived pre-emptively, ahead of any comment being re-pointed at it: PR #37 (still open on its own branch) adds two `docs/spec.md` citations for this cycle, which would otherwise dangle the moment Feature 2 overwrites `ac-24`'s `docs/spec.md` — this entry exists so PR #37 has a target to re-point at, not because a comment on this branch cites it yet. |
| `ac-24-f2-spec.md`, `ac-24-f2-design.md`, `ac-24-f2-implementation.md`, `ac-24-f2-test-review.md` | Story #24, Feature 2 — Horizontal tab bar (`Hotkey \| Clicking`, `Appearance \| Updates`). Four review rounds; the last two were spent on a `NumBoxFocus` flake that turned out to be a property of the test harness, not the feature — two Tk processes sharing one window-manager-less Xvfb display contend for X input focus, which is a single global resource there. The test-review's round 4 records the controlled measurements. |
| `ac-24-f3-spec.md`, `ac-24-f3-design.md`, `ac-24-f3-implementation.md`, `ac-24-f3-test-review.md` | Story #24, Feature 3 — the icon rail (sidebar collapses to icon-only below a width threshold, window floor rederived). Merged in PR #41. Two rounds of CI-only defects: the `<Configure>` handler was bound before the first `_build_ui()` returned, so a genuine window-manager resize could reenter the rebuild mid-construction and crash on `click_ms` — invisible under Xvfb, which has no WM and never generates that event. Read this cycle's round 3 before adding any resize- or rebuild-driven behaviour. |
| `ac-24-f4-spec.md`, `ac-24-f4-design.md`, `ac-24-f4-implementation.md`, `ac-24-f4-test-review.md` | Story #24, Feature 4 — each tab pane fills its own leftover vertical space. Merged in PR #42. Read the design doc's own limitation section before reopening this: a top/bottom spacer pair can only *relocate* empty space, so centring halves the largest band (630px to 315px) but cannot remove it, and distributing slack between cards does nothing because three of the four panes hold a single card. The cause is the `minh = 690 * s` floor, tracked separately in `backlog.md`. |
| `ac-24-f5-spec.md`, `ac-24-f5-design.md`, `ac-24-f5-implementation.md`, `ac-24-f5-test-review.md` | Story #24, Feature 5 — the flat minimal restyle. Merged in PR #43, the last of the five. Two things worth knowing before touching this chrome again: `CARD_R` was a radius *and* a width term in `CARD_INNER_W` *and* `card()`'s inset, so the inset role now lives in `CARD_PAD` and `CARD_INNER_W` must stay 396; and the reference's green was rejected on measurement, not taste — `#7EC700` is 8.60:1 on the dark background but 1.75:1 on light, below even the 3:1 UI floor. |
| `ac-27-implementation.md`, `ac-27-test-review.md` | G#27 / GH#46, the interpreter-shutdown abort — **investigated, not fixed**. PR #47 landed two pure-Python resource fixes (`_poll_games()` no longer holds `self` across a blocking call; `on_close()` drains its UI queue) plus a rebuild-time trace sweep. Its first attempt also added Tcl teardown to `on_close()` and *introduced* a macOS abort (`Tcl_FindHashEntry on deleted table`), which was backed out. Read before attempting the ticket again: 75 runs across four attempts never reproduced the original abort on Linux, and the only exit-134 anyone saw was the one we caused. |
| `ac-27-r3-implementation.md` | G#27 / GH#46 round 3 — **the fix that worked**. The abort's mechanism: leaked `tkinter.Variable`s finalised by automatic GC running on a worker thread mid-test, calling into Tcl off the main thread. Fixed by controlling *which thread* collects (`gc.disable()` at import, `gc.collect()` at teardown) rather than eliminating the references, which is what aborted macOS in round 2. Benign-`RuntimeError` metric 56/285 → 0/285. |
| `ac-28-spec.md`, `ac-28-implementation.md`, `ac-28-test-review.md` | G#28 / GH#48 — the window height floor, `690 * s` → `WINDOW_MIN_H = 620`. Five rounds, and the reasons are worth reading before touching pane geometry: round 1 passed 289/289 while the app visibly clipped "Hold for" (a settling loop had been added to the *test*); the real cause was `eat_card` being pack-toggled so `card()`'s redraw grows it after `_fill_pane()` already ran; Windows then exposed that an empty `tk.Frame` has a 1px floor, so `367+1+1 > 368` and `pack` unmaps a spacer it never restores. Verify pane layout by driving the live app, not by the suite. |
| `ac-30-implementation.md` | G#30 / GH#53 — the macOS flake in `QueuedNonResyncedUpdatesSurviveARebuild`, merged in PR #58. Root cause: `_rebuild_ui()`'s tail unconditionally restarts `_poll_games()`, so a second *real* scan races the test's fake one. Two dead ends recorded: stubbing `detect_running` to the same value the test queues blinds the guard entirely, and stubbing it to a *distinguishable* value fails 5/5 on correct code because an instant stub makes the second scan land deterministically first. The fix suppresses the rescan itself. |
| `ac-33-spec.md`, `ac-33-design.md`, `ac-33-implementation.md`, `ac-33-test-review.md` | G#33 / GH#59 — rename to Clickwork, user-visible strings only. Merged in PR #61. Read the spec's approach section before renaming anything else: the PyInstaller `--name` ("AFK Farm Clicker") and the settings directory (`AFKFarmClicker`) deliberately stayed, because every installed copy's already-shipped swap script relaunches its old `sys.executable` path after mirroring, so renaming the exe breaks auto-update for existing installs. Release archive names were safe to rename because `pick_asset()` matches on the suffix only (verified against the v0.3.1 and v0.5.0 tags). |
| `ac-34-spec.md`, `ac-34-design.md`, `ac-34-implementation.md`, `ac-34-test-review.md` | G#34 / GH#60 — the Loop app icon. Merged in PR #62. The `.ico`, `.icns` and runtime PNGs are generated once from `assets/icon.svg` and committed, so no rasterizer is a build dependency; 16/32 px use the loop-only `icon-simplified.svg`. Round 2's one finding is worth knowing before touching packaging: `selftest()` loads the icons through the same `_load_app_icon()` the app uses, because `--selftest` is the only thing the frozen smoke test runs and a wrong `--add-data` would otherwise ship a build that dies on launch with CI green. |
| `ac-35-spec.md`, `ac-35-implementation.md`, `ac-35-test-review.md` | G#35 / GH#63 — Windows in-app Install never applied. Merged in PR #65, shipped in 0.6.0. Under `DETACHED_PROCESS` the swap script's `cmd` tree stalled at its first `tasklist \| find`; fixed with `launch_swap_script()` (`CREATE_NO_WINDOW` + DEVNULL stdio), `ping` instead of `timeout`, and a shipped timestamped `update.log`. Two things worth reading before touching the updater: the Windows test launches the real script from a windowed `pythonw` parent that exits, and a red run there once came from the *fixture* — a `.cmd` relaunched via `start` goes through `cmd /K` quote stripping on `&`/`(`/`^`, which the real `.exe` does not — so keep a control variant that separates fixture from product. |
| `ac-37-spec.md`, `ac-37-implementation.md`, `ac-37-test-review.md` | G#37 / GH#66 — pane content starts right under its tab bar (`FILL_TOP_SHARE` 0.5 → 0.0), reversing story #24 feature 4's centring. Merged in PR #68. The top spacer is now inert (constant 1 px) but stays; removing it reopens ac-28's two-spacer arithmetic. Note before trusting the spec's floor proof: on Linux/Xvfb the floor leaves ~72 px spare (substituted font), on Windows/macOS 0–1 px, so the two floor tests' per-spacer assertions only discriminate on Linux — the sum invariant is what guards clipping everywhere. The spec's worked example also misstates `bottom_h` at the floor (it is 1, not 0). |
| `ac-39-spec.md`, `ac-39-implementation.md`, `ac-39-test-review.md` | G#39 / GH#69 — the G#30 macOS flake's return. Merged in PR #70; **mitigated, trigger unconfirmed** (40 isolated macOS runs never opened the race window). The test now quiesces the real poller (cancel `_timers["poll_games"]`, join `_poll_thread`, fail loudly after 5 s), and a product race it exposed is fixed: overlapping scans could land out of order and put stale data in the running-games indicator, so scans now carry `_poll_seq` and `_apply_scan` drops anything older than the newest applied. Read before touching `_poll_games`: joining the previous scan instead was rejected (a scan can stall indefinitely on `Display()`), and one review "failure" was a parallel reviewer's checkout of old code in the shared tree, not a flake. |
| `ac-36-spec.md`, `ac-36-design.md`, `ac-36-implementation.md`, `ac-36-test-review.md` | G#36 / GH#64 — the "send us the update log" dialog, follow-up to G#35's `update.log`. Merged in PR #72. Four rounds: two design-doc contrast-arithmetic fixes before build; a live-app-only bug where a theme/scale change destroyed the open dialog; a fallback view clipping its own buttons at 100% scale; a macOS-only crash from a scheduled startup check that `on_close()` never cancelled (same class as G#39: an untracked `after`/`after_idle` handle, not the same bug); and a real command-injection finding — a GitHub release tag flowed unvalidated into the generated swap script. Read before touching this dialog again: every scheduled job this app starts must be tracked and cancelled in `on_close()`, and any string that reaches `write_swap_script` from the network needs validating at the source, not escaping downstream. |
| `ac-5-spec.md`, `ac-5-implementation.md`, `ac-5-test-review.md` | G#5 / G#8 / G#9 (GH#7, #10, #11) — three review-residue tickets from PR #4's own review thread, combined into one cycle since they touch the same macOS Accessibility-permission code. Merged in PR #73. G#5 (the SIGTRAP crash) needed no code change — it was already fixed by the commit that introduced `macos_input_permitted()` and its two guards. `registered_hotkey` now only ever means a listener is running: round 1 fixed the first-Apply case but missed a second Apply after an earlier successful one, caught only by the PR review reproducing it live. Also: `selftest()` no longer skips constructing (only *starting*) the keyboard listener — confirmed safe by reading pynput's own source, not just its docstring. |
