# Answer key — case 01

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 01-a | 3 | BLOCKER | `_run` reads `self.ui.click_ms.var.get()` — a Tk variable — from a worker thread. Unsupported; works only while the main loop spins and raises `main thread is not in main loop` otherwise. It must read the settings snapshot. |
| 01-b | 3 | BLOCKER | `_run` calls `self.ui.status.set(...)` directly from the worker: a widget update off the main thread. Must go through `_ui()`. |
| 01-c | 2 | CONCERN | The counter increments on its own timer rather than being told about a click, so it counts *intended* clicks. It keeps counting during the eating pause, when no click happens, and its "verification" cannot have matched the log. |
| 01-d | 3 | CONCERN | `self._worker` is created in `start()` but never declared in `__init__`, and nothing joins or stops it; a second `start()` leaks a thread. |
| 01-e | 8 | CONCERN | No test at all. The PR's verification is a manual twenty-minute run, which is not repeatable and did not catch 01-c. |

## Deliberate non-defects — flagging these is a false positive

| id | Looks wrong because | Why it is right |
|---|---|---|
| 01-x | `max(1e-6, ...)` looks like a magic number | It guards a division by zero on the first pass; the comment is absent but the construct is correct. |
| 01-y | `time.monotonic()` over `time.time()` seems like over-engineering | It is correct and the comment explains it: a wall-clock adjustment would make the rate negative. |

## Scoring

- 5 defects, 2 traps.
- A report that names 01-a and 01-b as blockers has the essential finding.
- Full marks require 01-c, which is the one a reviewer reading only for
  threading will miss — the feature does not measure what the PR claims.
