# Spec: Minecraft default interval — sword sweep (Gitea admin/afk-clicker#15, GitHub #17)

## Summary
Raise Minecraft's default click interval from 510 ms to 650 ms so a full-charge
sword sweep (12 server ticks / 600 ms, +1 tick margin) actually lands, and
replace every "Rays Works" / "510" reference in code, docs and tests with the
verified tick-based reasoning — while leaving anyone who has genuinely tuned
their own interval untouched.

## Goals
- A Minecraft profile that has never had a real value typed into it (fresh
  install, or a settings.json whose `games.minecraft.click_ms` still equals the
  old default) ends up at 650 ms, not 510 ms.
- `DEFAULT_CLICK_MS`, the Minecraft profile's `defaults.click_ms`/`note`, the
  README table, and `CODING-GUIDELINES.md`'s worked example all cite 650 ms /
  12-tick charge math instead of "Rays Works' figure."
- No source in this repo attributes 510 to Rays Works after this change — the
  attribution has no basis and must go everywhere, not just in the constant's
  comment.
- Existing users who genuinely typed a different interval (anything other than
  exactly the old default) keep that value, per the ticket.

## Non-goals
- **No UI warning when `click_ms − jitter` drops below 600/650 ms.** The
  ticket's own default position is to leave this out of scope, and I agree:
  it needs its own design (where does the warning show, does it block Start,
  does it account for sub-20-TPS/Mining Fatigue III too) and is a separate,
  reviewable piece of work. Logging it as a follow-up candidate for
  `docs/ROADMAP.md`, not building it here.
