# Answer key — case 05

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 05-a | 8 | BLOCKER | `test_rate_matches_the_interval` sleeps for 50 ms and asserts 20/s within ±0.5 — a 2.5% tolerance on a `time.sleep` loop. On a shared CI runner that is measuring the scheduler, not the meter. This project measured a 100 ms spread on macOS with the timing *switched off*; the same assertion here is flaky by construction. |
| 05-b | 8 | BLOCKER | `test_window_is_bounded` asserts only the length. Replace `pop(0)` with `pop()` — dropping the *newest* sample instead of the oldest — and it still passes, while the meter now averages twenty timestamps that never advance and reports a rate that decays toward zero. The test names the property it does not check. |
| 05-c | 2 | CONCERN | `samples.pop(0)` on a list is O(n) per tick. At 20 entries this is irrelevant, and saying so is the point — but a reviewer should notice `collections.deque(maxlen=)` expresses the intent and removes the branch. |
| 05-d | 2 | CONCERN | The meter is never told about the eating pause, so a rate that drops to zero for two seconds is averaged in and the display sags for the next twenty ticks. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 05-x | `if span else 0.0` looks like it hides a division by zero | Two ticks inside one clock granularity genuinely give a zero span; returning 0.0 is the honest answer. |
| 05-y | `WINDOW = 20` looks arbitrary | Twenty samples at half a second is a ten-second window, which is a reasonable smoothing constant. Worth a comment, not a finding. |

## Scoring

05-a is the essential finding: an absolute timing assertion on CI measures the
runner. 05-b is the harder one — a test that looks like it covers the bound and
survives the mutation that breaks the meter. Mutation is the only way to see
it, and a reviewer who does not mutate will call this case clean.
