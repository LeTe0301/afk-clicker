# Test & Review: Number fields drop focus easily; window is resizable (ticket #14)

## Scope
Covers every acceptance criterion in `docs/spec.md`: `NumBox` focus-drop on
click-elsewhere/Enter/Escape/clicker-start, Tab traversal non-regression,
Segmented/GameItem click non-regression, and window resizability (both-axes
resizable, `minsize`, content-pane growth vs. pinned sidebar, shrink clamping).
Diff reviewed: `git diff main` in this worktree, `afk_clicker.py` +
`tests/test_ui.py` (159 lines changed, no other files).

## Test cases

| # | Criterion / case | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Click on a non-Entry widget (label) drops focus, wrap → LINE | Automated | pass | `tests/test_ui.py::NumBoxFocus::test_click_elsewhere_drops_focus` |
| 2 | Click on the focused entry itself keeps focus on an Entry | Automated | pass | `NumBoxFocus::test_click_the_entry_itself_keeps_it_focused` |
| 3 | Click a different NumBox switches focus to it | Automated | pass | `NumBoxFocus::test_click_a_different_numbox_switches_focus` |
| 4 | Enter blurs, value unchanged (no revert) | Automated | pass | `NumBoxFocus::test_enter_blurs_without_reverting_the_value` |
| 5 | Escape blurs, value unchanged (no revert) | Automated | pass | `NumBoxFocus::test_escape_blurs_without_reverting_the_value` |
| 6 | `start()` from a background thread drops focus once `_drain_ui` runs | Automated | pass | `NumBoxFocus::test_starting_from_a_background_thread_drops_focus` |
| 7 | Tab traversal unaffected | Automated | pass | `NumBoxFocus::test_tab_still_moves_focus` |
| 8 | Segmented control still changes its bound variable when clicked with a field focused | Automated | pass | `NumBoxFocus::test_a_segmented_control_still_changes_its_variable` |
| 9 | GameItem still calls `_select` when clicked with a field focused | Automated | pass | `NumBoxFocus::test_a_game_item_still_selects` |
| 10 | A `Button` canvas (e.g. Record) both drops focus and fires its own command when clicked with a field focused | Manual (probe script, not in automated suite — see Finding 1) | pass | see "Probe 1" below |
| 11 | `root.resizable()` reports `(1, 1)` | Automated | pass | `WindowResize::test_both_axes_are_resizable` |
| 12 | `root.minsize()` == `(int((SIDEBAR_W+1+CONTENT_W)*s), int(690*s))` | Automated | pass | `WindowResize::test_minsize_matches_todays_default_size` |
| 13 | Growing the window expands content, sidebar stays pinned (at default `s`) | Automated | pass | `WindowResize::test_growing_the_window_expands_content_not_the_sidebar` |
| 14 | Same, at `s = 1.5` (DPI scale ≠ 1.0) | Manual probe | pass | side 311→311, content 678→1088 after `geometry("1400x1200")` |
| 15 | Shrinking below `minsize` is clamped (default `s`) | Automated | pass | `WindowResize::test_shrinking_below_minsize_is_clamped` |
| 16 | Same, at `s = 1.5` | Manual probe | pass | `minsize=(990,1034)`; `geometry("50x50")` left window at exactly `(990,1034)` |
| 17 | Clearing a field then clicking away (edge case) | Covered by existing `NumericClamping` tests + `_num()`'s fallback; no new path | pass | pre-existing, unaffected by this diff |
| 18 | Thread safety: `start()`'s new Tk touch goes through `_ui()`, nothing else new touches Tk off-thread | Manual code trace + Round 8 revert check | pass | see Round 3 below |

