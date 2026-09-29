# Hotfix pipeline

Closes #47

A released build being broken in the field should not have to wait for the full
release ceremony. Pushing `hotfix/0.3.2` runs the suite and publishes.

The version is taken from the branch name through `env`, never interpolated
into the script, and shape-checked with `re.fullmatch` rather than `grep`,
which matches line by line. `contents: write` sits on the publish job only.

## Verification

Pushed `hotfix/0.0.1` to a fork; the suite ran and the release appeared.
