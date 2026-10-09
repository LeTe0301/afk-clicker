# Test & Review: Macros-specific regression test for the `put_game()` merge fix (G#58)

## Scope
Verifies the single new regression test
(`MacrosTab.test_a_macro_survives_an_unrelated_persist_call`,
`tests/test_ui.py:7573`) actually exercises G#57's `put_game()` merge fix via
the macros path, that the forward-ported one-line fix
(`afk_clicker.py:1760`) is byte-identical to G#57's own shipped fix, and that
nothing else in the suite regressed. Ties to `docs/spec.md`'s three
acceptance criteria.

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | New test added, passing against current (fixed) `put_game()` | Automated — ran test in isolation | pass | `DISPLAY=:99 .../python -m unittest tests.test_ui.MacrosTab.test_a_macro_survives_an_unrelated_persist_call -v` → `ok`, `Ran 1 test ... OK` |
| 2 | Sabotage-verified: fails against reverted (wholesale-replace) `put_game()` | Automated — reverted `put_game()` myself (not relying on developer's transcript), re-ran the same test alone | pass | `KeyError: 'macros'` at `self.ui.store.game("minecraft")["macros"]` — clear, unambiguous failure, not a silent pass. Fix then restored and diff re-confirmed byte-identical to the original (`git diff -- afk_clicker.py` matches the pre-sabotage diff exactly); re-ran the test alone → green again |
| 3 | Full suite still green, no other test's count/behavior changed | Automated — full discovery run | pass | `python -m unittest discover -s tests -t .` → `Ran 514 tests in 96.524s` / `OK (skipped=10)`. Independently cross-checked the +1 test count via `grep -c "    def test_"` on `tests/test_ui.py`: 391 (HEAD) → 392 (working tree), exactly one new test method; `git diff --stat` confirms only `tests/test_ui.py` (+22/-0 net test lines) and `afk_clicker.py` (1 line changed) were touched |
| 4 | Forward-ported `put_game()` fix is byte-identical to G#57's own shipped fix, not a second independent fix | Manual — diffed against the real commit on `feature/ac-57/per-game-hotkeys` (`b49db61`), not just the archived `docs/history/ac-57-implementation.md` prose | pass (code); see Finding 1 for a documentation-accuracy nuance | `git show b49db61:afk_clicker.py` shows the merge line `self.data["games"].setdefault(game_id, {}).update(values)` is character-for-character identical to this branch's `afk_clicker.py:1760`. Also confirmed `main`'s current `put_game()` (`git show main:afk_clicker.py`) still has the old bug (`self.data["games"][game_id] = values`, no comment) — G#57 hasn't merged to `main` yet, so this branch's forward-port is live-necessary, not redundant |
| 5 | `_persist()`'s `values` dict genuinely has no `"macros"` key (the gap the spec/test rely on) | Manual — read `_persist()` directly | pass | `afk_clicker.py:4351-4372`: `values` dict lists `click_ms`/`jitter_ms`/.../`eat_hold` and optionally `_profile`; no `"macros"` or `"hotkey"` key anywhere |
| 6 | Test fixture/call shape matches the established sibling precedent (`test_save_macro_persists_and_arms_its_hotkey`) | Manual — read both tests side by side | pass | Same `_select`/`Hotkey`/`steps`/`_save_macro` call shape, same `@needs_input_permission` decorator, same on-disk `app.Store(self.config)` reload assertion style; added to `MacrosTab` (not `StoreMacroFiltering`), correctly, since only `MacrosTab` has the `self.ui`/`self.store` fixture the spec asked for |
| 7 | `py_compile` sanity | Automated | pass | `python -m py_compile afk_clicker.py tests/test_ui.py` → no output, exit 0 |

## Regression check
Full existing suite run: `DISPLAY=:99 /home/dev/.venvs/afk-clicker-test/bin/python -m unittest discover -s tests -t .` — **514 tests, OK, skipped=10**. Matches the developer's reported count exactly, independently re-run and re-verified by me this session (not taken from the transcript). No lint/type-check config exists in this repo (no `.flake8`/`pyproject.toml`/CLAUDE.md lint section found) — none applicable.

## Defects found
None. Testing pass is clean.

---

## Spec coverage
All three acceptance criteria in `docs/spec.md` are implemented and tested, confirmed above (cases 1-3). The spec's "Test to add" steps 1-4 are followed exactly; no gaps.

## Findings (most severe first)

### 1. "No-op once merged" claim in `docs/implementation.md` is slightly inaccurate — nit
- File: `docs/implementation.md:17-18`, `docs/implementation.md:58-68` ("Deviations from spec")
- Issue: the doc says the forward-ported `put_game()` change "will net out as a no-op once G#57 and G#58 both merge to `main`." The *resulting code* is indeed byte-identical (confirmed above against G#57's real commit `b49db61`), so the end state is correct and this is genuinely not "a second independent fix with its own subtly different behavior." But G#57's actual shipped commit also adds a 13-line explanatory comment immediately above that line (`git show b49db61:afk_clicker.py:1800-1812`) that this branch's forward-port doesn't carry. Since both branches change the exact same original line (the bare `main` version, unchanged), git's three-way merge will see two different-sized replacements of the same original line and raise a **textual conflict**, not a silent no-op, whichever of G#57/G#58 is merged to `main` second.
- Failure scenario: not a bug in this ticket's code or test — purely a heads-up for whoever merges both branches to `main`: expect a trivial conflict on `put_game()` (resolve by keeping G#57's commented version; the code itself is identical either way). Worth a one-line correction to `docs/implementation.md`'s "Deviations from spec" wording so it doesn't overstate "no-op," but doesn't block this ticket — the test and fix are both correct as shipped.

## Follow-ups (non-blocking)
- Optionally reword `docs/implementation.md`'s "no-op" claim per Finding 1 before/when merging, or just note it in the merge step itself — either is fine, doesn't require a new dev cycle.

## Overall verdict
**Approve.** All three acceptance criteria verified by tests I ran myself this session (not inferred from the developer's transcript): the new test passes against the current fix, fails with a clear `KeyError: 'macros'` against a self-reverted wholesale-replace `put_game()`, and the full suite (514 tests, 10 skipped) stays green. The forward-ported one-liner is confirmed byte-identical to G#57's real shipped commit, not a second independent fix. One nit filed (non-blocking, documentation wording only) — does not require a new build cycle.