## Regression check
Full suite: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .`
Result: **97 tests, OK, skipped=5** (run twice in this session — once before the
Round 8 revert-and-restore sequence, once after — identical result both times).
No pre-existing test changed behavior; no regressions.

## Round 8 — test-genuinely-exercises-the-fix check
Reverted three pieces of the fix one at a time, ran the affected tests, then
restored the tree exactly (`git diff main -- afk_clicker.py` byte-identical
before/after, confirmed via diff, not just `--stat`):

1. Neutered `_maybe_drop_focus`'s body to `pass` (`afk_clicker.py:1330-1336`)
   → `test_click_elsewhere_drops_focus`, `test_a_segmented_control_still_changes_its_variable`,
   `test_a_game_item_still_selects` all failed (focus stayed on the entry).
   Restored, re-ran clean.
2. Removed the `<Return>`/`<Escape>` bindings and `_blur` closure
   (`afk_clicker.py:965-968`) → `test_enter_blurs_without_reverting_the_value`
   and `test_escape_blurs_without_reverting_the_value` failed (exactly those
   two, nothing else). Restored, re-ran clean.
3. Removed `self._ui(self.root.focus_set)` from `start()` (`afk_clicker.py:1477`)
   → `test_starting_from_a_background_thread_drops_focus` failed. Restored,
   re-ran clean.

Verdict: **PASS** — every test that claims to cover a fix genuinely fails
without it.

## Probes run manually (not part of the automated suite)

**Probe 1 — Round 1 concern, "does a click on Record both blur and fire?":**
Script instantiated `AfkAutoclicker`, focused `click_ms.entry`, located the
`Record` `Button` canvas by walking `ui.content`'s widget tree, and clicked
it. Result: `focus_get()` was no longer the entry, and `hotkey_label`'s text
changed to "Press up to 3 keys, then let go…" with `capture_thread.is_alive()
== True` — i.e. `register_hotkey()` (the button's own command) fired
normally. `bind_all` does not swallow or reorder the button's own binding.

**Probe 2 — DPI scale 1.5:** Set `root.tk.call("tk", "scaling", 1.333*1.5)`
before constructing `AfkAutoclicker`, giving `self.s ≈ 1.499`. `minsize()`
came back `(990, 1034)`, matching `int((208+1+452)*1.499)` /
`int(690*1.499)` exactly. `geometry("50x50")` left the window at exactly
`(990, 1034)` — Tk enforced the scaled floor, nothing clipped (`side`
`reqwidth`=311, `content` `reqwidth`=677, summing to within a pixel of
`minw`). Growing to `1400x1200` sent all the extra width to `content`
(678→1088) while `side` stayed at 311. No DPI-scale-specific defect found.

**Probe 3 — bindtag grep:** `grep -n "\.bind(\|bind_all("` lists every
`<Button-1>` binding in the module: `Button._click` (758), `Segmented._click`
(806), `GameItem` (897), `NumBox`'s implicit `Entry` class binding, and the
new `bind_all` (991). No other binding exists that `bind_all`'s `"all"`
bindtag (which fires last, per Tk's widget→class→toplevel→all order) could
plausibly suppress, and no handler returns `"break"` — confirmed empirically
via Probe 1 and the automated Segmented/GameItem tests, not just read from
the Tk docs.

## Defects found
None. Testing pass is clean — proceeding to review.

---

## Round-by-round review

### Round 1 — Ticket fidelity: PASS
Branch `feature/ac-14/number-fields-focus-window-resize` matches
`feature/{ab}-{ticket}/{description}` (`ac` = first letters of "afk" +
"clicker"; `14` matches Gitea `admin/afk-clicker#14` per `docs/spec.md`'s
title line). The diff does exactly what the ticket asks and nothing else:
`NumBox` gets two new key bindings plus exposed `wrap`/`entry`; one
`bind_all` handler; three-line `resizable`/`minsize`/`geometry` swap; one
`_ui()` call in `start()`; one attribute exposure (`self.side`). No
unrelated refactor rides along.

