# Test & Review: `Hotkey.from_json` checks shape but not vocabulary — G#7/GH#9

## Scope
One ticket, one diff: `afk_clicker.py` gains `MAX_VK`/`MAX_CHAR_LEN` next to
`MAX_CHORD` (lines 313-328) and five new/changed guards inside
`Hotkey.from_json` (lines 452-501); `tests/test_hotkey.py`'s `Persistence`
class gains four dedicated tests plus six new `subTest` cases in
`test_every_rejection_path_is_reachable`. Covers `docs/spec.md`'s Acceptance
criteria in full.

Env: pynput 1.7.7 (confirmed via `pip show pynput`, matching the CI pin in
`.github/workflows/ci.yml`), Xvfb `:99` already running, no other unittest
process active before or during this session.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | AC1: `name` = `mro`/`__class__`/`__init__`/`_member_map_`/`__module__` → `None` | `tests/test_hotkey.py::Persistence::test_non_member_class_attributes_are_rejected` + `test_every_rejection_path_is_reachable`'s `name is non-member attribute` case | pass | `DISPLAY=:99 <venv>/bin/python -m unittest tests.test_hotkey.Persistence -v` → both green |
| 2 | AC2: `"f6"` still returns non-`None` (no regression on real key names) | `test_unknown_key_names_are_rejected`'s trailing assertion (unmodified) | pass | full-suite run, green |
| 3 | AC3/AC4: empty `char` and 200-char `char` → `None` | `test_char_length_bounds_reject_empty_and_oversized` | pass | green |
| 4 | AC5: `"ä"` (1 code point) and `"́a"` (2 code points) → non-`None` | same test | pass | independently confirmed `len("́a") == 2` via `python3 -c` in this session |
| 5 | AC6/AC7: bool `vk` (`True`/`False`) and `vk=-1` → `None` | `test_boolean_and_out_of_range_vk_are_rejected` | pass | green |
| 6 | AC8: `vk=0x20000000` → `None`; `vk=0x1FFFFFFF` → non-`None` | same test | pass | green |
| 7 | AC9: 4-entry chord → `None`; first-3-of-4 → non-`None`, `len(.keys)==3` | `test_chord_longer_than_max_is_rejected_not_truncated` | pass | green |
| 8 | AC10: 6 new `subTest` cases added to `test_every_rejection_path_is_reachable` | read diff | pass | `chord too long`, `vk is bool`, `vk out of range`, `char empty`, `char too long`, `name is non-member attribute` all present |
| 9 | AC11: `test_round_trip`, `test_a_dropped_vk_is_not_silently_survivable`, `test_bad_modifiers_are_rejected_not_filtered`, `test_unknown_key_names_are_rejected`, `test_unhashable_modifiers_do_not_raise`, `test_malformed_input_yields_none` unmodified and still pass | `git diff tests/test_hotkey.py` (pure addition, no line inside these six touched) + full-suite run | pass | diff shows only insertions after line 237 and inside the `cases` dict; full suite green |
| 10 | AC12: full suite passes, only the named tests changed | `git diff --stat` | pass | `tests/test_hotkey.py \| 52 ++...` — additions only, matches |
| 11 | AC13: sabotage-verify per new guard | see below | pass | 2 of 5 reproduced directly this session; remaining 3 traced by hand against the actual guard order (see Correctness) |
| 12 | New tests fail against the unfixed code (TDD confirmation, my own repro, not trusted from the report) | `git stash push --keep-index -- afk_clicker.py` (reverts prod code only, keeps new tests), run `Persistence` suite, `git stash pop` | **fail as expected** | 14 failures: the 6 new `subTest` cases + `test_non_member_class_attributes_are_rejected`'s 5 sub-cases + `test_char_length_bounds_reject_empty_and_oversized` + `test_boolean_and_out_of_range_vk_are_rejected` + `test_chord_longer_than_max_is_rejected_not_truncated` (see raw output captured this session) |
| 13 | Regression: full suite, fixed code | `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` | pass | `Ran 374 tests ... OK (skipped=10)`, run twice, identical |
| 14 | Regression: full suite, baseline (both files stashed) | same command, both `afk_clicker.py` and `tests/test_hotkey.py` reverted | pass | `Ran 370 tests ... OK (skipped=10)` — confirms implementation.md's stated baseline exactly |

