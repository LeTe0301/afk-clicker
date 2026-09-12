# afk-clicker — backlog

Scoped to this project only. Claude: check this first when picking up work
here, keep it updated as items are resolved or new ones come up — same
convention as the homelab-wide /root/backlog.md.

Tickets live in Gitea (`admin/afk-clicker`, the number used in `ac-N` branch
names) and are mirrored as GitHub issues whose body starts `Gitea:
admin/afk-clicker#N`. GitHub numbers differ, so `Closes #X` in a PR uses the
GitHub number. Shown below as **G#** / **GH#**.

## In progress

- [ ] **Story: responsive layout and an icon-led minimal restyle** — G#24 / GH#36.
      **Features 1, 2 and 3 of 5 are merged** — PR #37 (`db20af2`, row value-column
      alignment), PR #40 (`5ab0196`, horizontal tab bar), PR #41 (`18c6f7c`, icon rail).
      Next: feature 4, content filling the available vertical height (no dead band
      below the last card). Depends on feature 2, which is in. Feature 5 (flat
      minimal restyle) is last and depends on all of 1-4.
      Branch `feature/ac-24/responsive-layout-icon-restyle`, worktree `ac-24`.
      Reference screenshots: `handoff/nvidia-reference/`.
      Still open: whether the accent moves from red toward the reference's green —
      that decision belongs to feature 5, not earlier.

      Feature 3 shipped the same crash twice before CI caught it, both times because
      Xvfb has no window manager and so never generates the post-map root
      `<Configure>` a real WM does. A green local suite was never evidence for that
      path. See `docs/history/ac-24-f3-implementation.md` round 3 before adding any
      resize- or rebuild-driven behaviour, and read the Housekeeping traps below
      before feature 4 — it is another geometry feature.

Story G#17 / GH#20 (themes that follow the system, and a Settings tab) closed
2026-09-11: features 1, 2, 3a, 3b and 4 merged (PRs #28–#31, #34), story-level
end-to-end pass clean on `main` at `0d6e784`. Report: `handoff/story-17-e2e.md`.

## Open

Bugs and residue:
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
- [ ] G#22 / GH#33 — Warn when the Minecraft interval minus jitter drops below 650 ms.
- [ ] G#13 / GH#15 — Story: a Macros tab, configurable per game. Blocked on the settings schema version (ROADMAP). Rebase its branch first.
- [ ] G#12 / GH#14 — Calibration suite for the review agent. Rebase its branch first.

Housekeeping:
- [ ] Branches `feature/ac-12/…` and `feature/ac-13/…` are stacked on `901f0a4`, whose FIFO tests fail on Windows. They stay red on CI until rebased onto `main`.
- [ ] Release: `main` carries #19, #21, #24, #27, #28–#31 since v0.3.1. `release.yml` needs `__version__` to match the `release/x.y.z` branch, so bump it there (0.4.0 suggested, since Settings is new UI).
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
## Session handoff — 2026-09-11

**Where things stand:**
- `main` is at `0d6e784`, CI green on all three platforms, 240 tests.
- The local checkout is on `main`, clean apart from this file (deliberately left
  uncommitted — the owner said "we commit later on").
- **Story G#17 / GH#20 is closed.** Nothing is in flight.

Merged this session, each after a critical PR review posted on the PR:

| PR | What |
|---|---|
| #19, #21, #24, #26, #27 | Updater checksums, focus release, Minecraft 650 ms, CI triggers, flaky macOS test |
| #28–#31 | Theme story features 1–3b |
| #34 | Feature 4, UI scale — `5619c5d` (feature) + `d7a2f46` (cross-platform geometry test fix) |

**Next:** the responsive-layout + icon restyle story above. It is agreed but
unspecced, and **its design half is blocked on the NVIDIA App reference
screenshot**, which was mentioned as sent but never arrived — ask for it again.

**Working docs:** every story and cycle doc, the PR reviews, and
`story-17-e2e.md` are in `/home/dev/projects/.worktrees/afk-clicker/handoff/`,
along with the theme mock `theme-board.html`. The `ac-17` worktree's `docs/*.md`
are feature 4's and are untracked scratch — a new story needs a fresh spec.

**Workflow:**
1. The pipeline runs product-manager → ux-designer → developer → reviewer.
2. An approved cycle is pushed and PR'd without asking.
3. The review agent gives each PR a critical review, using the token to read CI —
   including the Windows and macOS logs, not just pass/fail.
4. The review is posted on the PR.
5. The PR merges only on the owner's say-so, with green CI on all three platforms.

**Running tests here:** the README's `xvfb-run` needs `xauth`, which this
container lacks. Start `Xvfb :99` directly and use a venv with `pynput`:
`DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` — 240 tests
on `main`. The venv lives in the session scratchpad and does not survive a
container reset; rebuild it with `python3 -m venv` + `pip install pynput`.

**Lessons that cost a round each:**
- Tk prints callback exceptions instead of raising them. `UITestCase` records them.
- Local runs are Linux-only. CI's Windows and macOS legs have now caught five
  things the cycle reviews missed. **Three of them were the same mistake**: a test
  asserting an exact pixel quantity that this box happens to satisfy and another
  platform does not.
  1. A window geometry assumed granted — the WM clamps to the screen (~1024x768
     on the runners), so a requested size is not the size you get.
  2. The same test's premise unsatisfiable on a short screen, needing an honest
     skip rather than a looser assertion.
  3. A Label's `winfo_reqwidth()` compared against its own `wraplength` — different
     quantities (reqwidth includes padx and border), so the result is decided by
     the font. 144 vs 145 passed on DejaVu Sans; 141 vs 140 failed on Segoe UI.
  Before asserting a pixel value, ask what else could legitimately produce a
  different number on another machine — the font, the screen, the DPI, the WM.
  Prefer an assertion that is true by construction: compare two things measured
  the same way (a wrapped label is *taller* than an unwrapped one) rather than one
  measurement against a constant.
- Design docs' contrast numbers were wrong three times. Recompute with the WCAG
  formula.
- A comment asserting a hazard is worth empirically testing before trusting it.
  The trace-ordering `TclError` this codebase documents in two places turned out
  to be unobservable, because the rebuild always defers via `after_idle`.