- **No settings schema version / general migration framework.** `ROADMAP.md`
  already tracks "Settings schema version" as unresolved pre-1.0 work; this
  ticket does one narrowly-scoped, self-contained value fix (see "Proposed
  approach" step 3), not the general mechanism.
- **No change to non-Minecraft profiles**, eating tuning (`DEFAULT_EAT_EVERY_S`,
  `DEFAULT_EAT_HOLD_S`), the hotkey system, or the jitter algorithm itself.
- **No change to `fmt_num`'s docstring** (`afk_clicker.py:873-874`, `"510.0" ->
  "510"`). That's a generic float-formatting example unrelated to Minecraft's
  default value; touching it is drive-by cleanup outside this ticket's scope.
- **No change to `NumericClamping.test_a_sane_value_is_left_alone`**
  (`tests/test_ui.py:319-321`). It exercises `_num()`'s generic pass-through
  behaviour using 510 as an arbitrary sane number, not Minecraft's default —
  changing it would just be noise in the diff.

## Background / current state
`DEFAULT_CLICK_MS = 510` (`afk_clicker.py:55`) is both a general app-wide
fallback (initial `NumBox` value at line 1097, the `_num()` fallback at line
1352, and the click-loop's `cfg.get("click_ms", DEFAULT_CLICK_MS)` fallback at
line 1500) and, coincidentally, the number baked into the Minecraft profile's
own `defaults` dict (`afk_clicker.py:642`) and `note` string (line 641). The
ticket's decompilation-verified research (already posted on the ticket, not
reproduced here) establishes that 510 ms (10.2 ticks) almost never sweeps —
full charge needs > 0.9 charge, reached at tick 12 (600 ms), first possible at
tick 11 (550 ms) — and that "Rays Works' figure" has no traceable source. The
recommended default is 650 ms (13 ticks), which keeps a full tick of margin
against click/tick quantisation jitter.

**How a saved value actually gets to disk** (`Store`, `afk_clicker.py:595-624`;
`_select`/`_persist`, lines 1139-1191): `_select()` always calls `self._persist()`
unconditionally near its end (line 1173) — the `persist` parameter only gates
whether `store.data["selected"]` is written, not the per-game values. `_persist()`
reads the current widget values (which `_select()` just populated from
`profile["defaults"]` if nothing was saved yet) and calls
`store.put_game(...)`, which saves immediately. Critically, `_select()` is
called not only when a user clicks a game in the sidebar, but automatically
the first time Minecraft's window is ever detected
(`_mark_running` → `_select(sorted(fresh)[0])`, line 1303). So **`click_ms:
510` gets written to `settings.json` for a Minecraft profile the first time the
app ever sees a Minecraft window, before the user has touched the field at
all.** A stored value of exactly 510 is therefore not reliable evidence that
anyone deliberately chose it — for nearly every existing installation it is
just the old default having been auto-persisted. This is the crux of "Open
questions" below.

## Proposed approach
1. **Bump the constant.** `afk_clicker.py:55`:
   `DEFAULT_CLICK_MS = 650      # 12 ticks (600 ms) is Java's full sword-sweep charge; +1 tick covers click/tick quantisation jitter`
   (Leave line 54's rotten-flesh comment alone — it belongs to the eat-hold
   constants two lines down, not to this one; the ticket flagged the adjacency
   only as a locator, not a relationship.)

2. **Minecraft profile dict** (`afk_clicker.py:636-645`):
   - `"defaults": {"click_ms": 650, ...}` (rest of the dict unchanged).
   - `"note": "650 ms: Java sword full charge is 600 ms (12 ticks), +1 tick margin."`
     — verify this renders acceptably in `game_note`'s wrap column
     (`wraplength=(CONTENT_W - 32) * s` = `420 * s` at `CONTENT_W = 452`,
     `font=("Segoe UI", int(8.5 * s), "bold")`, `afk_clicker.py:1074-1077`).
     The current note is 65 characters and already wraps to two lines at this
     width; the proposed note is 71 characters, so expect a similar two-line
     wrap, not an overflow. Confirm by eye under `DISPLAY=:99` after selecting
     the Minecraft profile. If it visibly crowds the eating card below it,
     fall back to the shorter equivalent
     `"650 ms: full Java sword-sweep charge (12 ticks) + 1-tick margin."`
     (67 characters) rather than inventing new wording.

3. **Store migration, narrowly scoped** (`Store.__init__`, `afk_clicker.py:598-607`):
   after the existing load/validate block, add a small, explicitly-commented
   step: if `self.data["games"].get("minecraft", {}).get("click_ms") == 510`,
   rewrite that one field to `650`. Comment should explain *why* an equality
   check is safe here (see "Background" above and "Open questions" below) —
   something like: "`_persist()` writes this value to disk automatically the
   first time Minecraft is ever selected, before a user touches the field, so
   a stored 510 is the old default having been auto-saved, not a deliberate
   choice; any other value is left alone because it is." This is a single
   `if`, not a general migration mechanism — it doesn't touch the schema, the
   `games` dict shape, or any other profile, so it doesn't require (or
   conflict with) the unresolved "Settings schema version" roadmap item. It's
   naturally idempotent: after the first rewrite the stored value is 650, so
   later loads no-op on the equality check.

4. **Scrub "Rays Works" / stale "510" everywhere it's an attribution or a
   Minecraft-interval reference:**
   - `README.md:74` (German) — replace the Rays-Works sentence with the tick
     math, e.g.: `Abstand zwischen zwei Klicks. 650 ms deckt Javas volle
     Sword-Sweep-Aufladung ab (12 Ticks / 600 ms) plus einen Tick Puffer.`
   - `docs/CODING-GUIDELINES.md:10-12` — the worked example currently reads
     `` `510` is Rays Works' figure and faster breaks the sword sweep. `` —
     replace with the 650/12-tick reasoning, keeping the same "non-obvious
     constant carries its reason" teaching point, e.g.: `` `650` is Java's
     12-tick (600 ms) sword-sweep charge plus a tick of margin; faster and the
     hit lands as a 76%-damage non-sweep instead. ``
   - `tests/test_ui.py:115` (`PerGameSettings.test_defaults_differ_per_profile`)
     and `tests/test_ui.py:147-153`
     (`PerGameSettings.test_integral_values_do_not_gain_a_decimal_point`) —
     both assert `self.ui.click_ms.var.get() == "510"` for a freshly-selected
     Minecraft profile; update both to `"650"`.
   - Confirm nothing else references 510/Rays Works: `grep -rn "Rays Works"`
     over the tree should return zero hits after this change, and `grep -rn
     "\b510\b" afk_clicker.py README.md docs/CODING-GUIDELINES.md
     tests/test_ui.py` should return only `fmt_num`'s unrelated docstring
     example (`afk_clicker.py:873`) and, if left as-is per the non-goal above,
     `test_a_sane_value_is_left_alone` (`tests/test_ui.py:319-321`).

