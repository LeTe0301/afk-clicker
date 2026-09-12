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
- [ ] **`Segmented` never calls `trace_remove`**, so a destroyed widget's trace stays
      registered on its variable. Found during story #24's end-to-end pass: writing to
      `appearance_var`/`ui_scale_var` after closing Settings (without reopening) hits
      the dangling trace of the destroyed `Segmented`. Confirmed by grep that **no code
      path in the app itself can reach this** — it needs an external caller holding a
      stale reference, which is why it has never surfaced in normal use or in the suite.
      Not a story #24 regression; it predates the story. Worth fixing before anything
      starts driving those vars programmatically.
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
- [ ] **The test suite intermittently aborts at interpreter shutdown** —
      `Tcl_AsyncDelete: async handler deleted by the wrong thread`, exit 134, and
      unittest's summary never prints, so a run that passed looks like a failure.
      Reproduced on clean `main` at roughly 1 run in 4 (and at a similar rate on the
      feature/ac-17 branch), so it predates the UI-scale work. A Tk `Variable.__del__`
      is running off the main thread after the main thread has left the loop — most
      likely a test that starts a real worker thread not joining it before teardown.
      This is a strong candidate for the flaky CI runs already noted under
      Housekeeping, which matter more than usual because the token can't re-run jobs.
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
- [ ] **Should the window's minimum height shrink?** `minh = 690 * s`
      (`_apply_minsize`) was tuned by #14 for the old *single combined page* and
      never revisited after PR #40 split that page into tabs. Measured on `main`
      without feature 4: even the tallest pane (Clicking + Eating) carries **~148px
      of slack at the minimum window size** — pane 528, content span 380 — and the
      single-card panes (Hotkey, Appearance, Updates) carry far more. Feature 4
      centres that space, halving the largest single band from ~630px to ~315px on a
      tall window, but 315px is still 44% of the pane: centring treats the symptom.
      **At the actual window floor it is worse than the tall-window figure suggests** —
      the story's end-to-end pass measured the Hotkey pane at 409px of 527px, 78%
      empty. The tall-window 44% is the flattering case, not the typical one.
      A smaller floor, or one that scales with the tallest tab's actual content,
      would attack the cause. Raised independently by both the ux-designer and the
      developer during feature 4 and confirmed by two reviewers, so it is real and
      not a matter of taste. Out of scope for the story; needs a product decision
      from the owner before anyone specs it.
- [ ] G#22 / GH#33 — Warn when the Minecraft interval minus jitter drops below 650 ms.
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
