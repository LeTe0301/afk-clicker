# Test & Review: hotfix/ac-27/shutdown-abort-flake (G#27/GH#46)

## Scope and framing — read before the table

The ticket is "test suite intermittently aborts at interpreter shutdown"
(`Tcl_AsyncDelete`, exit 134, ~1 run in 4 per `backlog.md`). **That symptom
was not reproduced by anyone**, on either side of this branch: the developer
ran 20/20 before-and-after, the orchestrator ran 20 more under load/display
contention, and I ran 2 more full-suite executions myself here — 62 runs
total across three parties, zero exit-134 aborts. `docs/implementation.md`
discloses this itself as "Known limitations," honestly and up front.

**This review therefore does not evaluate "does this fix G#27" — nobody can
show that either way.** It evaluates what the branch actually contains: four
individually-confirmed reference leaks in `afk_clicker.py` (`bind_all`'s own
Tcl command, every un-removed `Variable` trace surviving a rebuild, an
undrained `_ui_queue` item, and `_poll_games()`'s scan thread holding `self`
across a blocking call) plus one new regression test. Diff reviewed: `git
diff main..HEAD` (base `5c32f3c`, HEAD `bf408e0`) — `afk_clicker.py` +143,
`tests/test_ui.py` +58.

Env: venv python at
`/tmp/claude-1000/-home-dev-projects-afk-clicker/55c5887c-a42c-438d-b08e-f1ad54920e0e/scratchpad/venv/bin/python`,
Xvfb `:99`/`:98`. All probe scripts live only in the scratchpad directory
(`probe_multi_rebuild.py`, `probe_restart_leak2.py`, `probe_poll_delivery.py`,
`probe_poll_after_close.py`, `probe_poll_stuck.py`); nothing was left in the
repo (`git status` clean throughout and at the end).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Full suite stays green, no new failures | automated, run twice on separate displays | pass | `:99` and `:98`: `Ran 285 tests ... OK (skipped=7)`, 56.2s/56.2s |
| 2 | Benign off-main-thread `RuntimeError` rate matches the developer's own reported ~55/285 (i.e. not made worse) | automated (grep on run logs) | pass | both runs: exactly 55 occurrences of `RuntimeError: main thread is not in main loop`; 0 occurrences of `Tcl_AsyncDelete` |
| 3 | New test `PollGamesScanDoesNotHoldSelfWhileBlocked` actually exercises the fix (not a tautology) | automated, revert-and-watch-it-fail | pass | ran it against `main`'s `afk_clicker.py` (temporarily checked out, then restored and diff-verified identical to HEAD): fails with `AssertionError: 'profiles' not found in {'self': <afk_clicker.AfkAutoclicker ...>}`; passes against HEAD |
| 4 | `_forget_traces()` does not break tab-bar click/underline behavior across **multiple** rebuilds | manual, scripted (event_generate against real widgets, not mocks) | pass | `probe_multi_rebuild.py`, 6 labeled rounds across 9 rebuilds (settings open, 2×appearance click, 1×ui-scale click, select-closes-settings, reopen, 2 more segment clicks, select-closes-settings again, explicit `_rebuild_ui()`) — content and settings `TabBar`s switch panes and the underline coordinates match the active tab's `(x1,x2)` exactly, every round |
| 5 | Appearance/UI-scale `Segmented` controls keep applying correctly across repeated rebuilds | manual, scripted | pass | same script — `appearance_var`/`ui_scale_var` reach the clicked value after every click, across 4 separate open/close cycles |
| 6 | `NumBox` values persist through `_persist()` across rebuilds | manual, scripted | pass | same script — `click_ms` set to `"444"` then `"555"` in two different post-rebuild rounds, both land correctly in `store.data["games"]["minecraft"]["click_ms"]` |
| 7 | A running clicker survives `_rebuild_ui()` | manual, scripted | pass | same script — `ui.start()`, then `ui._rebuild_ui()`: `running` stays `True`, `self.worker` is the *same* thread object, still alive, after the rebuild |
| 8 | `_button1_all_funcid` release in `on_close()` is correct and doesn't break anything | code review + full-suite regression (285 tests construct/destroy a `tk.Tk()` each) | pass | each `tk.Tk()` is its own Tcl interpreter, so `bind_all`/`unbind_all`/`deletecommand` on one root's "all" tag cannot affect another; wrapped in `try/except TclError`; no failures anywhere in 2 full runs |
| 9 | `_ui_queue` drain at `on_close()` discards rather than runs queued callbacks | code review | pass | the loop only calls `get_nowait()` and drops the result — no `fn(*args)` call, unlike `_drain_ui()` |
| 10 | A live (not-yet-closed) app still receives a delayed `_poll_games()` result after the weakref change | manual, scripted | pass | `probe_poll_delivery.py`: blocked `detect_running` released while the app is still alive → `_mark_running({"minecraft"})` observed via a spy, delivered through the normal queue/drain path |
| 11 | `on_close()`'s bounded (2.0s) join on `_poll_thread` doesn't hang forever on a permanently-stuck scan | manual, scripted | pass | `probe_poll_stuck.py`: `detect_running` blocks 30s, `on_close()` returns in 2.02s |
| 12 | `on_close()` doesn't wait the full timeout when the scan finishes early, and closing while a scan is in flight doesn't crash | manual, scripted | pass | `probe_poll_after_close.py`: scan released at 0.3s, `on_close()` returns in 0.30s; object collected (`gc`-verified `True`) afterward, no exception |
| 13 | New test class matches project convention (`@needs_display` on every `tk.Tk()`-constructing test class) | code review | **fails literally, but the finding is moot** — see Findings #3 | `PollGamesScanDoesNotHoldSelfWhileBlocked` has no `@needs_display`; confirmed the whole test module already cannot import without a display regardless (pre-existing, unrelated `RoundedCanvasBackgrounds._FLAT_BG_CLASSES` class-body reference to `app.Button` at line 2350 on `main` too) |
| 14 | The `restart()`/second-UI interaction the developer reports as unresolved actually reproduces on this branch | manual, scripted, corrected for a self-inflicted probe bug | pass (reproduces) | see "Known-limitation verification" below |
| 15 | That same interaction pre-dates this branch (not introduced/worsened) | manual, scripted, same script against `main` | pass (pre-existing, this branch modestly improves it) | see below |

