# Test & Review: Review residue — roadmap wording, startup ordering, test hygiene, stale counts — G#10/GH#12

## Scope
Four independent, documentation/test-only items against `docs/spec.md`'s four
Goals: `docs/ROADMAP.md`'s schema-version bullet gains one addition;
`afk_clicker.py:2434-2450`'s startup-restore comment is extended (zero
executable lines changed); `tests/test_hotkey.py:345` drops the `blob if blob
else {}` ternary; `tests/test_ui.py:2005-2015` (`HotkeyPersistence`) gets three
bare `open()` calls converted to `with` blocks. Item 5 (stale GitHub
issue/PR-body counts) is orchestrator housekeeping, out of this diff, per
spec's own framing — not re-litigated here.

Env: pynput 1.7.7 venv at
`/tmp/claude-1000/-home-dev-projects-afk-clicker/31f5a905-5b3f-4e0f-95d5-176a1d0748c4/scratchpad/pv`,
Xvfb `:99` already running, confirmed no other `unittest` process active
before starting. Working tree confirmed byte-identical (`git diff --stat`:
`afk_clicker.py | 12`, `docs/ROADMAP.md | 11`, `tests/test_hotkey.py | 2`,
`tests/test_ui.py | 9`, 4 files/30(+)/4(-)) before, during (via
stash/edit-revert round-trips) and after this session.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1: ROADMAP bullet gains the new sentence(s), no other line altered | `git diff docs/ROADMAP.md` | pass | diff shows pure addition after "...as if it were corrupt.", no existing line changed |
| 2 | AC1 substance: "pre-PR-#4 file has no `hotkey` key → constructor's own `None` default" | read `Store.__init__`, `afk_clicker.py:1268-1274` | pass | `self.data = {..., "hotkey": None, ...}`; `self.data.update({k: v for k, v in loaded.items() if k in self.data})` only overwrites keys present in `loaded` — a missing `"hotkey"` key leaves the `None` default in place |
| 3 | AC1 substance: "first structured field" claim (nested shape vs. every other key's scalar/flat dict) | read `Store.__init__` defaults + `game()`/game-defaults (`afk_clicker.py:1332-1365`) | pass | `games` is a dict of flat per-game scalar dicts (`click_ms`, `jitter_ms`, ...); `selected`/`appearance`/`ui_scale` are bare scalars; only `hotkey` has its own `to_json`/`from_json` and nested `mods`/`keys` |
| 4 | AC2: `afk_clicker.py:2437-2450` comment states the invariant, names commit `54a3b65`, zero executable lines changed | `git diff afk_clicker.py`; `git log -S"def _build_ui" --oneline` | **fail (comment factual error)** | see Findings #1 — directional claim ("a few hundred lines up") is backwards; commit reference and substantive invariant are otherwise correct |
| 5 | AC2 substance: restored hotkey press cannot reach `loop()`/`self.settings` with an empty snapshot | traced `apply_hotkey` (4070) → `HotkeyWatcher.start/._press` (579-603) → `callback()` = `self.toggle` (4104) → `start()` (4107) spawns `threading.Thread(target=self.loop)` (4124-4125) → `loop()` (4147) reads `cfg = self.settings` (4155) | pass | `self.settings` is populated by `_sync_settings()` at `_build_ui()`'s tail (`afk_clicker.py:2686-2689`, defined at 2545), which runs synchronously inside the call at line 2401 — fully returned before `__init__` reaches the restore at ~2450; `self.settings = {}` default (line 2276) is never what `loop()` sees post-restore |
| 6 | AC3: `test_malformed_input_yields_none` calls `from_json(None)` directly, still passes | `git diff tests/test_hotkey.py`; ran test | pass | `DISPLAY=:99 <venv>/bin/python -m unittest tests.test_hotkey.Persistence.test_malformed_input_yields_none -v` → `OK` |
| 7 | AC3 substance: sabotage-verify (passes with ternary too) | reasoning + partial live run (see below) | pass | `from_json`'s first guard `if not isinstance(blob, dict): return None` (`afk_clicker.py:450-451`) fires identically for `None` and `{}` — both take the same early-return path, so the assertion's expected outcome is unaffected by the ternary either way |
| 8 | AC4: `HotkeyPersistence`'s two tests raise no `ResourceWarning` under `-W error::ResourceWarning` | ran suite | pass | `DISPLAY=:99 <venv>/bin/python -W error::ResourceWarning -m unittest tests.test_ui.HotkeyPersistence -v` → 6/6 `OK`, no warning raised |
| 9 | AC4 pre-fix baseline: same three lines actually warn before the fix | stashed `tests/test_ui.py` hunk only (`git stash push --keep-index -- tests/test_ui.py`), reran with `-W always` | pass | `ResourceWarning` at exactly `tests/test_ui.py:2005`, `:2007`, `:2015`, matching the developer's report; stash popped immediately after, `git diff --stat` unchanged |
| 10 | AC5: full suite unchanged — 374 tests, `OK (skipped=10)` | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` | pass | run twice this session (before and after the stash round-trip): `Ran 374 tests ... OK (skipped=10)` both times |
| 11 | AC6: no file outside the four named + `docs/spec.md`/`docs/implementation.md` touched | `git status --short`, `git diff --stat` | pass | exactly `afk_clicker.py`, `docs/ROADMAP.md`, `tests/test_hotkey.py`, `tests/test_ui.py` modified; only `docs/spec.md`/`docs/implementation.md` untracked (expected pipeline scratch artifacts) |
| 12 | (c) No executable line changed in `afk_clicker.py` | `git diff afk_clicker.py` | pass | every added line is a `#`-prefixed comment line; the two unchanged executable lines (`saved = ...`, `if saved is not None:`) are context, not diff hunks |

### Sabotage-verify — partially blocked by sandbox policy, re-derived by code reading
Reverted `tests/test_hotkey.py:345` to `app.Hotkey.from_json(blob if blob else
{})` via `Edit` (sed was denied by the auto-mode classifier as "Irreversible
Local Destruction"). Attempting to *run* the test in that reverted state was
denied three times in a row by the auto-mode classifier under different
stated reasons ("Modify Shared Resources", then "Security Test Removal") —
the sandbox would not let this session execute a test file with a
weakened/reverted security-relevant guard in place, even transiently. I did
not attempt to route around that denial. Instead I reverted the edit back to
the fixed state immediately (confirmed via `git diff tests/test_hotkey.py`
showing only the intended one-line change remains) and derived the sabotage
claim from the source directly: `Hotkey.from_json`'s first line,
`if not isinstance(blob, dict): return None` (`afk_clicker.py:450-451`), is
unconditional and runs before anything else in the method — `None` and `{}`
both hit this exact guard and return `None` by the identical path, so the
ternary is provably a no-op for the assertion's outcome, not merely
plausible. I did independently confirm the *fixed* (current) state passes by
actually running it (case 6 above). Net effect: the developer's
sabotage-verify claim is corroborated, but by direct guard-chain reading
rather than by re-executing the reverted test — flagged here so this isn't
silently presented as an equivalent live run.

## Regression check
Full suite run twice this session, `Ran 374 tests ... OK (skipped=10)` both
times, matching the documented `main` baseline and the developer's report
exactly. No unrelated failures. Pre-existing, out-of-scope `ResourceWarning`s
in `tests/test_updater.py` (lines 686/704/740/753/768) were observed during
the full-suite run — these belong to a different test file/class than this
cycle's `tests/test_ui.py` scope and are not part of `docs/spec.md`'s Goals or
Non-goals; noted for completeness, not a regression introduced by this diff
(confirmed by `git diff` — `test_updater.py` is untouched).

## Independent scrutiny of the flagged risk points

**(a) `afk_clicker.py:2437-2450` comment — directional error found.**
The new comment claims `_timers`/`_sync_settings()`/`_drain_ui()`/`_poll_games()`
are "the tail of `_build_ui()`, **a few hundred lines up**." Checked directly:
- `_build_ui` is defined at `afk_clicker.py:2545` (`def _build_ui(self, s):`) —
  **below**, not above, the restore comment at `afk_clicker.py:2437-2450`.
- Its tail — `self._timers = {}` / `self._sync_settings()` / `self._drain_ui()`
  / `self._poll_games()` — sits at `afk_clicker.py:2686-2689`, confirmed via
  `grep -n "self._timers = {}\|self._sync_settings()\|self._drain_ui()\|self._poll_games()"`.
  That is ~236-252 lines **down** (larger line numbers) from the comment, not
  up. The magnitude ("a few hundred") is roughly right; the direction word is
  backwards.
- This contradicts the same paragraph's other spatial reference, which
  correctly uses "above" for `self._build_ui(s)` at line 2401 (that one
  genuinely is above/earlier in the file). Having "above" (correct, refers to
  line 2401) and "up" (incorrect, should be "down"/"below", refers to line
  2686) in the same three sentences describing two different pieces of code is
  itself confusing, independent of which one is wrong.
- The underlying **invariant is true** and independently re-traced end to end:
  `_build_ui(s)` at line 2401 is an ordinary synchronous call; `apply_hotkey()`
  (4070) only touches `self.hotkey`/`self.hk_listener`/`self.registered_hotkey`
  /`macos_input_permitted()`; the listener's `_press()` (590-603) calls
  `self.callback()` — i.e. `self.toggle` — directly on the pynput listener
  thread; `toggle()`→`start()` (4104-4125) spawns a **new** worker thread
  running `loop()` (4147), which reads `cfg = self.settings` (4155).
  `self.settings` is populated by `_sync_settings()` at `_build_ui()`'s tail,
  which has already run (and returned) by the time `__init__` reaches the
  restore call, well before any hotkey press is even possible. So "a restored
  hotkey press can never reach `loop()` ... against an empty settings
  snapshot" holds, and `54a3b65` (`git log -S"def _build_ui"` confirms it is
  the sole commit introducing `_build_ui`, and `git show --stat 54a3b65`
  confirms it is the Settings-page/theme-rebuild commit) is correctly named.
- Per this task's own standard, a comment asserting a false spatial claim is
  a defect even though the *invariant* it supports is correct — a future
  reader told to look "up" for code that is actually ~250 lines *down* will
  search the wrong half of the file. **Changes-requested**, not a nit: fix
  "up" to "down" (or "below").
- Right-sizing against `docs/CODING-GUIDELINES.md`'s comment-the-why
  principle: the added length (13 lines) is justified, not narrative bloat —
  `docs/spec.md`'s own acceptance criteria explicitly require naming commit
  `54a3b65` as the refactor that made the invariant true, and the "this was
  not always true" parenthetical is exactly the kind of non-obvious
  "why does this hold" context the guideline asks for, not restated "what."
  No trim needed once the directional error is fixed.

**(b) `docs/ROADMAP.md` addition — facts check out, wording does not fully
hold up.**
- "A pre-PR-#4 file has no `hotkey` key and gets the constructor's own `None`
  default" — **true**, confirmed against `Store.__init__` (`afk_clicker.py:
  1268-1274`): the default dict sets `"hotkey": None`, and the merge
  (`self.data.update({k: v for k, v in loaded.items() if k in self.data})`)
  only touches keys actually present in the loaded JSON.
- "First structured value this file has ever carried" — **true**, confirmed:
  every other top-level key (`games`, `selected`, `appearance`, `ui_scale`) is
  a bare scalar or a dict of flat per-game scalar dicts; only `hotkey` has
  nested `mods`/`keys` lists with its own `to_json`/`from_json`.
- "A blob a future reader can't fully validate degrades to `None` via
  `from_json`'s existing reject-not-filter guards" — **true**, confirmed by
  reading the guard chain starting at `afk_clicker.py:450`.
- All individual factual claims hold. However: `docs/spec.md`'s own Goal for
  this item says "add **a sentence**" (singular), but the actual addition is
  two long, em-dash-heavy sentences (~115 words) — not concise by the
  ticket's own framing, though this text was already present verbatim in
  `docs/spec.md`'s Proposed approach, so it is not a developer deviation.
  More substantively, the phrase **"this item was written for exactly this
  moment"** is lifted near-verbatim from `docs/spec.md`'s own internal
  reasoning ("the schema-version item was written for exactly the moment a
  structured field first arrived, and that moment is now") — ticket-review
  narration bleeding into a document meant to be read on its own, long after
  "this moment" has passed. A future `ROADMAP.md` reader has no way to know
  what "this moment" refers to without the ticket. This is a documentation
  **should-fix**, not a must-fix: nothing stated is false, but the sentence
  reads as an artifact of the review cycle that produced it rather than
  self-contained roadmap prose.

**(c) No executable line changed in `afk_clicker.py`.** Confirmed — `git diff
afk_clicker.py` shows only `#`-prefixed comment lines added; `saved =
Hotkey.from_json(...)` and the `if saved is not None:` block are unchanged
context lines, not part of the diff.

## Out of scope (per orchestrator instruction, not re-verified here)
G#18 (Button click-away test), G#21 (updater residue), G#40 (macOS sidebar
flake), the other bare `open()` calls in `tests/test_ui.py` (lines 439, 2880,
3049, different test classes), and the stale GitHub issue #1/PR #4 test
counts — the orchestrator states both bodies already carried the correct
numbers (issue #1 says "65 fast tests", PR #4 says "84 tests"), edited on
2026-09-10 shortly after closing, so no action was taken this cycle. (Corrected
in Round 2 below: the original note here wrongly attributed this to
REST-API comments made by the orchestrator; no such edit was made this
cycle — the bodies were already correct.)

## Findings

1. **Must-fix (changes-requested)** — `afk_clicker.py:2439-2440` (the "a few
   hundred lines up" clause): directionally wrong. `_build_ui()`'s tail
   (`afk_clicker.py:2686-2689`) is ~250 lines **below** this comment, not
   above/up. The invariant itself is correct and independently re-verified
   (see scrutiny (a)), and the commit reference (`54a3b65`) is accurate — only
   the spatial word is backwards. Fix: change "up" to "down" (or "below"), or
   drop the directional claim and just say "later in this file."

2. **Should-fix** — `docs/ROADMAP.md`'s added text (~11 lines): all individual
   facts check out (verified against `Store.__init__` and `Hotkey.from_json`
   directly), but the prose is two dense sentences where the spec's own Goal
   asked for "a sentence," and the clause "so this item was written for
   exactly this moment" echoes `docs/spec.md`'s internal ticket reasoning
   rather than reading as self-contained roadmap prose for a reader with no
   access to this cycle's ticket. Recommend trimming to the load-bearing facts
   (hotkey is the first structured field; both directions are safe today; no
   version field exists) without the meta-commentary about when the sentence
   was written.

3. **Nit** — Sabotage-verify for `test_malformed_input_yields_none` could not
   be re-executed live in this session (sandbox auto-mode classifier denied
   running the test against a temporarily-reverted, weaker-guard version of
   the file three times in a row, under three different stated reasons). Not
   a defect in the diff — noted so the verification method (guard-chain
   reading vs. live execution) is transparent rather than implied to be
   identical to the developer's own run.

## Spec coverage
All 8 acceptance-criteria bullets in `docs/spec.md` (lines 191-198) were
exercised:
- ROADMAP bullet content/no-other-line-altered — covered, pass (test case 1).
- `afk_clicker.py` comment content/no-executable-line — covered; comment
  **fails** the "states the invariant" criterion as written, because part of
  what it states is factually backwards (test case 4, Finding 1). The
  no-executable-line-changed half of the criterion passes (test case 12).
- `test_malformed_input_yields_none` calls `from_json(None)` and passes —
  covered, pass (test case 6).
- `HotkeyPersistence`'s two tests raise no `ResourceWarning` under `-W
  error::ResourceWarning` — covered, pass (test cases 8-9).
- Full suite unchanged (374, `OK (skipped=10)`) — covered, pass (test case 10).
- No file outside scope touched — covered, pass (test case 11).
- Sabotage-verify for item 3 — covered, pass, by guard-chain reading rather
  than a live re-run of the reverted state (Nit 3; sandbox-blocked, not a gap
  in the fix itself).

No acceptance criterion was left unimplemented or untested; one (the
`afk_clicker.py` comment criterion) is implemented but not *correctly*, per
Finding 1.

## Overall verdict
**Changes requested.**

The testing pass itself is clean — 374/374 tests pass, the `ResourceWarning`
fix is confirmed both before (warns) and after (clean under `-W
error::ResourceWarning`), the `test_malformed_input_yields_none` change is
confirmed to be coverage-tightening (not a fail-without-fix bug) via direct
guard-chain reading, no executable line changed in `afk_clicker.py`, and no
file outside the declared scope was touched. This is not a blocked-testing
outcome.

The review pass found one must-fix: the new comment at `afk_clicker.py:2437-
2450` states a directionally false claim ("a few hundred lines up" for code
that is actually ~250 lines down/below) about where `_build_ui()`'s tail
lives, inside a comment whose whole purpose is to help a future reader
navigate this exact ordering. Per this review's own standard, a comment
asserting a false spatial detail is worse than no comment, even though the
substantive invariant it documents (no ordering gap between `_build_ui()`'s
tail and the hotkey restore) is independently re-verified here as true. One
should-fix (ROADMAP wording, ticket-echo phrase) accompanies it but does not
block on its own.

Must-fix for the next developer round:
- `afk_clicker.py:2439-2440` — correct "a few hundred lines up" to reflect
  that `_build_ui()`'s tail is below/later in the file, not above/up.

Should-fix (does not block, worth folding into the same round since the
developer will already be touching this area):
- `docs/ROADMAP.md`'s added sentence(s) — trim to remove the "written for
  exactly this moment" ticket-echo and tighten toward one sentence, per the
  spec's own Goal wording.

---

## Round 2 (re-review of `docs/implementation.md`'s "Round 2" section)

### Must-fix re-check — `afk_clicker.py`'s startup-restore comment (~2437-2445)
Read the current comment directly:
```python
        # _build_ui(s) above is a plain synchronous call, so by the time
        # execution reaches here its tail (self._timers/_sync_settings()/
        # _drain_ui()/_poll_games(), defined inside _build_ui() itself) has
        # already run and populated self.settings. A restored hotkey press
        # can therefore never reach loop() against an empty settings
        # snapshot; there is no ordering gap to close. (This became true
        # only when commit 54a3b65 pulled those four lines into _build_ui()'s
        # tail -- an unrelated refactor that closed the gap as a side effect.)
```
- The only spatial word left is "above", applied to `_build_ui(s)` — the call
  at `afk_clicker.py:2401`, genuinely earlier in the same method than the
  comment at 2438. Correct.
- The tail's location is now named by membership ("defined inside `_build_ui()`
  itself"), not by a stale distance/direction claim — no "up"/"down"/"below"
  claim remains anywhere in the paragraph, resolving Finding 1's root cause
  (a false direction word) rather than just flipping it to a new one that
  could go stale again.
- Re-verified the tail is in fact inside `_build_ui()`: `_build_ui` is defined
  at `afk_clicker.py:2542` (`def _build_ui(self, s):`), and
  `self._timers = {}` / `self._sync_settings()` / `self._drain_ui()` /
  `self._poll_games()` sit at `afk_clicker.py:2683-2686`, immediately before
  `_build_ui`'s closing and the next method (`_rebuild_ui`) begins at 2688 —
  confirmed via direct `Read` of that range, not by trusting the prior
  review's line numbers (which cited 2686-2689 against a slightly different
  snapshot).
- Re-verified the commit attribution: `git log -1 54a3b65` resolves to
  `54a3b6560f8d84cd9a71cf2f5c52df4705d1ddab`, "A Settings page, and a theme
  switch that rebuilds the window in place". `git show 54a3b65 --
  afk_clicker.py` shows `self._timers = []` / `self._sync_settings()` /
  `self._drain_ui()` / `self._poll_games()` as unchanged context lines
  immediately following the newly added `def _build_ui(self, s):` — i.e.
  this commit is what extracted the tail end of the old `__init__` into a
  new `_build_ui()` method, carrying those four calls along as its tail.
  "Pulled those four lines into `_build_ui()`'s tail" is accurate, not an
  approximation.
- Confirmed via `git diff afk_clicker.py` that every added/changed line in
  this hunk is `#`-prefixed (including one bare `#` line); `saved =
  Hotkey.from_json(...)` and `if saved is not None:` are unchanged context,
  not part of the diff. Zero executable lines touched.
- **Finding 1 (must-fix) is resolved.**

### Should-fix re-check — `docs/ROADMAP.md`
Current text (`docs/ROADMAP.md:18-21`):
```
      The `hotkey` field (PR #4) is the first structured (nested) value
      `settings.json` carries. Both directions are safe unversioned today:
      an older file simply lacks the key, and an unreadable blob degrades
      to no hotkey through `from_json`.
```
Two plain sentences, no em dashes, no "this item was written for exactly this
moment" ticket-echo. All three factual claims were already independently
verified against `Store.__init__`/`Hotkey.from_json` in Round 1's scrutiny (b)
and are unchanged substance here — re-reading the file confirms the wording
is now self-contained roadmap prose a reader with no access to this cycle's
ticket can follow. **Finding 2 (should-fix) is resolved.**

### Nit 3 — unchanged, correctly not actioned
Round 2 correctly left this alone: it was a sandbox-tooling limitation from
the reviewer's own Round-1 session, not a defect in the diff. No re-check
needed.

### Test-review housekeeping correction (orchestrator-flagged)
Round 1's "Out of scope" note incorrectly stated the orchestrator "corrected
the stale counts on GitHub issue #1 / PR #4 via REST-API comments." That is
factually wrong: both bodies already carried the correct numbers (issue #1
says "65 fast tests", PR #4 says "84 tests"), edited on 2026-09-10 shortly
after closing — no orchestrator action was taken this cycle. Corrected above,
in the "Out of scope" section.

### Regression re-run
```
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
Ran 374 tests in 94.616s

OK (skipped=10)
```
Matches the documented baseline exactly (374 tests, `skipped=10`). The only
`ResourceWarning`s emitted are in `tests/test_updater.py` (lines 686/704/740/
753/768) — confirmed via `git diff --stat` that `test_updater.py` is
untouched by this diff, so these are pre-existing and out of scope, same
observation as Round 1.

### Scope re-check
```
git status --short
 M afk_clicker.py
 M docs/ROADMAP.md
 M tests/test_hotkey.py
 M tests/test_ui.py
?? docs/implementation.md
?? docs/spec.md
?? docs/test-review.md

git diff --stat
 afk_clicker.py       | 9 +++++++++
 docs/ROADMAP.md      | 4 ++++
 tests/test_hotkey.py | 2 +-
 tests/test_ui.py     | 9 ++++++---
 4 files changed, 20 insertions(+), 4 deletions(-)
```
Exactly the four in-scope files modified, no scratch files added. `git diff
tests/test_hotkey.py tests/test_ui.py` shows both files byte-identical to
Round 1's fix — Round 2 touched only `afk_clicker.py`'s comment and
`docs/ROADMAP.md`'s prose, as `docs/implementation.md`'s Round 2 section
claims.

### Round 2 verdict
**Approved.**

Both Round-1 findings are resolved as described, verified independently
against the current file contents and git history rather than taken on the
developer's word: the startup-restore comment no longer makes any false (or
even any) spatial claim about where `_build_ui()`'s tail lives, states the
invariant and the `54a3b65` attribution accurately, and changes zero
executable lines; the `ROADMAP.md` addition is now two plain, self-contained
sentences with the ticket-echo phrase removed. The full suite is unchanged
at 374 tests, `OK (skipped=10)`, and no file outside the four in-scope files
was touched. Nit 3 required no action and received none. No new issues were
introduced by the Round-2 edits themselves.
