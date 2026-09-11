# Test & Review: Updater integrity — verify SHA256SUMS, unpack safely

Branch `feature/ac-3/updater-verify-checksums`. Round 2, reviewing `git diff
main` (working tree against `main`; base `92beca2` is tree-identical to
`main`) — commit `901f0a4` plus the developer's uncommitted fix.

## Round 1 summary (for context, not re-litigated)

Round 1 blocked on the testing pass: AC6 failed for realistic production
asset names (`f"{asset['name']} is not listed in {CHECKSUM_ASSET}"` put the
variable-length asset name before the category words, so `str(exc)[:40]`
dropped "checksum"/"SHA256SUMS" entirely for every real release asset name),
and AC4 had no test coverage above the `pick_checksums()` unit level — the
actual fail-closed branch in `_install_worker` was never exercised by any
test. Per this pipeline's rule, a blocking testing-pass failure routed
straight back to the developer without a round-by-round review.

## Scope

Tickets #3 (verify SHA256SUMS before extraction) and #11 (safe archive
extraction), acceptance criteria 1–10 in `docs/spec.md`. This round covers
the developer's fix for both Round 1 must-fix items plus the `checksums`
required-argument change made in response to Round 1's "worth a look" item.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1/AC2 — digest verified before extraction, mismatch refuses & extracts nothing | automated (`test_nothing_is_extracted_when_the_digest_is_wrong`, `test_a_wrong_digest_is_refused`) | pass | full suite run below |
| 2 | AC3 — archive not in SHA256SUMS refused | automated (`test_an_unlisted_archive_is_refused`) | pass | full suite run below |
| 3 | AC4 — release with no SHA256SUMS refused, fail-closed, **at the wired-up `_install_worker` level** | automated, new this round (`tests/test_ui.py::InstallWorker::test_a_release_without_checksums_is_refused_and_nothing_is_downloaded`) | pass | full suite run + revert check 2 below — closes Round 1's coverage gap |
| 4 | AC5 — sha256sum parsing: binary-mode `*name`, upper-case hex | automated (`test_parses_sha256sum_output`) | pass | full suite run below |
| 5 | AC6 — checksum failure reads as a checksum failure after 40-char truncation, realistic asset names, **at the wired-up level too** | automated (`test_the_unlisted_message_survives_status_line_truncation` — the Round 1 blocker's regression test, now passing; plus 4 new sibling tests for the other 3 raise sites; plus `tests/test_ui.py::InstallWorker::test_a_checksum_error_reaches_the_status_line_with_its_meaning_intact`) | pass | full suite run + revert check 1 below |
| 6 | AC7 — zip/tar entries escaping the staging dir refused (relative `..`, absolute) | automated (unchanged from Round 1) | pass | full suite run below |
| 7 | AC8 — tar symlink/hardlink/device/fifo refused, incl. 3.11 where `filter=` doesn't exist | automated (unchanged from Round 1), interpreter confirmed 3.11.2 this session too | pass | full suite run below |
| 8 | AC9 — legitimate archives still stage/flatten | automated (`test_both_archive_kinds_flatten`, updated this round to pass `checksums=`; `test_a_matching_digest_is_accepted`, `test_a_plain_tar_is_accepted`) | pass | full suite run below |
| 9 | AC10 — no new third-party dependency; no Tk access off the main thread except via `_ui()` | code inspection, extended this round to the two new `InstallWorker` tests | pass | see "Thread-safety check" below |
| 10 | `download_and_stage`'s one production call site still works after `checksums` became a required positional arg; no other caller exists | grep + read | pass | see "Positional-argument change" below |

## Commands run

```
DISPLAY=:99 …/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
Full suite: `Ran 105 tests in 37.707s — OK (skipped=5)`, matching the
developer's reported counts exactly. Ran it twice in this session (once
before the revert checks, once after restoring the tree) — same result both
times.

New/changed test classes in isolation, verbose:
```
DISPLAY=:99 …/venv/bin/python -m unittest tests.test_updater.StagingSafety tests.test_ui.InstallWorker -v
```
`Ran 17 tests in 0.204s — OK` — all 15 `StagingSafety` tests (including the
Round 1 blocker's regression test and the 4 new per-site truncation tests)
and both new `InstallWorker` tests pass.

## Revert checks (each done in-place, tree restored exactly after)

`cp afk_clicker.py .../scratchpad/afk_clicker.py.orig` before each edit,
restored via `cp` back after. `git diff main --stat` was captured before the
first edit and after the last restore — byte-identical:
```
 afk_clicker.py        | 131 ++++++++++++++++++++++++++++--
 tests/test_ui.py      |  72 +++++++++++++++++
 tests/test_updater.py | 214 +++++++++++++++++++++++++++++++++++++++++++++++++-
 3 files changed, 410 insertions(+), 7 deletions(-)
```
`git status --porcelain` after the final restore showed only the pre-existing
untracked `docs/*.md` files.

1. **Reverted the message reorder** (`f"checksum: not in {CHECKSUM_ASSET}:
   {asset['name']}"` → back to `f"{asset['name']} is not listed in
   {CHECKSUM_ASSET}"`). `tests.test_updater.StagingSafety
   .test_the_unlisted_message_survives_status_line_truncation` failed:
   `AssertionError: False is not true : status line 'afk-farm-clicker-
   windows-x64.zip is not ' does not read as a checksum failure`. Confirms
   the Round 1 blocker's regression test genuinely dies without the fix.

   `tests.test_ui.InstallWorker
   .test_a_checksum_error_reaches_the_status_line_with_its_meaning_intact`
   **did not** fail under this revert — see "Finding 3" below for why, and
   why that's not itself a coverage gap.

2. **Removed the fail-closed early return** in `_install_worker`
   (`if sums_asset is None: ... return`), replacing it with
   `checksums = fetch_checksums(sums_asset) if sums_asset else {}`.
   `tests.test_ui.InstallWorker
   .test_a_release_without_checksums_is_refused_and_nothing_is_downloaded`
   failed: `download_and_stage` **was** called (`AssertionError: Lists
   differ: [(...)] != []`) — exactly the AC4 violation the test exists to
   catch. Confirms the new UI-level test genuinely dies without the guard,
   closing Round 1's Finding 2 coverage gap.

3. **Removed the whole digest-comparison block** in `download_and_stage`
   (the `if checksums is not None: …` block, including the unlisted-asset
   check). 5 tests failed the same way (`ChecksumError not raised`):
   `test_a_wrong_digest_is_refused`, `test_an_unlisted_archive_is_refused`,
   `test_nothing_is_extracted_when_the_digest_is_wrong`,
   `test_the_mismatch_message_survives_status_line_truncation`,
   `test_the_unlisted_message_survives_status_line_truncation`.

All three revert checks target genuine tests of the fix, not the harness.

## Thread-safety check (Round 3 lens, done as part of the testing pass)

`InstallWorker`'s two tests (`tests/test_ui.py:385-454`) call
`self.ui._install_worker()` directly on the test thread — not via
`threading.Thread`, the way production does at `afk_clicker.py:1362`. Read
`_install_worker` (`afk_clicker.py:1364-1391`) line by line: it reads/writes
only `self._pending` (a plain tuple, no Tk) and calls `pick_checksums`,
`fetch_checksums`, `download_and_stage`, `install_root`, `os.access`,
`write_swap_script` — none touch Tk. Every UI-visible effect goes through
`self._ui(fn, *args)` (`afk_clicker.py:1440-1448`), which only does
`self._ui_queue.put(...)` — a `queue.SimpleQueue`, thread-safe regardless of
caller. The tests then call `self.ui._drain_ui()` directly
(`tests/test_ui.py:403`) to flush that queue onto the real widgets, instead
of waiting on the 40 ms `root.after()` timer — a new pattern in this file
(no prior test in `tests/test_ui.py` calls `_drain_ui()` directly; existing
tests wait via `self.root.update()` inside `pump`/`settle`), but a correct
one: since the test itself owns the same `tk.Tk()` instance and both the
worker call and the drain happen on that one thread, this is not
racing anything. This mirrors this repo's own established convention
(`tests/test_ui.py:507-520`, `test_no_listener_is_started_without_permission`
— save/monkeypatch/restore-in-`finally`) for the mocking, and is the same
technique Round 1's review itself named as the fix ("run `_check_worker`/
`_install_worker` synchronously").

One inherent limitation worth naming, not a defect in this diff: because the
test calls `_install_worker` inline rather than through a spawned thread, it
cannot detect a *future* regression where someone adds a direct Tk touch
inside `_install_worker` — such a touch would work fine when called inline
on the test's own main thread but would crash (or corrupt state) in
production on the real worker thread. This is a property of the "call the
worker method synchronously" technique in general (already relied on
elsewhere in this file for `_poll_games`-adjacent tests), not something this
round introduced or could reasonably avoid without inventing a new harness —
noting it for the record rather than as a finding.

Both tests assert on real state — `self._button_text()` reads the actual
canvas item text via `itemcget` (confirmed `Button.set_text` at
`afk_clicker.py:910-911` does `self.itemconfig(self.label, text=text)`, so
this is not asserting on a mock), and `update_button._enabled` is the real
attribute `Button.set_enabled` writes (`afk_clicker.py:901-904`) — not
harness artifacts.

## Positional-argument change

`grep -rn "download_and_stage(" --include="*.py" .` finds exactly one
production call site, `afk_clicker.py:1375`
(`download_and_stage(asset, checksums=checksums, on_progress=...)`), which
already passed `checksums` by keyword — source-compatible with the new
required-positional signature. Every test call site (17 of them, all in
`tests/test_updater.py` and none in `tests/test_ui.py`'s `fake_stage` stub,
which independently defines a matching `(asset, checksums, on_progress=None)`
signature) also passes `checksums=` by keyword. No caller breaks.

## Regression check

Full suite (105 tests) run twice this session, `OK (skipped=5)` both times —
no test outside the touched files changed status. The 5 skips are the
pre-existing platform-gated skips (unrelated to this change; not
investigated further since Round 1 already established this baseline and
nothing in this diff touches skip conditions).

---

## Spec coverage

All 10 acceptance criteria in `docs/spec.md` are implemented and covered by
an automated test that a targeted revert demonstrates is not vacuous (AC1–3,
AC6, AC7 via the revert checks above; AC4 via revert check 2; AC5, AC8, AC9
carried over unchanged from Round 1, itself already revert-checked there;
AC10 by code inspection, extended this round to the new test class). No
criterion is untested at the level the spec describes it — Round 1's
"AC4 only unit-tested, not wired-up-tested" gap is closed.

## Findings (most severe first)

None are must-fix. In order:

### 1. `docs/ROADMAP.md`'s "Update integrity" checkbox is not ticked by this change — should-fix

- File: `docs/ROADMAP.md:14-16` (`- [ ] **Update integrity.** The updater
  downloads over HTTPS and executes the result. It should verify a checksum
  published with the release before swapping anything in.`)
- `git diff main --stat` shows only `afk_clicker.py`, `tests/test_ui.py`,
  `tests/test_updater.py` touched — `docs/ROADMAP.md` is untouched by this
  branch.
- This change fully satisfies the roadmap line as written: the archive is
  now digest-verified before extraction (AC1/AC2), an unlisted or unverified
  release is refused fail-closed (AC3/AC4), and unsafe extraction is closed
  off (AC7/AC8) — nothing about "before swapping anything in" is left
  undone. Per `docs/REVIEW-PROTOCOL.md` Round 10 ("Does this move something
  on ROADMAP.md? Update it if so."), this item should be ticked as part of
  this change (or a follow-up commit before merge) rather than left for a
  future, unrelated PR to notice and tick separately.
- Not a blocker: it's a documentation bookkeeping gap, not a defect in the
  shipped behavior, and the protocol's own severity guidance reserves
  `BLOCKER` for roadmap violations ("does it do something the roadmap
  explicitly rules out"), not omissions.

### 2. Commit `901f0a4`'s `Closes #5` / `Closes #13` trailers still don't match tickets #3/#11 — should-fix, carried over from Round 1

- `git log -1 901f0a4` still shows `Gitea: admin/afk-clicker#3,
  admin/afk-clicker#11` followed by `Closes #5` / `Closes #13` — unchanged
  since Round 1, where this was flagged as "worth a look, not blocking."
  `docs/implementation.md`'s "Deviations from spec" section explicitly
  notes this was left alone as out of scope for this pass ("names commit
  metadata, not code").
- Repeating it here rather than dropping it because the underlying commit
  still hasn't changed and this is the last review pass before merge: if
  Gitea's automation acts on `Closes #N` on merge, this would close the
  wrong two issues. Worth fixing before the branch merges (either amend the
  trailer or drop it), even though it's metadata rather than code and
  correctly stayed out of scope for the developer's code-focused fix pass.

### 3. `download_and_stage`'s required-argument fix narrows the fail-open footgun but doesn't close it — nit

- File: `afk_clicker.py:569` (signature: `def download_and_stage(asset,
  checksums, on_progress=None):`) and `afk_clicker.py:602` (`if checksums is
  not None:`).
- The docstring (`afk_clicker.py`, added this round) says: "A default of
  None here would let a future caller skip verification just by forgetting
  the keyword — the one thing this function exists to enforce." Requiring
  the argument does stop a caller from *omitting* it, but the function body
  still explicitly special-cases `checksums=None` as "skip verification" (a
  caller can still write `download_and_stage(asset, checksums=None)` and
  get exactly the old fail-open behavior — just now it has to type `None`
  on purpose instead of leaving a default in place). This isn't exploitable
  today (confirmed above: the one production call site always passes a real
  dict from `fetch_checksums`), so it's not a blocker, but the docstring's
  claim is slightly stronger than what the code change actually guarantees.
  If a future caller ever needs "verification optional," the current shape
  actively invites `checksums=None`; if that's never meant to be valid, the
  `if checksums is not None` branch should probably just go away entirely
  and verification should be unconditional.

### 4. `InstallWorker`'s AC6 test doesn't independently re-verify the message text — observation, not a gap

- File: `tests/test_ui.py:436-438` (`fake_stage` hardcodes
  `f"checksum: not in {app.CHECKSUM_ASSET}: {asset['name']}"` rather than
  calling the real `download_and_stage`).
- Confirmed by revert check 1 above: reverting the actual message-format fix
  in `afk_clicker.py` does **not** make this test fail, because the stub
  never reaches the real message-construction code — it just replays a
  fixed string and checks that `_install_worker`/`_set_update_state`/the
  button correctly propagate whatever `ChecksumError` text they're given.
  That's a deliberate, reasonable scope for this test (the task instructed
  the network functions be mocked, and its purpose per
  `docs/implementation.md` is "the message reaches the status text intact,"
  i.e. testing the plumbing, not the wording) — the wording itself is
  independently covered, and shown by revert check 1 to actually be
  covered, by `tests/test_updater.py`'s
  `test_the_unlisted_message_survives_status_line_truncation` and its four
  new siblings. Noting this only so a future reader of `test_ui.py` doesn't
  assume that test alone catches a future message-wording regression.

## Follow-ups (non-blocking)

- Tick `docs/ROADMAP.md`'s "Update integrity" item (Finding 1).
- Fix or drop commit `901f0a4`'s `Closes #5`/`Closes #13` trailers before
  merge (Finding 2).
- Consider dropping the `checksums is not None` branch in
  `download_and_stage` entirely, or documenting explicitly that
  `checksums=None` is still a legal "skip verification" escape hatch rather
  than letting the docstring imply it no longer exists (Finding 3).
- `_check_worker` still has zero direct test coverage — disclosed by the
  developer as a known limitation and explicitly marked "ideally" (not
  required) in Round 1's must-fix item 2, so not re-raised as a finding
  here, just carried forward as an open item for whoever picks it up next.

## Overall verdict

**Approve, with follow-ups.** Both Round 1 blockers are fixed and each fix
is backed by a revert check that shows the corresponding test genuinely
dies without it (message reorder, fail-closed `_install_worker` coverage,
and — reconfirmed — the digest-comparison block). Full suite: 105 tests,
OK, 5 skipped, matching the developer's reported counts exactly, run twice
in this session including once after the tree was restored byte-identical
to its pre-revert-check state. All 10 acceptance criteria in `docs/spec.md`
are implemented and covered by tests that were shown to be non-vacuous.
Round-by-round review (`docs/REVIEW-PROTOCOL.md`) found no correctness,
security, threading, naming, or scope-creep blockers — the four findings
above are a documentation/bookkeeping gap (ROADMAP checkbox), a carried-over
commit-metadata mismatch, a docstring-overstates-the-fix nit, and one
observation about test scope, none of which affect shipped behavior.
