# Answer key — case 07

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 07-a | 2 | BLOCKER | `publish` passes no `target_commitish`, so the tag is created on the **default branch**, not on the hotfix commit that was built and tested. The released binary and the tag point at different code — the exact failure the version-match step exists to prevent, and one this project already shipped once. |
| 07-b | 2 | BLOCKER | There is no build job at all. `download-artifact` runs with nothing to download, so the release is published **empty**. The PR's verification says "the release appeared" — which it did, with no files. |
| 07-c | 2 | CONCERN | No step checks `__version__` against the branch name, which the release pipeline does for a stated reason: a binary reporting the wrong version breaks the updater's comparison permanently. |
| 07-d | 10 | CONCERN | No manual gate. The whole point of the release environment was that nothing reaches users without approval; a hotfix path that bypasses it makes the gate optional. |
| 07-e | 8 | CONCERN | The suite runs on Linux only, so a hotfix for a Windows-specific bug is published without ever being tested on Windows. |
| 07-f | 10 | CONCERN | No `SHA256SUMS`, so an updater that verifies them cannot install the hotfix. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 07-x | `V="${REF##*/}"` looks fragile against a branch like `hotfix/foo/0.3.2` | It takes the last segment, and the `re.fullmatch` immediately rejects anything that is not a bare version. Correct as written. |
| 07-y | The heredoc inside `run:` looks like the injection pattern | It is not: the value arrives via `env` and is passed as `argv`, never interpolated. This is the *fixed* form and flagging it is a false positive. |

## Scoring

07-a and 07-b are both blockers and both invisible to a reviewer who reads the
workflow for security only — it is safe, and it publishes an empty release
tagged on the wrong commit. 07-y is the trap: the construct that was a
vulnerability in case 06 is correct here, and the difference is `env`.
