# Implementation: Review residue — roadmap wording, startup ordering, test hygiene, stale counts — G#10/GH#12

## Summary
Four independent one-liners, all documentation/test-only, none changing production behavior: `docs/ROADMAP.md`'s "Settings schema version" bullet gained one sentence naming `hotkey` (PR #4) as the first structured field `settings.json` has carried, and stating both migration directions are safe today; the comment above `afk_clicker.py`'s startup hotkey-restore call was extended to document that `_timers`/`_sync_settings()`/`_drain_ui()`/`_poll_games()` (at `_build_ui`'s tail) have already run once by the time the listener is armed, naming commit `54a3b65` as the refactor that made this true, with zero executable lines touched; `tests/test_hotkey.py::Persistence::test_malformed_input_yields_none` now passes `blob` directly instead of `blob if blob else {}`, so its own `None` entry is actually exercised as `None`; and the three bare `open()` calls in `tests/test_ui.py::HotkeyPersistence` (`test_a_corrupt_hotkey_starts_clean`, `test_nothing_is_saved_when_no_hotkey_was_applied`) became `with` blocks, closing the file handles instead of leaking them. Item 5 (stale test counts in GitHub issue #1/PR #4 bodies) is orchestrator housekeeping per the spec — no code change, not touched here.

## Changes by file
- `docs/ROADMAP.md` (~line 17): appended one sentence to the existing "Settings schema version" bullet. No other line in the bullet changed.
- `afk_clicker.py` (~lines 2433-2450): extended the comment above `saved = Hotkey.from_json(...)` to state the invariant that `_build_ui(s)` (called synchronously at line 2401) has fully returned — tail included — before the restore runs, and to name commit `54a3b65` as the refactor that pulled `_timers`/`_sync_settings`/`_drain_ui`/`_poll_games` into `_build_ui`'s own tail. Zero executable lines changed; `git diff` confirms only comment lines were added.
- `tests/test_hotkey.py` (~line 345): `app.Hotkey.from_json(blob if blob else {})` → `app.Hotkey.from_json(blob)` in `Persistence.test_malformed_input_yields_none`. Every other entry in the `for blob in (...)` tuple is unaffected (`{}` was already passed as `{}`; every other entry is truthy and passed through unchanged either way).
- `tests/test_ui.py` (~lines 2005-2015), class `HotkeyPersistence`: the three bare `open()` calls in `test_a_corrupt_hotkey_starts_clean` and `test_nothing_is_saved_when_no_hotkey_was_applied` became `with open(...) as f:` blocks. Same reads/writes, same assertions — only the handles now close deterministically. The other bare `open()` calls elsewhere in `tests/test_ui.py` (lines 439, 2880, 3049, in different, unnamed test classes) were left untouched, per the spec's Non-goals.

## Key decisions / tradeoffs
- Matched the spec's proposed diff verbatim for all four items — wording, comment text, and code all came directly from `docs/spec.md`'s "Proposed approach", which had already resolved the one judgment call in this cycle (item 2: document the existing ordering rather than move any code, since the ticket's premise about a real gap doesn't hold against current `main`). No new judgment calls were needed.
- Item 2 is comment-only by design: the spec's own reasoning (restated in the comment itself) is that `_build_ui(s)` at line 2401 is a plain synchronous call, so textual position already matches execution order for the four lines that matter — moving working code for cosmetic reasons would violate this repo's minimal-diff convention.
- Item 3's fix only tightens what's exercised, it does not fix a fail-without-fix bug: `Hotkey.from_json`'s own `isinstance(blob, dict)` guard already returns `None` for a real `None` input, so the assertion's expected outcome is unchanged before and after — only which value actually reaches `from_json` for the `None` case changes. The spec's own acceptance criteria and sabotage-verify instructions call this out explicitly, so no attempt was made to construct an artificial "red without the fix" narrative that doesn't apply here.

## Deviations from spec
None. All four items match `docs/spec.md`'s "Proposed approach" line for line; all four items in "Affected areas" were the only files touched.

## Known limitations
- Item 2's documented invariant is comment-only and unenforced by code: if a future change wraps `self._build_ui(s)` in `after_idle`/a thread/anything asynchronous, the guarantee the comment states would silently stop holding. This is the same class of risk as any other comment-only invariant in this file, and is called out in the comment itself (see spec's Edge cases).
- Item 5 (stale test counts on GitHub issue #1 and PR #4) is explicitly out of this diff — it lives only in those artifacts' bodies, not in any tracked file, and is orchestrator housekeeping per the spec.

## How to verify locally
Environment (this repo's convention: venv + Xvfb `:99`, confirm nothing else is running first):
```
pgrep -a Xvfb            # :99 should already be up
pgrep -af "[u]nittest"   # nothing else running
cd /home/dev/projects/afk-clicker
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```

### Full suite result (this session, final state)
```
Ran 374 tests in 93.861s

OK (skipped=10)
```
Matches the documented baseline on `main` exactly — same count, same skip count, since no test was added or removed (two existing tests reshaped, one existing test's argument corrected).

### ResourceWarning before/after (this session)
Before the fix (verified by stashing `tests/test_ui.py`'s change only, then running with `-W always`):
```
DISPLAY=:99 <venv>/bin/python -W always -m unittest tests.test_ui.HotkeyPersistence -v
```
produced, at the three bare `open()` call sites:
```
tests/test_ui.py:2005: ResourceWarning: unclosed file <...mode='r'...>
tests/test_ui.py:2007: ResourceWarning: unclosed file <...mode='w'...>
tests/test_ui.py:2015: ResourceWarning: unclosed file <...mode='r'...>
```
After the fix (stash popped, fix restored), the same command with `-W error::ResourceWarning`:
```
DISPLAY=:99 <venv>/bin/python -W error::ResourceWarning -m unittest tests.test_ui.HotkeyPersistence -v
```
ran all 6 `HotkeyPersistence` tests to `OK` with no `ResourceWarning` raised as an error. A second pass with `-W always | grep -i resourcewarning` on the same class found zero matches (grep exit code 1), confirming the warning is gone entirely, not merely downgraded.

### Sabotage-verify performed this session (item 3)
Per the spec's own framing (this fix only tightens coverage; it does not turn a currently-failing test green), temporarily reverted `test_malformed_input_yields_none` back to `app.Hotkey.from_json(blob if blob else {})` and reran:
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_hotkey.Persistence.test_malformed_input_yields_none -v
```
Result: `OK` — the test passes either way, exactly as the spec anticipated (`Hotkey.from_json`'s own `isinstance(blob, dict)` guard already returns `None` for a real `None` input regardless of whether the ternary intercepts it first). Reverted back to `app.Hotkey.from_json(blob)` immediately after, confirmed via `git diff tests/test_hotkey.py` showing only the intended one-line change remains.

## Verification of scope
`git diff --stat` at the end of this session:
```
 afk_clicker.py       | 12 ++++++++++++
 docs/ROADMAP.md      | 11 +++++++++++
 tests/test_hotkey.py |  2 +-
 tests/test_ui.py     |  9 ++++++---
 4 files changed, 30 insertions(+), 4 deletions(-)
```
No file outside `docs/ROADMAP.md`, `afk_clicker.py` (comment only), `tests/test_hotkey.py`, and `tests/test_ui.py` was touched; the only untracked file in the tree is `docs/spec.md`, present before this session began.

## Round 2 (addresses `docs/test-review.md`)

`docs/test-review.md`'s verdict was "changes requested" on one must-fix and one
should-fix, both confined to the comment/prose text added in Round 1. No test
or executable-code change was requested or made.

### Must-fix — `afk_clicker.py`'s startup-restore comment (~lines 2437-2444)
The reviewer's Finding 1: the Round-1 comment claimed `_build_ui()`'s tail
(`_timers`/`_sync_settings()`/`_drain_ui()`/`_poll_games()`) sits "a few
hundred lines up" from the restore comment. It's actually ~250 lines *down* —
`_build_ui` is defined at `afk_clicker.py:2545`, its tail at `2686-2689`, both
below the comment at `2433-2444`. The magnitude was right, the direction was
backwards, and the same paragraph already used "above" correctly elsewhere for
`_build_ui(s)`'s call site at line 2401 — mixing a correct "above" and an
incorrect "up" in three sentences describing two different pieces of code
compounded the confusion.

Fixed by dropping spatial words entirely (per the round-2 instruction to avoid
"up"/"below"-style references that go stale) and naming the methods instead.
The new text:
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
Trimmed from 11 comment lines to 8: states the invariant (restore always runs
after `_build_ui()`'s tail has populated `self.settings`), the why (`_build_ui`
is a plain synchronous call), and keeps the `54a3b65` pointer the spec's own
acceptance criteria require, without repeating the mechanism explanation twice.
Zero executable lines changed — confirmed via `git diff afk_clicker.py`, every
added/changed line is `#`-prefixed; `saved = Hotkey.from_json(...)` and the
`if saved is not None:` block are unchanged.

### Should-fix — `docs/ROADMAP.md`'s schema-version bullet addition
The reviewer's Finding 2: the Round-1 addition was two dense, em-dash-heavy
sentences (~115 words) against the spec's own Goal of "add a sentence"
(singular), and included the ticket-echo phrase "so this item was written for
exactly this moment," lifted from `docs/spec.md`'s own internal reasoning —
meaningless to a `ROADMAP.md` reader with no access to this cycle's ticket.

Trimmed to two plain sentences:
```
      The `hotkey` field (PR #4) is the first structured (nested) value
      `settings.json` carries. Both directions are safe unversioned today:
      an older file simply lacks the key, and an unreadable blob degrades
      to no hotkey through `from_json`.
```
Keeps the load-bearing facts the reviewer independently verified (hotkey is
the first structured/nested field; both directions are safe today) and drops
the meta-commentary and em-dash asides. No other line in the bullet changed.

### Nit — sabotage-verify re-execution (not actioned)
The reviewer's Nit 3 (sandbox denied re-running the reverted
`test_malformed_input_yields_none` three times) is a sandbox/tooling
limitation from the reviewer's own session, not a defect in this diff — no
action taken, per the round-2 task's scope (must-fix + should-fix only).

### Verification
- `git diff afk_clicker.py`: only `#`-prefixed comment lines changed (8 lines
  replacing the prior 11); `saved = Hotkey.from_json(...)` and the `if saved
  is not None:` block remain unchanged context.
- `git diff docs/ROADMAP.md`: pure addition of 4 lines after "...as if it were
  corrupt.", no existing line altered.
- Full suite, same environment as Round 1:
  ```
  DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
  Ran 374 tests in 95.182s
  OK (skipped=10)
  ```
  Matches the documented baseline exactly. The `ResourceWarning`s emitted
  during this run are all in `tests/test_updater.py` (lines 686/704/740/
  753/768), confirmed pre-existing and out of this cycle's scope (`git diff`
  shows `test_updater.py` untouched) — same observation the reviewer already
  made in Round 1's review pass.
- `git status --short` at the end of this round: only the four files the
  spec names as in-scope are modified (`afk_clicker.py`, `docs/ROADMAP.md`,
  `tests/test_hotkey.py`, `tests/test_ui.py`); no scratch files added to the
  tree.

### Deviations from spec (Round 2)
None. Both fixes are text-only corrections to Round 1's own comment/prose,
scoped exactly to the reviewer's must-fix and should-fix findings; no new
acceptance criterion was introduced or reinterpreted.
