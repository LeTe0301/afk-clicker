# Spec: `Hotkey.from_json` checks shape but not vocabulary — G#7/GH#9

## Summary
`Hotkey.from_json` validates that a saved hotkey blob has the right *shape* (dict, list, str/int/None types) but not that its values are real, admits an empty or 200-character `char`, a boolean or negative `vk`, and truncates rather than rejects an over-length chord — every one of these currently produces an armed, labelled hotkey that can never fire, with no error anywhere; this cycle tightens `from_json`'s guards to reject all five cases instead.

## Goals
- `name in kb.Key.__members__` replaces `hasattr(kb.Key, name)` at `afk_clicker.py:468`, so non-member class attributes (`mro`, `__class__`, `__init__`, `_member_map_`, `__module__`, …) are rejected instead of accepted.
- `char` must be non-empty and no longer than a stated, justified bound (see judgment call 1 below), rejecting both the empty-string case and the 200-character case.
- `vk` must be a real, non-boolean `int` within a stated, justified range (see judgment call 2), rejecting `True`/`False` and negative values.
- A chord with more than `MAX_CHORD` (3) key entries is rejected outright (`if len(raw) > MAX_CHORD: return None`) rather than silently truncated by `Hotkey.__init__`'s `records[:MAX_CHORD]`, per the ticket. `__init__`'s truncation stays as-is — a defensive constructor invariant for any other caller, not the vocabulary gate itself.
- Every new guard gets a `tests/test_hotkey.py` case in both `test_every_rejection_path_is_reachable` (one case per guard, chosen so removing that guard — and only that guard — fails the case) and, where it fits the existing pattern, its own descriptively-named test alongside `test_unknown_key_names_are_rejected`.

## Non-goals
- G#10/GH#12's review-residue grab-bag (`ROADMAP.md`'s schema-version wording, listener-arming order in `AfkAutoclicker.__init__`, and `test_malformed_input_yields_none`'s `blob if blob else {}` never actually exercising a `None` blob) — separate, already-tracked ticket. Not touched here, including the `None`-blob test gap: fixing it is one line but belongs to that ticket's own diff, not this one's.
- Any change to `HotkeyRecorder`, `_mod_base`, `_record`, `_same_key`, `_key_label`, or chord-matching logic (`Hotkey.matches`) — all out of scope, not implicated by this ticket. Only `Hotkey.from_json` (and, per the chord-length goal above, a one-line addition there referencing the existing `MAX_CHORD`) changes in `afk_clicker.py`.
- A settings-file schema-version bump. The blob shape (`{"mods": [...], "keys": [[name, vk, char], ...]}`) is unchanged; this cycle only narrows which *values* inside that shape are accepted. No migration is needed for existing valid files — every blob a stricter `from_json` still accepts is a blob today's `from_json` already accepted (this is a strict narrowing of the accept set, never a widening), so nothing previously-valid becomes invalid except the five exploit shapes themselves.
- `ux-designer` is skipped for this cycle. There is no visual or layout change: a blob that used to produce a silently-broken armed hotkey now produces `None` (the same "damaged setting starts clean" outcome every other rejection in `from_json` already produces), which the existing UI already renders as "no hotkey configured" with no new string, dialog, or layout decision involved.

## Background / current state
`Hotkey.from_json` (`afk_clicker.py:426-471`) is the sole production path from a persisted `settings.json` blob to an armed, listening hotkey — called once, at `afk_clicker.py:2404`: `Hotkey.from_json(self.store.data.get("hotkey") or {})`. Its docstring already states the operating principle: "Checked rather than wrapped in try/except... Reject, do not filter." — the guards added here are the same discipline applied to five gaps the shape checks leave open.