### Round 2 — Correctness: PASS
Traced `_persist()` (1186-1202) and `_sync_settings()` (1361-1382): both read
`field.var.get()` live through `_num()` on every keystroke / every 200 ms,
independent of focus state. The new `<Return>`/`<Escape>` bindings and the
`bind_all` handler only ever call `focus_set()` — they never touch `.var`, so
there is no code path where blurring could race or clobber an in-progress
value. Confirmed with `test_enter_blurs_without_reverting_the_value` /
`test_escape_blurs_without_reverting_the_value`, which set `"321"` and assert
it survives blur unchanged.

`_maybe_drop_focus`'s `isinstance(event.widget, tk.Entry)` check is sound
because `NumBox`'s `Entry` is verified (by grep, reproduced above) as the
only `tk.Entry` in the module — no false negative is possible from a second
`Entry` type existing.

No failing input found: empty field (`_num()`'s existing fallback, unaffected
by this diff), rapid double-click on the same entry, hotkey firing while
nothing is focused (`_maybe_drop_focus`/`start()`'s `focus_set()` is a no-op
if nothing was focused) — all fine.

### Round 3 — Threading and Tk safety: PASS
This is the BLOCKER-level lens per the review protocol, so verified directly
rather than taking the implementation doc's word for it:
- `start()` (`afk_clicker.py:1463-1481`) is reached only through `toggle()`
  (1460-1461), which is the `callback` passed to `HotkeyWatcher(self.hotkey,
  self.toggle)` at `afk_clicker.py:1445`. `HotkeyWatcher._press`/`_release`
  invoke `self.callback()` directly — confirmed by reading the class
  (343-370) — from the `pynput.keyboard.Listener` thread, never the Tk main
  thread. So `start()` genuinely needs the `_ui()` indirection.
- The one new line in `start()`, `self._ui(self.root.focus_set)`
  (`afk_clicker.py:1477`), queues through the exact same `_ui()`/`_drain_ui()`
  mechanism (`1339-1359`) every other cross-thread Tk touch in `start()`/
  `stop()` already uses (`self._ui(self.status.set, ...)` right below it) —
  not a new mechanism, not a direct Tk call from the worker.
- `self.running = True` (line before it) is a plain attribute assignment, not
  a Tk touch, so it doesn't need `_ui()`.
- No new repeating `after()` job was added (the diff adds no `after(...)`
  call), so there's nothing new to cancel in `on_close`.
- No new second-worker risk: `start()`'s existing join-before-arm logic
  (1472-1475) is untouched; the new line sits after it, so it doesn't affect
  the "only one worker at a time" guarantee.
- `_maybe_drop_focus` and the `<Return>`/`<Escape>` bindings only ever run as
  Tk event-dispatch callbacks on the main thread (that's what `bind`/
  `bind_all` guarantee) — they are not reachable from a worker thread at all.

Round 8's revert-and-restore for the `start()` line (above) confirms the test
that exists for this is real, not decorative.

### Round 4 — Naming and shadowing: PASS
`self.side` (`afk_clicker.py:1032`) — grepped for every other `self.side`/
`.side` use in the module; the only other occurrences are `pack(side="left",
...)` string literals, not attribute references, so no collision.
`NumBox.wrap`/`NumBox.entry` — grepped for `.wrap`/`.entry` elsewhere in
`afk_clicker.py`; no prior use of either name on `NumBox` or any other class.
`_maybe_drop_focus` — no existing method of that name. No shadowing of an
import, builtin, or existing class introduced.

### Round 5 — Untrusted input: PASS — no new input surface
Nothing in this diff reads new data from disk, network, or a field at a new
trust boundary. The one behavior this round exists to protect (`_num()`
clamping a `NumBox` at the point of use, not at entry) is explicitly
preserved by design (Decision 2) and confirmed by the Enter/Escape tests.

### Round 6 — Tech stack conformance: PASS
No new dependency. `bind_all`, `resizable`, `minsize`, `geometry`,
`focus_set`, `winfo_toplevel` are all stdlib `tkinter`/Tcl calls already in
use elsewhere in the file. Nothing here touches the PyInstaller build flags,
`--hidden-import` list, or anything resolved at import time.

