# Answer key — case 08

## Planted defects

| id | Round | Severity | Defect |
|---|---|---|---|
| 08-a | 7 | BLOCKER | `profile_name_from_path` splits on `"/"`. On Windows a path is `C:\Users\x\Downloads\minecraft.afkprofile` and the function returns the whole string. `os.path.basename` exists and is used correctly two functions below, which makes the inconsistency the tell. |
| 08-b | 7 | BLOCKER | `export_dir` assumes `~/Downloads` exists and is the right place. It is not created if missing, is localised on Windows and German macOS, and `open()` raises `FileNotFoundError` — the export simply fails with a traceback. |
| 08-c | 5 | BLOCKER | `import_profile` feeds `blob["game"]` and `blob["values"]` straight into the store with no validation. An import file is untrusted input from another person; a crafted `values` writes arbitrary keys into `settings.json`, and a missing key raises `KeyError` out of the import. |
| 08-d | 2 | CONCERN | `temp_copy` is defined and never called, so the protection the PR advertises does not exist. |
| 08-e | 7 | CONCERN | The file is opened without `encoding=`, so it is read and written in the platform's default encoding — a profile exported on Windows and imported on Linux can mangle a game name with non-ASCII characters. |
| 08-f | 8 | CONCERN | No test; the manual round-trip was done on one platform, which is exactly where 08-a does not show. |

## Deliberate non-defects

| id | Looks wrong because | Why it is right |
|---|---|---|
| 08-x | `store.put_game` writing immediately looks like it should batch | It is the existing contract; every setting change persists at once. |
| 08-y | A custom `.afkprofile` extension looks like over-invention | It is a reasonable way to make the file recognisable and is not a defect. |

## Scoring

08-a is the essential finding, and it is deliberately placed next to a correct
use of `os.path.basename` so that a reviewer reading carefully can see the
author knew better twelve lines away. 08-d is the quiet one: a safety
mechanism named in the PR that is never invoked.
