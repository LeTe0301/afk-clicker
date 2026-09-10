# Answer key — case 04

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 04-a | 8 | BLOCKER | The skip is keyed off a probe of the very subsystem under test, so in any environment where the backend is missing **both tests skip and the suite reports success**. "Degrade gracefully" is a suite that passes without testing anything — the `OK (skipped=N)`, exit 0 failure this project already shipped once. |
| 04-b | 8 | BLOCKER | `_make` is never defined or imported. Both tests would error on the first line — and nobody noticed, because in the author's environment they skipped. That is the same defect as 04-a, seen from the other side. |
| 04-c | 2 | CONCERN | `is_reserved` compares a *label* — display text — against a set of pynput combo strings. `Hotkey.label()` produces `"Alt + F4"`, which lowercased and despaced is `"alt+f4"`, never `"<alt>+<f4>"`. The function always returns `False`. |
| 04-d | 7 | CONCERN | `RESERVED` mixes macOS (`<cmd>+q`, `<cmd>+tab`) and Windows (`<ctrl>+<alt>+<delete>`) combinations with no platform branch, so every user is warned about combinations their system does not claim and not warned about ones it does. |
| 04-e | 9 | CONCERN | The class-body `try/except` runs at import time, so importing the test module has a side effect. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 04-x | A hard-coded `RESERVED` set looks lazy | There is no portable API for this; a curated list is the honest approach, and the roadmap does not promise more. |
| 04-y | `.lower().replace(" ", "")` looks like sloppy normalisation | Normalising before comparison is correct; the bug is *what* is being compared (04-c), not that it is normalised. |

## Scoring

04-a and 04-b together are the point of this case: a test that cannot run and a
skip that hides it. A reviewer that reports "tests pass" without checking
**what the skip count means** has reproduced the exact mistake this project
made.