5. **New tests for the migration** (developer's call on exact placement,
   likely alongside `PerGameSettings` or a small `StoreMigration` test class):
   - A `settings.json` with `games.minecraft.click_ms: 510` gets rewritten to
     `650` on `Store()` load.
   - A `settings.json` with `games.minecraft.click_ms: 444` (or any non-510
     value) is left at `444` after `Store()` load.
   - Running the migration twice (load, save, load again) is a no-op the
     second time (idempotence) — or simply follows from the first assertion
     plus the existing `test_survives_a_restart`-style pattern already in the
     file.

## Affected areas
Single-layer change — one module (`afk_clicker.py`), two docs (`README.md`,
`docs/CODING-GUIDELINES.md`), one test file (`tests/test_ui.py`). No schema
change, no new files, no API/interface change. Not split into sub-specs (skill
11 doesn't apply — this doesn't span architectural layers).

## Edge cases
- Fresh install, `settings.json` missing or has no `"minecraft"` key: gets 650
  straight from `PROFILES[0]["defaults"]`, migration check is a no-op
  (`.get("minecraft", {}).get("click_ms")` is `None`, `None != 510`).
- `games.minecraft.click_ms == 510` exactly (the common case — see
  "Background"): migrated to 650 on next load.
- `games.minecraft.click_ms` is any other number (e.g. 444, 600, 700): left
  untouched, per the ticket's "a user who tuned their own interval keeps it."
- Corrupt/unreadable `settings.json`: `Store.__init__`'s existing
  `except (OSError, ValueError): pass` already falls back to
  `{"games": {}, ...}` before the new migration check runs, so a corrupt file
  still starts from defaults and the migration check is a harmless no-op —
  no new failure mode introduced.
