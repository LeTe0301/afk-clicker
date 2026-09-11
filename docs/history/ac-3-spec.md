# Spec — Updater integrity: verify SHA256SUMS, unpack safely

Tickets: Gitea `admin/afk-clicker#3` (Updater must verify the published
checksums) and `#11` (Archive extraction has no path-traversal protection).
Branch: `feature/ac-3/updater-verify-checksums`, one commit `901f0a4`, based on
`92beca2` (tree-identical to current `main`, merges cleanly).
Roadmap: `docs/ROADMAP.md` → "Before 1.0.0" → **Update integrity**.

This spec was written by the orchestrator after the fact: the implementation
already exists and the scope is fixed by the two tickets, so there was no
triage or product decision left for a product-manager pass. The two tickets
belong together because verifying an archive and then unpacking it unsafely
leaves the hole open.

## Ticket text

**#3** — The release pipeline now publishes SHA256SUMS but the in-app updater
downloads an archive over HTTPS and executes the result without checking it
against them. Fetch SHA256SUMS alongside the asset, verify the digest before
staging, and refuse the update on a mismatch.

**#11** — `download_and_stage` calls `zipfile.extractall` and
`tarfile.extractall` on a downloaded archive. Neither is safe against entries
whose names escape the destination — `../../.bashrc` is written outside the
staging directory. `tarfile` additionally honours symlinks and device nodes
unless `filter="data"` is passed, which Python 3.12 supports and 3.14 makes the
default.

## Affected areas

- `afk_clicker.py`: `CHECKSUM_ASSET`, `pick_checksums`, `fetch_checksums`,
  `file_digest`, `ChecksumError`, `_safe_names`, `_safe_tar_members`,
  `download_and_stage`, `AfkAutoclicker._check_worker` (`_pending` now carries
  the release), `AfkAutoclicker._install_worker`.
- `tests/test_updater.py`: 15 new tests.

## Acceptance criteria

1. The install path fetches the release's `SHA256SUMS` asset and verifies the
   downloaded archive's SHA-256 against it **before any extraction**.
2. A digest mismatch refuses the update; nothing is extracted or swapped in.
3. An archive not listed in `SHA256SUMS` is refused.
4. A release that publishes no `SHA256SUMS` is refused (fail closed), not
   installed unverified.
5. `sha256sum` output parses correctly, including binary-mode `*name` and
   upper-case hex digests.
6. A checksum failure is reported to the user as a checksum failure, not as a
   generic "Update failed" — and the message the user sees must still be
   intelligible after the status line's truncation.
7. Zip and tar entries whose resolved path escapes the staging directory
   (relative `..` and absolute) are refused before anything is written.
8. Tar symlinks, hardlinks, device nodes and FIFOs are refused, on every
   supported interpreter — including 3.11, where `extractall(filter=...)` does
   not exist.
9. Legitimate release archives (top-level folder on Linux/macOS, flat on
   Windows, `.app` bundle nesting) still stage and flatten as before.
10. No new third-party dependency (`hashlib` is stdlib); no Tk access from the
    worker thread except through `_ui()`.

## Out of scope

- Signing releases (checksums from the same release as the asset only defend
  against transport/storage corruption and a swapped asset, not a compromised
  release — note it, don't build it).
- Any other open ticket (#4–#10, #12, #13).

## Open questions

None blocking. The reviewer should judge whether `download_and_stage`'s
`checksums=None` default (verification skipped when omitted) is an acceptable
API or a fail-open footgun.
