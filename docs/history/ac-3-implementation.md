# Implementation: Updater integrity — fix status-line truncation, add `_install_worker` coverage, close the fail-open default

## Summary
Fixed the BLOCKER from `docs/test-review.md`: the "archive not listed in
SHA256SUMS" `ChecksumError` put the variable-length asset name before the
category words, so any real release asset name pushed "checksum"/"SHA256SUMS"
past the 40-character status-line budget. Added test coverage for
`AfkAutoclicker._install_worker` (the coverage gap the reviewer named,
covering AC4 and AC6 at the wired-up UI level, not just the module-level
helpers). Made `download_and_stage`'s `checksums` parameter required instead
of defaulting to `None`, closing the fail-open footgun the reviewer flagged
as a concern.

## Root cause
`download_and_stage` built the unlisted-archive message as
`f"{asset['name']} is not listed in {CHECKSUM_ASSET}"` — the attacker/
release-controlled variable-length part (`asset['name']`) came *first*, and
`_install_worker` displays only `str(exc)[:40]`. For a real release asset
name (`AFK-Farm-Clicker-linux-x86_64.tar.gz`, from
`.github/workflows/release.yml:110-116`), the category words never survive
into the visible 40 characters — the user sees `'afk-farm-clicker-linux-x86_64.tar.gz is'`,
an incomplete sentence fragment with no indication anything checksum-related
happened. The fix is a reordering, not a length increase: put the fixed
category words first so they always land inside the truncation budget,
regardless of how long the variable part is. The other three `ChecksumError`
raise sites (`_safe_names`'s escape message, `_safe_tar_members`'s link/
device messages) already put their fixed category words first and were
verified — not just assumed — to survive truncation with arbitrarily long
entry names (see "Changes by file" below).

## Changes by file

- `afk_clicker.py:569` (`download_and_stage` signature) — `checksums` is now
  a required positional parameter (`asset, checksums, on_progress=None`)
  instead of `asset, on_progress=None, checksums=None`. The one production
  call site (`afk_clicker.py:1375`, `_install_worker`) already passes it by
  keyword, so this is source-compatible there. A docstring paragraph
  explains why the default was removed (a future caller could silently skip
  verification by omitting the keyword). This closes the "Worth a look"
  concern in `docs/test-review.md` (item 3 of the developer task): the
  concern noted no current call reaches the fail-open path, but a required
  argument makes that true by construction instead of by accident.
- `afk_clicker.py:599-606` (`download_and_stage`, unlisted-asset
  `ChecksumError`) — reordered the message to
  `f"checksum: not in {CHECKSUM_ASSET}: {asset['name']}"` so the fixed words
  lead and the variable-length asset name trails. This is the BLOCKER fix
  (AC6). The digest-mismatch message just below it (`afk_clicker.py:609-610`)
  and the `_safe_names`/`_safe_tar_members` messages (`afk_clicker.py:546`,
  `562`, `564`, `566`) were inspected and confirmed already fixed-prefix
  first (see regression tests below) — no change needed there.
- `tests/test_updater.py` — the reviewer's uncommitted regression test
  (`StagingSafety.test_the_unlisted_message_survives_status_line_truncation`,
  now passing) was kept as-is, not weakened. Added:
  - `test_the_mismatch_message_survives_status_line_truncation`,
    `test_the_escape_message_survives_status_line_truncation`,
    `test_the_link_message_survives_status_line_truncation`,
    `test_the_device_message_survives_status_line_truncation` — one per
    remaining `ChecksumError` raise site, each using a realistically long
    variable-length part (a long archive entry name for the escape/link/
    device cases, a real release asset name for the mismatch case) and
    asserting the category keyword survives `str(exc)[:40]`. These close the
    "check every raise site" and "add equivalents … if not covered" parts of
    the task.
  - `Staging.test_both_archive_kinds_flatten` — updated the one test call
    that omitted `checksums`, now passing a matching digest, since the
    parameter is required.