Current guard chain, `afk_clicker.py:435-471`:
```python
if not isinstance(blob, dict):
    return None
raw, mods = blob.get("keys"), blob.get("mods", [])
if not isinstance(raw, (list, tuple)) or not raw:
    return None
if not isinstance(mods, (list, tuple)):
    return None
if not all(isinstance(m, str) for m in mods):
    return None
if any(m not in _MOD_ORDER for m in mods):
    return None
records = []
for entry in raw:
    if not isinstance(entry, (list, tuple)) or not 1 <= len(entry) <= 3:
        return None
    name, vk, char = (list(entry) + [None, None, None])[:3]
    if not (name is None or isinstance(name, str)):
        return None
    if not (vk is None or isinstance(vk, int)):
        return None
    if not (char is None or isinstance(char, str)):
        return None
    if name is None and vk is None and char is None:
        return None
    if name is not None and not hasattr(kb.Key, name):     # <-- line 468, the bug
        return None
    records.append((name, vk, char))
return cls(list(mods), records)
```
`_key_label` (`afk_clicker.py:387-396`) is what actually renders the broken results: a `None` name/char falls through to `f"Key {vk}"`, so an empty char labels as `Key None`, a `True` vk labels as `Key True`, and a 200-character char is rendered verbatim as the label (`_key_label` upper-cases and returns it unchanged otherwise).

`MAX_CHORD = 3` (`afk_clicker.py:313`), with its own comment already explaining the choice (most membrane keyboards ghost past two simultaneous keys in the same matrix row). `Hotkey.__init__` (`afk_clicker.py:413-415`) does `self.keys = tuple(records[:MAX_CHORD])` — a silent truncation that, per the ticket, makes a restored 4-key chord *strictly easier* to trigger than the one the user actually recorded (any 3 of the 4 keys fires it) — the same reject-vs-adjust mistake `from_json`'s own docstring already calls out for modifier filtering (`_MOD_ORDER` rejection, lines 440-442).

**Confirmed against pynput 1.7.7 (the version CI pins in `.github/workflows/ci.yml:54` and `release.yml:76`/`126`; this sandbox has 1.8.2 installed by default, so a throwaway 1.7.7 venv was built under Xvfb `:99` to check this directly rather than reasoning from the newer version):**
- `kb.Key.__members__` on the X11 (`_xorg`) backend has exactly 60 entries (`alt`, `alt_gr`, `alt_l`, … `up`) — a real, closed vocabulary, unlike `hasattr`, which also answers `True` for `mro`, `__class__`, `__init__`, `_member_map_`, `__module__`, and every other attribute `Enum`/`object` supplies. `kb.Key.__members__` is evaluated against the `kb` this process actually imported, so it is automatically scoped to whichever platform backend is running — no special-casing needed for "this is the darwin build" vs "this is the X11 build".
- `pynput.keyboard._base.KeyCode.__init__` sets `self.char = six.text_type(char)` with no length constraint of its own — length is purely a function of what the platform backend hands it. Reading all three backends in the installed 1.7.7 package:
  - `_xorg.py`: characters come from a `SYMBOLS`/`CHARS` keysym table — single code points.
  - `_win32.py`: characters come from `VkKeyScan`/UTF-16 scan-code translation — single code points (with an explicit `ord(self.char) > 0xFFFF` surrogate-pair check, still one logical character).
  - `_darwin.py:350-352`: `length, chars = CGEventKeyboardGetUnicodeString(event, 100, None, None)` — this is the one backend that can hand back more than one code point from a single physical keypress: a dead-key/compose sequence or an uncommitted IME composition can legitimately produce a short multi-code-point string, up to the 100-UTF-16-unit ceiling pynput itself requests from the OS call. In practice this stays at a handful of code points (a combining accent plus base, or a decomposed script cluster); nothing in real-world dead-key/compose behavior produces anywhere near 100, let alone the ticket's 200-character adversarial example.

