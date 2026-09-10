# Review calibration

Ten dummy features, each carrying planted defects. The review agent reviews
them exactly as it reviews a real pull request — the ten rounds in
`docs/REVIEW-PROTOCOL.md`, measured against `docs/TECHSTACK.md`,
`CODING-GUIDELINES.md` and `ROADMAP.md`. Its report is then scored against a
sealed answer key.

## What is in each case

Deliberately not written down here. `GRADING.md` holds the list, and it is for
graders. The first run of this suite was measured against an agent that had
already read a table in this file naming one planted defect per case, which is
not a measurement.

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
