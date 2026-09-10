# Version the settings schema

Closes #50

`settings.json` had no version field, so any future format change would have
silently reset everyone's per-game values. This adds `"schema": 2` and migrates
v1 files in place.

A `.bak` copy is written before anything is rewritten, so a failed migration
cannot lose a configuration.

The rename from `click_s` to `click_ms` is done on the serialised text, which
handles the key wherever it appears — top level or nested inside a game —
without walking the structure by hand.

## Verification

Migrated a v1 file; the schema field appeared and the window opened with the
settings intact.
