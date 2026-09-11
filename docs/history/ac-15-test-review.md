# Test & Review: Minecraft default interval — sword sweep (ac-15) — Round 2

## Round 1 summary (for context)
Round 1 blocked on Defect 1: the new `Store.__init__` migration line
(`self.data["games"].get("minecraft", {}).get("click_ms") == 510`) ran after
the constructor's only guard (`except (OSError, ValueError)`, which catches
I/O/parse errors, not shape errors), so a syntactically-valid but
structurally-wrong `settings.json` — `{"games": {"minecraft": null}}`,
`{"games": "oops"}`, `{"games": {"minecraft": [1,2,3]}}` — raised an uncaught
`AttributeError` inside `Store.__init__` and the app never opened, breaking
`Store`'s own documented "a corrupt file is replaced, never fatal" contract.
Two other Round 1 notes (the CODING-GUIDELINES.md 76%-damage figure, and a
`__version__` bump precedent) have since been reviewed and dismissed by the
orchestrator and are not re-raised here.

## Round 2 fix under test
`Store.__init__` (`afk_clicker.py:609-623`) now sanitises `self.data["games"]`
immediately after the existing load/validate block and before the migration
line touches it: a non-dict `games` value is replaced with `{}`, and any
per-game entry that isn't a dict is dropped. The migration line itself
(`afk_clicker.py:635-636`) is unchanged — it's safe by construction once the
sanitiser has run. Four new tests were added to
`tests.test_ui.StoreMigration`: a `null` minecraft entry, a non-dict `games`
value, a list minecraft entry, and a string `"510"` `click_ms` (left
untouched, confirming the fix doesn't change the exact-match migration
semantics).

## Test cases (this round)

| # | Case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Full suite regression | `unittest discover -s tests -t .` under `DISPLAY=:99` | pass | `Ran 94 tests in 37.7s — OK (skipped=7)`. Baseline was 90 OK/5 skipped before this round's 4 new tests; skip count differs by 2 — both are `test_updater.LiveRepository` tests hitting `HTTP Error 403: rate limit exceeded` against the live GitHub API, an environment condition (network-dependent skip firing cleanly per Round 8's own standard), not caused by this diff. Confirmed via `-v` output: the 5 `AFK_SLOW_TESTS` skips are identical to baseline; the 2 extra are the two `LiveRepository` network tests. |
| 2 | `{"games": {"minecraft": null}}` does not crash `Store()` | automated (`StoreMigration.test_a_null_minecraft_entry_does_not_crash_the_load`) + manual real-app construction | pass | `store.data["games"].get("minecraft", {}) == {}`; separately built a real `tk.Tk()` + `app.AfkAutoclicker(root, store=app.Store(path))` against this file — no exception, window builds |
| 3 | `{"games": "oops"}` does not crash `Store()` | automated + manual real-app construction | pass | same as above, `store.data["games"] == {}` |
| 4 | `{"games": {"minecraft": []}}` does not crash `Store()` | automated + manual real-app construction | pass | `store.data["games"].get("minecraft", {}) == {}` |
| 5 | `{"games": {"minecraft": {"click_ms": "510"}}}` left untouched (string is not int `510`) | automated (`test_a_string_click_ms_is_not_mistaken_for_the_old_default`) | pass | `store.data["games"]["minecraft"]["click_ms"] == "510"` |
| 6 | Broader shape-crash sweep: `games` as a list/number/bool, `{"games": {"minecraft": "oops"}}`, a per-game dict with a non-dict nested `click_ms` (`null`/`True`/`1e309`→`inf`/`NaN`), top-level JSON list/number/string instead of an object, `hotkey`/`selected` as a list or number | manual: constructed a real `tk.Tk()` + `app.AfkAutoclicker(root, store=app.Store(path))` for each of 15 malformed files | pass — none crash `Store()` or app construction | All 15 cases: `store_ok=True, app_ok=True`. `games`-shape cases are caught by this round's sanitiser. `click_ms` odd scalar values (`None`/`True`/`inf`/`NaN`) pass through as valid dict entries (the per-game entry is still a dict, so it survives the filter) and reach `fmt_num`/`NumBox` without crashing — this path is unchanged by this diff and is not new exposure. `hotkey`/`selected` odd types don't crash because of pre-existing, unrelated guards: `Hotkey.from_json` explicitly rejects non-dict input (`afk_clicker.py:250`), and `self.current = self.store.data.get("selected") or "global"` followed by an `if self.current not in self.by_id` fallback (`afk_clicker.py:1031-1033`) absorbs a non-string `selected`. Confirmed these guards are unchanged by `git diff main` and pre-date this ticket — not this diff's protection, but confirms no new crash surface opened by leaving them alone. |
| 7 | Revert check: do the 3 new malformed-shape tests actually fail without the sanitiser? | manual: removed the 15-line sanitiser block from `afk_clicker.py` (in-place edit, no `git checkout`), reran `StoreMigration`, restored from a pre-edit backup copy | pass (tests genuinely fail red) | `test_a_null_minecraft_entry_does_not_crash_the_load`, `test_a_non_dict_games_value_does_not_crash_the_load`, `test_a_list_minecraft_entry_does_not_crash_the_load` all `ERROR`ed with `AttributeError: '<type>' object has no attribute 'get'` at the migration line, matching Defect 1 exactly. Restored via `cp` from a backup taken before the edit; verified `md5sum afk_clicker.py` and `git diff main --stat` identical before/after, then reran the full suite (94 OK, skipped=7) to confirm the restored tree behaves identically. |
| 8 | Valid saved custom-game data (with `_profile` metadata) survives the sanitiser | manual code trace | pass | Traced `_persist()` (`afk_clicker.py:1204-1220`): a custom game's saved entry is `{"click_ms": ..., ..., "_profile": {"id":..., "name":..., "title":...}}` — a single dict at `self.data["games"][game_id]`, with `_profile` nested *inside* it, not a sibling top-level key. The sanitiser only checks `isinstance(g, dict)` for each top-level per-game entry; it does not inspect one level deeper into `_profile`. A legitimately-saved custom game is a dict, so it passes the filter unchanged. Traced the read side too: `AfkAutoclicker.__init__` (`afk_clicker.py:1024-1029`) reads `saved.get("_profile")` for every `games` value to rebuild the custom-profile list on startup — this runs after `Store.__init__`, so it only ever sees already-sanitised (dict) entries, consistent with pre-fix behaviour for well-formed data. |

