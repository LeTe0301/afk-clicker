# Test & Review: Rename product to Clickwork (part 1 — branding/strings, G#33/GH#59)

## Scope
Covers `docs/spec.md`'s 8 acceptance criteria only (the branding/strings rename).
`docs/spec-part2-icon.md` (the Loop icon) is explicitly out of scope for this
cycle — confirmed no icon-related code/assets exist anywhere in the diff.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Grep sweep: no stray `AFK Farm Clicker`/`AFK-Farm-Clicker` outside deliberately-unchanged sites | Automated (`grep -rn`) | pass | `grep -rn "AFK Farm Clicker\|AFK-Farm-Clicker" --exclude-dir=.git --exclude-dir=history .` — every hit is `build.bat`/`release.yml`'s unchanged `--name`/smoke-test/packaging paths, README settings-path table, `tests/test_updater.py`'s build-folder fixtures, or `docs/*.md` (which describe the rename and are expected to quote the old name); zero hits in `tests/test_ui.py` |
| 2 | Window title bar + header label both read "Clickwork" | Manual, live app under Xvfb | pass | Constructed `app.AfkAutoclicker` under `DISPLAY=:94`; `root.title()` → `'Clickwork'`; walked the widget tree for `tk.Label`s → only match containing "lick"/"AFK" is `'Clickwork'` |
| 3 | `release.yml` matrix `asset:` = `Clickwork-{windows-x64.zip,linux-x86_64.tar.gz,macos-arm64.zip}`, `--name "AFK Farm Clicker"` and all `dist/AFK Farm Clicker...` paths byte-unchanged | Automated (`yaml.safe_load`) + diff read | pass | Parsed the workflow with PyYAML; printed resolved `Build` step `run:` string — full command intact, ends in `afk_clicker.py`, no truncation from the new comment; matrix list is exactly the 3 new asset names; `git diff main` shows smoke-test (3) and packaging (3) `dist/AFK Farm Clicker...` lines untouched |
| 4 | `build.bat` `--name "AFK Farm Clicker"` and echo-block paths byte-unchanged | Diff read | pass | `git diff main -- build.bat` — only the header comment (line 3) and two new explanatory comment blocks added; `--name "AFK Farm Clicker"` line and the two `echo dist\AFK Farm Clicker\...` lines are content-identical, just shifted down by the inserted comments |
| 5 | `pick_asset()`/`ASSET_SUFFIX` select correctly for `Clickwork-*` names, asserted directly by a test | Automated (existing test) + sabotage check | pass | `tests/test_updater.py::AssetSelection::test_picks_the_asset_matching_this_platform` passes against the renamed `RELEASE` fixture; **sabotage check**: mutated the fixture's Linux asset name from `Clickwork-linux-x86_64.tar.gz` to `Clickwork-linux-x86.tar.gz` (breaks the suffix match) → test failed (`AssertionError: unexpectedly None`); reverted → test passes again. Confirms the test genuinely exercises the renamed fixture, not a tautology |
| 6 | Full test suite passes, no new failures, including updated fixtures | Automated (`unittest discover`) | pass | `DISPLAY=:94 <venv>/bin/python -m unittest discover -s tests -t .` → `Ran 293 tests in 61.286s — OK (skipped=5)`, matches the developer's reported baseline exactly. Pre-existing noise (one `invalid command name ..._drain_ui` after-script error, several `ResourceWarning`s on unclosed temp files) is unrelated to any changed line (no production logic touched by this diff) and does not affect the `OK` result |
| 7 | README settings-path table byte-unchanged; download table lists new `Clickwork-*` names | Diff + byte comparison | pass | `git show main:README.md` lines 55-65 vs. working tree lines 55-65 — identical; download table diff shows only the three file names changed |
| 8 | `config_path()`/`APP_DIR_NAME` byte-unchanged, no migration code | Direct read + `git diff` scope check | pass | `git diff main -- afk_clicker.py` is 7 hunks total (verified count via `grep -c '^@@'`), all accounted for above (3× User-Agent, 2× temp-dir prefix, 1 comment, title, header — that's actually 8 string edits across 7 hunks); none touch `APP_DIR_NAME`, `config_path()`, `GITHUB_REPO`, `ASSET_SUFFIX`, `pick_asset()`, `install_root()`, or `write_swap_script()`'s logic |

## Regression check
Full existing suite run: `DISPLAY=:94 <venv>/bin/python -m unittest discover -s tests -t .` from repo root — result: **293 tests, OK (skipped=5)**, identical to the developer's reported baseline and to main's known CI baseline (per `docs/implementation.md`). `python -m py_compile afk_clicker.py tests/test_ui.py tests/test_updater.py` also succeeds with no syntax errors.

## Defects found
None. Testing pass is clean — proceeding to review.

---

## Spec coverage
All 8 acceptance criteria in `docs/spec.md` map directly to test cases 1–8 above; every one is implemented and independently verified this session (not inferred from the implementation doc). No gaps found.

The two "Non-goal" constraints (exe/bundle name, settings directory) and the "Open questions" (version bump, executable rename timing) are correctly left untouched — confirmed by direct diff inspection, not just by trusting `docs/implementation.md`'s own claim.

## Findings (most severe first)

No must-fix or should-fix issues found.

### 1. Comment's "wider margin" claim is imprecise (pre-existing pattern, not a new defect) — nit
- File: `afk_clicker.py:770-772` (the `ChecksumError` comment) / `docs/implementation.md`'s "Verification" section
- Issue: the implementation doc states the 40-char truncation-budget argument now holds "by a wider margin than before since the new name is shorter." Recomputed directly: with the *old* name leading the message, only 2 of the 40 characters would have been available to show any part of "not listed in SHA256SUMS" (`len("AFK-Farm-Clicker-linux-x86_64.tar.gz: ") = 38`); with the *new*, shorter name leading, 9 characters would show (`len("Clickwork-linux-x86_64.tar.gz: ") = 31`). The new name actually leaves *more* of the phrase visible, i.e. a narrower margin of "push past budget," not wider — the claim's direction is backwards, though the underlying point ("still mostly truncated, so fixed-words-first still matters") remains true either way.
- Failure scenario: none — this doesn't affect production behavior (the actual message format already puts "checksum: not in SHA256SUMS:" first, well inside the 40-char budget regardless of asset name length: `len("checksum: not in SHA256SUMS: ") = 29` for both old and new names). Purely a wording nit in a comment/doc explaining a hypothetical, not a functional issue. Not blocking.

## Follow-ups (non-blocking)
- None beyond what the spec/implementation already tracked (exe/bundle rename timing, `__version__` bump) — both are explicitly out of scope per "Open questions" and correctly not addressed here.

## Overall verdict
**Approve.**

All 8 acceptance criteria verified with direct evidence gathered this session (live Xvfb app inspection, PyYAML parse of the workflow, byte-diff of unchanged sections, full test suite run, and a sabotage-check proving the renamed `pick_asset` test isn't a tautology). No must-fix or should-fix issues. One cosmetic nit noted above, non-blocking. Diff is minimal and exactly matches spec scope — no scope creep into part 2 (icon), no logic changes, no unintended renames of load-bearing on-disk names.
