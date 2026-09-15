# Spec: Review residue — roadmap wording, startup ordering, test hygiene, stale counts — G#10/GH#12

## Summary
Four small, independent one-liners carried across three review rounds on PR #4, none blocking: `ROADMAP.md`'s schema-version item needs one sentence naming the `hotkey` field as the exact moment it was written for; `AfkAutoclicker.__init__`'s startup-restore ordering (flagged as load-bearing and undocumented) turns out to already be safe on current `main` and only needs the "why" written down, not a code move; `test_malformed_input_yields_none` needs its `blob if blob else {}` guard removed so the `None` case it claims to test is actually passed; and three bare `open()` calls in `tests/test_ui.py`'s `HotkeyPersistence` need `with` blocks to stop leaking file handles. A fifth item (stale test counts in GitHub issue #1 and PR #4's own bodies) is orchestrator housekeeping, not a code change — see the dedicated section below.

## Goals
- `docs/ROADMAP.md:11-17` — add a sentence to the "Settings schema version" item naming `hotkey` as the first structured (nested, own-`to_json`/`from_json`, own value-vocabulary) field `settings.json` has ever carried, and stating that both migration directions are safe today.
- `afk_clicker.py` — document, in the existing comment directly above the startup restore (`afk_clicker.py:2433-2436`), the invariant that the restore already runs after `_timers`/`_sync_settings`/`_drain_ui`/`_poll_games` have executed once (they live at `_build_ui`'s own tail, `afk_clicker.py:2674-2677`, and `_build_ui()` — called synchronously at `afk_clicker.py:2401` — has already returned by the time the restore code at `afk_clicker.py:2437-2440` runs). No code moves; see "Proposed approach" for why this is a documentation-only fix, not the code move the ticket's own wording assumes is still needed.
- `tests/test_hotkey.py:345` — `Persistence.test_malformed_input_yields_none` passes `blob` directly instead of `blob if blob else {}`, so the `None` case in its own parametrized list is actually exercised as `None`, not silently rewritten to `{}` before the call.
- `tests/test_ui.py:2005,2007,2015` — the three bare `open()` calls in `HotkeyPersistence.test_a_corrupt_hotkey_starts_clean` and `test_nothing_is_saved_when_no_hotkey_was_applied` become `with open(...) as f:` blocks, closing the handles instead of leaking them (`ResourceWarning` on every leg of every run).

## Non-goals
- G#18 (Button click-away test), G#21 (updater residue), G#40 (macOS sidebar flake) — separate, already-tracked tickets, untouched here.
- Any settings-file schema-version *implementation* (an actual version field, a migration runner, or reordering `Store.__init__`'s existing unversioned rewrites relative to a future migration). This cycle only adds one sentence of `ROADMAP.md` prose; the schema-version work itself stays an open roadmap item, not something this cycle starts.
- Any change to `AfkAutoclicker.__init__`'s actual statement order, `_build_ui()`'s tail, `apply_hotkey()`, or the hotkey-restore logic itself. Per the judgment call below, the ordering concern the ticket names is already resolved on current `main` (by an unrelated refactor, commit `54a3b65`) — this cycle documents that, it does not restructure anything to *make* it true.
- `Hotkey.from_json`'s value-vocabulary guards (G#7/GH#9, already shipped in commit `991c8bc`) — untouched; the one line this cycle touches in `test_malformed_input_yields_none` only changes what gets *passed into* `from_json`, not `from_json` itself.
- The other bare `open()` calls elsewhere in `tests/test_ui.py` (lines 439, 2880, 3049) that produce the identical `ResourceWarning` pattern — real, but in different test classes the ticket does not name (`Selftest`/whatever `test_offer_lands_through_a_real_worker_thread_with_settings_open` and its neighbors belong to). Left for a separate cleanup pass if wanted; fixing them here would be scope creep past what G#10 actually names.
- Editing the stale counts anywhere in the repo — there is nothing to edit; the stale numbers live only in GitHub issue #1's and PR #4's own bodies (see the dedicated section below), not in any tracked file.
- **ux-designer is skipped for this cycle.** Nothing here has a visual or layout component: one is a roadmap-doc sentence, one is a code comment, two are test-only file-handle/argument fixes. No screen, dialog, or rendered string changes.

## Background / current state

### Item 1 — `docs/ROADMAP.md:11-17`, verified as given
```
- [ ] **Settings schema version.** `settings.json` has no version field, so a
      future format change has no migration path and would silently reset
      everyone's per-game values. Two unversioned rewrites already run in
      `Store.__init__` (#15): entries under `games` that are not objects are
      dropped, and a saved Minecraft `click_ms` of exactly 510 becomes 650.
      Whatever versioned migration comes first must run **before** that
      shape filter, or it will discard old-format data as if it were corrupt.
```
`Store.__init__` (`afk_clicker.py:1268-1320`) shows `self.data`'s five top-level keys: `games` (a dict of per-game dicts of scalars — `click_ms`, `jitter_ms`, etc.), `hotkey`, `selected`, `appearance`, `ui_scale`. Every key except `hotkey` is either a bare scalar or a dict-of-scalars. `hotkey`, added by PR #4 (`feature/ac-2/hotkey-lost-on-restart`, merged `1283b57`) and hardened by G#7 (commit `991c8bc`), is the only field with its own nested internal shape (`{"mods": [str, ...], "keys": [[name, vk, char], ...]}`), its own round-trip methods (`Hotkey.to_json`/`Hotkey.from_json`, `afk_clicker.py:426-471`), and its own value-level vocabulary (key-name membership, `vk` range, `char` length, chord-length cap). It is, concretely, the first field this schema-version item's "future format change" warning was describing in the abstract — the roadmap item was drafted before this field existed and has not been updated since it landed.

Both migration directions are currently safe with no version field: an old `settings.json` predating PR #4 has no `"hotkey"` key at all, and `Store.__init__`'s own merge (`self.data.update({k: v for k, v in loaded.items() if k in self.data})`, line ~1276) leaves the constructor's own default (`"hotkey": None`, line 1270) in place for a missing key — this is the same "corrupt/missing starts clean" contract as every other field, not a special case. In the other direction, a blob written by *this* version of `from_json`/`to_json` that a hypothetical older or differently-configured reader can't fully validate degrades to `None` (via `from_json`'s existing "reject, do not filter" guard chain) rather than crashing — "damaged/unrecognized setting starts clean" again. Nothing about this is at risk today; the point of the added sentence is only to record that the schema-version item was written for exactly the moment a structured field first arrived, and that moment is now.

### Item 2 — startup ordering, verified against current `main`, premise does not hold
The ticket's premise, verified line-by-line against `afk_clicker.py` on this branch (tip `b853890`):

- `AfkAutoclicker.__init__` (starts `afk_clicker.py:2212`) calls `self._build_ui(s)` at **line 2401** — a plain, synchronous method call.
- `_build_ui()` (`afk_clicker.py:2533-2677`) is "the rebuildable widget-construction body" per its own docstring, called once from `__init__` and again by `_rebuild_ui()` on every appearance/scale change. Its own **tail**, lines **2674-2677**, is:
  ```python
  self._timers = {}
  self._sync_settings()
  self._drain_ui()
  self._poll_games()
  ```
- Back in `__init__`, *after* `self._build_ui(s)` at line 2401 has returned: `self.root.bind("<Configure>", ...)` at line 2403, then the startup restore at **lines 2437-2440**:
  ```python
  saved = Hotkey.from_json(self.store.data.get("hotkey") or {})
  if saved is not None:
      self.hotkey = saved
      self.apply_hotkey()
  ```
- `apply_hotkey()` (`afk_clicker.py:4058-4084`) is what actually arms the listener (`HotkeyWatcher(...).start()`, line ~4077); its only interaction with settings-derived state is reading `self.hotkey`/`self.registered_hotkey`/`self.hk_listener` and, through the guard added by G#8 (PR #73, commit `6d3b92b`), `macos_input_permitted()` — none of these touch `self.settings`, `self._timers`, or the UI queue `_drain_ui()` drains. The thing that actually reads `self.settings` (populated by `_sync_settings()`) is `loop()` (`afk_clicker.py:4135-...`), reached only if a key press fires the listener's callback into `toggle()` → `start()`.

Since Python executes `__init__` top to bottom and `self._build_ui(s)` (line 2401) is an ordinary, synchronous call, **`_build_ui`'s entire body — including its tail at lines 2674-2677 — has already finished running by the time execution reaches line 2401's next statement**, let alone line 2437. By the time `apply_hotkey()` arms the listener, `self._timers` already exists, `_sync_settings()` has already populated `self.settings` with real values (not the `{}` default), and `_drain_ui()`'s own `after()` chain is already scheduled. There is no window, milliseconds-wide or otherwise, in which a restored-hotkey press could reach `loop()` with an empty settings snapshot.

This was not always true. `git log -S"def _build_ui" --oneline -- afk_clicker.py` shows `_build_ui()` was introduced by commit `54a3b65` ("A Settings page, and a theme switch that rebuilds the window in place") — the extraction that split `__init__`'s original single-pass widget construction into a reusable `_build_ui()`/`_rebuild_ui()` pair for the theme-rebuild feature. At the time PR #4 (and G#10's own filing, both dated `2026-09-10`) described this ordering, `_timers`/`_sync_settings`/`_drain_ui`/`_poll_games` most likely sat inline in `__init__` in whatever order they were originally written, with no guarantee they preceded the restore call. The `_build_ui` extraction — an unrelated refactor, done for the Settings-page/theme feature, not for this ticket — moved all four into `_build_ui`'s own tail, which is called *before* the restore in the caller. The ticket's premise was accurate against the code as it stood at PR #4 review time; it is stale against current `main`.

**Judgment call, stated for the record:** the ticket asks to "move the restore below `_drain_ui`, or say why it cannot move." Neither literally applies — there is nothing to move, because the restore already executes after all four lines complete, as a side effect of where `_build_ui()` is called from. The rejected alternative is moving the restore's *textual position* further down in `__init__` (e.g., physically placing it after the `_log_report_after_id` scheduling) purely for readability. Rejected because textual position already matches execution order for the four lines that matter (they live inside a function called earlier), and moving working code for cosmetic reasons violates this repo's minimal-diff convention (`docs/CODING-GUIDELINES.md`'s comment-the-why principle applies the same discipline to structure: don't restructure to narrate what a comment can state directly). The fix is a documentation-only addition to the comment already sitting at `afk_clicker.py:2433-2436` (see Proposed approach), not a code move.

### Item 3 — `tests/test_hotkey.py:345` (shifted from ~336 by PR #74/commit `991c8bc`)
```python
    def test_malformed_input_yields_none(self):
        # "keys": "nope" raises nothing on its own -- iterating a string hands
        # back characters and would build a plausible hotkey out of garbage.
        for blob in ({}, {"keys": []}, {"keys": "nope"}, {"mods": ["ctrl"]},
                     {"keys": [[]]}, {"keys": [[None, None, None]]},
                     {"keys": [["f6"]], "mods": "ctrl"},
                     {"keys": [[1, 2, 3]]}, "not a dict", None):
            with self.subTest(blob=blob):
                self.assertIsNone(app.Hotkey.from_json(blob if blob else {}))
```
`{}` and `None` are the only two falsy entries in this tuple (`"not a dict"` is truthy). `blob if blob else {}` silently rewrites both to `{}` before the call, so `None` — the one entry in this list actually named "malformed" in the sense of "not a dict at all" alongside `"not a dict"` — is never the value handed to `from_json`; the test asserts `from_json({})` twice instead of `from_json({})` once and `from_json(None)` once. `Hotkey.from_json`'s first guard, `if not isinstance(blob, dict): return None` (`afk_clicker.py:435-436`), already handles a real `None` correctly — the guard is not the bug, the test's own ternary is. This exact gap was flagged in round 2 on PR #3, deferred to G#10 explicitly by `docs/history/ac-7-spec.md`'s own Non-goals ("including the `None`-blob test gap: fixing it is one line but belongs to that ticket's own diff, not this one's" — that ticket is this one), and has now traveled across PR #3 and PR #4 unfixed.

### Item 4 — `tests/test_ui.py:1975-2015`, class `HotkeyPersistence`
```python
    @needs_input_permission
    def test_a_corrupt_hotkey_starts_clean(self):
        self.ui.hotkey = hotkey(set(), [kb.Key.f6])
        self.ui.apply_hotkey()
        self.ui.on_close()
        data = json.load(open(self.config))                    # line 2005
        data["hotkey"] = {"keys": "garbage"}
        json.dump(data, open(self.config, "w"))                # line 2007
        self.root = tk.Tk()
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        self.root.update()
        self.assertIsNone(self.ui.registered_hotkey)

    def test_nothing_is_saved_when_no_hotkey_was_applied(self):
        self.ui.on_close()
        self.assertIsNone(json.load(open(self.config)).get("hotkey"))   # line 2015
```
All three `open()` calls are bare — no `with`, no assignment to a variable that gets closed — so CPython relies on refcounting/GC to close the underlying file object, which `unittest`'s `-W error`-adjacent warning capture (or any `-W` flag, or just running under `python -Walways`) surfaces as a `ResourceWarning` on every one of these three call sites, on every leg of every test run. `grep -n "open(" tests/test_ui.py tests/test_hotkey.py | grep -v "with open"` finds three more bare calls elsewhere in `tests/test_ui.py` (lines 439, 2880, 3049) — all in different test classes the ticket does not name, so they are out of scope here (see Non-goals).

## Proposed approach

### Item 1 — `docs/ROADMAP.md`
Append one sentence to the existing bullet (`docs/ROADMAP.md:11-17`), after "...as if it were corrupt.":
```
      The `hotkey` field (PR #4) is the first structured value this file
      has ever carried — nested `mods`/`keys` lists with their own
      `to_json`/`from_json` round-trip and value vocabulary, unlike every
      other top-level key's bare scalar or flat dict — so this item was
      written for exactly this moment. Both directions are safe today with
      no version field: a pre-PR-#4 file has no `hotkey` key and gets the
      constructor's own `None` default, and a blob a future reader can't
      fully validate degrades to `None` via `from_json`'s existing
      reject-not-filter guards — but neither direction is versioned, so a
      genuinely incompatible future change to this field's own shape still
      has no way to tell old data from new except by inference.
```
Wording only; no other line in the bullet changes.

### Item 2 — `afk_clicker.py:2433-2436`
Extend the existing comment above the restore to state the invariant explicitly:
```python
        # Registers an OS-level global hotkey listener -- runs once, after
        # the first _build_ui() call, never inside _build_ui()/_rebuild_ui()
        # itself: re-running it on every rebuild would try to register a
        # second listener while self.hk_listener is still running.
        #
        # This also means _timers/_sync_settings()/_drain_ui()/_poll_games()
        # (the tail of _build_ui(), a few hundred lines up) have already run
        # once by the time this listener is armed -- _build_ui(s) above is a
        # plain synchronous call, so its entire body, tail included, has
        # already returned before execution reaches this point. A restored
        # hotkey press can never reach loop() (which reads self.settings)
        # against an empty settings snapshot; there is no ordering gap here
        # to close. (This was not always true: _build_ui() itself did not
        # exist until commit 54a3b65 pulled these four lines out of __init__
        # for the Settings-page/theme-rebuild feature -- an unrelated
        # refactor that happened to close this gap as a side effect.)
        saved = Hotkey.from_json(self.store.data.get("hotkey") or {})
        if saved is not None:
            self.hotkey = saved
            self.apply_hotkey()
```
No other line changes. No test changes for this item — nothing about behavior changed, only a comment grew.

### Item 3 — `tests/test_hotkey.py:345`
```python
                self.assertIsNone(app.Hotkey.from_json(blob))
```
(replaces `app.Hotkey.from_json(blob if blob else {}))`). Every other entry in the `for blob in (...)` tuple is unaffected: `{}` was already passed as `{}` (falsy, ternary was a no-op for it); every other entry is truthy and was already passed through unchanged. Only `None` changes what is actually passed. `from_json(None)` returns `None` via the existing `isinstance(blob, dict)` guard (`afk_clicker.py:435-436`) — confirmed by reading that guard, not by running the suite in this session — so the assertion's expected outcome (`None`) is unchanged; only the coverage improves.

### Item 4 — `tests/test_ui.py`
```python
    @needs_input_permission
    def test_a_corrupt_hotkey_starts_clean(self):
        self.ui.hotkey = hotkey(set(), [kb.Key.f6])
        self.ui.apply_hotkey()
        self.ui.on_close()
        with open(self.config) as f:
            data = json.load(f)
        data["hotkey"] = {"keys": "garbage"}
        with open(self.config, "w") as f:
            json.dump(data, f)
        self.root = tk.Tk()
        self.ui = app.AfkAutoclicker(self.root, store=app.Store(self.config))
        self.root.update()
        self.assertIsNone(self.ui.registered_hotkey)

    def test_nothing_is_saved_when_no_hotkey_was_applied(self):
        self.ui.on_close()
        with open(self.config) as f:
            self.assertIsNone(json.load(f).get("hotkey"))
```
No behavior change — same file, same reads/writes, same assertions; only the handles now close deterministically.

## Affected areas
- `docs/ROADMAP.md`: one sentence appended to one bullet (~line 17).
- `afk_clicker.py`: one comment block extended (~lines 2433-2436); zero executable lines changed.
- `tests/test_hotkey.py`: one line changed (~345).
- `tests/test_ui.py`: two test methods reshaped from bare `open()` to `with` blocks (~lines 2005-2015); zero assertions changed.
All four are documentation/test-only changes in a single architectural layer (docs + tests); no split needed — this stays one developer dispatch.

## Stale test counts (item 5) — orchestrator housekeeping, not a code change
The ticket's stale numbers ("issue #1 says 70 fast tests but 70 is the total on that branch and 65 are fast," "PR #4's body says 82 tests where every leg now runs 84") live entirely in the **bodies of already-closed GitHub artifacts** — issue #1 and PR #4 — not in any file this repo tracks. `grep -rn "70 fast\|82 tests\|84 tests\|65 fast" --include=*.md .` finds nothing in the tree; every count found in `docs/history/*.md` (e.g. `84 tests` in `ac-17-f1-design.md`, `284 tests` throughout the `ac-24`/`ac-27` history docs) is that cycle's own contemporaneous, still-accurate snapshot at the time it was written, not a copy of issue #1's or PR #4's numbers. There is nothing here for the developer to touch.

Recommendation for the orchestrator: **add a correcting comment to issue #1 and PR #4, do not edit their bodies.** A closed issue/PR body is a historical record of what was claimed *at that time* — editing it in place erases what the original author actually wrote with no trace that a correction happened, which is a worse outcome than a stale number sitting in old, closed context that nobody is actively relying on for current test-count expectations (the live count lives in CI's own output and this repo's current `docs/history/*.md`, not in a two-cycle-old ticket body). A comment appended now, dated and explicit about the current count, corrects the record for anyone who reads the thread later without silently rewriting it. This is a REST-API action outside this cycle's diff — not the developer's or reviewer's job — so it is listed here for the orchestrator to action separately, if it chooses to.

## Edge cases
- **Item 2's "no gap" finding depends on `_build_ui()` staying a synchronous, non-deferred call from `__init__`.** If a future change wraps `self._build_ui(s)` (line 2401) in `after_idle`/a thread/anything asynchronous, the invariant documented here breaks silently — this is exactly why the comment states the *mechanism* (plain synchronous call) and not just the conclusion, so a future reader touching that call site has to notice the comment's premise no longer holds. No code enforces this; it is a documented invariant, same class of risk as any other comment-only guarantee in this file.
- **`test_malformed_input_yields_none`'s `"not a dict"` string entry** is unaffected by the item-3 change (already truthy, already passed through as-is) — confirms the fix is scoped to exactly the `None`/`{}` pair the ticket names, not a wider rewrite.
- **The two `HotkeyPersistence` tests being fixed already run under `@needs_input_permission`/no-skip conditions identically to before** — the `with` rewrite changes nothing about *when* the test runs, only how the file handles are managed within it.
- **ROADMAP wording addition must not read as "action needed now"** — it's context for the next reader of this item, not a call to start the schema-version work in this cycle (see Non-goals).

## Acceptance criteria
- [ ] Given `docs/ROADMAP.md`'s "Settings schema version" bullet, when read after this change, then it contains the new sentence naming `hotkey` as the first structured value and stating both migration directions are safe today — no other line in the bullet is altered.
- [ ] Given `afk_clicker.py:2433-2436`'s comment, when read after this change, then it explicitly states that `_timers`/`_sync_settings`/`_drain_ui`/`_poll_games` (at `_build_ui`'s tail) have already run once by the time the restore arms the listener, and names commit `54a3b65` as the refactor that made this true — no executable line in `__init__`/`_build_ui`/`apply_hotkey` changes.
- [ ] Given `tests/test_hotkey.py::Persistence::test_malformed_input_yields_none`, when run, then it calls `app.Hotkey.from_json(None)` directly (not `app.Hotkey.from_json({})`) for the `None` entry in its `for blob in (...)` tuple, and still asserts `None` for every entry, and still passes.
- [ ] Given `tests/test_ui.py::HotkeyPersistence::test_a_corrupt_hotkey_starts_clean` and `test_nothing_is_saved_when_no_hotkey_was_applied`, when run under `python -W error::ResourceWarning` (or equivalent), then neither raises a `ResourceWarning` — confirmed by running with warnings escalated to errors, not just by inspection.
- [ ] Full existing suite still passes: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` (venv at `/tmp/claude-1000/-home-dev-projects-afk-clicker/31f5a905-5b3f-4e0f-95d5-176a1d0748c4/scratchpad/pv`, starting `Xvfb :99` directly if not already running, never running two Tk processes on one display) reports the same 374 tests, `OK (skipped=10)` as the documented baseline on `main` — no test count changes, since no test is added or removed, only two existing tests reshaped and one existing test's argument corrected.
- [ ] No file other than `docs/ROADMAP.md`, `afk_clicker.py` (comment only), `tests/test_hotkey.py`, and `tests/test_ui.py` is touched. No new file added to the repo tree other than this `docs/spec.md`.
- [ ] Sabotage-verify per this repo's convention: temporarily restore `blob if blob else {}` in `test_malformed_input_yields_none` and confirm the test still passes either way (this is the one item in this cycle where the "fix" only *tightens what's exercised*, not a behavior bug — so the sabotage check here is "does removing the ternary reduce coverage if reverted", not "does the test fail without the fix", and `docs/implementation.md` should say so explicitly rather than force a fail-without-fix framing that doesn't apply).

## Open questions
None blocking. One judgment call made without a further human decision point, stated in full under Background/current state, item 2: the startup-restore ordering is documented as already-safe rather than moved, because it already executes after `_build_ui`'s tail on current `main` — the rejected alternative (a cosmetic textual reorder) is named there.

## Risk / rollback notes
- Every change in this cycle is either prose (roadmap, one code comment) or a test-only edit with no production-code behavior change — blast radius is effectively zero for runtime behavior. The only thing that could regress is test coverage/hygiene itself (e.g., a `with` rewrite that accidentally changes what's asserted), which the acceptance criteria above check directly.
- Rollback is a single revert of this cycle's commit; no persisted-state, schema, or API surface is touched anywhere in this diff.
- Item 5 (stale counts) is explicitly out of this diff — its own action (or inaction) carries no rollback concern for this repo, since nothing in the tree changes for it.