## Regression check
Full suite: `DISPLAY=:99 /tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/venv/bin/python -m unittest discover -s tests -t .` — **94 tests, OK, skipped=7** (2 more skips than the 90-OK/5-skipped baseline, both explained above as GitHub rate-limiting on `test_updater.LiveRepository`, unrelated to this diff). Ran twice in this session (once before the revert-and-restore probe, once after), identical result both times. No existing test newly failed.

## Defects found
None. Round 1's Defect 1 is fixed; no new defect found this round.

## Spec coverage (`docs/spec.md` acceptance criteria)
All criteria were already covered and verified in Round 1 and remain unaffected by the Round 2 fix (the fix touches only load-time shape safety, not the 510→650 value logic, the profile dict, or the doc/test text). Re-confirmed this round:
- No-`"minecraft"`-key → 650 on selection: unaffected by sanitiser (empty `games` dict either way). Covered by `PerGameSettings.test_defaults_differ_per_profile`.
- `click_ms: 510` → migrated to 650: `StoreMigration.test_the_old_default_is_migrated`, still passes (94-test run).
- `click_ms: 444` (non-510) untouched: `StoreMigration.test_a_tuned_value_is_left_alone`.
- `game_note` text / no "Rays Works": unchanged from Round 1, not touched by this round's diff.
- New defect coverage (this round's addition, not a spec AC but required by the reviewer's own Round 1 finding): malformed `games`/per-game shapes no longer crash startup — the 4 new tests plus the manual 15-case sweep above.

## Ten-round review (`docs/REVIEW-PROTOCOL.md`)

**Round 1 — Ticket fidelity.** PASS. Branch `feature/ac-15/minecraft-default-interval-sweep` matches the `feature/{ab}-{ticket}/{description}` shape for ticket #15. The Round 2 diff is scoped exactly to the reviewer's own reported defect — a 15-line addition inside `Store.__init__`, plus 4 new tests. No unrelated code moved or touched.

