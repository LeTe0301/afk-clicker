# Test & Review: Button click-away test (G#18 / GH#22)

## Scope
One new test, `NumBoxFocus.test_a_button_still_runs_its_command`
(`tests/test_ui.py:917-938`), against `docs/spec.md`'s single Goal: prove a
real `app.Button` click still drops focus off a number field and still runs
its own command, guarding the bindtag ordering between `Button._click`
(widget-level bind, `afk_clicker.py:1596`) and `_maybe_drop_focus` (`all`-tag
bind via `root.bind_all`, `afk_clicker.py:2243`). No production code changes
(confirmed throughout, see below).

Env: pynput 1.7.7 venv at
`/tmp/claude-1000/-home-dev-projects-afk-clicker/31f5a905-5b3f-4e0f-95d5-176a1d0748c4/scratchpad/pv`,
Xvfb `:99` already running, confirmed no other `unittest` process active
before starting. Working tree confirmed unchanged before, during, and after
this session: `git status --short` → ` M tests/test_ui.py`, `??
docs/implementation.md`, `?? docs/spec.md`; `git diff --stat` →
`tests/test_ui.py | 23 +++++++++++++++++++++++`, one file, 23 insertions, 0
deletions, matching the spec's own "Only `tests/test_ui.py` changes" AC
throughout.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1: new test clicks an `app.Button` while `click_ms.entry` holds focus, asserts focus dropped | `DISPLAY=:99 <venv>/bin/python -m unittest tests.test_ui.NumBoxFocus.test_a_button_still_runs_its_command -v` | pass | `ok`, `Ran 1 test in 0.139s` — `OK` |
| 2 | AC1 substance: command ran exactly once (`clicked == [1]`) | same run as above, both assertions inside one test method | pass | test method reaches `finally: button.destroy()` without raising — both `assertNotEqual` and `assertEqual(clicked, [1])` (`tests/test_ui.py:935-936`) held |
| 3 | Flakiness check (developer claimed 5/5 isolated) | ran the isolated test 5 times back to back | pass | 5/5 `ok`, ~0.135-0.139s each, no variance |
| 4 | Whole-class regression (developer claimed 10/10) | `unittest tests.test_ui.NumBoxFocus -v` | pass | `Ran 10 tests in 1.203s` — `OK`, all 10 including the new one |
| 5 | AC2: sabotage-verify — `Button._click` returning `"break"` after calling the command must fail the new test on the focus assertion, command assertion must still hold | monkeypatched `afk_clicker.Button._click` in a one-off scratchpad script (nothing written to the repo — see below), reran the exact test through `unittest.TestLoader.loadTestsFromName` against the live, patched module | pass | `FAIL` at `tests/test_ui.py:935`, `self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)` — `AssertionError: <Entry ...> == <Entry ...>`; exactly the developer's reported failure point |
| 6 | AC2 substance: command assertion holds independently under the same sabotage (not merely unreached) | reordered probe (command assertion first, focus assertion second), same monkeypatch, same live steps, run via a `unittest.TestCase` subclass in the same scratchpad script | pass | `assertEqual(clicked, [1])` raised nothing; failure occurred only at the (now second) focus assertion, same message as case 5 — confirms the command ran under sabotage |
| 7 | AC2: no trace left in `afk_clicker.py` after sabotage | `git diff --stat afk_clicker.py`, `git status --short afk_clicker.py` | pass | both empty — the sabotage never touched disk; it was a monkeypatch on the already-imported module object inside a throwaway script, not an edit to the file |
| 8 | AC3: full suite passes, 375 OK / skipped=10, one more than the 374 baseline | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` | pass | `Ran 375 tests in 67.175s` — `OK (skipped=10)`; the only `ResourceWarning`s are the pre-existing, out-of-scope ones in `tests/test_updater.py` (686/704/740/753/768), same as `docs/history/ac-10-test-review.md` already noted for that file |
| 9 | AC4: only `tests/test_ui.py` changes, plus `docs/implementation.md` | `git status --short`, `git diff --stat` | pass | exactly `tests/test_ui.py` modified (+23/-0); `docs/implementation.md`/`docs/spec.md` untracked pipeline artifacts, as expected |

### Note on sabotage methodology
The auto-mode classifier was not tested against a direct edit of
`afk_clicker.py` — instead, per the orchestrator's own suggested fallback,
the sabotage was applied as a monkeypatch of `afk_clicker.Button._click`
inside a one-off script run from the scratchpad directory, against the
already-imported, cached `afk_clicker` module (`tests/context.py:96`, `import
afk_clicker as app`, is the same module object the patched script imports and
the same one `tests.test_ui` picks up). This reaches the real code path
(the genuine `Button._click` method is replaced, the genuine `NumBoxFocus`
test class is loaded and run unmodified via `unittest.TestLoader`) while
guaranteeing zero bytes land on disk — confirmed by `git diff` staying empty
throughout, not just after a manual revert.

## Regression check
Full suite run once this session end-to-end: `Ran 375 tests in 67.175s`,
`OK (skipped=10)` — one more than the documented 374 baseline on `main`
`2c89b3a`, same skip count, matching the spec's AC3 exactly. The `NumBoxFocus`
class was also run in isolation (10/10) and the new test alone 6 times total
(1 + 5 back-to-back) with no flakiness observed. No unrelated failures.

## Independent scrutiny of the four flagged risk points

**(a) Does the test really exercise the bindtag path it claims to? Yes,
confirmed independently.**
`Button.__init__` binds `<Button-1>` directly on the widget instance
(`afk_clicker.py:1596`, `self.bind("<Button-1>", self._click)`) — the
"widget" bindtag, which Tk always dispatches before "class"/"toplevel"/"all".
`_maybe_drop_focus` (`afk_clicker.py:3952-3959`) is bound once via
`root.bind_all("<Button-1>", self._maybe_drop_focus)` (`afk_clicker.py:2243`)
— the "all" tag, dispatched last. A live monkeypatch sabotage (test case 5/6
above) reproduced the developer's exact claim: a `"break"` return from
`_click` after calling the command stops `_maybe_drop_focus` from ever
running, and the failure lands precisely on the focus assertion while the
command assertion independently holds. This is a real, reproduced proof, not
an inference from reading the code.

**(b) Does the "no app-placed Button is viewable alongside the Clicking
pane" claim hold? No — found a real counterexample.**
`docs/implementation.md`'s "Which button to click" section states it
"[c]hecked every app `Button` for viewability while the Clicking pane is
shown" and lists exactly two: Record/Apply (`afk_clicker.py:2874-2875`, in
`self.hotkey_pane`) and `self.update_button` (`afk_clicker.py:3058`, in
Settings' Updates pane) — concluding neither is viewable, so the fallback
path (construct-and-destroy) was used.

`grep -n "Button(" afk_clicker.py` turns up a third call the investigation
never mentions: `afk_clicker.py:2608-2609`,
`Button(side, add_label, self.add_current_game, s, width=rail_w - 28).pack(...)`
— the "Add current game" button, packed into `self.side` (`afk_clicker.py:2590`,
the persistent sidebar). `self.side` and `self.content` (which houses the
`hotkey_pane`/`clicking_pane` toggle `_set_content_tab` switches between,
`afk_clicker.py:2636-2637, 2851-2887, 3225-3252`) are packed side-by-side as
siblings inside `shell` — the sidebar is not part of the tab toggle at all,
and stays visible regardless of which content tab is active.

Confirmed live, not just by reading the layout code: built a real
`AfkAutoclicker` in a fresh `tk.Tk()` (mirroring `UITestCase.setUp`), called
`_set_content_tab("clicking")`, then walked the widget tree for every
`app.Button` instance and read `winfo_viewable()`:

```
Add current game viewable= 1 parent= .!frame2.!frame
Record viewable= 0 parent= .!frame2.!frame3.!frame.!frame2.!canvas.!frame.!frame
Apply viewable= 0 parent= .!frame2.!frame3.!frame.!frame2.!canvas.!frame.!frame
```

("Test", the new test's own constructed button, was not present in this
run — it's built only inside the test, not by app startup.) Record/Apply
read `0`, matching the developer's own (correct) finding for those two. "Add
current game" reads `1` — it is viewable alongside the Clicking pane, the
one case the investigation missed.

The spec's own "Proposed approach" section is explicit and conditional:
"**Preferred:** a real `app.Button` the app already places where it is
viewable at that point ... **Fallback, if no app `Button` is viewable
alongside the Clicking pane:** construct a real `app.Button` ..." The
precondition for the fallback is false, so per the spec's own stated
ordering the preferred path — swap `add_current_game_button.command` for a
recording stub, matching the pattern the spec describes at
`docs/spec.md:47-50` — should have been used instead. This is also the sole
outlier within `NumBoxFocus` itself: every other click-away test in this
class targets a real, already-placed widget the app itself put there
(`count_label` at `tests/test_ui.py:857`, the `Segmented` found via
`_find_segmented_for` at `tests/test_ui.py:900`, `self.ui.items["minecraft"]`
at `tests/test_ui.py:911`) — none of them construct-and-destroy a throwaway
widget. The new test breaks that pattern based on an investigation that
missed a real, viable target.

**(c) Is `pump_until`'s unasserted result a real problem? No — matches this
file's own established convention; one gap is honestly unverifiable this
session.**
`self.pump_until(lambda: button.winfo_viewable(), timeout=1.0)`
(`tests/test_ui.py:932`) does not assert its own outcome, but neither does
`focus_and_settle`'s own identical call one line earlier in the same class
(`tests/test_ui.py:813`) — and `pump_until`'s own docstring
(`tests/test_ui.py:142-160`) states this is deliberate: "Returns without
failing if the predicate never becomes true, so the caller's own assertion
still reports the regression." Traced the failure mode if the button never
maps: `event_generate` is then a no-op (the very comment the new test cites
at `tests/test_ui.py:793-813`), so `clicked` stays `[]` and focus never
moves — both `assertNotEqual` (935) and `assertEqual(clicked, [1])` (936)
still raise a plain `AssertionError`, not a silent pass. The message
wouldn't name "the button never became viewable" as the root cause, but
that's the same trade-off every other `pump_until` call in this file already
accepts, not a new one this diff introduces.

Packing an extra widget into `clicking_pane` before `focus_and_settle` runs
did not visibly disturb anything in this environment — the isolated test
passed 6/6 runs and the full suite passed once, with no timing-related
flakiness observed. However, this was only exercised under Linux/Xvfb `:99`
this session; the 1.0s timeout's sufficiency "on the slow macOS CI runner"
the orchestrator asked about was **not independently verified** — there is
no macOS runner available in this environment, and I have nothing beyond the
developer's own (unverified-by-me) claim to go on there. Flagging this
explicitly per this project's own review-protocol conventions ("macOS is the
least verified target ... say so plainly rather than implying coverage that
does not exist") rather than asserting it's fine.

**(d) Comment hygiene — matches established repo convention, not a
deviation.**
The new comment (`tests/test_ui.py:918-925`) cites `afk_clicker.py:2874-2875`,
`:3058`, `:1596` by line number and says "Per docs/spec.md's fallback."
Checked whether bare `docs/spec.md` references (which go stale the moment a
cycle's spec is archived to `docs/history/ac-N-...`) are already this
codebase's norm: `grep -n "docs/spec.md"` across `tests/test_ui.py`,
`tests/test_updater.py`, and `afk_clicker.py` turns up dozens of matches
(e.g. `tests/test_ui.py:795, 1029, 1188, 1274, 1703, 1855, 1877, 2587, 2792`;
`afk_clicker.py:169, 235, 1047, 1064, 1107, 1124, 1147, 1160, 1176, 1727,
2485, 2517, 2837, 2844, 3591, 3712, 3726, 3772, 3801`), including plenty that
demonstrably refer to already-archived, older tickets. Specific
`afk_clicker.py:N` line citations inside comments are likewise pervasive
(e.g. the `docs/history/ac-10-test-review.md` precedent itself is built
entirely around one). This is an established, repo-wide, accepted
convention — the new test's comment matches it exactly rather than
deviating from it. No action needed here.

## Findings

1. **Must-fix (changes-requested)** — `docs/implementation.md`'s "Which
   button to click" investigation (and, consequently,
   `tests/test_ui.py:917-938`'s implementation choice) is factually wrong.
   A real, already-placed `app.Button` — "Add current game"
   (`afk_clicker.py:2608-2609`, packed into `self.side`) — **is** viewable
   alongside the Clicking pane, confirmed live (`winfo_viewable() == 1`
   immediately after `_set_content_tab("clicking")`, vs. `0` for Record and
   Apply). The spec's own "Proposed approach" makes the fallback
   conditional on this being false ("Fallback, if no app `Button` is
   viewable alongside the Clicking pane"); since it isn't false, the
   preferred approach (swap `command` on the real button for a recording
   stub) should have been used, matching every other test in this class.
   Concrete failure scenario this causes: the shipped test exercises a
   widget that exists only for the duration of the test (extra
   `pack()`/`destroy()`, an extra `pump_until` wait, and a docs claim a
   future reader will trust at face value) instead of the simpler, more
   representative real widget already sitting in the production tree — the
   one true difference the spec cared enough to write a preference order
   for.

2. **Nit** — the 1.0s `pump_until` timeout for the freshly packed button's
   viewability, and whether packing an extra widget into `clicking_pane`
   ahead of `focus_and_settle` disturbs its own timing, was only exercised
   under this session's Linux/Xvfb environment (6/6 passes, no flakiness);
   the developer's macOS-CI timing claim was not independently
   re-verified here, no macOS runner being available. Not a defect found,
   an honest coverage gap worth naming rather than silently accepted.

## Spec coverage
All 4 bullets in `docs/spec.md`'s Acceptance criteria (lines 58-67) were
exercised:
- New `NumBoxFocus` test clicks an `app.Button` canvas while
  `click_ms.entry` holds focus, asserts focus left and command ran exactly
  once — covered, pass (test cases 1-4).
- Sabotage-verify (`Button._click` returning `"break"`) fails the focus
  assertion, command assertion still holds, `git diff afk_clicker.py` stays
  empty — covered, pass, reproduced independently via monkeypatch rather
  than trusted from the developer's report (test cases 5-7).
- Full suite: 375 OK, skipped=10, one more than the 374 baseline — covered,
  pass (test case 8).
- Only `tests/test_ui.py` changes, plus `docs/implementation.md` — covered,
  pass (test case 9).

No acceptance-criterion bullet is unimplemented or untested. The gap found
is not against a bulleted AC but against the spec's own "Proposed approach"
section, which sets an explicit, conditional preference the implementation
did not correctly evaluate (Finding 1).

## Overall verdict
**Changes requested.**

The testing pass is clean: every one of the developer's reported results was
independently reproduced this session, not taken on trust — 375/375 (skipped
10) on the full suite, 10/10 on the whole `NumBoxFocus` class, 6/6 on the new
test alone, and the sabotage-verify reproduced via an independent monkeypatch
(never touching `afk_clicker.py` on disk) landing on exactly the reported
failing assertion, with the command assertion independently confirmed to
hold under the same sabotage via a reordered probe. This is not a
blocked-testing outcome.

The review pass found one must-fix: `docs/implementation.md`'s investigation
into "which button to click" missed a real, already-placed, already-viewable
`app.Button` (`afk_clicker.py:2608-2609`, "Add current game" in the sidebar),
and used the spec's fallback construction path even though the spec's own
stated precondition for that fallback ("no app `Button` is viewable
alongside the Clicking pane") does not hold. This breaks from every other
test in the same class, all of which target a real, already-placed widget.

Must-fix for the next developer round:
- Rework `tests/test_ui.py:917-938` to target the real "Add current game"
  `app.Button` (`afk_clicker.py:2608-2609`, packed into `self.side`) instead
  of constructing a throwaway one — locate it via a widget-tree walk (same
  pattern as `_find_segmented_for`, `tests/test_ui.py:841-852`) and swap its
  `.command` for a recording stub, per the spec's preferred approach. Update
  `docs/implementation.md`'s "Which button to click" section to reflect the
  corrected investigation.

No should-fix items beyond the noted nit (macOS-timing claim not
independently re-verified in this environment, which is a coverage gap to
flag rather than something to act on immediately).

## Round 2

### Diff verified
`git diff -- tests/test_ui.py` (34 insertions, 0 deletions, matching
`docs/implementation.md`'s Round 2 stat): a new helper
`_find_add_game_button` (`tests/test_ui.py:917-927`) and a reworked
`test_a_button_still_runs_its_command` (`tests/test_ui.py:929-948`). No
other file touched; `git status --short` shows only `M tests/test_ui.py`
plus the untracked `docs/*.md` pipeline artifacts.

### Must-fix resolution (round 1, finding 1)
Confirmed directly against `afk_clicker.py`:
- `self.side` (`afk_clicker.py:2590`) and `self.content`
  (`afk_clicker.py:2636`) are packed as siblings inside `shell`
  (`afk_clicker.py:2585-2637`), not parent/child — the sidebar sits outside
  the Hotkey/Clicking tab toggle and stays viewable regardless of which
  content tab is active, exactly as round 1 found live.
- "Add current game" is a real `app.Button` at `afk_clicker.py:2608-2609`,
  packed directly into `side`.
- `Button.command` (`afk_clicker.py:1585`) is a plain instance attribute,
  not a property or `__slots__`-guarded field, so it is freely swappable and
  restorable, and bound-method equality (`widget.command ==
  self.ui.add_current_game`) holds across separate attribute accesses of the
  same bound method — standard Python semantics, and this was also
  empirically proven: the helper found the button and all runs below
  passed.
- `_find_add_game_button` (`tests/test_ui.py:917-927`) walks from
  `self.ui.side`, matches on `isinstance(w, app.Button) and w.command is
  self.ui.add_current_game`-equivalent (`==`, per above), independent of the
  "+"/"Add current game" label swap driven by `self._rail_collapsed`
  (`afk_clicker.py:2607`) — confirmed by reading that line, the label text
  is irrelevant to the match. `self.assertIsNotNone(found, "no matching
  Button found for add_current_game")` (`tests/test_ui.py:926`) gives a
  clear failure message if the widget tree ever stops containing this
  button.
- The reworked test (`tests/test_ui.py:929-948`) now swaps `button.command`
  for a recording stub and restores the original in `finally`
  (`tests/test_ui.py:934-948`) — no `pack()`/`destroy()` of a throwaway
  widget, matching the spec's preferred approach and every sibling test in
  the class (`count_label`, `_find_segmented_for`,
  `self.ui.items["minecraft"]`).

This resolves round 1's sole must-fix in full: the real, already-placed
button is used, found robustly (label-independent), and the helper fails
loudly if it's ever missing.

### Re-verification performed this session (not re-trusted from the doc)
All of the following were run fresh, this session, against the current
working tree (`DISPLAY=:99`, Xvfb `:99` already up, confirmed via `pgrep -a
Xvfb` / `pgrep -af "[u]nittest"` that nothing else was using it first):

| # | Check | Command | Result |
|---|---|---|---|
| 1 | New test, isolated, 3x | `unittest tests.test_ui.NumBoxFocus.test_a_button_still_runs_its_command -v` x3 | `ok` all 3, ~0.14s each |
| 2 | Whole `NumBoxFocus` class | `unittest tests.test_ui.NumBoxFocus -v` | `Ran 10 tests in 1.211s` — `OK`, all 10 including the reworked test |
| 3 | Sabotage-verify (focus assertion fails) | Monkeypatched `app.Button._click` to call `self.command()` then `return "break"` inside a one-off script (`sabotage_check_r2.py`) in the scratchpad, run via `unittest.TestLoader.loadTestsFromName` against the live, already-imported module — never an on-disk edit | `FAIL` at `tests/test_ui.py:946`, `self.assertNotEqual(self.root.focus_get(), self.ui.click_ms.entry)` — `AssertionError: <Entry ...> == <Entry ...>` |
| 4 | Sabotage-verify (command assertion holds independently) | Same sabotage, separate scratchpad script (`sabotage_order_check_r2.py`) subclassing `NumBoxFocus` with the two assertions reordered (command first, focus second) | `assertEqual(clicked, [1])` raised nothing; failure occurred only at the now-second focus assertion, same message as #3 |
| 5 | No trace on disk after sabotage | `git diff --stat afk_clicker.py`, `git status --short afk_clicker.py` | both empty |
| 6 | Full suite | `unittest discover -s tests -t .` | `Ran 375 tests in 66.629s` — `OK (skipped=10)`; only the pre-existing `test_updater.py` `ResourceWarning`s (686/704/740/753/768), unrelated to this change |
| 7 | Scope | `git status --short`, `git diff --stat` | `M tests/test_ui.py` only (+34/-0); `docs/*.md` untracked pipeline artifacts |

Both scratchpad scripts (`sabotage_check_r2.py`, `sabotage_order_check_r2.py`)
were written under the session scratchpad directory only, never inside the
repo tree; `git status --short` for the repo shows no new/scratch files.

### Point 3 checks (new-in-round-2 risk surface)
- **Can the `.command` swap leak into a later test if this test errors
  before `finally`?** No, doubly guarded: (a) the swap is inside a
  `try/finally` (`tests/test_ui.py:938-948`) so any exception raised after
  the assignment still restores `original_command`; (b) even setting that
  aside, `UITestCase.setUp` (`tests/test_ui.py:70-83`) constructs a brand
  new `app.AfkAutoclicker(self.root, store=...)` per test method, and
  `tearDown` (`tests/test_ui.py:85-99`) calls `self.ui.on_close()` — so even
  a hypothetical unrestored swap could not survive into the next test's
  `self.ui`, which is a different object entirely.
- **Does `UITestCase` build a fresh app per test?** Yes, confirmed by
  reading `setUp`/`tearDown` directly (`tests/test_ui.py:70-99`) — a new
  `tk.Tk()` and a new `AfkAutoclicker` every test.
- **Is `self.ui.side` a real attribute?** Yes, `afk_clicker.py:2590`, `side
  = self.side = tk.Frame(shell, bg=BG, ...)`, set unconditionally in
  `__init__` regardless of which tab or Settings state is active.

### Spec coverage (re-checked against the corrected implementation)
All 4 acceptance-criteria bullets (`docs/spec.md:58-67`) hold, and the
"Proposed approach" section's own conditional preference is now correctly
applied: the preferred path (swap `.command` on a real, already-placed,
already-viewable button) is used, not the fallback — resolving round 1's
gap against that section.

### Findings
None must-fix. No should-fix items beyond restating round 1's already-noted
nit (macOS CI timing for the `pump_until` wait was not independently
verified here either round — no macOS runner available in this
environment; unchanged from round 1, not a new gap introduced by round 2).

### Overall verdict
**Approved.**

Round 1's sole must-fix — target the real "Add current game" `app.Button`
instead of constructing a throwaway one — is fully resolved, verified
against the actual diff and re-run independently this session (not taken on
trust from `docs/implementation.md`): 3/3 isolated runs, 10/10 for the whole
`NumBoxFocus` class, sabotage-verify reproduced via monkeypatch (focus
assertion fails, command assertion independently holds under a reordered
probe), zero trace on `afk_clicker.py` after sabotage, and 375/375
(skipped=10) on the full suite. Only `tests/test_ui.py` changed (+34/-0),
matching the spec's scope AC exactly. No new must-fix or should-fix items
found in round 2's diff.
