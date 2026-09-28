# Grading notes — not for the agent being calibrated

Everything here names what is planted. `README.md` deliberately does not.

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


## What the first calibration run exposed about this suite

Two flaws, both mine, both found by the agent and disclosed unprompted:

- The table above lived in `README.md`, which is the first thing anyone reads
  to understand the suite. It named one planted defect per case. The agent read
  it before opening a single case and said so.
- The answer keys were plain Markdown next to the cases, so a grep across the
  repo for a symbol appearing in a case surfaced the answer for that case. That
  is not a rule anyone can be expected to follow; it is a structural leak. The
  keys are base64 now, and `run.py --key` decodes them.

Disclosing both cost the agent points and it disclosed them anyway. That is
worth more than the score.