## Proposed approach
Two new module-level constants next to `MAX_CHORD` (`afk_clicker.py:313`), each carrying the "why" the coding guidelines require of a non-obvious constant:
```python
# X11 hands _record a keysym as "vk" (see _record's docstring above), and the
# X11 protocol reserves keysym values up to 0x1FFFFFFF -- the largest vk any
# of the three backends can produce. Win32 VKs (0-255) and macOS keycodes
# (roughly 0-127) both already fall well inside this, so one bound covers a
# settings file recorded on any platform and read back on any other.
MAX_VK = 0x1FFFFFFF

# A real dead-key/compose keypress (CGEventKeyboardGetUnicodeString on the
# darwin backend, the only one of the three that can hand back more than one
# code point per event) stays at a small handful of code points in practice --
# nothing about real input-method composition approaches this. Generous
# enough not to reject a genuine composed character, far short of an
# adversarial payload like the 200-char string this guard exists to stop.
MAX_CHAR_LEN = 8
```
`from_json`'s guard chain (`afk_clicker.py:426-471`), in order, with new/changed lines marked:
```python
        if not isinstance(blob, dict):
            return None
        raw, mods = blob.get("keys"), blob.get("mods", [])
        if not isinstance(raw, (list, tuple)) or not raw:
            return None
        # Reject, do not truncate -- a restored 4-key chord silently trimmed
        # to 3 fires on any 3 of the 4 keys the user actually recorded, which
        # is strictly *easier* to trigger than the saved combination. The
        # same reject-vs-adjust mistake as the modifier filtering below.
        if len(raw) > MAX_CHORD:                                   # NEW
            return None                                            # NEW
        if not isinstance(mods, (list, tuple)):
            return None
        if not all(isinstance(m, str) for m in mods):
            return None
        if any(m not in _MOD_ORDER for m in mods):
            return None
        records = []
        for entry in raw:
            if not isinstance(entry, (list, tuple)) or not 1 <= len(entry) <= 3:
                return None
            name, vk, char = (list(entry) + [None, None, None])[:3]
            if not (name is None or isinstance(name, str)):
                return None
            if not (vk is None or isinstance(vk, int)):
                return None
            # isinstance(True, int) is True -- bool is an int subclass, so the
            # check above alone lets a bool vk through to label as "Key True".
            if isinstance(vk, bool):                               # NEW
                return None                                        # NEW
            if vk is not None and not (0 <= vk <= MAX_VK):          # NEW
                return None                                        # NEW
            if not (char is None or isinstance(char, str)):
                return None
            # bool("") is False, so an empty char slid through here into a
            # rendered "Key None" label; an unbounded char rendered a 200-char
            # string verbatim into the same label.
            if char is not None and not (1 <= len(char) <= MAX_CHAR_LEN):  # NEW
                return None                                               # NEW
            if name is None and vk is None and char is None:
                return None
            # Shape is not vocabulary: kb.Key is an Enum class, so hasattr
            # says yes to mro, __class__, __init__, _member_map_, __module__
            # -- everything Enum/object supplies, not just real key names.
            if name is not None and name not in kb.Key.__members__:  # CHANGED (was hasattr)
                return None
            records.append((name, vk, char))
        return cls(list(mods), records)
```
`Hotkey.__init__`'s `records[:MAX_CHORD]` truncation (`afk_clicker.py:413-415`) is left exactly as-is: with the new `len(raw) > MAX_CHORD` guard, `from_json` never calls `cls(...)` with more than `MAX_CHORD` records, so the truncation there becomes dead for this call path and instead stands as a constructor-level invariant protecting any other future caller of `Hotkey(...)` directly (there is none today besides `from_json` and `HotkeyRecorder`, per a repo-wide grep for `Hotkey(`).

## Affected areas
- `afk_clicker.py`: two new constants near `MAX_CHORD` (~line 313), five new/changed guard lines inside `Hotkey.from_json` (~lines 437-471). One function, one file, one architectural layer (application logic) — no split needed.
- `tests/test_hotkey.py`, class `Persistence` (~lines 197-294): new cases in `test_every_rejection_path_is_reachable`, plus new dedicated tests alongside `test_unknown_key_names_are_rejected` (see Acceptance criteria for the full list). No other test file touched.
- No data model, schema, or public API change — `to_json`'s output shape and `Hotkey`'s public surface (`matches`, `label`, `to_json`) are untouched. No `docs/design.md` needed (see Non-goals).

