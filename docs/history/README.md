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
