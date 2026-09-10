# Answer key — case 03

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 03-a | 5 | BLOCKER | `except Exception` around a parse is the pattern `CODING-GUIDELINES.md` names explicitly. It hides real bugs as readily as bad data: a `TypeError` from a code change is swallowed exactly like a corrupt value, and the window silently loses its position with nothing logged. The blob must be *validated* — four keys, all `int`. |
| 03-b | 2 | BLOCKER | Nothing bounds the restored geometry. A stored position from a monitor that is no longer attached puts the window off-screen where it cannot be moved back, and the only recovery is editing the config by hand. |
| 03-c | 5 | CONCERN | `"%dx%d+%d+%d" % (...)` raises `TypeError` on a string value, which 03-a then swallows — so the defence and the bug are the same line. A validated version would reject it explicitly. |
| 03-d | 2 | CONCERN | Negative `x`/`y` are legal Tk geometry with a different meaning (offset from the far edge), so a validator that merely checks `isinstance(int)` still restores a window off-screen. Bounds, not just types. |
| 03-e | 8 | CONCERN | No test. The manual "hand-edited to garbage" check passes for the wrong reason — it proves the `except` fires, not that the value was rejected. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 03-x | `store.data.get("window") or {}` looks like it hides a missing key | It is the correct idiom here: absent and empty are the same case, and the caller handles `None` from the function. |
| 03-y | Saving on every close rather than on move | Cheap, and avoids writing the config on every drag event. |

## Scoring

03-a is the essential finding. 03-b is the one that costs a user real trouble
and that a reviewer reading only for the `except` will walk past — the feature
is unusable, not merely fragile, when the monitor layout changes.
