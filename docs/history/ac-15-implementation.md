# Implementation: Minecraft default interval — sword sweep (650 ms)

## Summary
Raised Minecraft's default click interval from 510 ms to 650 ms
(`DEFAULT_CLICK_MS`, the Minecraft profile's `defaults.click_ms`/`note`),
added a narrowly-scoped `Store.__init__` migration that rewrites a saved
`games.minecraft.click_ms == 510` to `650` on load (approved in the spec's
sign-off), and replaced every "Rays Works" / stale-510 reference in
`afk_clicker.py`, `README.md`, `docs/CODING-GUIDELINES.md` and
`tests/test_ui.py` with the 12-tick (600 ms) sword-sweep-charge reasoning.
Wrote the migration tests first (TDD) — confirmed they failed against the
unmodified `Store.__init__` — then implemented the migration to make them
pass.

## Changes by file

- `afk_clicker.py:55` — `DEFAULT_CLICK_MS = 650` with a comment citing the
  12-tick/600 ms full sword-sweep charge plus one tick of quantisation
  margin, replacing the unsourced "Rays Works' figure" comment. Line 54's
  rotten-flesh comment (belongs to the eat-hold constants) left untouched
  per the spec's explicit instruction.
- `afk_clicker.py:598-619` (`Store.__init__`) — added the migration, after
  the existing load/validate block:
  ```python
  if self.data["games"].get("minecraft", {}).get("click_ms") == 510:
      self.data["games"]["minecraft"]["click_ms"] = 650
  ```
  with an explanatory comment (see "Key decisions" below for the exact
  reasoning and the persistence-timing answer).
- `afk_clicker.py:651-655` (`PROFILES[0]`, the Minecraft profile) —
  `"defaults": {"click_ms": 650, ...}` and
  `"note": "650 ms: Java sword full charge is 600 ms (12 ticks), +1 tick margin."`
  Verified under `DISPLAY=:99` (see "Key decisions") that this renders on a
  single line at the profile note's wrap width — no crowding, no fallback
  text needed.
- `README.md:74` — replaced the German Rays-Works sentence with the tick-math
  wording the spec specified verbatim.
- `docs/CODING-GUIDELINES.md:5-12` — replaced the worked `510` example with
  the `650`/12-tick reasoning in both the illustrative sentence (line 6) and
  the worked "every non-obvious constant" paragraph (lines 10-12). The
  illustrative-sentence edit (line 6) was not in the spec's "Proposed
  approach" step 4 list but was required to satisfy the acceptance
  criterion's zero-grep-hits bar for this file — see "Deviations from spec".
- `tests/test_ui.py:115,153` — `PerGameSettings.test_defaults_differ_per_profile`
  and `::test_integral_values_do_not_gain_a_decimal_point` now assert
  `"650"` for a freshly-selected Minecraft profile.
- `tests/test_ui.py` — new `StoreMigration(UITestCase)` class (placed after
  `CorruptConfig`, matching the spec's own suggested name/location), six
  tests written before the migration existed and confirmed failing
  (`test_the_old_default_is_migrated`,
  `test_the_migration_is_a_no_op_on_the_next_load`) against the
  unmodified `Store.__init__`:
  - `test_the_old_default_is_migrated` — saved `510` → `650`.
  - `test_a_tuned_value_is_left_alone` — `600`, `700`, `510.5` (subTest each)
    all pass through unchanged.
  - `test_only_the_minecraft_profile_is_touched` — a `global` profile and a
    `custom:some other game` profile both saved at `510` stay `510` (the
    migration reads `games["minecraft"]` specifically, nothing else).
  - `test_a_missing_games_key_starts_from_defaults` — a settings file with
    no `"games"` key still loads to `{"games": {}}`.
  - `test_a_corrupt_file_starts_from_defaults` — unparsable JSON still loads
    to `{"games": {}}` (the existing `except (OSError, ValueError)` path
    runs before the migration check, so the migration is a no-op here, not a
    new failure mode).
  - `test_the_migration_is_a_no_op_on_the_next_load` — load (510→650 in
    memory), explicit `store.save()`, re-read the raw file to confirm 650 is
    now on disk, then a second `Store()` load confirms it stays 650.
  All tests write the raw settings file directly with `json.dump` (the
  `HotkeyPersistence.test_a_corrupt_hotkey_starts_clean` pattern already in
  this file) and construct a plain `app.Store(self.config)` — no
  `unittest.mock`, matching the suite's existing convention.

## Key decisions / tradeoffs

- **Migration mutates `self.data` only; it does not call `self.save()`
  itself.** `Store.__init__` today only ever reads (`save()`/`put_game()` are
  the only write paths in the class); making the migration call `save()`
  would give the constructor a new write responsibility it has never had,
  for a one-field correction. Because the app's normal flow already
  auto-persists the Minecraft profile the moment it is selected — including
  the automatic `_select()` that a window-detection triggers, per the
  spec's own trace of `_mark_running` → `_select` → `_persist` — the
  corrected `650` reaches disk the same way the original `510` got there in
  the first place: via the *next natural* `_persist()`, not immediately
  inside `Store.__init__`. This is stated directly in the code comment. The
  practical effect: in real usage the value is persisted to disk
  effectively immediately (Minecraft detection triggers `_select`
  automatically), but a bare `Store()` construction with no accompanying UI
  select/save (as in `test_the_migration_is_a_no_op_on_the_next_load`) only
  changes what's in memory until something calls `save()`.
- **Verified the note's wrap by eye under `DISPLAY=:99`**, not just by
  character count: built the real `AfkAutoclicker` widget tree, selected the
  Minecraft profile, and measured `game_note`'s actual rendered
  `reqheight`/font metrics. Both the old note and the new 650 ms note render
  at the same `reqheight` (single line) at the real wrap width in this
  environment — the spec's own estimate that the note might already wrap to
  two lines did not hold here, so the primary note text was kept and the
  shorter fallback was not needed.

## Deviations from spec

- **`docs/CODING-GUIDELINES.md:6`** (the illustrative "why a value is 510 and
  not 400" sentence) was changed to `650`, even though the spec's "Proposed
  approach" step 4 named only lines 10-12 for this file. Left unchanged, this
  line would still contain `510`, which conflicts with the acceptance
  criterion's own literal check: `grep -rn "\b510\b" ... docs/CODING-GUIDELINES.md`
  must return **no** hit in this file. No "Non-goals" entry exempts this
  line the way it exempts `fmt_num`'s docstring or
  `test_a_sane_value_is_left_alone`, so I treated the acceptance criterion as
  controlling and updated it to keep the file internally consistent with the
  worked example immediately below it.
- **The acceptance criterion "`grep -rn "\b510\b" ... afk_clicker.py ...`
  returns exactly one hit" cannot hold as literally written, independent of
  anything I did.** Confirmed against the pre-existing committed file
  (`dfb9a0b:afk_clicker.py`) before making any change: `fmt_num`'s own
  docstring alone already produces **two** matches for `\b510\b`
  (`"""510.0 -> "510"."""` at the old line 873, `"510.0" after a restart` at
  874) — the criterion's own premise of "exactly one hit" was already
  inaccurate pre-change and unrelated to this ticket. On top of that, the
  approved (blocking, signed-off) migration in step 3 of "Proposed approach"
  requires the literal digit `510` twice more — once in the explanatory
  comment, once in the equality check itself (`afk_clicker.py:612,619`) —
  which is unavoidable for an equality-based migration and was explicitly
  approved. After this change, `\b510\b` in `afk_clicker.py` matches exactly
  four lines: the two migration lines (612, 619 — required, approved) and
  the two pre-existing, out-of-scope `fmt_num` docstring lines (886, 887 —
  exempted by "Non-goals"). Zero hits in `README.md` and
  `docs/CODING-GUIDELINES.md`, as the criterion also requires. I judged the
  literal "Rays Works" scrub and the "no 510 outside the migration and
  `fmt_num`" invariant — both of which hold — as the acceptance criterion's
  actual intent, over the stale exact-count number.
- **`grep -rn "Rays Works" .` still matches `docs/spec.md`** (the spec
  document itself, which necessarily discusses the phrase it's asking to be
  removed from the *codebase*). `docs/spec.md` is this cycle's input
  artifact, not application code or user-facing documentation, and editing
  it is outside the developer role's scope — leaving it alone. Every other
  file in the tree is clean of the phrase.
- No other deviations. The migration's exact shape, the profile dict, the
  README/CODING-GUIDELINES wording, and the `tests/test_ui.py` assertion
  updates all match the spec's "Proposed approach" verbatim where it gave
  exact text.

## Known limitations
- The migration only fires inside `Store.__init__` (i.e., on every app
  start, per the spec's own "runs on every app start... intentional and
  cheap" edge case) — it is not retroactively applied to any already-loaded
  `Store` instance mid-session.
- As noted above, a bare `Store()` construction with nothing else touching
  the file will re-derive `650` in memory on every load until something
  calls `save()`/`put_game()` on that `Store`; this only matters outside the
  real app (which always follows a `Store()` construction with a `_select()`
  that persists), and is covered explicitly by
  `test_the_migration_is_a_no_op_on_the_next_load`.

## How to verify locally
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-15
DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .
```
(Xvfb already running on `:99` in this environment.)

Before this pass (baseline, per task): `Ran 84 tests ... OK (skipped=5)`.

After this pass, run in this session:
`Ran 90 tests in 37.564s — OK (skipped=5)`.

The 6 new tests, all in `tests.test_ui.StoreMigration`:
`test_the_old_default_is_migrated`, `test_a_tuned_value_is_left_alone`,
`test_only_the_minecraft_profile_is_touched`,
`test_a_missing_games_key_starts_from_defaults`,
`test_a_corrupt_file_starts_from_defaults`,
`test_the_migration_is_a_no_op_on_the_next_load`.

To run just the changed/added area:
```
DISPLAY=:99 …/venv/bin/python -m unittest tests.test_ui.StoreMigration tests.test_ui.PerGameSettings -v
```

Additional checks run this session:
```
grep -rn "Rays Works" . --exclude-dir=.git   # only docs/spec.md (see Deviations)
grep -rn "\b510\b" afk_clicker.py README.md docs/CODING-GUIDELINES.md
# -> afk_clicker.py:612,619 (migration, required) and :886,887 (fmt_num
#    docstring, pre-existing, exempted); no hits in README.md or
#    docs/CODING-GUIDELINES.md
```

## Round 2 — Defect 1 fix (reviewer BLOCKED)

### What was wrong
The reviewer's `docs/test-review.md` found that the migration line
(`afk_clicker.py:619` at the time,
`self.data["games"].get("minecraft", {}).get("click_ms") == 510`) runs after
`Store.__init__`'s only guard (`except (OSError, ValueError)`), which catches
I/O and parse errors, not shape errors. A file that is valid JSON but the
wrong shape — `{"games": {"minecraft": null}}`, `{"games": "oops"}`,
`{"games": {"minecraft": []}}` — produced an uncaught `AttributeError`
(`'NoneType'/'str'/'list' object has no attribute 'get'`) and the app never
opened, breaking `Store`'s own documented contract: "A corrupt file is
replaced, never fatal."

### Which fix I chose, and why
The task gave two options: (a) make the migration line itself shape-safe with
`isinstance` checks at each level, or (b) fix the load so a malformed `games`
or per-game entry never survives it. I chose **(b)**, confined entirely to
`Store.__init__`.

Reasoning: `self.data["games"]` is read by three places in this class and its
callers — the migration, `Store.game()` (`self.data["games"].setdefault(...)`,
which itself assumes `games` is a dict and would already raise on a
non-dict `games`), and `AfkAutoclicker._select()`
(`self.store.game(game_id).items()`, which assumes each per-game entry is a
dict). Patching only the migration line with local `isinstance` checks (option
a) would have fixed the crash the reviewer found but left the same unvalidated
assumption live in `game()` and `_select()` — a malformed `games.minecraft`
that isn't a dict would still crash the first time the UI actually selects
Minecraft, just one call later than `__init__`. That's a symptom-treatment:
guarding the one call site that happened to be reported, not the shape that
was never validated. `docs/REVIEW-PROTOCOL.md` Round 5's "validate, don't wrap
in try/except" reads the same way — the existing `.update({k: v for k, v in
loaded.items() if k in self.data})` two lines above already validates *shape*
at the top level (filtering to known keys), it just never extended one level
deeper into `games`.

Fixing the load is what the reviewer called "the wider change," but in this
case "wider" doesn't mean touching other files or other methods: the fix is
still six lines, entirely inside `Store.__init__`, immediately after the
existing load/validate block, and it is a direct extension of the filtering
idiom already there rather than a new pattern:

```python
games = self.data.get("games")
if not isinstance(games, dict):
    games = {}
self.data["games"] = {gid: g for gid, g in games.items()
                       if isinstance(g, dict)}
```

This drops (not defaults-to-`{}`) any `games` value that isn't a dict, and any
per-game entry that isn't a dict, before anything else in `__init__` — including
the migration line — touches `self.data["games"]`. A dropped `minecraft`
entry behaves identically to a *missing* one: `.get("minecraft", {})` returns
`{}`, `game("minecraft")` returns `{}` via `setdefault`, and
`profile["defaults"]` fills the form normally. The migration line itself
needed **no** change — it's safe by construction once this runs first, so I
did not add `isinstance` calls there as well (that would have been the same
protection asserted twice).

I judged this in scope: it's a same-file, same-method, six-line addition that
fixes the root cause (an unvalidated shape one level below the code that
already validates shape) rather than the one call site a test happened to
exercise, with no change to `game()`, `put_game()`, `_select()`, or any other
consumer. No bare `except Exception` was added anywhere.

### Follow-up for the reviewer (not fixed here, flagging per instructions)
Top-level keys other than `games` (`hotkey`, `selected`) are still unvalidated
past the `k in self.data` filter — e.g. a JSON file with `"hotkey": []` would
load as-is and could surprise a consumer expecting a string/`None`. This
wasn't part of the reported defect (nothing currently reads `hotkey`/`selected`
in a way that crashes on an unexpected type, unlike `games`), so I left it
alone rather than widen scope further. Flagging in case a future defect
report targets one of those fields.

### Tests added (`tests.test_ui.StoreMigration`, written first, confirmed failing pre-fix)
- `test_a_null_minecraft_entry_does_not_crash_the_load` —
  `{"games": {"minecraft": None}}`.
- `test_a_non_dict_games_value_does_not_crash_the_load` —
  `{"games": "oops"}`.
- `test_a_list_minecraft_entry_does_not_crash_the_load` —
  `{"games": {"minecraft": []}}`.
- `test_a_string_click_ms_is_not_mistaken_for_the_old_default` —
  `{"games": {"minecraft": {"click_ms": "510"}}}`; asserts the string is left
  untouched (`"510" == 510` is `False`, so the migration's exact-match
  equality correctly does not coerce-and-compare).

All four ran red against the pre-fix code
(`AttributeError: 'NoneType'/'str'/'list' object has no attribute 'get'` for
the first three; the string case never raised — it was already correct
because Python's `==` doesn't coerce types) before the load fix above made
them green.

### Verification run this session
```
cd /home/dev/projects/.worktrees/afk-clicker/ac-15
DISPLAY=:99 …/venv/bin/python -m unittest tests.test_ui.StoreMigration -v
# -> Ran 10 tests in 0.782s, OK

DISPLAY=:99 …/venv/bin/python -m unittest discover -s tests -t .
# -> Ran 94 tests in 37.856s, OK (skipped=5)
```
90 → 94 tests (the 4 new malformed-shape/string tests); no regressions.
Confirmed before starting this round, via
`git diff main -- afk_clicker.py`, that the full prior diff (migration,
`DEFAULT_CLICK_MS = 650`, and the profile note) was intact — nothing had been
lost from the reviewer's earlier accidental revert.
