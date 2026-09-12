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
      **Features 1-4 of 5 are merged** — PR #37 (`db20af2`, row value column),
      PR #40 (`5ab0196`, tab bar), PR #41 (`18c6f7c`, icon rail), PR #42
      (`cb5900e`, vertical fill).
      **Next: feature 5, the last one** — the flat minimal restyle: drop
      `CARD_R`/`PILL_R` rounding, a single sparingly-used accent, sentence-case
      section headers with a right-aligned action slot. It touches `Button`,
      `Segmented`, `TabBar`, `card()`, `section()`, `StatusPill`, `GameItem`,
      `SettingsItem` and every `round_rect()` call site.
      **It carries the one product decision the story deliberately deferred:
      whether the accent moves from today's red/orange toward the reference's
      green.** `ACCENT` is `#e08a55` dark / `#2b58cc` light (`afk_clicker.py`
      THEMES). Needs the owner's answer before feature 5 is specced.
      After feature 5 the story needs one end-to-end pass before it closes.
      Branch `feature/ac-24/responsive-layout-icon-restyle`, worktree `ac-24`.
      Reference screenshots: `handoff/nvidia-reference/`.

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
- [ ] **Should the window's minimum height shrink?** `minh = 690 * s`
      (`_apply_minsize`) was tuned by #14 for the old *single combined page* and
      never revisited after PR #40 split that page into tabs. Measured on `main`
      without feature 4: even the tallest pane (Clicking + Eating) carries **~148px
      of slack at the minimum window size** — pane 528, content span 380 — and the
      single-card panes (Hotkey, Appearance, Updates) carry far more. Feature 4
      centres that space, halving the largest single band from ~630px to ~315px on a
      tall window, but 315px is still 44% of the pane: centring treats the symptom.
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
## Session handoff — 2026-09-12

**Where things stand:**
- `main` is at `73f38f4` (code at `cb5900e`), CI green on all three platforms,
  **276 tests**.
- The local checkout is on `main` and clean. The `ac-24` worktree is on
  `feature/ac-24/responsive-layout-icon-restyle` at merged `main`, clean, with
  its `docs/*.md` ready to be overwritten by feature 4.
- **Story G#24 / GH#36 is 4 of 5 features done. Nothing is in flight.** Feature 5
  (flat restyle) is blocked on the owner's accent-colour decision.

Merged this session, each after a critical PR review posted on the PR:

| PR | What | Merge |
|---|---|---|
| #40 | Feature 2 — horizontal tab bar (`Hotkey \| Clicking`, `Appearance \| Updates`) | `5ab0196` |
| #41 | Feature 3 — icon rail, window floor rederived | `18c6f7c` |
| #42 | Feature 4 — each tab pane fills its own leftover vertical space | `cb5900e` |

(Feature 1, the row value column, merged as PR #37 / `db20af2` at the end of the
previous session.)

**Next:** feature 4 — content fills the available vertical height, no dead band
below the last card. It depends on feature 2, which is in. Feature 5 (the flat
minimal restyle, and the red-vs-green accent decision) is last and depends on
all of 1–4. The feature breakdown is `docs/history/ac-24-story.md`; the accent
question must not be decided before feature 5.

**Read before starting feature 4** — it is another geometry feature, and both
traps below are geometry traps:
- `docs/history/ac-24-f3-implementation.md` round 3 (the WM/`<Configure>` crash).
- The two CI-only entries under Housekeeping above.

**Working docs:** each cycle's spec/design/implementation/test-review is archived
into `docs/history/ac-24-f{1,2,3}-*.md` as the last step of that cycle. The
`ac-24` worktree's own `docs/*.md` are scratch for the *current* cycle only.

**Workflow:**
1. The pipeline runs product-manager → ux-designer → developer → reviewer.
2. An approved cycle is pushed and PR'd without asking.
3. The review agent gives each PR a critical review in the ten-round format of
   `docs/REVIEW-PROTOCOL.md`, re-deriving claims rather than trusting the cycle's
   own docs, and posts it on the PR.
4. Merge on a `MERGE` verdict **and** green CI on all three platforms. A red leg
   routes back to the developer as a new round — never merge through it.
5. If a fix lands after a verdict, ask the same reviewer to verify the delta and
   re-issue, rather than paying for a fresh ten-round pass.

**Running tests here:** the README's `xvfb-run` needs `xauth`, which this
container lacks. Start `Xvfb :99` directly and use a venv with `pynput`:
`DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` — 269 tests on
`main`. The venv lives in the session scratchpad and does not survive a container
reset; rebuild with `python3 -m venv` + `pip install pynput`. Keep a second
display (`:98`) for load loops — see Housekeeping.

**Lessons that cost a round each:**
- Tk prints callback exceptions instead of raising them. `UITestCase` records them.
- Local runs are Linux-only. CI's Windows and macOS legs have now caught **eight**
  things the cycle reviews missed. The recurring shape: *a green local run is not
  evidence for behaviour this box cannot produce.*
  1. A window geometry assumed granted — the WM clamps to the screen (~1024x768
     on the runners), so a requested size is not the size you get.
  2. The same test's premise unsatisfiable on a short screen, needing an honest
     skip rather than a looser assertion.
  3. A Label's `winfo_reqwidth()` compared against its own `wraplength` — different
     quantities, so the font decides. 144 vs 145 passed on DejaVu Sans; 141 vs 140
     failed on Segoe UI.
  4. A geometry assertion on a widget inside a hidden pane — stale-but-plausible on
     X11, 0 and 1 on Windows.
  5. A fixed pixel headroom on a window height — real WM/DPI rounding overshot it
     by 24px on macOS and 148px on Windows. No constant fixes that; assert only the
     axis the property under test actually depends on.
  6. A `<Configure>` handler bound before construction finished — only a real WM
     generates the event that triggers it.
  Before asserting a pixel value, ask what else could legitimately produce a
  different number elsewhere — the font, the screen, the DPI, the WM. Prefer an
  assertion true by construction: compare two things measured the same way rather
  than one measurement against a constant.
- Design docs' contrast numbers were wrong three times. Recompute with the WCAG
  formula. The compound scale is `_dpi_s * UI_SCALE_FACTORS[...]` — the two
  **multiply**, so the worst case is low-DPI *and* the 90% step together
  (`s = 0.675`), not either alone. A design that reasons about them separately is
  wrong; this is the same error as open ticket G#23.
- A comment asserting a hazard is worth empirically testing before trusting it.
  Two of this story's comments claimed safety properties that were simply false:
  the trace-ordering `TclError` (unobservable — the rebuild always defers via
  `after_idle`), and `<Configure>`'s bind site claiming "placed after every
  attribute `_request_rebuild()` reads already exists" when `_persist()` reads
  `click_ms`, created later in `_build_ui()`.
- Verify a stress-test harness before trusting its numbers. A load loop killed by
  PID rather than process group leaves an orphan hammering the display, which
  produced a fake 25% failure rate that was briefly reported as a real regression.
