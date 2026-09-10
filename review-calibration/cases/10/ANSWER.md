# Answer key — case 10

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 10-a | 2 | BLOCKER | The migration renames the key and does **not convert the value**. A v1 file holding `"click_s": 0.51` becomes `"click_ms": 0.51`, which `_num` then clamps to the 50 ms floor — every migrated user silently gets the fastest possible click rate, which is the one setting that breaks the sword sweep. The comment says v1 stored seconds; nothing multiplies by 1000. |
| 10-b | 2 | BLOCKER | `text.replace('"click_s"', ...)` is a string substitution on serialised JSON. If no key matches it does nothing, reports nothing, and `migrate` still returns `True` and stamps `"schema": 2` — a silent no-op that marks the file as migrated. A v1 file whose key was spelled differently is now permanently labelled v2 and will never be migrated again. |
| 10-c | 5 | CONCERN | It would also rewrite the string `"click_s"` occurring in *data* — a game the user added whose name contains it. Structural edits belong on the structure, not the serialisation. |
| 10-d | 2 | CONCERN | `shutil.copy(path, path + ".bak")` overwrites any previous backup, so running the migration twice destroys the only copy of the original. |
| 10-e | 5 | CONCERN | `json.load` is unguarded: a corrupt settings file raises out of `ensure_schema` and the window never opens — the failure `Store` is specifically written to survive. |
| 10-f | 9 | CONCERN | `store.__init__(store.path)` re-runs a constructor on a live object to reload it. It works, and it is the kind of thing that stops working the moment `__init__` acquires a side effect. A `reload()` method says what is meant. |
| 10-g | 8 | CONCERN | No test. A migration is exactly the code that runs once, on a user's only copy of their data, and cannot be retried. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 10-x | Returning `False` when the file is absent looks like it hides a problem | A fresh install has no file; nothing to migrate is the normal case. |
| 10-y | `SCHEMA_VERSION = 2` starting at 2 rather than 1 | v1 is the unversioned format, so 2 is the first written version. Correct. |

## Scoring

10-a and 10-b are both blockers and they compound: the value is wrong *and* the
file is marked migrated so it can never be corrected. 10-b is the silent-no-op
pattern this project hit three times in one session with `str.replace`. A
reviewer that catches only the missing multiplication has found the smaller
half.