- `tests/test_ui.py:385-451` — new `InstallWorker(UITestCase)` test class,
  reusing the existing `UITestCase` fixture (`tests/test_ui.py:32-86`) rather
  than inventing a new one. Two tests, both driving the real
  `AfkAutoclicker._install_worker` (not the module-level helpers) on a real
  `tk.Tk()`:
  - `test_a_release_without_checksums_is_refused_and_nothing_is_downloaded` —
    AC4: a release with no `SHA256SUMS` asset is refused fail-closed, the
    button stays showing "…publishes no SHA256SUMS" and re-enabled, and
    `download_and_stage` is never invoked (monkeypatched to a
    call-recording stub, asserted empty).
  - `test_a_checksum_error_reaches_the_status_line_with_its_meaning_intact` —
    AC6: `fetch_checksums` and `download_and_stage` are monkeypatched (no
    network, per the task's instruction) so `download_and_stage` raises a
    realistic `ChecksumError`; asserts the text actually shown in
    `update_button` reads as a checksum failure. This is the test that would
    have caught the BLOCKER before it shipped, per the reviewer's note that
    a test on the real `_install_worker` path would have caught it.
  - Monkeypatching follows this suite's own existing convention
    (`tests/test_ui.py`'s `test_no_listener_is_started_without_permission`:
    save the original module attribute, restore it in `finally`) rather than
    introducing `unittest.mock`, since nothing in this test suite uses it.
    `_install_worker` is called synchronously in the test thread (it only
    ever touches Tk through `self._ui()`, same as `_poll_games`), and
    `self.ui._drain_ui()` is called directly afterward to flush the queued
    UI update onto the real widgets, instead of waiting on the 40 ms timer.

## Key decisions / tradeoffs
- Did **not** reword the `_safe_names`/`_safe_tar_members` messages
  ("archive entry escapes the staging directory: …", "archive contains a
  link/device entry: …") even though the task's phrasing suggested
  "unsafe archive entry" as a category label. Measured (see regression tests
  added) that these four messages already put their fixed category words
  before the variable entry name and comfortably survive 40-character
  truncation with the keyword the existing tests already assert on
  (`"escapes"`, `"link entry"`, `"device entry"`). Rewording working,
  already-passing messages would have been an unrequested style change with
  no correctness benefit — minimal-diff discipline says leave it.
- `checksums` was made a required *positional* parameter, not required
  keyword-only (`*, checksums`). The task didn't ask for keyword-only, the
  one production call site already passes it by keyword anyway, and several
  existing tests in `test_updater.py` pass it positionally-adjacent via
  keyword too — a plain required parameter is the minimal change that
  achieves "can't be skipped by omission" without also changing every
  passing call's call style.
- `InstallWorker`'s tests call `_install_worker()` directly rather than via
  `install_update()` + a real background thread. `install_update()` also
  guards on `is_frozen()`, which is false when running from source (as the
  test suite always does) and would make the button path untestable without
  additionally monkeypatching `is_frozen`. Calling `_install_worker`
  directly is the same technique `docs/test-review.md` names as the fix
  ("run `_check_worker`/`_install_worker` synchronously"), and keeps the
  test deterministic instead of racing a daemon thread.

## Deviations from spec
None. `docs/spec.md`'s acceptance criteria (particularly AC4 and AC6) and
`docs/test-review.md`'s two must-fix items and one concern are all addressed
as described there. The out-of-scope items (signing releases, tickets other
than #3/#11) were left untouched, and the review's "worth a look, not
blocking" item about the commit's `Closes #5`/`Closes #13` trailers was left
alone since it names commit metadata, not code, and is outside what the
review marked as in scope for this pass.

## Known limitations
- The digest-mismatch message deliberately still loses the actual/expected
  SHA-256 prefixes to truncation (only "checksum mismatch:" survives, per
  `docs/test-review.md`'s own note on this) — unchanged from before this
  pass, since the review flagged it only as an observation, not a defect,
  and the category is intelligible.
- `InstallWorker`'s two new tests do not exercise `_check_worker` (only
  `_install_worker`, which is what the review's must-fix items named). Their
  method of driving the worker directly and monkeypatching module functions
  would extend to `_check_worker` in the same way if that becomes a
  requirement later; not added here since it wasn't asked for by the review.

## How to verify locally
```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
(Xvfb already running on `:99` in this environment; start with
`Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &` if not.)

Before this pass: `Ran 99 tests in 37.687s — OK (skipped=5)` with the
reviewer's added regression test failing once landed:
`Ran 99 tests in 37.576s — FAILED (failures=1, skipped=5)`.

After this pass, run in this session:
`Ran 105 tests in 37.806s — OK (skipped=5)`.

The 6 new tests: 4 in `tests.test_updater.StagingSafety`
(`test_the_mismatch_message_survives_status_line_truncation`,
`test_the_escape_message_survives_status_line_truncation`,
`test_the_link_message_survives_status_line_truncation`,
`test_the_device_message_survives_status_line_truncation`) and 2 in
`tests.test_ui.InstallWorker`
(`test_a_release_without_checksums_is_refused_and_nothing_is_downloaded`,
`test_a_checksum_error_reaches_the_status_line_with_its_meaning_intact`).
The reviewer's own added test
(`tests.test_updater.StagingSafety.test_the_unlisted_message_survives_status_line_truncation`)
now passes, unmodified in what it asserts.

To run just the changed/added areas:
```
DISPLAY=:99 …/venv/bin/python -m unittest tests.test_updater.StagingSafety tests.test_ui.InstallWorker -v
```

## Round 3: Windows CI

PR #19's `windows-latest` leg failed with `AttributeError: module 'os' has no
attribute 'mkfifo'` in two tests; Linux and macOS passed. Two fixes.

**Fix 1 — root cause: `os.mkfifo` doesn't exist on Windows.**
`tests/test_updater.py:292-306` (`test_a_tar_fifo_is_refused`,
`test_the_device_message_survives_status_line_truncation`) called
`os.mkfifo` to put a real FIFO on disk before tarring it up, but the code
under test (`_safe_tar_members`, `afk_clicker.py:549-566`) only ever
inspects `member.isfifo()`/`member.isdev()` — a property of the tar entry's
type byte, not of anything the host filesystem has to support. Added
`StagingSafety._tar_with_entry_type(name, entry_type)`
(`tests/test_updater.py:256-275`), a sibling to the existing `_tar_with`
helper: it builds the normal payload directory as before, then appends one
synthetic entry directly via `tarfile.TarInfo(name=...); info.type =
entry_type; tf.addfile(info)` — no `os.mkfifo`, `os.mknod`, or any other
platform-specific filesystem call. Both tests now call
`self._tar_with_entry_type(name, tarfile.FIFOTYPE)` instead of
`self._tar_with(lambda d: os.mkfifo(...))`. This runs identically on all
three platforms and does not skip on Windows — it was proven in-process (see
"How to verify" below) that both tests still pass with `os.mkfifo` deleted
from the `os` module entirely, confirming they no longer depend on the host
having FIFO support.

Left the symlink and hardlink tests (`tests/test_updater.py:263-290`,
`test_a_tar_symlink_is_refused`, `test_the_link_message_survives_status_line
_truncation`, `test_a_tar_hardlink_is_refused`) unchanged. They already pass
on the Windows runner (per the task's own log excerpt — only the two
`mkfifo` tests errored) because `os.symlink`/`os.link` are real, working
calls on Windows (`windows-latest`'s Developer Mode / admin context
notwithstanding — the log shows they ran clean). Converting them to the same
`TarInfo`-direct technique would need a `linkname` field pointed at another
archive member, which is more moving parts for no CI benefit today. Not a
"don't touch it because it's not broken" call alone — the concrete reason is
that unlike FIFO/device nodes, there's no known platform under CI where
`os.symlink`/`os.link` themselves are unavailable, so there's nothing here
for the on-disk-then-tar approach to fail to cover. Revisit only if a runner
actually starts failing on the link tests.

**Fix 2 — `download_and_stage`'s `checksums is not None` guard was
residue.** `afk_clicker.py:602` (pre-fix) still read `if checksums is not
None:` around the verification block, even though Round 1 already made
`checksums` a required parameter specifically so it couldn't be silently
skipped — an explicit `checksums=None` from a caller defeated that guarantee
by walking straight past the `if` and extracting the archive unverified.
Removed the guard and dedented the block (`afk_clicker.py:600-618`); a
`None` now reaches `checksums.get(asset["name"])` and raises
`AttributeError: 'NoneType' object has no attribute 'get'`. Chose to let
that surface naturally rather than adding an explicit `isinstance`/`is None`
check that raises `ChecksumError`: this is a programming error at a call
site, not a data problem the archive's publisher could trigger, so it
doesn't need its own fail-closed status-line message — the two existing
production call sites (`afk_clicker.py:1375`) never construct `checksums`
as `None`, and a stray future call site that did would fail immediately and
loudly in dev/CI rather than needing its own translated error text. Added
`StagingSafety.test_checksums_none_extracts_nothing`
(`tests/test_updater.py:218-230`), modeled on the existing
`test_nothing_is_extracted_when_the_digest_is_wrong`: asserts an `Exception`
is raised and that no `staged` directory (or anything else) appears next to
the archive.

### How to verify

```
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
Result in this session: `Ran 106 tests in 37.850s — OK (skipped=5)` (105
from Round 2 + 1 new: `test_checksums_none_extracts_nothing`; the two FIFO
tests were rewritten in place, not added).

Proof the FIFO tests no longer depend on the host filesystem — run in-process
with `os.mkfifo` deleted before either test module is imported:
```
python -c "
import os
del os.mkfifo
import unittest
from tests.test_updater import StagingSafety
suite = unittest.TestSuite()
suite.addTest(StagingSafety('test_a_tar_fifo_is_refused'))
suite.addTest(StagingSafety('test_the_device_message_survives_status_line_truncation'))
unittest.TextTestRunner(verbosity=2).run(suite)
"
```
Output:
```
test_a_tar_fifo_is_refused (tests.test_updater.StagingSafety.test_a_tar_fifo_is_refused) ... ok
test_the_device_message_survives_status_line_truncation (tests.test_updater.StagingSafety.test_the_device_message_survives_status_line_truncation) ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.006s

OK
```
