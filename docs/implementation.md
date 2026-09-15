# Implementation: `Hotkey.from_json` checks shape but not vocabulary — G#7/GH#9

## Summary
`Hotkey.from_json` (`afk_clicker.py:441-505`) now rejects all five exploit shapes named in the ticket instead of admitting them as an armed, unfireable hotkey: non-member `kb.Key` class attributes, an empty or over-length `char`, a boolean or out-of-range `vk`, and a chord longer than `MAX_CHORD` (previously silently truncated by `Hotkey.__init__`). Two new module-level constants (`MAX_VK`, `MAX_CHAR_LEN`) were added next to `MAX_CHORD`. Every new guard has a dedicated test and a case in `test_every_rejection_path_is_reachable`, written before the fix and confirmed to fail against the unfixed code (TDD), then confirmed to pass after. `Hotkey.__init__`'s `records[:MAX_CHORD]` truncation is untouched, per the spec.

## Root cause
`from_json`'s guard chain checked *shape* (dict, list, str/int/None types) at every step but never checked that the values inside that shape were real:
- Line 468 (`if name is not None and not hasattr(kb.Key, name)`) used `hasattr` against `kb.Key`, an `Enum` class. `hasattr` answers `True` for anything `Enum`/`object` supplies as an attribute — `mro`, `__class__`, `__init__`, `_member_map_`, `__module__` — not just the 60 real key names in `kb.Key.__members__`. A blob naming one of these non-member attributes passed straight through to `_key_label`, which falls through to `f"Key {vk}"` for a `None` name/char, i.e. `Key None`.
- `char` had a type check (`isinstance(char, str)`) but no length check. `bool("")` is `False`, so an empty string slid past the `name is None and vk is None and char is None` all-null check (char is `""`, not `None`) and rendered as `Key None`; an unbounded string (the ticket's 200-char example) rendered verbatim as the label.
- `vk` had a type check (`isinstance(vk, int)`) but no range check, and no boolean exclusion. `isinstance(True, int)` is `True` — `bool` is an `int` subclass in Python — so a boolean `vk` passed the type check and rendered as `Key True`/`Key False`. A negative `vk` had no lower bound either.
- A chord with more than `MAX_CHORD` (3) entries was never rejected in `from_json` at all; it reached `Hotkey.__init__`, which silently truncates via `records[:MAX_CHORD]`. That makes a restored 4-key chord *easier* to trigger than the recorded one — any 3 of the 4 keys fires it — the same reject-vs-adjust mistake the function's own modifier-filtering guard already exists to avoid.

Every one of these five gaps produced a hotkey object that `Hotkey.from_json` happily returned non-`None`, with no error surfaced anywhere, that could never actually fire (or, in the chord case, fired on an easier subset than recorded).

## Changes by file
- `afk_clicker.py`
  - Two new constants added directly below `MAX_CHORD` (~line 313): `MAX_VK = 0x1FFFFFFF` (X11's keysym ceiling, the widest of the three backends' vk spaces) and `MAX_CHAR_LEN = 8` (generous headroom above the darwin dead-key/compose backend's realistic multi-code-point output, far short of an adversarial payload). Each carries the "why" comment the coding guidelines require of a non-obvious constant.
  - `Hotkey.from_json` (~lines 441-505): five new/changed guard lines, in the same order and with the same "why" comments as `docs/spec.md`'s proposed diff:
    - `if len(raw) > MAX_CHORD: return None` — added right after the "keys" shape check, before the mods checks, per the spec's ordering (cheapest/structural checks first).
    - `if isinstance(vk, bool): return None` — added between the existing `vk` type check and the new range check.
    - `if vk is not None and not (0 <= vk <= MAX_VK): return None` — new range guard.
    - `if char is not None and not (1 <= len(char) <= MAX_CHAR_LEN): return None` — added after the existing `char` type check.
    - `if name is not None and name not in kb.Key.__members__: return None` — replaces the `hasattr(kb.Key, name)` line; comment updated to explain why `hasattr` was wrong.
  - No other line in `from_json`, `Hotkey.__init__`, or anywhere else in the file changed.
- `tests/test_hotkey.py`, class `Persistence`
  - New dedicated tests, added alongside `test_unknown_key_names_are_rejected`: `test_non_member_class_attributes_are_rejected`, `test_char_length_bounds_reject_empty_and_oversized`, `test_boolean_and_out_of_range_vk_are_rejected`, `test_chord_longer_than_max_is_rejected_not_truncated`.
  - `test_every_rejection_path_is_reachable` gained six new `subTest` cases: `chord too long`, `vk is bool`, `vk out of range`, `char empty`, `char too long`, `name is non-member attribute`.
  - `test_malformed_input_yields_none`, `test_round_trip`, `test_a_dropped_vk_is_not_silently_survivable`, `test_bad_modifiers_are_rejected_not_filtered`, `test_unknown_key_names_are_rejected`, and `test_unhashable_modifiers_do_not_raise` are all unmodified.

## Key decisions / tradeoffs
- Matched the spec's proposed diff verbatim — constant values, guard order, and comment wording all came from `docs/spec.md`'s "Proposed approach", which had already resolved both judgment calls (`MAX_CHAR_LEN = 8`, `MAX_VK = 0x1FFFFFFF`) with rejected alternatives recorded there. No new judgment calls were needed in this cycle.
- `char empty` and `char too long` are two `subTest` cases in `test_every_rejection_path_is_reachable` even though they're caught by the same single guard line (`not (1 <= len(char) <= MAX_CHAR_LEN)`) — the spec's acceptance criteria names both explicitly as separate cases, and the sabotage-verify below confirms both go red together when that one line is disabled, which is the correct/expected result for a single guard covering both boundaries of one range check.
- Left `Hotkey.__init__`'s `records[:MAX_CHORD]` truncation untouched, per the spec's explicit instruction: with the new `len(raw) > MAX_CHORD` guard, `from_json` never calls `cls(...)` with more than `MAX_CHORD` records, so the truncation is dead for this call path and stands only as a constructor-level invariant for any other caller.

## Deviations from spec
None. The implementation matches `docs/spec.md`'s "Proposed approach" diff line for line, and all listed acceptance criteria were exercised as dedicated tests or `subTest` cases.

## Known limitations
- Same platform-confirmation gap the spec's own "Risk / rollback notes" already calls out: this Linux/Xvfb sandbox (pynput 1.7.7, matching the CI pin) can confirm the X11 and read-installed-source reasoning for all three backends, but cannot exercise a real macOS `CGEventKeyboardGetUnicodeString` dead-key/compose keypress to confirm `MAX_CHAR_LEN = 8` doesn't clip a genuine composed character in practice. The next green `macos-latest` CI run on this branch is the real confirmation, not this session.
- G#10/GH#12's review-residue grab-bag (schema-version wording, listener-arming order, `test_malformed_input_yields_none`'s `blob if blob else {}` never exercising a `None` blob) is out of scope per the spec's Non-goals and was not touched.

## How to verify locally
Baseline and post-change suite (this repo's convention: venv + Xvfb `:99`, confirm nothing else is running first):
```
pgrep -a Xvfb            # :99 should already be up
pgrep -af "[u]nittest"   # nothing else running
cd /home/dev/projects/afk-clicker
DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .
```
Baseline (before this cycle, on `hotfix/ac-7/from-json-hotkey-vocabulary` before any edit): `Ran 370 tests ... OK (skipped=10)`.
After this cycle: `Ran 374 tests ... OK (skipped=10)` — 4 new dedicated test methods; `test_every_rejection_path_is_reachable` itself is still one test method (its 6 new `subTest` cases don't change the top-level count).

Targeted run used during development:
```
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_hotkey.Persistence -v
DISPLAY=:99 <venv>/bin/python -m unittest tests.test_hotkey -v
```
All 11 `Persistence` tests and all 39 `test_hotkey` tests pass.

TDD confirmation (before the fix): with the new tests added and the production guards not yet written, `tests.test_hotkey.Persistence -v` produced 14 failures — the six new `test_every_rejection_path_is_reachable` subTest cases plus the four new dedicated tests' assertions (`test_non_member_class_attributes_are_rejected` failed once per name, 5 names) — confirming every new test actually exercises code that didn't exist yet, not a tautology.

Sabotage-verify performed this session (each: disabled exactly one new guard with `if False and <condition>:` so the line stays syntactically in place, ran `tests.test_hotkey.Persistence -v`, confirmed the exact expected case(s) turned red and nothing else did, then restored and re-ran green):
1. `len(raw) > MAX_CHORD` disabled → `test_chord_longer_than_max_is_rejected_not_truncated` and `test_every_rejection_path_is_reachable`'s `chord too long` case failed (2 failures, nothing else). Restored.
2. `isinstance(vk, bool)` disabled → `test_boolean_and_out_of_range_vk_are_rejected` and `test_every_rejection_path_is_reachable`'s `vk is bool` case failed (2 failures, nothing else). Restored.
3. `vk is not None and not (0 <= vk <= MAX_VK)` disabled → `test_boolean_and_out_of_range_vk_are_rejected` and `test_every_rejection_path_is_reachable`'s `vk out of range` case failed (2 failures, nothing else — the bool guard alone did not catch `-1` or `0x20000000`). Restored.
4. `char is not None and not (1 <= len(char) <= MAX_CHAR_LEN)` disabled → `test_char_length_bounds_reject_empty_and_oversized` and both `test_every_rejection_path_is_reachable` subTest cases `char empty` and `char too long` failed (3 failures, nothing else). Restored.
5. `name not in kb.Key.__members__` reverted to `not hasattr(kb.Key, name)` → `test_every_rejection_path_is_reachable`'s `name is non-member attribute` case and all 5 subTest cases of `test_non_member_class_attributes_are_rejected` (`mro`, `__class__`, `__init__`, `_member_map_`, `__module__`) failed (6 failures, nothing else — `test_unknown_key_names_are_rejected`'s plain-bogus-string cases still passed, since `hasattr` already rejects those). Restored.

After all five restores, `grep -n "SABOTAGE" afk_clicker.py` returns nothing, and the full suite (`374 tests ... OK (skipped=10)`) was re-run clean as the final state.