- A custom "Add current game" profile cannot collide with the `"minecraft"`
  key: custom games are stored under `custom:<title>` ids
  (`tests/test_ui.py`'s `test_added_game_persists` confirms this), so the
  migration's `games.get("minecraft", ...)` lookup only ever touches the
  built-in profile.
- The migration runs on every app start (every `Store()` construction), not
  just once ever — this is intentional and cheap (one dict `.get()` and
  comparison), and is what makes it self-correcting without a schema version.
- Jitter can still pull the effective interval below 650 ms today
  (`click_ms − jitter`, `afk_clicker.py:1501-1505`) with no warning — noted,
  explicitly out of scope (see Non-goals).

## Acceptance criteria
- [ ] Given a `settings.json` with no `"minecraft"` key, when the app starts
      and the Minecraft profile is selected, then `click_ms` reads `650`.
- [ ] Given a `settings.json` with `games.minecraft.click_ms: 510`, when the
      app starts, then the stored value becomes `650` and the Minecraft
      profile shows `650` on selection.
- [ ] Given a `settings.json` with `games.minecraft.click_ms: 444`, when the
      app starts, then the stored value remains `444` after load.
- [ ] Given the Minecraft profile is selected, then `game_note` reads text
      describing the 600 ms/12-tick charge and the 650 ms/1-tick margin, and
      contains no mention of "Rays Works."
- [ ] `grep -rn "Rays Works" .` (excluding `.git`) returns no matches anywhere
      in the tree.
- [ ] `grep -rn "\b510\b" afk_clicker.py README.md docs/CODING-GUIDELINES.md`
      returns exactly one hit: `fmt_num`'s docstring example at
      `afk_clicker.py:873` (`"510.0" -> "510"`), which is unrelated to
      Minecraft's default and is the one `510` this ticket deliberately
      leaves in place (see Non-goals). No hit in README.md or
      docs/CODING-GUIDELINES.md.
- [ ] `tests/test_ui.py::PerGameSettings::test_defaults_differ_per_profile`
      and `::test_integral_values_do_not_gain_a_decimal_point` assert `"650"`
      and pass.
- [ ] New Store-migration tests (510→650 rewrite; non-510 left alone) pass.
- [ ] Full suite: `DISPLAY=:99
      /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python
      -m unittest discover -s tests -t .` from the worktree passes, at or
      above the 84-tests-OK/5-skipped baseline (count grows by however many
      migration tests are added; no existing test should newly fail or newly
      skip).

## Open questions

**Blocking — needs explicit sign-off before the developer stage, because it
changes what code gets written, not just an assumption I can safely make on
your behalf:**

Do you approve the Store migration in step 3 (rewriting a saved
`games.minecraft.click_ms == 510` to `650` on load)?

- **My recommendation: yes, do it.** The empirical trace above shows
  `_persist()` auto-writes the default the moment Minecraft is first detected
  or selected — not only when a user edits the field. That means essentially
  every existing installation that has ever run the app with Minecraft open
  already has `click_ms: 510` on disk, tuned or not. If I only change the
  in-code default (option below), the fix reaches nobody who has ever run the
  app before — it would be a silent no-op for the exact population the ticket
  is about. The equality check is narrow (one field, one profile id, exact
  match against the literal old default) and low-risk even in the
  false-positive case: a user who supposedly *chose* exactly 510 on purpose
  chose the precise value that breaks sweeps, so moving them to 650 cannot
  leave them worse off.
- **Rejected: change only the in-code default, leave saved values alone.**
  Simpler and closer to "never touch a user's data," but per the trace above
  this is very likely a no-op for real users — most Minecraft profiles are
  already stamped with 510 whether or not anyone typed it. This satisfies "a
  tuned value is never touched" trivially by also never fixing anyone.
- **Rejected: one-time UI hint/banner instead of (or in addition to)
  migrating.** Passive and easy to miss — this is an AFK tool by design, so a
  banner nobody is watching doesn't reach the actual use case. Could be added
  later as a supplement, but isn't a substitute for fixing the stored value.
- Note re: `ROADMAP.md`'s open "Settings schema version" item and
  `REVIEW-PROTOCOL.md` Round 10 ("Does the settings format change? Without a
  schema version there is no migration path, and users lose their per-game
  values silently.") — I read that round as guarding against *structural*
  format changes losing data, not a single-field default nudge scoped to one
  named key on one named profile id with an explicit equality guard. Flagging
  this reading explicitly since Round 10 exists precisely to catch this kind
  of change.

**Not blocking — my assumption, stated for the record:** the `click_ms −
jitter` UI warning (dispatch question 2) stays out of scope for this ticket,
per the ticket's own default and my agreement above. Proceeding on that
assumption; not gating on it.

## Risk / rollback notes
- **Risk:** the 510→650 migration could, in the vanishing edge case of a user
  who re-typed exactly 510 after already knowing it breaks sweeps, silently
  change their saved value. As reasoned above, that user ends up with the
  value that actually works, not a regression, so this risk is judged
  acceptable if the migration is approved.
- **Rollback:** a plain `git revert` removes the migration code from future
  runs; it does not automatically move an already-migrated `settings.json`
  back to 510. Reverting only stops *further* rewrites — restoring an old 510
  for someone who received the migration would need a manual settings edit,
  which is not expected to matter since 510 is the value this ticket exists to
  move people off of.
- **No blast radius beyond the Minecraft profile:** the equality check only
  ever reads/writes `games["minecraft"]["click_ms"]`; every other key, every
  other profile, and the overall `settings.json` shape are untouched, so this
  does not consume or require the still-open "Settings schema version"
  roadmap item.