### Round 7 — Cross-platform behaviour: PASS, with an explicit caveat
`resizable`, `minsize`, `geometry`, `bind_all`, and `focus_set` are
documented as platform-uniform Tk/Tcl calls with no `sys.platform` branch
anywhere in the diff or the surrounding code, matching the spec's own
cross-platform edge case note. **However: this was only run and verified
under Linux/Xvfb in this session.** `bind_all`'s bindtag-ordering behavior
and `focus_set`'s interaction with window-manager focus policy are two of
the more OS-dependent corners of Tk in practice (per-platform focus-follows-
mouse settings on Linux WMs, `NSWindow` focus semantics on macOS, Windows'
own activation rules) — none of that is exercised here. Consistent with
`ROADMAP.md`'s "macOS verification" item (never run by a human), this
finding is **unverified, not "assumed fine,"** on Windows and macOS.

### Round 8 — Tests: PASS
Covered in detail above (revert-and-restore section). Every new/changed
behavior has a test that provably fails without it. Tests assert properties
(`focus_get()` identity, `wrap.cget("bg")`, `resizable()`/`minsize()` tuples,
`winfo_width()` deltas) rather than exact XTEST fire counts, correctly
avoiding the Xvfb double-delivery trap called out in `TECHSTACK.md`. No slow
test added to the PR suite (`WindowResize`/`NumBoxFocus` run in ~1s combined).
`UITestCase.setUp`'s added `focus_force()` (`tests/test_ui.py:34-46`) is a
test-only concession, well-commented with the *why* (Xvfb + no WM never
grants real input focus otherwise), and does not change what the app itself
calls (`focus_set()` only, confirmed by grep — `focus_force` appears exactly
once in the whole diff, in the test file).

### Round 9 — Comments and documentation: PASS
`_maybe_drop_focus`'s comment (`afk_clicker.py:1331-1335`) explains *why*
only non-`Entry` widgets are affected, not what the `isinstance` check does.
The updated comment above `resizable`/`minsize` (`982-986`) explains what
`minsize` is for in addition to the pre-existing explanation of why an
explicit geometry is still needed — kept accurate rather than stale.
`tests/test_ui.py`'s new `focus_force()` comment documents the Xvfb quirk
where the next person will actually look (next to the call itself). No
comment found that merely restates its line. README: no behavior-visible-to-
a-human-reading-the-README changed in a way that would need a README update
(this is an internal UI polish ticket, not a documented CLI/config surface).

### Round 10 — Roadmap and release readiness: PASS
Doesn't touch any `ROADMAP.md` item, doesn't do anything the roadmap
explicitly rules out (no new GUI toolkit, no settings-format change — `Store`/
`on_close` are untouched, confirmed by the diff containing no changes to
either). Versioning: no hardcoded version literal exists in `afk_clicker.py`
to bump; per `docs/CODING-GUIDELINES.md`/`ROADMAP.md`, tagging happens at
release, not per-feature-commit — nothing to flag here.

---

## Spec coverage
Every acceptance criterion in `docs/spec.md` maps to an implemented behavior
and a test case above (table rows 1-9, 11-13, 15), with two exceptions
verified manually instead of by the automated suite (rows 10, 14, 16 — DPI
scale and the plain-`Button` click case) — see Finding 1 below for the one
genuine automation gap. No criterion is unimplemented. No criterion is
completely untested (the two manual-only cases were personally exercised
this session, not left unchecked).

## Findings (most severe first)

### 1. `Button`-canvas click-away is not covered by the automated suite — should-fix
- File: `tests/test_ui.py` (the `NumBoxFocus` class, ~385-487)
- Issue: `docs/spec.md`'s first acceptance criterion explicitly lists "a
  `Button` or `Segmented` canvas" as one of the click targets that must drop
  focus. `NumBoxFocus` automates the `Segmented` and `GameItem` cases
  (`test_a_segmented_control_still_changes_its_variable`,
  `test_a_game_item_still_selects`) and a plain `Label`
  (`test_click_elsewhere_drops_focus`), but no test clicks a `Button` canvas
  (e.g. Record/Apply/"Add current game") and asserts both that focus drops
  *and* that the button's own command still fires.