## Regression check

Full suite run twice on independent Xvfb displays, no reuse of state between
runs:
```
DISPLAY=:99 <venv> -m unittest discover -s tests -t .   → Ran 285 tests in 56.259s — OK (skipped=7)
DISPLAY=:98 <venv> -m unittest discover -s tests -t .   → Ran 285 tests in 56.196s — OK (skipped=7)
```
285 matches the developer's own math (284 on `main` + 1 new test). Both runs
report exactly 55 instances of the benign, always-caught `RuntimeError: main
thread is not in main loop` and 0 fatal aborts — consistent with
`docs/implementation.md`'s own numbers, not worse, not better in a way that
would suggest the fix resolved the underlying flake (it explicitly says it
doesn't).

## Revert-and-watch-it-fail (new test)

Confirmed `PollGamesScanDoesNotHoldSelfWhileBlocked` is not a tautology:
temporarily `git checkout main -- afk_clicker.py` (pre-fix `_poll_games`),
ran the single test — it fails with the local `self` present and `profiles`
absent, exactly the pre-fix shape. Restored with `git checkout HEAD --
afk_clicker.py` and diff-verified byte-identical to the pre-change working
tree before continuing. `git status` was clean at every step.

## Multi-rebuild trace-safety stress test (the dispatch's central concern)

Wrote `probe_multi_rebuild.py` (scratchpad only) to drive a real running
`AfkAutoclicker` through 9 sequential rebuilds via the actual production
triggers (`_show_settings()`, two `Segmented` clicks per open, `_select()`
closing settings, reopening, closing again, plus one direct
`_rebuild_ui()` call), re-finding each widget fresh after every rebuild
(since a rebuild legitimately destroys and replaces it — a probe-script
detail, not a defect). Every one of the dispatch's four specific asks passed
on every round, not just once:

- content and settings `TabBar`s: real `<Button-1>` clicks at the tab's
  measured x-range move `content_tab_var`/`settings_tab_var`, swap which pane
  is packed, and move `bar.underline`'s coordinates to exactly match the
  newly-active tab's `(x1, x2)` — checked after rounds 0, 1, 2, 3, 4, 5.
- Appearance and UI-scale `Segmented` controls: clicking a different segment
  after every rebuild correctly updates `appearance_var`/`ui_scale_var` —
  checked in rounds 1 and 4 (4 total click-cycles across the run).
- `NumBox`: `click_ms.var.set(...)` followed by `_persist()` correctly wrote
  through to `store.data` in round 3 (`"444"`) and again in round 5
  (`"555"`), i.e. after several intervening rebuilds, not just the first one.
- A running clicker (`ui.start()`) survives a direct `_rebuild_ui()` call:
  `running` stays `True`, `self.worker` is the same thread object and stays
  alive across the rebuild.

No failure, no `TclError`, no silently-dropped trace observed anywhere in
this sequence. This directly addresses the dispatch's worry that "a trace
silently dropped one generation too early would look fine in a
single-rebuild test and break on the second" — it did not, across 9.

## `_poll_games()` / weakref change — three targeted probes

1. **Live app, delayed delivery** (`probe_poll_delivery.py`): blocked
   `detect_running`, let the app sit fully alive, released the block —
   `_mark_running` was called with the correct result through the normal
   `_ui()`/`_drain_ui()` path. A live app's `self` is held by many other
   strong references (the widget tree, `root`, the mainloop) besides the
   scan thread, so `weak()` reliably resolves for as long as the app is
   actually running — nothing is lost that used to land.
2. **Stuck scan, bounded close** (`probe_poll_stuck.py`): a scan that never
   returns; `on_close()` returned in 2.02s, not indefinitely — the new
   `self._poll_thread.join(timeout=2.0)` bound is respected.
3. **Close races an in-flight scan** (`probe_poll_after_close.py`): scan
   released mid-`on_close()`; `on_close()` returned in ~0.3s (joined the
   scan rather than waiting the full 2s), and the object was confirmed
   `gc`-collected afterward with no exception. The result being silently
   dropped in this specific case (`me = weak()` resolves to `None`) is not a
   behavior change from `main`: pre-fix, the drain timer was already
   cancelled by this point in `on_close()`, so a late scan's push into
   `_ui_queue` was never delivered there either — it just leaked in memory
   instead of being discarded. No result that used to reach a live UI is now
   lost; only the leak-vs-discard outcome for an already-gone UI changed.

## Known-limitation verification (dispatch item 3)

Reproduced the developer's reported interaction directly, correcting one
bug in my own first attempt (a probe that held `ui`/`root` as still-live
locals during `gc.collect()`, which trivially "proved" every widget was
alive — the corrected version drops all locals before collecting):

- **Baseline** (fresh process, nothing run first): construct, close, collect
  → **0/98** widgets alive. Clean.
- **After running `PerGameSettings.test_survives_a_restart`** in the same
  process, then constructing and closing a *second*, unrelated UI: **61/98**
  widgets alive after a verified-correct `on_close()` (`_tclCommands is
  None`, `children == {}}` on every one, confirming Tcl-level cleanup is not
  the gap, exactly as `docs/implementation.md` describes).
- **A third UI, constructed and closed after that**, with no further
  `restart()` in between: still **61/98** alive. This is a refinement worth
  recording, not a contradiction: `docs/implementation.md`/`backlog.md`
  describe the interaction as "a preceding test... causes a *later* test's
  widgets to survive," which reads as a one-shot, adjacent-test effect. What
  I observed is that it is **sticky for the rest of the process** once
  triggered once by `restart()`, not limited to the immediately-following
  construct/close. Doesn't change the "not fully resolved, out of scope"
  conclusion, but the backlog item should say "every subsequent
  construct/close in the process," not "the next one."
- **Same script against `main` (pre-fix `afk_clicker.py`, restored and
  diff-verified after)**: **64/98** alive after the identical `restart()`
  trigger. The leak pre-dates this branch and this branch modestly reduces
  it (64→61, consistent with 3 of the 4 fixed leak sources no longer
  contributing to *this specific* residual set) without resolving the
  dominant mechanism — matching the developer's own "not fully resolved"
  framing exactly.

## Spec coverage

There is no `docs/spec.md` for this ticket (this was a direct backlog-item
hotfix, not a spec'd feature cycle) — the dispatch's own framing and
`docs/implementation.md`'s stated scope serve as the acceptance criteria
here. Every claim in `docs/implementation.md`'s "Changes by file" and
"Measurements" sections was independently checked against the diff and/or
exercised directly above:

- Three named leaks (`bind_all` funcid, trace sweep, `_ui_queue` drain):
  code-reviewed for correctness, each covered by the regression suite, and
  the `_forget_traces()` mechanism specifically stress-tested across 9
  rebuilds with no regression found.
- `_poll_games()` weakref hardening: covered by the new unit test (confirmed
  non-tautological) plus three additional targeted probes of my own beyond
  what the developer's own test exercises (live delivery, stuck-scan bound,
  close-races-scan).
- The "not fully resolved" claim and its specific repro: independently
  reproduced, confirmed pre-existing on `main`, and slightly refined (see
  above).
- The "60 runs, zero exit-134" claim: I added 2 more full-suite runs (62
  total across this investigation) — still zero.

Nothing in `docs/implementation.md` was found to overstate what the code
does.

## Findings (most severe first)

### 1. `backlog.md`'s residual-leak description understates its own scope — should-fix
- File: `backlog.md` (the "test suite intermittently aborts" item, and
  `docs/implementation.md`'s "Known limitations")
- Issue: both describe the `restart()` interaction as affecting "a *later*
  test" (singular, implying the immediately-following one). My probe showed
  it is sticky for the rest of the process once triggered — a third,
  unrelated UI construct/close after the `restart()`-using test still shows
  the same 61/98-alive count with no further trigger in between.
- Failure scenario: whoever picks up this backlog item next scopes their
  investigation to "what's different about the test immediately after a
  `restart()`-using one" and misses that the effect persists across every
  subsequent UI in the same process — a narrower, wrong mental model of the
  bug's actual shape could send that investigation down the wrong path.
- Not a code defect and not introduced by this branch; a one-line correction
  to the backlog text would close this.

### 2. Stack-frame inspection in the new test is fragile, though currently correct — should-fix (follow-up, not blocking)
- File: `tests/test_ui.py`, `PollGamesScanDoesNotHoldSelfWhileBlocked`
- Issue: the test's own pass/fail hinges on `scan()`'s exact local variable
  names (`"me"`, `"profiles"`) via `sys._getframe(1).f_locals`, which is a
  white-box, implementation-coupled check rather than the behavioral style
  the rest of this file uses (asserting on visible widget/geometry/state). A
  purely mechanical rename inside `scan()` (e.g. renaming the local without
  changing its behavior) would break this test with no real regression; a
  hypothetical different-shaped regression that still happens to keep a
  local literally named `"profiles"` present would not necessarily be
  caught by name alone.
- I confirmed it does correctly fail on pre-fix code and pass on the fix
  today (see "Revert-and-watch-it-fail" above), so this is not a
  must-fix — the test earns its keep right now. The developer's own
  documented reason for choosing this over a whole-object `gc`/`weakref`
  check (that approach was shown, in this same investigation, to be
  sensitive to the unrelated `restart()` interaction) is a legitimate,
  verified trade-off, not an oversight.
- Suggested follow-up, not required for this cycle: make the "no strong
  self-reference crosses the blocking call" property structurally enforced
  instead of introspected — e.g. have `scan()` take `profiles` as an
  explicit parameter of a module-level (or `staticmethod`) function bound
  via `functools.partial`, so the thread's target closure cannot capture
  `self` by construction, and test that shape rather than frame locals.

### 3. New test class omits `@needs_display` — nit, effectively moot
- File: `tests/test_ui.py:265` (`PollGamesScanDoesNotHoldSelfWhileBlocked`)
- Issue: every other `tk.Tk()`-constructing test class in this file is
  decorated `@needs_display`; this one isn't, which is inconsistent with an
  established, deliberate convention (`tests/context.py`'s own comment
  explains why it exists).
- In practice this makes no observable difference today: I confirmed
  (setting `DISPLAY` unset, `CI` unset) that the whole module already fails
  to import with no display at all, because of a pre-existing, unrelated
  class-body reference in `RoundedCanvasBackgrounds` (`_FLAT_BG_CLASSES =
  (app.Button, ...)` at module-load time) that exists identically on `main`
  — so `@needs_display` on the new class would change nothing about how a
  display-less run fails; the whole file already can't be collected in that
  case. Filing as a nit for consistency's sake only, not because it changes
  any real behavior.

## Overall verdict

**Approve, with the follow-ups above (non-blocking) and one explicit
scoping decision the orchestrator should make before merge.**

The testing pass is clean: full suite green twice (285/285), the new test
genuinely tests what it claims (verified by reverting the fix and watching
it fail), and every one of the dispatch's specific worries — multi-rebuild
trace safety across tabs/segments/NumBox/a running clicker, the bind_all
release, the `_ui_queue` discard, the `_poll_games` weakref change under
three different timing scenarios, and the `restart()` interaction — was
independently exercised against the running app, not just read in the diff.
No regression was found anywhere. The review pass found no must-fix: the
three findings above are a backlog-text scoping correction, a fragility
worth a future follow-up (not now), and a moot style nit.

**Merge/do-not-merge judgment, since the dispatch asked for one explicitly:**
merge this as what it honestly is — three confirmed reference-leak fixes
plus one confirmed thread-safety hardening — and **keep G#27 open**. The
leaks are real (each independently demonstrated via `gc`/weakref
before-and-after, not just argued), the fix measurably improves the exact
`restart()` residual case (64→61 objects alive, same trigger, same
process) without a regression anywhere I could find after deliberately
stress-testing the highest-risk surface (repeated rebuilds), and the 143
production-line diff is mostly (~60%) explanatory comment in a file whose
existing style already runs this dense — not new decision surface. Weighed
against that: it does not touch the ticket's own stated symptom rate, which
nobody in 62 combined runs could even measure, so closing G#27 on the
strength of this branch would be a false "fixed" that a future flake report
would have to re-litigate from zero. "Real bug fixed" and "the reported
ticket is resolved" are genuinely different claims here, and only the first
one is true today — the commit title and `docs/implementation.md` already
draw this line correctly, and the backlog.md rewrite (once finding #1's
one-line scope correction lands, which does not need to block merge) is an
honest, well-evidenced record for whoever continues the flake investigation
next.