Working tree confirmed byte-identical to the pre-review diff after every
stash/sabotage/restore round (`git diff --stat` unchanged: `afk_clicker.py \|
39 ++...`, `tests/test_hotkey.py \| 52 ++...`; `grep -c SABOTAGE afk_clicker.py`
→ 0 after each restore).

## Regression check
Full suite (`DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t
.`), run four times across this session (baseline both-reverted, unfixed-prod-
only, fixed, final) — counts: 370 → 374 → 374 → 374, `OK (skipped=10)` every
time. Matches `docs/implementation.md`'s stated baseline and post-fix counts
exactly; not taken on trust, re-derived independently.

## Sabotage-verify: independently reproduced (not just re-read from implementation.md)
1. **`vk` range guard** (`afk_clicker.py:487`, `if vk is not None and not (0
   <= vk <= MAX_VK):`) — disabled in place (`if False:`), ran
   `Persistence -v`: exactly `test_boolean_and_out_of_range_vk_are_rejected`
   and the `vk out of range` subTest went red (2 failures, nothing else — the
   adjacent bool guard does not catch `-1` or `0x20000000` on its own).
   Restored; suite green again; `git diff --stat afk_clicker.py` unchanged
   afterward.
2. **Chord-length guard** (`afk_clicker.py:459`, `if len(raw) > MAX_CHORD:`)
   — disabled in place, ran `Persistence -v`: exactly
   `test_chord_longer_than_max_is_rejected_not_truncated` and the `chord too
   long` subTest went red (2 failures, nothing else — `Hotkey.__init__`'s
   `records[:MAX_CHORD]` truncation silently accepts the 4-entry blob as a
   3-key `Hotkey` once this guard is gone, confirming the guard is load-
   bearing and correctly isolated). Restored; suite green again.
