# Spec: UI scale follows the window size (G#38 / GH#67)

## Summary
Add an "Auto" UI-scale option (default) next to the existing fixed 90/100/115/130% steps, that continuously derives `self.s` from how much of the screen the window currently fills, replacing per-pixel-drag rebuilds with a settle-debounced one, without ever fighting `WINDOW_MIN_H` or the icon-rail collapse threshold.

## Goals
- A new `"auto"` value for `ui_scale`, selectable from the same Settings > Appearance > "UI scale" `Segmented` control as the four fixed steps, and made the default for fresh installs (`UI_SCALE_DEFAULT = "auto"`).
- In Auto mode, `self.s` scales continuously (not stepped) with the window's current size, computed relative to the screen so a maximised window looks visually similar on a small laptop screen and a large monitor (Leo's own framing, GH#67 comment).
- A live drag resize in Auto mode must not run a full `_rebuild_ui()` per pixel — rebuilds settle after the drag pauses.
- Reuse `fs(base, s)` (`afk_clicker.py:149-154`, `FONT_SIZE_FLOOR = 6`) unmodified for the continuous `s` values Auto produces.
- Auto's live scale tracking must never fight `WINDOW_MIN_H` (`afk_clicker.py:204`) or `RAIL_COLLAPSE_THRESHOLD` (`afk_clicker.py:252`) mid-drag — precise interaction defined below.

## Non-goals
- G#13's Macros tab, G#12's calibration suite — untouched.
- No settings-schema version bump. `ui_scale` stays an unversioned string key; `"auto"` is just one more valid value in the same sanitisation shape `appearance` already uses.
- No live font/relayout-without-rebuild mechanism. Leo's GH#67 comment floated "settle, or scale fonts without a full rebuild" as alternatives; this spec picks settle-then-rebuild (see "Rejected alternative" below) — a live per-widget font-rescale engine is out of scope.
- No change to the fixed 90/100/115/130% steps' own behavior (`_apply_ui_scale` for those values is untouched) or to non-Auto resize handling (`_on_root_resize`'s rail-collapse-only behavior for fixed steps is unchanged).
- No re-detection of DPI (`_dpi_s`) or screen size mid-session. Both are read once at startup, same policy `_dpi_s` already documents (`afk_clicker.py:2307-2311`) — dragging the window to a different-DPI/different-size monitor mid-session is a known, accepted limitation (see Edge cases), not something this feature solves.

## Background / current state
`UI_SCALE_FACTORS = {"90": 0.9, "100": 1.0, "115": 1.15, "130": 1.3}` (`afk_clicker.py:130`) is a fixed enum; `Store.__init__` sanitises any on-disk value not in this dict back to `UI_SCALE_DEFAULT = "100"` (`afk_clicker.py:1356-1357`). `self.s = self._dpi_s * UI_SCALE_FACTORS[value]` is computed once in `__init__` (`afk_clicker.py:2312`) and recomputed by `_apply_ui_scale(value)` (`afk_clicker.py:3313-3328`) on a `Segmented` pick, which persists the choice, sets `self.s`, calls `_apply_minsize(grow_only=True)`, then `_request_rebuild()` (an `after_idle`-coalesced deferred `_rebuild_ui()`). Every widget's font/padding is baked in at construction time via `fs(base, s)`/`int(x * s)` — there is no live re-scale of an already-built widget, only a full teardown-and-rebuild.

`_on_root_resize` (`afk_clicker.py:2629-2654`) already binds root `<Configure>` (bound only after the first `_build_ui()` returns, `afk_clicker.py:2519-2546`, to avoid the documented WM-driven-reentrancy crash) and today only recomputes a boolean (`self._rail_collapsed = event.width < RAIL_COLLAPSE_THRESHOLD * self.s`), requesting a rebuild only on an actual flip — this is what already keeps a live drag cheap: `self.s` itself never changes from a resize today, only from a `Segmented` pick.