**Round 2 — Correctness.** PASS. Traced the sanitiser against every input shape it can see: non-dict `games` (list/number/bool/string) → replaced with `{}`; dict `games` with a non-dict per-game entry → that entry dropped, siblings kept (`afk_clicker.py:619-623`); a dict per-game entry → kept as-is regardless of its internal field types (matches the narrow scope the developer argued for — `game()`/`_select()`/`_persist()` already assumed a dict one level down, and now that's guaranteed). Manually verified 15 malformed-shape files against both `Store()` alone and a full `AfkAutoclicker` build — none crash (evidence table row 6). No off-by-one or wrong-branch found in the filter's dict comprehension.

**Round 3 — Threading and Tk safety.** PASS — no threaded code touched. `Store.__init__` runs synchronously on the main thread during app construction, before any worker thread starts; the sanitiser adds no widget access, no Tk variable access, no `after()` scheduling.

**Round 4 — Naming and shadowing.** PASS. The new local `games` variable in `Store.__init__` doesn't shadow an import, builtin, or existing class — its scope is 4 lines and it's never referenced outside `__init__`.

**Round 5 — Untrusted input.** PASS, with one carried-forward, already-flagged follow-up. The sanitiser is exactly the "validate, don't wrap in try/except" fix the protocol calls for — it filters by `isinstance`, not by catching the `AttributeError` after the fact. Confirmed a corrupt config still starts from defaults, not a crash (row 1-4, 7). Follow-up (not new this round, already documented in `implementation.md`'s "Follow-up for the reviewer" section, and confirmed non-crashing by my own probe, row 6): `hotkey`/`selected` are still unvalidated past the top-level `k in self.data` filter, e.g. `{"hotkey": []}` loads as-is. This does not crash today only because of separate, pre-existing guards in `Hotkey.from_json` and the `selected`-fallback check — it is fragile-by-coincidence rather than validated-by-design, but it is out of scope for this ticket (the developer's Round 1 defect was specifically about `games`) and is correctly flagged as a follow-up rather than fixed here.

**Round 6 — Tech stack conformance.** PASS — no new dependency, no build-flag change, nothing resolved at import time.

**Round 7 — Cross-platform behaviour.** PASS. `Store.__init__`'s file-shape handling is pure Python dict/JSON logic with no platform branch; behaviour is identical on Windows/Linux/macOS. Verified only under Linux/Xvfb (`DISPLAY=:99`) this session — consistent with `docs/ROADMAP.md`'s pre-existing, unrelated "macOS verification" gap, not a new gap introduced by this diff.

**Round 8 — Tests.** PASS. Confirmed live this round (row 7): reverted the sanitiser, watched the 3 relevant new tests fail with the exact `AttributeError` Defect 1 reported, then restored the tree exactly (`md5sum` and `git diff main --stat` both identical before/after) and reran the full suite green. The 4th new test (`test_a_string_click_ms_is_not_mistaken_for_the_old_default`) doesn't need a revert check — it never failed pre-fix (string `"510"` was never affected by the crash), and it's documented as such in `implementation.md`; it's regression coverage for the equality-match semantics, not fix-coverage for Defect 1, correctly distinguished by the developer.

**Round 9 — Comments and documentation.** PASS. The sanitiser's comment (`afk_clicker.py:609-618`) explains *why* — the same "corrupt file is replaced, never fatal" contract applies one level down, and names the three readers (migration, `game()`, `_select()`) that all inherited the same unvalidated assumption — not what the code does. No restated-code noise.

**Round 10 — Roadmap and release readiness.** CONCERN (documentation gap, not a blocker). Does not move anything on `ROADMAP.md`; does not touch anything the roadmap rules out. Versioning: no `__version__` bump this round either, consistent with the orchestrator's Round 1 dismissal of that note — not re-raised. On "does the settings format change": this diff is the **first time `Store.__init__` rewrites/drops data based on a structural shape check** rather than a literal value substitution — the 510→650 migration (Round 1) only ever replaced one known scalar with another known scalar at one known key; this round's sanitiser instead *drops* any `games` value or per-game entry that doesn't pass an `isinstance(dict)` check, silently, in-memory, on every load, with no schema version to record that this happened. What the next format change inherits from this: (a) a workable precedent — validate-and-filter at the top of `Store.__init__`, immediately after the existing load block, is now an established pattern any future consumer of `self.data["games"]` can rely on without re-checking shape itself; but (b) a real risk that isn't obvious from this diff alone — because the filter is a blunt `isinstance(dict)` check with no version marker, a *future* structural migration (e.g. renaming `click_ms` to `interval_ms`, or nesting per-game values one level deeper) that runs *after* this generic filter would have its old-format data silently discarded by this filter before the migration ever sees it, unless the future migration is deliberately sequenced *before* the generic shape filter (or the filter is loosened to recognise the old shape too). This diff doesn't need to solve that — `docs/ROADMAP.md`'s "Settings schema version" item already owns the general mechanism, and this fix is narrowly correct for the shapes it targets today — but it should be written down now, while the reasoning is fresh, rather than rediscovered by whoever picks up that roadmap item after this filter has already eaten someone's differently-shaped-but-valid old data.

### VERDICT: MERGE
### BLOCKERS: 0
### CONCERNS: 1 (Round 10 — no schema version to distinguish "malformed, correctly dropped" from "old valid shape, about to be silently dropped by a future structural migration that doesn't sequence around this filter"; plus the carried-forward `hotkey`/`selected` shape-validation follow-up already logged in `implementation.md`, non-blocking)

## Overall verdict
**Approve.** Round 1's Defect 1 is fixed, verified live (revert-and-watch-it-fail, then restored exactly), and covered by 4 new tests plus a broader manual malformed-shape sweep (15 additional cases, including the ones the task specifically asked about: `click_ms` as `null`/`true`/`1e309`/`NaN`, a top-level JSON list/number, and odd `hotkey`/`selected` types) — none crash `Store()` or a real `AfkAutoclicker` construction. Full suite green (94 OK; the skip count moved from 5 to 7 only because of live GitHub API rate-limiting on two pre-existing network tests, confirmed unrelated to this diff). No must-fix findings from the ten-round review; one non-blocking Round 10 documentation concern recorded above for whoever eventually builds the schema-version mechanism.
