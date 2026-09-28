# Review calibration

Ten dummy features, each carrying planted defects. The review agent reviews
them exactly as it reviews a real pull request — the ten rounds in
`docs/REVIEW-PROTOCOL.md`, measured against `docs/TECHSTACK.md`,
`CODING-GUIDELINES.md` and `ROADMAP.md`. Its report is then scored against a
sealed answer key.

## Why these ten

Every planted defect is one this project actually shipped, or one a review
round actually caught late. Inventing plausible-looking bugs would calibrate
the agent against my imagination; these calibrate it against the record.

| Case | Planted defect | Where it really happened |
|---|---|---|
| 01 | Tk touched from a worker thread | the settings snapshot rework |
| 02 | A class shadowing an imported symbol | `Button` vs `pynput.mouse.Button` |
| 03 | `try/except` where validation is needed | `{"keys": "nope"}` builds a hotkey out of garbage |
| 04 | A test that skips instead of failing | `OK (skipped=57)`, exit 0, no display |
| 05 | A test that measures the harness | XTEST double-delivery; the CI interval spread |
| 06 | `${{ }}` interpolated into a `run:` | the release workflow's version job |
| 07 | A release tagged on the wrong commit | missing `target_commitish` |
| 08 | A Linux-only assumption | `dirname(dirname(mkdtemp())) == os.sep` |
| 09 | A fix whose test passes without it | the swap-script root-walk guard |
| 10 | A silent no-op reporting success | `str.replace()` matching nothing |

## The trap in every case

Each case also contains at least one thing that **looks** wrong and is not —
an unusual construct with a good reason, a comment that seems to contradict
the code, a value that looks arbitrary and is measured. A reviewer that flags
everything scores no better than one that flags nothing, and the answer key
counts those as false positives.

## Running it

```
python3 review-calibration/run.py --list
python3 review-calibration/run.py --case 03        # print the case for a reviewer
python3 review-calibration/run.py --score 03 report.md
```

The answer keys live in `cases/NN/ANSWER.md`. **Do not put them in front of the
agent being calibrated.** `run.py --case` prints only `feature.py` and `PR.md`.

## What to do with the result

A miss is not a mark against the agent, it is a gap in the protocol. Each miss
should end as either a sharper question in `docs/REVIEW-PROTOCOL.md` or a rule
in `docs/CODING-GUIDELINES.md`. The score is the instrument, not the goal.