`_apply_minsize(grow_only=True)` (`afk_clicker.py:2577-2614`) recomputes `root.minsize()` from `self.s` on every scale change; `minw` is deliberately derived from `SIDEBAR_RAIL_W` (the collapsed-rail floor), not `SIDEBAR_W`, specifically so the window can always be dragged down far enough to reach `RAIL_COLLAPSE_THRESHOLD` and collapse (`afk_clicker.py:2591-2595`) — this invariant is what this feature leans on to guarantee minsize and the collapse threshold never contradict each other (see "The debounce decision" below).

`docs/history/ac-23-*.md` and the `FONT_SIZE_FLOOR` comment at `afk_clicker.py:141-145` already anticipate this ticket: *"G#38 (UI scale follows window size) will reuse this unmodified for its own continuous-s scaling — keep it a pure function of (base, s), not tied to the four discrete UI_SCALE_FACTORS keys."* `fs()` already is that pure function; no change needed there.

Leo's own words on GH#67 (2026-09-15, verified via `gh issue view 67`): *"Screen-relative reference: scale by how much of the screen the window fills, so a maximised window looks alike on a laptop and a large monitor."* This is the one part of the three headline decisions that needs a concrete formula — worked out below from the existing `_dpi_s`/`UI_SCALE_FACTORS` machinery, not re-litigated.

## Proposed approach

