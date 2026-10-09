# Spec: Reuse the Xlib connection in detect_running() (G#62)

## Summary
Replace `_window_titles()`'s X11 branch's current open-a-fresh-`Xlib.display.Display()`-and-close-it-every-call pattern with one shared, lazily-(re)connected module-level connection, so the every-5-seconds detection poll stops paying a full X11 handshake (and occasionally stalling inside it) on every single scan.

## Goals
- Cut the per-scan cost of `_window_titles()`'s X11 branch from "open a new Xlib connection, walk, close" to "reuse an already-open connection, walk" on the common path.
- Reduce how often the app hits the already-documented rare stall inside `Xlib.display.Display()` (observed ~1 scan in a couple hundred) by making connection-opening a rare event instead of a per-scan one.
- Recover automatically if the shared connection dies or errors (X server restart, dropped socket, any transient Xlib exception) — detection must not be permanently broken for the rest of the app's lifetime.
- Preserve every existing concurrency guarantee this call path already depends on (see Background): two `scan()` threads legitimately alive at once, no join-on-supersede, G#39's sequence-numbered stale-result dropping.

## Non-goals
- No event-driven/WM-notification rearchitecture (explicitly rejected already — depends on window-manager cooperation Xvfb doesn't provide, so would be untestable in this project's CI and possibly WM-dependent on a real desktop).
- No change to the win32 (`ctypes`/`EnumWindows`) or darwin (`osascript`) branches of `_window_titles()`. X11-only.
- No change to `detect_running()`'s or `foreground_title()`'s signatures, return values, or their existing broad `try/except Exception` fallback behaviour (set()/None on failure) — reconnect logic is added *inside* `_window_titles()`'s X11 branch, under that same existing safety net, not duplicated at every caller.
- No proactive staleness detection (e.g. periodic forced reconnect, or treating an all-empty result as a signal the connection might be bad). The only documented failure mode is "`Display()` stalls/raises on open" and "an already-open connection raises on use" — both are handled. A connection that stays technically open but silently returns garbage with no exception is not an observed failure mode for this ticket and is explicitly out of scope; flagged under Open questions, not built for.
- No change to `_poll_games()`'s own no-join-on-supersede design, its sequence-number/`_apply_scan()` staleness guard, or `on_close()`'s existing join/cleanup ordering beyond the one new line this ticket adds.