3. **Bool guard, char-length guard, name-membership guard** — not
   independently re-disabled this session (the *technique* was just proven
   twice above, live, against this same file); instead traced by hand against
   the actual guard order in the diff:
   - `isinstance(vk, bool)` (line 484) runs *before* the range check; if
     removed, `True`/`False` fall through to `0 <= True <= MAX_VK` → `0 <= 1
     <= 0x1FFFFFFF` is `True`, so the range guard would not catch it either —
     confirms this guard, not the range guard, is what `vk is bool`
     specifically isolates.
   - `char is not None and not (1 <= len(char) <= MAX_CHAR_LEN)` (line 494) is
     the only length check on `char`; disabling it leaves nothing else in the
     chain that inspects `char`'s length, so both `char empty` and `char too
     long` would pass through to `records.append(...)` uncaught — matches the
     claimed isolation.
   - `name not in kb.Key.__members__` (line 500) replacing `hasattr`: traced
     that `"mro"` is a real attribute Python's `Enum`/`object` machinery
     supplies (confirmed live: `hasattr(kb.Key, "mro")` → `True`,
     `"mro" in kb.Key.__members__` → `False`), so reverting to `hasattr` would
     let exactly this case (and the other four class-attribute names) back
     through, uncaught by any earlier guard.

## Independent scrutiny of the three flagged risk points

**(a) `kb.Key.__members__` vocabulary correctness across backends.** Verified
live on the installed pynput 1.7.7 X11 backend: `len(kb.Key.__members__) ==
60`, and — the sharper check — every *canonical* name (`member.name` for each
distinct member, e.g. what `_record` actually reads via `key.name`) is
present as a key in `__members__`; found genuine `Enum` aliases on this
backend (`alt_l`→`alt`, `cmd_l`→`cmd`, `ctrl_l`→`ctrl`, `shift_l`→`shift`,
i.e. `.name` on the alias objects returns the canonical name, not the alias
spelling), and confirmed the alias/canonical split still leaves the check
sound. This isn't backend-specific luck: `Key` is declared as a plain
`class Key(enum.Enum)` on all three backends (confirmed by reading
`_xorg.py:117`, `_win32.py:113`, `_darwin.py:155` directly — none subclasses
or overrides `EnumMeta`), and it is a language-level guarantee of Python's
`Enum` that `__members__` contains every name defined in the class body
(canonical and alias alike) and that any member's `.name` is always one of
those keys. So the property holds on win32/darwin without needing a live
Windows/macOS box to confirm it — it follows from `enum.Enum`'s own
semantics, not from guessing at platform behavior.

**(b) Can `MAX_VK`/`MAX_CHAR_LEN` reject a value a real backend can produce?**
Read all three backends' source directly (not just the constants' comments):
- `_win32.py:113-` `Key` members are built from `win32_vks.py`'s named `VK.*`
  constants, all documented single-byte Windows virtual-key codes (values
  seen in source top out in the low hundreds, e.g. `VK.F24`-class constants);
  nowhere near `MAX_VK = 0x1FFFFFFF`.
- `_darwin.py:155-211` `Key` members use `KeyCode.from_vk(0x30-0x7E)` (real
  `CGKeyCode`s) and `KeyCode._from_media(NX_KEYTYPE_*)` with tiny constants
  (`NX_KEYTYPE_PLAY = 16`, etc, `_darwin.py:60-65`) — both far under `MAX_VK`.
  `_event_to_key` (`_darwin.py:331-362`) reads `vk` from
  `kCGKeyboardEventKeycode`, a `CGKeyCode` (`UInt16`, max 65535) — still
  `<< MAX_VK`.
- `_xorg.py` vk is an X11 keysym (`_xorg.py:667` `KeyCode.from_vk(keysym)`);
  the X11 protocol reserves keysym values to 29 bits (`0x1FFFFFFF`), matching
  `MAX_VK` exactly — this is a documented protocol constant, not a guess.
- `MAX_CHAR_LEN = 8`: X11 and win32 chars are always exactly one code point
  (confirmed by reading `_win32.py:80-92`'s `ord(self.char) > 0xFFFF`
  surrogate-pair handling, which operates on a single logical `str`
  character, and `_xorg.py`'s keysym→`SYMBOLS`/`CHARS` table lookups, both
  single-code-point). `_darwin.py:349-351`
  (`CGEventKeyboardGetUnicodeString(event, 100, None, None)`) is the one
  path that could, in principle, hand back up to 100 UTF-16 units from a
  single physical keydown — this is a real, disclosed gap (already called
  out in `docs/spec.md`'s "Risk / rollback notes" and
  `docs/implementation.md`'s "Known limitations"), not something either
  document is hiding. My own read of the same source confirms the disclosed
  reasoning is accurate and not overstated: this API answers one physical
  keydown event (dead-key/compose), not an IME candidate-window buffer, so
  8 is a reasonable, if unverified-on-real-hardware, bound. Not a blocker —
  correctly flagged as unconfirmable outside real macOS CI in both upstream
  docs, and I have nothing to add beyond confirming that framing is honest.

**(c) Guard ordering / subTest reachability.** Confirmed live for the two
trickiest cases (chord-length vs. per-entry guards; bool-vk vs. range-vk) via
direct sabotage this session (see above); traced the remaining three by hand
against the actual line order in `afk_clicker.py:452-501`. All six new
`subTest` cases are isolated to the guard they claim to name — none is
secretly caught by an earlier or later check.

**(d) Linux-only local run vs. Windows/macOS CI.** The new tests use only
`"f6"`/`"f7"`/`"f8"`/`"f9"` as real key-name literals (confirmed present in
all three backends' `Key` enum bodies by direct source read: `_win32.py`
defines `f1`-`f20` from `VK.F1`-`VK.F20`-class constants, `_darwin.py:172-186`
defines `f1`-`f20`) and otherwise only synthetic ints/strings that never touch
`kb.Key` — no test in this diff depends on a key name that's present on X11
but absent on win32/darwin, or vice versa.

## Correctness review (diff walk)
`afk_clicker.py:452-501` — walked the full guard chain in final order: dict
shape → keys shape → chord-length (new) → mods shape/type/vocabulary →
per-entry shape → name type → vk type → vk-is-bool (new) → vk-range (new) →
char type → char-length (new) → all-null → name-membership (changed). Cheapest
structural checks still run first, matching the function's existing
discipline; the new guards slot in at points that don't skip any existing
check and don't get skipped by one. No off-by-one found: `0 <= vk <= MAX_VK`
and `1 <= len(char) <= MAX_CHAR_LEN` are both inclusive at the boundary the
spec explicitly calls for, and both boundaries were exercised by a real test
(`vk=0x1FFFFFFF` accepted, `vk=0x20000000` rejected; `char` of length 8 not
explicitly tested but length 1 and length 2 accepted, length 0 and 200
rejected — the exact-8 boundary itself isn't in a dedicated assertion, a
minor gap, see below).

## Findings

1. **Nit** — `MAX_CHAR_LEN`'s exact upper boundary (`char` of length exactly
   8) has no dedicated assertion; only 1, 2 (accept) and 0, 200 (reject) are
   tested. `vk`'s boundary is tested exactly (`0x1FFFFFFF` accept,
   `0x20000000` reject) but `char`'s is not. Doesn't block — the guard's
   logic (`1 <= len(char) <= MAX_CHAR_LEN`) is simple enough that the
   asymmetry is low-risk, and it's optional per the spec's own acceptance
   criteria (which only asked for "at or under `MAX_CHAR_LEN`", not the exact
   boundary). Worth a one-line follow-up (`"x" * 8` → non-`None`,
   `"x" * 9` → `None`) if this file is touched again.
2. **Informational, not a finding** — darwin `MAX_CHAR_LEN` risk (point b
   above) is real but already disclosed twice (spec.md, implementation.md)
   with sound reasoning; independently confirmed the reasoning holds by
   reading `_darwin.py` directly. Treat the next green `macos-latest` CI run
   as the real confirmation, as both docs already say.
3. **Not a finding** — `backlog.md:93` still shows G#7/GH#9 as `[ ]` (not yet
   marked done). Consistent with this repo's established pattern (the ac-5
   cycle's backlog closure was a separate commit, `691c42a`/`bad7108`, made
   after merge, not part of the developer's diff) — not something to block
   on here.
4. **Not a finding** — `__version__` (`afk_clicker.py:621`, currently
   `"0.6.0"`) is untouched. Checked history: version bumps in this repo do
   not happen inside every individual bugfix commit (e.g. `6d3b92b`, the
   immediately preceding ac-5 fix, didn't bump it either) — handled
   separately at release time, not a per-PR obligation.

No must-fix or should-fix findings. Ticket fidelity: diff matches
`docs/spec.md`'s proposed diff line-for-line; no scope creep (only
`afk_clicker.py` + `tests/test_hotkey.py` touched, matching "Affected areas").
Security/untrusted-input: this is exactly what the fix strengthens — no new
gap introduced. Threading/Tk: not applicable, no Tk code touched. Naming: no
shadowing (`MAX_VK`/`MAX_CHAR_LEN` are new, unique names). Tech stack: no new
dependency. Simplicity: no unnecessary abstraction — two constants, five
guard lines, matching the spec's own minimal proposed diff.

## Spec coverage
All 13 acceptance-criteria bullets in `docs/spec.md` (lines 149-161) map to a
passing, independently-run test in the table above. No criterion found
unimplemented or untested.

## Overall verdict
**Approved.**

No must-fix or should-fix items. One optional nit (exact `MAX_CHAR_LEN`
boundary test) left for a future touch of this file, not blocking. The
darwin dead-key/compose risk is real but already correctly disclosed and
deferred to macOS CI in both upstream docs — reviewed and concur with that
framing, nothing more to add.