### 1. Store / constants
- `UI_SCALE_DEFAULT = "auto"` (was `"100"`).
- `Store.__init__`'s sanitiser (`afk_clicker.py:1356`) becomes `if self.data["ui_scale"] not in UI_SCALE_FACTORS and self.data["ui_scale"] != "auto":` — same shape as today, one more accepted literal.
- New constants, next to `UI_SCALE_FACTORS`:
  - `AUTO_SCALE_MIN = UI_SCALE_FACTORS["90"]` (`0.9`), `AUTO_SCALE_MAX = UI_SCALE_FACTORS["130"]` (`1.3`) — Auto is clamped to the same range the fixed steps already cover, reusing the existing numbers rather than inventing new bounds. This is also what prevents a shrink/grow feedback runaway (see "The debounce decision").
  - `AUTO_REF_SCREEN_W, AUTO_REF_SCREEN_H = 1920, 1080` — a calibration anchor only, not a hardcoded target screen (see below).
  - `AUTO_REFERENCE_FILL = ((SIDEBAR_W + 1 + CONTENT_W) * WINDOW_MIN_H / (AUTO_REF_SCREEN_W * AUTO_REF_SCREEN_H)) ** 0.5` — derived once at module load from the app's own existing default-geometry constants, the same way `CARD_INNER_W` is already derived from other constants (`afk_clicker.py:231`).
  - `AUTO_SETTLE_MS = 150` — the debounce window (see "The debounce decision"); flagged as an initial value, not empirically tuned (Xvfb can't validate perceived responsiveness — see Acceptance criteria).

### 2. The Auto scale formula
`_auto_scale_factor(self, width, height)`:
```
fill = ((width * height) / (self._screen_w * self._screen_h)) ** 0.5
factor = fill / AUTO_REFERENCE_FILL
return min(AUTO_SCALE_MAX, max(AUTO_SCALE_MIN, factor))
```
`self._screen_w, self._screen_h = root.winfo_screenwidth(), root.winfo_screenheight()`, cached once in `__init__` (same "detected once at startup" policy as `_dpi_s`).

Reasoning, to hand to the developer/reviewer as the concrete resolution of "screen-relative reference" (flagged as an assumption under Open questions, not one of Leo's three already-settled headline decisions):
- "How much of the screen the window fills" is read literally as an **area** fraction (`width*height / screen_w*screen_h`), square-rooted so the result scales roughly linearly with window size the way the existing percentage steps do (doubling both axes — 4x the area — yields 2x the factor, not 4x).
- `AUTO_REFERENCE_FILL` is calibrated so that the app's own existing default launch geometry (`(SIDEBAR_W+1+CONTENT_W) x WINDOW_MIN_H` = `661x620`, unscaled) sitting on a **1920x1080** screen (the most common desktop resolution, used only as the calibration anchor) yields `factor ≈ 1.0` — i.e., on a typical screen, Auto's very first computed value lands at parity with today's "100%" step, so existing muscle memory/screenshots aren't jarringly different on a common setup. On a screen far from that resolution, Auto is expected to compute something visibly different on first launch — that is the feature working as designed (see Acceptance criteria), not a bug.
- Using **area** rather than width alone or height alone means neither axis dominates: this app's window is taller than it is wide relative to a typical wide monitor (width has the rail-collapse concern, height has `WINDOW_MIN_H`), so a pure width-fill or height-fill fraction would either barely change on any real monitor (width) or swing enormously between a short laptop screen and a tall external monitor (height). Area-based fill balances both.

### 3. Wiring self.s to the mode
- `__init__` (`afk_clicker.py:2312`): if `self.store.data["ui_scale"] == "auto"`, bootstrap `self.s = self._dpi_s * 1.0` for the very first `_build_ui()`/`_apply_minsize()` call — there is no mapped window size yet to derive Auto from (same chicken-and-egg the codebase already avoids for `<Configure>` binding, `afk_clicker.py:2519-2546`). The first genuine post-map root `<Configure>` (already the documented trigger point) then recomputes `self.s` for real via `_auto_scale_factor()` against the actual mapped size, through the same settle path new resizes use (§5) — on a screen close to 1920x1080 this is a no-op in practice (factor already ≈ 1.0); on a screen far from it, exactly one settle-triggered rebuild happens shortly after first launch, sizing the UI to the real screen.
- `_apply_ui_scale(value)` (`afk_clicker.py:3313-3328`): guard becomes `if value not in UI_SCALE_FACTORS and value != "auto": value = UI_SCALE_DEFAULT`. Branch on `value == "auto"`: compute `self.s = self._auto_scale_factor(self.root.winfo_width(), self.root.winfo_height())` (window is already mapped — Settings is only reachable post-launch) instead of the `UI_SCALE_FACTORS[value]` lookup. Persist/`_apply_minsize`/`_request_rebuild()` tail is unchanged, matching every other value's existing behavior — picking Auto rescales immediately from the window's current size, it does not wait for a subsequent resize.

### 4. Continuous tracking during a live resize
`_on_root_resize` (`afk_clicker.py:2629-2654`) gains an Auto-mode branch, checked via `self.store.data["ui_scale"] == "auto"` (reuses existing persisted state — no new mode flag):
- **Fixed-step mode: unchanged.** Exactly today's code path (collapsed-flip-only, immediate `_request_rebuild()` via `after_idle`).
- **Auto mode**, on every qualifying event (`event.widget is self.root`, already guarded):
  1. Recompute `self.s = self._auto_scale_factor(event.width, event.height)` — cheap, no widget churn.
  2. Call `self._apply_minsize(grow_only=True)` — also cheap (a WM-level constraint update only; `_apply_minsize`'s own docstring already calls this "safe to change regardless of the window's current actual size").
  3. Recompute `collapsed = event.width < int(RAIL_COLLAPSE_THRESHOLD * self.s)` against the just-updated `self.s` (today's formula, unchanged) and update `self._rail_collapsed` if it flipped.
  4. If either `self.s` actually changed or `self._rail_collapsed` flipped, request the **settled** rebuild (§5) instead of the immediate `after_idle` one fixed-step mode uses.

Steps 1-3 run on literally every `<Configure>` during a drag — this is intentional and is what satisfies "must not fight `WINDOW_MIN_H`/the rail threshold mid-drag": `minsize()` and the collapse comparison always reflect the true live `self.s`, so the floor relaxes/tightens smoothly as the user drags in either direction, with no lag-induced snap. Only step 4 (the actual widget-tree rebuild that repaints fonts/padding/rail state) is deferred — the window frame itself resizes freely under WM control throughout, exactly like a fixed-step `Segmented` pick already behaves today (instant `minsize`/geometry update, deferred visual rebuild).

**Which threshold wins, in what order:** neither needs to — they operate on different axes and `_apply_minsize`'s existing invariant (`minw` derived from the *collapsed*-rail floor, `afk_clicker.py:2591-2595`) guarantees `minw <= RAIL_COLLAPSE_THRESHOLD * s` at every instant, since both are computed from the same just-updated `self.s` in the same event handler. The WM can never grant a width below `minw`, so the rail-collapse comparison only ever sees widths the WM already permitted — collapse is always reachable, never fought. This is the same guarantee that already holds for fixed-step resizes today; continuous `s` doesn't change the invariant, only how often it's recomputed.

### 5. The debounce decision
`after_idle` (the existing `_request_rebuild()`/`_rebuild_after_id` coalescing pattern, `afk_clicker.py:2616-2627`) is **not** reused for the rebuild trigger itself in Auto mode, and this is a deliberate, called-out deviation from that pattern's shape, not a new one invented from scratch: `after_idle` fires the next time Tk's event loop is idle, which — during a live OS-level drag — is typically *between every single native resize callback*, not after the drag as a whole settles. It would coalesce two rapid discrete triggers (e.g. two fast Segmented clicks, which is what it already does), but it would not coalesce a continuous stream of drag-generated `<Configure>` events into one rebuild — that needs a genuine timed debounce.

New mechanism, mirroring the existing single-slot cancel-or-schedule shape (`_rebuild_after_id`, `_pane_fill_after_id`) but with a real timeout instead of `after_idle`:
```
self._auto_settle_after_id = None   # new slot, same __init__/on_close cancellation
                                     # treatment as _rebuild_after_id/_pane_fill_after_id
                                     # (afk_clicker.py:2485/2494, cancelled in on_close
                                     # around afk_clicker.py:4586-4601)

def _request_auto_settle(self):
    if self._auto_settle_after_id is not None:
        self.root.after_cancel(self._auto_settle_after_id)
    self._auto_settle_after_id = self.root.after(AUTO_SETTLE_MS, self._on_auto_settle)

def _on_auto_settle(self):
    self._auto_settle_after_id = None
    self._request_rebuild()   # existing coalesced-rebuild entry point, unchanged
```
Step 4 above calls `_request_auto_settle()` in place of `_request_rebuild()`. `_on_auto_settle` hands off into the *existing* `_request_rebuild()`/`_rebuilding`/`_rebuild_wanted` machinery unchanged, so every existing reentrancy guarantee `_rebuild_ui()`'s own docstring documents still holds — this mechanism only changes *when* a rebuild gets requested, never how the rebuild itself is coalesced or run.

**Rejected alternative** (named explicitly per Leo's own GH#67 comment, which floated it): live per-widget font/padding rescaling without a full `_rebuild_ui()`. Rejected because every widget's font is a plain `("Segoe UI", fs(base, s))` tuple baked in at construction (`afk_clicker.py`, ~33+ call sites per the G#23 precedent) — making that live would mean threading a dynamic scale binding through every widget constructor in the file, a far larger and more invasive change than a 150ms settle delay for what is, in practice, an infrequent interaction (a user actively drag-resizing this settings-heavy utility window).

### 6. Rounding between steps
`fs(base, s) = max(FONT_SIZE_FLOOR, int(base * s))` (`afk_clicker.py:149-154`) already handles the floor and truncates via `int()`. Continuous `s` values Auto produces need **no additional rounding logic**: `fs()` is already a pure function of `(base, s)` for any float `s`, not just the four discrete keys (the `FONT_SIZE_FLOOR` comment at `afk_clicker.py:141-145` says this explicitly, anticipating this exact ticket). Confirmed: nothing else in the file rounds `s` itself before multiplying — every call site is `int(x * s)` or `fs(base, s)`, both already correct for a continuous `s`.

## Affected areas
Single file, single architectural layer (UI/desktop app logic + its own persisted settings) — no schema/API/backend split, so this stays one spec/one build cycle, not a load-balanced decomposition.
- `afk_clicker.py`:
  - `UI_SCALE_DEFAULT`, new `AUTO_SCALE_MIN/MAX`, `AUTO_REF_SCREEN_W/H`, `AUTO_REFERENCE_FILL`, `AUTO_SETTLE_MS` constants (near `UI_SCALE_FACTORS`, `afk_clicker.py:130`).
  - `Store.__init__`'s `ui_scale` sanitiser (`afk_clicker.py:1356-1357`).
  - `AfkAutoclicker.__init__` (`afk_clicker.py:2304-2312` for the bootstrap branch, plus a new `self._screen_w/_screen_h` cache and `self._auto_settle_after_id = None` slot alongside the existing `_rebuild_after_id`/`_pane_fill_after_id` slots at `afk_clicker.py:2485-2494`).
  - New `_auto_scale_factor`, `_request_auto_settle`, `_on_auto_settle` methods (near `_apply_minsize`/`_request_rebuild`, `afk_clicker.py:2577-2627`).
  - `_apply_ui_scale` (`afk_clicker.py:3313-3328`) — `"auto"` branch.
  - `_on_root_resize` (`afk_clicker.py:2629-2654`) — Auto-mode branch.
  - `on_close`'s existing after-id cancellation block (`afk_clicker.py:4586-4601`) — add `_auto_settle_after_id` to the list already cancelled there.
  - The Settings > Appearance > "UI scale" `Segmented(...)` call (`afk_clicker.py:3143-3145`) — add `("auto", "Auto")` to the options list; **exact widths and label wording are ux-designer's call**, not decided here (see design note below).
- `tests/test_ui.py` — five existing tests hard-code `"100"` as the default/fallback and must be updated to expect `"auto"` (found via archaeology, not guessed): `UIScaleStore.test_a_fresh_store_defaults_to_100` (`tests/test_ui.py:3395`), `test_garbage_values_fall_back_to_100` (`:3405`), `test_a_missing_ui_scale_key_defaults_to_100` (`:3411`), `test_a_garbage_on_disk_value_resolves_to_100_end_to_end` (`:3415`, also asserts `ui.s == ui._dpi_s` which no longer holds for the new default — needs its own Auto-aware assertion or an explicit non-"auto" garbage value in that test's fixture instead). `UIScale.test_each_step_multiplies_the_dpi_factor` (`:3654`) iterates the four fixed values only — unaffected, but a parallel `Auto` test class is expected alongside it (see Acceptance criteria).
- No `docs/ROADMAP.md` items reference this feature; nothing there to reconcile.

**Note for the ux-designer**: the `Segmented` control (`afk_clicker.py:1683-1719`) divides its fixed pixel `width` evenly across however many options it's given — there is no per-option minimum. Today's 4-option "UI scale" row uses `width=220` (55px/option) and fits inside `CARD_INNER_W` (396px) alongside the Row's fixed 152px label column (`140` `ROW_LABEL_W` + `12` `ROW_LABEL_GAP`, `afk_clicker.py:235-238`) with room to spare (152+220=372 <= 396). Adding a 5th ("Auto") option at the same 55px/option would total 152+275=427, overflowing `CARD_INNER_W` by 31px. The available width for a 5-option control before overflowing is 396-152=244px (~49px/option average) — a real layout decision (narrower per-option width, a shorter fixed-step label style, wrapping to two rows, or something else) is deliberately left to `docs/design.md`, not decided here.

## Edge cases
- **First launch in Auto mode on a screen far from 1920x1080**: expected to size the window differently than the current familiar 661x620 default shortly after the first real `<Configure>` lands (§3) — one settle-triggered rebuild, not a bug, not a flicker loop.
- **Multi-monitor drag mid-session**: `_screen_w/_screen_h` and `_dpi_s` are both detected once at startup and never re-read — dragging the window to a monitor with a different resolution or DPI won't re-anchor Auto's reference until restart. Named as an accepted limitation (Non-goals), matching the existing `_dpi_s` "detected once" policy.
- **Continuous shrink drag below the pre-drag floor**: because `self.s`/`minsize()` are recomputed live on every event (§4, not just at settle), a single continuous shrink drag can reach all the way down to Auto's true live floor without needing a second drag — this was a real risk with a naive "only touch `self.s` at settle" design (rejected) and is called out here so the reviewer can verify it explicitly (see Acceptance criteria).
- **Switching from a fixed step to Auto**: `_apply_ui_scale("auto")` computes `self.s` from the window's *current* size immediately (§3) — it does not wait for the next resize, and does not silently keep the old fixed-step `self.s`.
- **Switching from Auto to a fixed step mid-drag**: any pending `_auto_settle_after_id` job becomes moot once `self.store.data["ui_scale"]` is no longer `"auto"` — `_on_root_resize`'s branch check reads live state on every event, so the very next `<Configure>` (if any) takes the fixed-step path; a settle job already in flight still only ever calls `_request_rebuild()`, which is safe/idempotent regardless of which mode is active by the time it fires.
- **Garbage/missing on-disk `ui_scale`**: still sanitises to `UI_SCALE_DEFAULT`, now `"auto"`, via the same `Store.__init__` shape `appearance` already uses — see the five test updates listed under Affected areas.
- **Platform differences**: the Auto formula itself (`winfo_screenwidth/height`, `winfo_width/height`) is plain Tk, identical across Windows/macOS/Linux. The *testability* differs (see Acceptance criteria) — a real WM (macOS WindowServer, Windows) sends a post-map root `<Configure>` that Xvfb never generates (`backlog.md`'s "Xvfb has no window manager" lesson), which affects verifying the first-launch-on-an-unusual-screen bootstrap path specifically, not the general resize/debounce/collapse mechanics.

## Acceptance criteria
- [ ] Given a fresh `Store` with no `settings.json`, when read, then `data["ui_scale"] == "auto"`.
- [ ] Given an on-disk `ui_scale` of `"auto"`, `"90"`, `"100"`, `"115"`, or `"130"`, when a `Store` loads it, then the value round-trips unchanged (existing `test_known_values_round_trip` pattern, extended to include `"auto"`).
- [ ] Given an on-disk `ui_scale` of a garbage value (wrong type, unknown string, `None`), when a `Store` loads it, then it resolves to `"auto"`.
- [ ] Given the Settings > Appearance pane is open, then the "UI scale" `Segmented` control shows 5 options including "Auto", and "Auto" is selected by default on a fresh install.
- [ ] Given `ui_scale == "auto"` and the window at its default launch geometry on a screen at or near 1920x1080, when the app starts, then `self.s` is within a small tolerance of `self._dpi_s * 1.0` (parity with today's "100%" default, per the calibration in Proposed approach §2).
- [ ] Given Auto mode, when `self.root.geometry(...)` is set to a series of increasing sizes followed by `self.root.update()` between each (mirroring `WindowResize`'s existing pattern, `tests/test_ui.py:1036-1088`), then `self.ui.s` strictly increases and stays within `[AUTO_SCALE_MIN, AUTO_SCALE_MAX]` at every step.
- [ ] Given Auto mode and a window shrunk in a single continuous sequence of `geometry()` calls without an intervening settle/rebuild, then `root.minsize()` tracks the live (not stale) `self.s` at every intermediate call — i.e., the floor visibly relaxes as the sequence proceeds, not just at the final settled state (directly verifies the "must not fight `WINDOW_MIN_H`" requirement, and the shrink-spiral edge case above).
- [ ] Given a burst of `<Configure>` events fired within `AUTO_SETTLE_MS` of each other (simulating a fast drag), then `_rebuild_ui()` (or an equivalent instrumented counter) runs at most once for the whole burst, only after the last event plus `AUTO_SETTLE_MS` have elapsed — the debounce, not just the coalescing, is under test (distinguish from the existing `test_a_resize_that_never_crosses_the_threshold_triggers_no_rebuild`, `tests/test_ui.py:1332`, which tests a different thing).
- [ ] Given Auto mode, when the window width crosses `RAIL_COLLAPSE_THRESHOLD * self.s` (recomputed live) during a resize sequence, then `self._rail_collapsed` flips at the correct point and the eventual settled rebuild reflects it — mirroring `WindowResize.test_shrinking_past_the_threshold_collapses_the_rail`/`test_growing_back_past_the_threshold_re_expands_the_rail` (`tests/test_ui.py:1059-1081`) but under Auto's continuously-changing `self.s` rather than a fixed one.
- [ ] Given a fixed-step selection (90/100/115/130%), then all existing `UIScale` class behavior (`tests/test_ui.py:3644-3780`) is unchanged — no regression to non-Auto scaling.
- [ ] Given continuous `s` values between the tested fixed steps, then every rendered font size still respects `FONT_SIZE_FLOOR` (existing `fs()` behavior, no new logic — a direct/property-style test with a range of `s` values suffices, no UI needed).
- [ ] All of the above (except the "screen at or near 1920x1080" and any genuinely WM-mapping-dependent bootstrap case) must be exercisable and verified on Linux/Xvfb CI via explicit `root.geometry()` + `root.update()` calls, the same technique the existing `WindowResize`/`UIScale` test classes already use successfully under Xvfb (`tests/test_ui.py:1036-1088`, `:3644-3780`) — Xvfb's lack of a window manager only blocks verifying a **genuine WM-generated post-map** `<Configure>` (the first-launch-on-an-unusual-real-screen bootstrap path, §3), not the general resize/debounce/rail-collapse mechanics, which don't depend on a WM at all. Only the former needs the macOS/Windows CI legs to be trustworthy; say so explicitly in the PR/test-review notes rather than claiming full coverage from a green Linux run alone.

## Open questions
- **Assumption, not a blocker**: the exact "screen-relative" formula (area-based fill fraction, `sqrt(w*h / screen_w*screen_h)`, calibrated against a 1920x1080 reference so Auto ≈ today's 100% on a common screen) is this spec's own concrete resolution of Leo's directional decision ("scale by how much of the screen the window fills") — the *direction* was already settled on GH#67, the *formula* was not spelled out there. Proceeding under this definition; flag during design/dev/review if it should instead be width-only, height-only, or anchored to a different reference resolution.
- **Assumption, not a blocker**: `AUTO_SETTLE_MS = 150` is a reasonable starting debounce value, not empirically tuned — Xvfb can't validate perceived drag responsiveness (only correctness of the debounce mechanism itself, see Acceptance criteria). If it feels laggy or twitchy on a real OS during manual testing, adjusting the constant is a one-line change, not a design change.
- **Real UI decision, explicitly deferred to ux-designer**: exact layout of the 5-option "UI scale" `Segmented` control (per-option width, whether "Auto"/"90%" etc. need shorter labels, or a different control shape) given the `CARD_INNER_W` overflow math in Affected areas. Not resolved here on purpose — this is `docs/design.md`'s job, not `docs/spec.md`'s.

## Risk / rollback notes
- Changing `UI_SCALE_DEFAULT` from `"100"` to `"auto"` changes the out-of-the-box sizing for every fresh install — a real behavior change, not just additive, and the reason the five existing default/fallback tests must be updated rather than left to silently start failing. Existing installs are unaffected (an already-written `ui_scale` value round-trips unchanged, same as today; users who already picked a fixed step keep it).
- All new logic is additive/branch-gated on `ui_scale == "auto"` — every fixed-step code path (`_apply_ui_scale`, `_on_root_resize`, `_apply_minsize`) keeps its existing behavior byte-for-byte when Auto isn't selected, so a revert of just the Auto branches (leaving `UI_SCALE_DEFAULT` at `"100"`) is a clean, low-risk rollback if Auto turns out to need more iteration than expected.
- If the `AUTO_SETTLE_MS` debounce mechanism ever needs to be reverted independently (e.g. found to fight some other coalesced rebuild source), `_request_auto_settle`/`_on_auto_settle` are isolated new methods that only ever get called from `_on_root_resize`'s new Auto branch — deleting the branch alone (falling back to `_request_rebuild()` directly, i.e. per-flip-only like fixed-step mode) fully reverts to a "no continuous tracking, manual Auto re-pick only" degraded-but-functional mode without touching any other mechanism.