## Background / current state
- `_window_titles()` (`afk_clicker.py:2004-2059`) has three platform branches; only the X11 one (`afk_clicker.py:2039-2058`) is in scope. Today it does, every single call: `disp = xdisplay.Display()` → recursive `walk()` (depth-limited to 4, `get_wm_name()`/`query_tree()` per node, each node's own `try/except Exception: pass`) → `disp.close()`.
- Two callers: `detect_running(profiles)` (`afk_clicker.py:2062-2069`, used by `_poll_games()`'s `scan()` closure, `afk_clicker.py:5209-5218`) and `foreground_title()` (`afk_clicker.py:2072-2079`, used by `MainWindow.add_current_game()`'s own one-shot thread, `afk_clicker.py:4532-4536`). Both already wrap their call to `_window_titles()` in a broad `try/except Exception` and degrade gracefully (`set()` / `None`) — this existing safety net is reused, not duplicated.
- `_poll_games()` (`afk_clicker.py:5172-5230`) reschedules itself every 5000ms and also runs once from `_build_ui()`'s tail, and **overwrites `self._poll_thread` on every call with no join of whatever scan it just superseded** — a deliberate choice (G#39/GH#69, PR #70 review) because connection setup can stall unboundedly (observed directly, ~1 scan in a couple hundred), and blocking a new scan on an old one finishing would let one stuck connection freeze detection entirely. **Consequence: two `scan()` threads can legitimately be alive and calling into `_window_titles()` concurrently today.** Xlib `Display` objects are not safe for concurrent use from multiple threads, so any shared connection needs its own serialization — and critically, that serialization must not reintroduce the exact freeze this design went out of its way to avoid.
- G#39's own sequence-number guard (`self._poll_seq`/`self._poll_applied_seq`, compared in `_apply_scan()`, `afk_clicker.py:5232+`) already handles a *slow* scan landing after a faster, newer one. It is orthogonal to this change (operates on results handed back to the main thread) and must keep working unmodified.
- `on_close()` (`afk_clicker.py:6148+`) already has precedent for dropping a long-lived Xlib-backed resource on teardown: `self.mouse`/`self.keyboard` (pynput `Controller`s) are set to `None` near the end (G#53/GH#95) specifically so their `__del__` closes the underlying connection immediately, called out there because the test suite shares one process across ~150+ UI-building test classes and Xvfb's max-clients ceiling is already marginal.
- No `threading.Lock` exists anywhere in this file today; `threading.Event`/`threading.Thread`/`weakref.ref` are the only primitives currently used for cross-thread coordination. A new `Lock` is a minimal, stdlib, directly-motivated addition — not a deviation worth more than this one-line note.

## Proposed approach

Add two **module-level** names next to `_window_titles()` (not instance-level on `AfkAutoclicker`): a connection slot and a lock.

```python
_x11_display = None
_x11_display_lock = threading.Lock()
```

**Why module-level, not instance-level:** `_window_titles()`, `detect_running()`, and `foreground_title()` are free functions today, called from several places (two different thread-spawning call sites, plus directly in tests) with no `self`/instance threaded through any of them. Making the connection instance-level would mean plumbing an `AfkAutoclicker` reference into all three functions' signatures — a much bigger diff for no behavioural benefit, since this app only ever runs one window/one detection path per process. Module-level matches the functions' existing free-function shape exactly.

**X11 branch of `_window_titles()`, new shape:**

1. Take a local reference to the module-level connection (`disp = _x11_display`, read without the lock — see "why not lock the open" below).
2. If `disp is None`, open a new one: `disp = xdisplay.Display()`. This call happens **outside** `_x11_display_lock`. Then, briefly under the lock, install it into `_x11_display` if nothing else beat us to it (double-checked: if `_x11_display` is still `None`, set it to `disp`; otherwise another thread already installed a different connection first — close the one we just opened and use the winner instead, i.e. `disp = _x11_display`).
3. Under `_x11_display_lock`, run the existing `walk(disp.screen().root)` against this connection and collect `titles`.
4. If step 3 raises: the shared connection is bad. Under the lock, if `_x11_display is disp`, set `_x11_display = None` (so the *next* call reconnects) and best-effort `disp.close()` (swallow any exception from close itself). Then fall back, for *this* call only, to today's original behaviour: open one brand-new throwaway connection, walk it, close it, return its titles — this is exactly the pre-change code path, so a single bad shared connection degrades to "one extra open/close for this one scan," never to a dead detection path. Re-raising rather than falling back was considered and rejected: the existing `detect_running`/`foreground_title` callers already swallow any exception from `_window_titles()` into `set()`/`None`, so letting a transient reconnect failure propagate would silently skip a whole scan cycle instead of still trying once more right now.
5. Return `titles`.

**Why the open in step 2 happens outside the lock:** this is the crux constraint. The one documented failure mode is `Display()` itself stalling unboundedly (~1 in a couple hundred historically). If connection-opening happened *under* `_x11_display_lock`, a stall there would block every other thread waiting on that same lock — i.e. the one `_poll_games()` scan that happens to hit the stall would now also freeze the *other* concurrently-running scan (and any concurrent `foreground_title()` call), which is strictly worse than today (today each stuck scan only ever blocks itself) and would violate the no-single-stuck-call-freezes-everything guarantee G#39 was built around. Opening outside the lock means a stall only ever blocks the one thread that triggered it; the lock is only ever held for the two genuinely fast, bounded operations — installing a just-opened connection, and walking an already-open one.

**Thread-safety model chosen: one global lock around connection install + connection use, not one connection per thread.** A connection-per-thread model was considered and rejected: it would mean a long-lived connection per `scan()`-spawning thread identity, which doesn't actually exist as a stable identity here (`_poll_games()` spawns a *new* `threading.Thread` every 5 seconds, not a persistent worker thread), so "per thread" would degenerate right back into "per call" — defeating the whole point of this ticket. A single shared connection with a lock serializing actual *use* is simpler and correct: in the normal case the tree walk itself is fast (bounded by window count and the existing depth-4 limit), so lock contention between two legitimately-concurrent scans is brief, not a new stall source — only connection *opening*, the one call known to stall unboundedly, is kept outside the lock.

**`foreground_title()`:** shares the exact same persistent connection, via the same unmodified `_window_titles()` call site — no special-casing. It's a one-shot, user-triggered, infrequent call (the "Add current game" button), not latency-sensitive, so reuse costs it nothing, and it benefits the same way from not paying a fresh handshake (and its stall risk) on every click.

**`on_close()`:** add one guarded block, same spirit and same place as the existing `self.mouse = None` / `self.keyboard = None` (G#53/GH#95), right after that pair:

```python
global _x11_display
if _x11_display is not None:
    try:
        _x11_display.close()
    except Exception:
        pass
    _x11_display = None
```

Only for `sys.platform` outside win32/darwin (the module-level name is simply never set on those platforms, so a `None` check alone is already correct — no platform branch needed in `on_close()` itself). This is *not* a strict requirement for correctness (the connection is module-level, not instance-owned, and would otherwise just get reused by the next `AfkAutoclicker` instance in the same process — exactly how the ~150+-test-classes-per-process suite runs today), but it mirrors the existing mouse/keyboard precedent's reasoning: an explicit, immediate close on teardown is cheap insurance against Xvfb's already-marginal max-clients ceiling (G#53) in the test suite, same justification as the precedent it mirrors. One potential test-suite wrinkle this introduces, deliberately accepted: successive `AfkAutoclicker` instances *within one test run* will each force a fresh reconnect on their first scan after a previous instance's `on_close()`, instead of reusing a connection that outlived the instance that opened it — strictly fewer total connections than today's per-scan-per-instance churn either way, so not a regression.

## Affected areas
- `afk_clicker.py` only (X11 branch of `_window_titles()`, plus `on_close()`). Single file, single architectural layer (one function's internals + one teardown hook) — no split needed.
- No UI, no schema, no new dependency (`python-xlib` is already a transitive pynput dependency and already imported at the point of use).
- No ux-designer needed — backend-only, no user-visible surface changes.

## Edge cases
- **First call ever (cold start):** `_x11_display is None` → opens fresh, same as today's behaviour for every call. No regression; this is simply call #1 of what used to be every call.
- **Two concurrent `scan()` threads, both finding `_x11_display is None`** (e.g. right after an `on_close()`/reconnect reset): both open their own `Display()` outside the lock; the second one to reach the lock closes its redundant connection and uses the winner's. Never more than one connection stays installed.
- **Shared connection dies mid-use** (X server restart, socket reset): caught by step 4's `except`, discarded, this call falls back to a one-shot connection (today's exact behaviour), next call reconnects the shared one fresh.
- **`Display()` stalls unboundedly on open** (the known, already-observed failure mode): only the one thread that triggered the open is blocked, exactly like today, for exactly as long as today — the difference is this now happens far less often (once per reconnect, not once per 5-second scan).
- **`on_close()` races a scan still using the shared connection:** unaffected by this change — `on_close()` already joins `self._poll_thread` with a 2-second bound *before* reaching the mouse/keyboard/connection cleanup lines, same ordering this new block slots into. A scan still past that join window and still inside `walk()` when `_x11_display.close()` runs could see a (swallowed, per-node) exception from the now-closed connection — no worse than the connection dying for any other reason, handled by the exact same per-node `try/except` and step-4 fallback already in place.
- **Platform split:** `_x11_display`/`_x11_display_lock` are simply never touched on win32/darwin; `on_close()`'s check is a plain `is not None` guard, so it's a no-op there with no explicit `sys.platform` branch required.

## Acceptance criteria
- [ ] Given the X11 branch is called twice in a row with no error in between, then the second call reuses the same `Display` object as the first (no second `xdisplay.Display()` construction) — verified by mocking `Xlib.display.Display`/the module's `xdisplay.Display` and asserting call count == 1 across two `_window_titles()` calls.
- [ ] Given the shared connection raises on use (mocked), when `_window_titles()` is called, then it still returns a usable title list (falls back to a fresh one-shot connection for that call) and does not raise out of `_window_titles()`.
- [ ] Given the shared connection raised once and was discarded, when `_window_titles()` is called again, then it reconnects (opens exactly one new `Display`) rather than staying permanently broken.
- [ ] Given two `scan()`-style calls are in flight concurrently (mirroring the existing `PollGamesScanDoesNotHoldSelfWhileBlocked`/G#39 overlapping-scan test style), when one is mocked to block inside the connection-open step, then the other does not block on it — i.e. opening a connection never holds `_x11_display_lock` across the blocking part, verified the same way the existing overlap tests verify non-blocking behaviour (a blocking fake released explicitly by the test, with a bounded `Event.wait`, never a bare `sleep`).
- [ ] `_poll_games()`'s existing sequence-number/stale-result-dropping behaviour (`self._poll_seq`/`_apply_scan()`) is unaffected — existing tests covering that (e.g. around `afk_clicker.py:7128`'s overlapping-scan test class) still pass unmodified.
- [ ] `foreground_title()` still returns the correct frontmost-window title under normal operation (existing behaviour/tests unchanged) and goes through the same shared-connection path as `detect_running()`.
- [ ] `on_close()` clears the shared module-level connection (mock `_x11_display`, call `on_close()`, assert `.close()` was called and the module-level reference is `None` afterward) without raising even if `.close()` itself raises.
- [ ] win32 and darwin branches of `_window_titles()` are byte-for-byte unchanged (diff review, not a runtime-checkable assertion on this Linux CI).
- [ ] No new test in this change uses a bare `time.sleep()` as its only synchronization for a race-sensitive assertion — matches this project's existing `threading.Event`-based pattern (see `PollGamesScanDoesNotHoldSelfWhileBlocked`, `afk_clicker.py`/`tests/test_ui.py:695-759`) — and each new race-sensitive test is sabotage-verified (temporarily revert the fix under test, confirm the new test goes red, then restore) per this project's standing rule (`backlog.md`'s "flake fix tends to work by blinding the test" lesson).

## Open questions
- None blocking. One deliberate non-goal restated for visibility: a shared connection that stays open but silently returns bad/garbage data on every per-node call (without ever raising) would currently be indistinguishable from "genuinely no windows have titles right now," and nothing in this spec adds detection for that shape of failure, because it has never been observed (the one documented failure mode is stall-or-raise, both handled). If this ever turns out to be a real occurrence, treat it as a new ticket with its own evidence, not something to speculatively guard against here.

## Risk / rollback notes
- Worst case if the lock/reconnect logic has a bug: detection silently stops working (same user-visible symptom as today's pre-existing "detect_running returns empty on error" fallback), not a crash and not a hang — every new code path funnels through the same existing broad `except Exception` at the `detect_running()`/`foreground_title()` call sites.
- Rollback is a single-file revert of `afk_clicker.py`'s X11 branch and the `on_close()` addition; no data migration, no schema, no stored state involved.
- Biggest real risk is reintroducing a lock-ordering mistake that lets connection-*opening* block under `_x11_display_lock` (see "why the open happens outside the lock" above) — the acceptance criteria's concurrent-scan test exists specifically to catch that regression mechanically, not just by code review.
