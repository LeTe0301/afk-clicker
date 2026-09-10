# Answer key — case 09

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 09-a | 8 | BLOCKER | `test_log_is_not_written_to_the_root` passes with the fix removed. Replace the body of `session_log_path` with `return os.path.join(os.sep, name)` and the assertion still holds on any system whose temp directory is nested — the test asserts a property of `tempfile.gettempdir()`, not of the function. This is the "fix with no failing test" pattern: the PR claims a fix and a test for it, and the test cannot detect its absence. |
| 09-b | 2 | BLOCKER | `focused_window_title` takes the *first* title, which is the frontmost window on Windows and the **last** one in an X11 tree walk. On Linux the check therefore reads the wrong window and `may_start` is true whenever any window exists — including when the desktop has focus. |
| 09-c | 2 | CONCERN | `may_start` refuses only when the list is empty. A focused window belonging to the clicker itself passes, so starting the clicker from its own window is allowed and clicks land in the app. |
| 09-d | 9 | CONCERN | The PR describes the log-path fix as incidental ("found while writing this"), which mixes two tickets in one change. |
| 09-e | 8 | CONCERN | `LogPathTests.setUp` sets `self.name` and nothing else; the fixture implies shared state that does not exist. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 09-x | `os.makedirs(..., exist_ok=True)` on every call looks wasteful | It is the idiomatic guard and costs a stat; correct. |
| 09-y | Refusing to start on an empty list looks too strict | It is the stated feature, and the PR explains why. |

## Scoring

09-a is the point of the case and the hardest kind of finding: everything looks
right, the test is named after the behaviour, and it passes either way. Only
mutation shows it. A reviewer who reports "covered by a test" without checking
whether the test can fail has missed the entire lesson.