- Failure scenario this would have caught: if a future change added a
  `Button`-specific `<Button-1>` binding that returned `"break"` (contrary to
  the spec's Decision 1 reasoning), `bind_all`'s `"all"` bindtag would never
  fire for a `Button` click and focus would stick — nothing in the current
  automated suite would catch that regression, only Segmented/GameItem ones.
- I manually verified the actual current behavior is correct (Probe 1 above:
  clicking Record while a field is focused both blurs it and fires
  `register_hotkey()`), so this is not a live bug — it's a coverage gap that
  would let a future regression on `Button` specifically slip through
  unnoticed. Given `Button`, `Segmented`, and `GameItem` all share the same
  code path (`_maybe_drop_focus` doesn't special-case any of them), the risk
  this gap represents is low, but it is the one acceptance-criterion example
  the ticket names explicitly that has zero automated coverage.

### 2. `docs/design.md`'s WCAG contrast-ratio numbers are computed incorrectly — nit
- File: `docs/design.md:96-98`
- Issue: The design doc states ACCENT-on-BG luminance as "0.734 and 0.010 →
  contrast ratio ≈ 73:1" and LINE-on-BG as "0.026 and 0.010 → contrast ratio
  ≈ 2.6:1". Both ratios were computed as a naive luminance division
  (0.734/0.010, 0.026/0.010) instead of the WCAG formula
  `(L_lighter + 0.05) / (L_darker + 0.05)`. Recomputing relative luminance
  directly from the hex values (`#ffc542`, `#262a35`, `#0e0f13`) via the
  standard sRGB→linear→luminance formula gives L_accent ≈ 0.616,
  L_line ≈ 0.023, L_bg ≈ 0.0048 — different from the doc's stated luminance
  values too — and correct WCAG ratios of **≈12.2:1** (ACCENT/BG) and
  **≈1.34:1** (LINE/BG), not 73:1 / 2.6:1.
- This does not change either conclusion the doc draws: ACCENT/BG still
  comfortably clears both the 4.5:1 text threshold and the 3:1 non-text
  threshold (12.2:1 either way), and LINE/BG still fails both (1.34:1 is
  *worse* than the doc's own already-failing 2.6:1, not better) — so the
  substantive design decision (leave LINE alone, pre-existing, out of scope
  per the spec's non-goals) is unaffected. This is a documentation-accuracy
  nit, not a functional or design-conclusion defect, and it concerns
  pre-existing, unchanged visual tokens the ticket explicitly does not ask to
  touch.

## Follow-ups (non-blocking)
- Consider adding a `Button`-canvas case to `NumBoxFocus` (Finding 1) in a
  future small commit — same technique as the existing
  `test_a_segmented_control_still_changes_its_variable`, just walk to a
  `Button` instance instead of a `Segmented` one.
- Cross-platform focus/bindtag behavior (Round 7) remains unverified outside
  Linux/Xvfb, consistent with the project's existing "macOS verification"
  roadmap gap — no action requested by this ticket specifically, flagging for
  awareness only.

## Overall verdict
**Approve with follow-ups.** Testing pass is fully clean (97 tests, OK,
skipped=5; every claimed-fixed behavior verified to actually fail when
reverted, then restored byte-identically). Review pass found zero blockers
and zero must-fix items — both findings above are non-blocking (one test-
coverage gap for a case I personally verified works, one documentation math
correction that doesn't change the underlying conclusion). Every acceptance
criterion in `docs/spec.md` is implemented and either automated or manually
verified this session.

```
VERDICT: MERGE
BLOCKERS: 0
CONCERNS: 2 (both non-blocking: should-fix test-coverage gap, nit doc-math
             correction — see Findings 1-2)
```