## Edge cases
- **Settings file recorded on one platform, read on another (the ticket's own scenario).** `kb.Key.__members__` is evaluated against whichever backend *this* process imported, so a name valid on the recording platform (e.g. `media_play_pause`, X11/Win32-only) but absent from this machine's `Key` enum (e.g. a stripped-down or different backend) is rejected → `None`, identical to today's "a damaged setting starts clean" contract for every other rejection in this function. This is not a new problem this cycle introduces — it already falls out of comparing against `kb.Key` as imported — but the ticket asks it be stated explicitly, so: yes, that mismatch rejects rather than crashing or arming a dead hotkey.
- **`char` at exactly the new boundary.** A single-code-point char (the overwhelming common case — every named key, and every X11/Win32 character key) and a short darwin dead-key/compose cluster both pass; the ticket's 200-character example and the empty string both fail. `len()` on a Python `str` counts code points, not UTF-16 code units or grapheme clusters, which matches what `_record` (`afk_clicker.py:373-374`) actually stores.
- **`vk` at exactly the new boundary.** `0` is a legitimate vk (a real X11 keysym/Win32 VK could be `0` in principle) and is kept accepted; `-1` and any value `> MAX_VK` are rejected; `True`/`False` are rejected regardless of the numeric value they'd coerce to, before the range check even runs.
- **A chord of exactly `MAX_CHORD` (3) entries** is unaffected (still accepted); exactly `MAX_CHORD + 1` (4) is the new rejection boundary, replacing today's silent truncation to 3.
- **Interaction between the new chord-length guard and the existing per-entry guards.** The `len(raw) > MAX_CHORD` check runs first, before the mods checks and the per-entry loop, so an over-long chord is rejected regardless of whether its individual entries would otherwise have passed — consistent with the function's existing "cheapest/structural checks first" ordering (dict shape, then keys shape, before ever touching `mods` or looping entries).
- **A blob that is otherwise fully valid except for one bad entry deep in a 3-entry chord** still rejects the whole blob, not just that entry — unchanged from today's "reject, do not filter" behavior; this cycle changes which values count as bad, not the all-or-nothing shape of the rejection.

## Acceptance criteria
- [ ] Given `{"keys": [["mro", None, None]]}` (and likewise `"__class__"`, `"__init__"`, `"_member_map_"`, `"__module__"`), when `Hotkey.from_json` is called, then it returns `None` — these are exactly the non-key attributes the ticket names as accepted by `hasattr(kb.Key, name)` today; each must fail once `name in kb.Key.__members__` lands, and the test must be written *before* the fix to confirm it fails against the current code (sabotage-verify in reverse).
- [ ] Given `{"keys": [["f6", None, None]]}` (unchanged real key name), `from_json` still returns a non-`None` `Hotkey` — the tightened vocabulary check does not regress any real key name.
- [ ] Given `{"keys": [[None, None, ""]]}` (empty char), `from_json` returns `None`.
- [ ] Given `{"keys": [[None, None, "x" * 200]]}` (the ticket's 200-char example), `from_json` returns `None`.
- [ ] Given `{"keys": [[None, None, "ä"]]}` (single non-ASCII code point, already covered by `test_round_trip`) and a short multi-code-point string at or under `MAX_CHAR_LEN` (e.g. `"́a"`, a combining acute accent plus a base letter — 2 code points), `from_json` still returns a non-`None` `Hotkey` — the length bound does not reject realistic composed input.
- [ ] Given `{"keys": [[None, True, None]]}` and `{"keys": [[None, False, None]]}` (bool vk), `from_json` returns `None` for both.
- [ ] Given `{"keys": [[None, -1, None]]}` (negative vk), `from_json` returns `None`.
- [ ] Given `{"keys": [[None, 0x20000000, None]]}` (one past `MAX_VK`), `from_json` returns `None`; given `{"keys": [[None, 0x1FFFFFFF, None]]}` (exactly `MAX_VK`), `from_json` returns a non-`None` `Hotkey`.
- [ ] Given a 4-entry `"keys"` list (e.g. `[["f6",1,None],["f7",2,None],["f8",3,None],["f9",4,None]]`), `from_json` returns `None` (not a 3-entry truncated `Hotkey`); given the same list with only the first 3 entries, `from_json` returns a non-`None` `Hotkey` whose `.keys` has length 3.
- [ ] `tests/test_hotkey.py::Persistence::test_every_rejection_path_is_reachable` gains one `subTest` case per new guard above (chord-too-long, vk-is-bool, vk-out-of-range, char-empty, char-too-long, name-is-non-member-attribute), each chosen — per the existing discipline documented in that test's own comment — so that reverting only that one guard makes that one case fail, not one already caught by a different, later guard.
- [ ] Existing tests `test_round_trip`, `test_a_dropped_vk_is_not_silently_survivable`, `test_bad_modifiers_are_rejected_not_filtered`, `test_unknown_key_names_are_rejected`, `test_unhashable_modifiers_do_not_raise`, and `test_malformed_input_yields_none` all still pass unmodified — this cycle only narrows the accept set, it does not touch any path those tests exercise.
- [ ] Full existing suite still passes locally (`DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .`, per `backlog.md`'s documented run command) with no test other than `test_every_rejection_path_is_reachable` and the new dedicated tests listed above modified.
- [ ] Sabotage-verify per this repo's convention: for each new guard, temporarily revert just that guard and confirm the corresponding new test (and only that test, not a later guard's) fails, then restore.

## Open questions
None blocking. Two judgment calls made without a human decision point, stated here for the record along with the rejected alternative:
- **`MAX_CHAR_LEN = 8`** — rejected alternative: capping at exactly 1 code point. Rejected because the installed-and-read pynput 1.7.7 `_darwin.py` backend (`CGEventKeyboardGetUnicodeString`, line ~351) can genuinely hand `_record` more than one code point from a single dead-key/compose keypress, so a strict 1-code-point cap would reject some real, honestly-recorded macOS hotkeys on round-trip, not just the ticket's adversarial 200-char case. 8 is a judgment call, not a spec'd platform limit; if a real composed sequence is ever observed exceeding it, raise the constant rather than special-case a backend.
- **`MAX_VK = 0x1FFFFFFF`** — rejected alternative: a platform-specific bound (Win32 0-255, macOS ~0-127) selected by detecting `sys.platform` at validation time. Rejected because `vk` for a settings file is not tied to the platform reading it back (the whole point of the "moved between machines" scenario) — a single fixed ceiling wide enough for the largest of the three (X11's keysym space) accepts every legitimately-recorded value from any backend without needing to know, at validation time, which backend originally recorded it.

## Risk / rollback notes
- Purely additive/narrowing guards inside one already-defensive classmethod; no change to `to_json`, no change to what a *previously-accepted* well-formed blob does. Blast radius is exactly the five exploit shapes named in the ticket plus the chord-truncation path.
- Rollback is a single revert of this cycle's commit; no persisted-state format change, no migration — `settings.json`'s `"hotkey"` blob shape is unchanged, only the value-level acceptance criteria applied to it on read.
- The one thing this Linux/Xvfb sandbox cannot independently confirm is real dead-key/compose behavior on an actual macOS `CGEventKeyboardGetUnicodeString` call producing more than one code point in practice (the reasoning above is from reading the installed pynput 1.7.7 source, not from a live macOS keypress) — call this out in `docs/implementation.md`/`docs/test-review.md` the same way `docs/history/ac-5-spec.md` flagged its own macOS-only leg, and treat the next green `macos-latest` CI run as the real confirmation that `MAX_CHAR_LEN = 8` doesn't clip a genuine composed character, not a local guarantee.
