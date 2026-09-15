# Spec: Review residue from the updater PRs (#19, #31) — G#21/GH#32

## Summary
Four small, independent items left open across the PR #19 (checksum/staging safety) and PR #31 (update-check/offer flow) review rounds, none reachable as a user-facing bug today: `fetch_checksums` accepts any 64-character token as a digest without checking it is hex; `_safe_names`'s docstring overstates zipfile's own risk (verified false for Python 3.6.2+, true for tarfile) and needs to say which half of the check actually closes a real hole; a superseded update-check worker could in principle write `self._pending` after a newer check has already cleared it, with no test driving that ordering; and `Store.save()` swallows every `OSError`, so a read-only config directory lets the Theme/UI-scale shown in Settings silently diverge from what's on disk, invisible before the Settings page existed and visible now.

## Goals
- `afk_clicker.py:796` `fetch_checksums` — reject a 64-character token that is not actually hex, so a garbage digest can never masquerade as a real one (it already can only fail to match, never match falsely, per the ticket — this closes the one-line gap anyway).
- `afk_clicker.py:813-826` `_safe_names`'s docstring, plus the matching stale comment at `tests/test_updater.py:287` — state plainly that zipfile's own `extractall`/per-member extraction already strips `..`, drive letters, and absolute-path components (true since Python 3.6.2, verified against both the sandbox's installed 3.11.2 and this project's CI/release-pinned 3.12), so the zip-side check here is defense-in-depth, not the thing that closes a real hole — that's tarfile's job, per `_safe_tar_members`'s own docstring (verified symlink escape).
- `afk_clicker.py:3402-3436` `check_update`/`_check_worker` — close the latent (currently UI-unreachable, but real) race where an older worker's result can land after a newer check has already cleared `self._pending`, using the same sequence-stamp-and-drop-stale-results idiom this file already established for `_poll_games`/`_apply_scan` (G#39/PR #70). This also moves the write of `self._pending` onto the main thread, closing a second, narrower gap noted below.
- `afk_clicker.py:1322-1330` `Store.save()` — return whether the write actually landed, and surface a single, non-blocking, non-repeating notice in the Settings → Appearance pane when it doesn't, per `docs/CODING-GUIDELINES.md`'s "Failure behaviour" ("A read-only install directory gets named as such rather than producing a silent no-op").

## Non-goals
- G#22 (Minecraft interval warning), G#23 (macOS font floor), G#40 (macOS sidebar flake) — separate, already-tracked tickets, untouched here.
- Any redesign of the updater's check/offer/install flow, or of `Store`'s load/migration logic. This cycle only tightens one parsing guard, corrects two comments, adds one ordering guard following an existing idiom, and adds one failure-reporting path — no new update-check trigger, no settings schema change.
- A generic toast/notification system. The new save-failure notice is scoped to the Appearance pane only (see Proposed approach, item 4) — it does not add a sidebar-wide indicator or touch `SettingsItem`/`settings_item.set_state`, which stays reserved for the update-offer marker it already has.
- Making `_safe_names`/`_safe_tar_members` do anything different at runtime. Item 2 is a docstring/comment-only correction; the actual guard behavior (reject on escape, for both zip and tar) is unchanged.
- Retrying a failed save automatically, or blocking any UI action on a save failure. The existing "corrupt/unwritable config never blocks startup or interaction" contract (`docs/CODING-GUIDELINES.md`) is preserved — this cycle only makes the already-silent failure visible, once.

## Background / current state

### Item 1 — `afk_clicker.py:781-798`, `fetch_checksums`, verified as given
```python
def fetch_checksums(asset, timeout=30):
    ...
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            sums[parts[1].lstrip("*").strip()] = parts[0].lower()
    return sums
```
`len(parts[0]) == 64` checks length only. A 64-character token that is not hex (e.g. a corrupted download, or a line some other tool wrote into a same-named file) is accepted as if it were a real digest. Per the ticket, this can only ever fail to match `file_digest()`'s real hexdigest later (`download_and_stage`'s `actual != expected` check, `afk_clicker.py:897`) — never match falsely — so this is not a live vulnerability, but the check is one line and the function's own job (per `docs/CODING-GUIDELINES.md`'s "Input validation": "Parsing stored structures validates instead of wrapping the parse in try/except... check the shape and the types, then decide") is exactly this kind of validation.

### Item 2 — `afk_clicker.py:813-826`, `_safe_names`, verified against this project's Python version
```python
def _safe_names(names, destination):
    """
    Reject any archive entry that would land outside the destination.

    zipfile and tarfile both happily write "../../.bashrc": the name is used as
    given. Publishing digests and then unpacking unsafely would leave open the
    hole the digests were meant to close.
    """
```
CI and release both pin Python 3.12 (`.github/workflows/ci.yml:46`, `release.yml:71,122`); this sandbox's own interpreter is 3.11.2. Read directly from the installed `zipfile` module (`inspect.getsource(zipfile.ZipFile._extract_member)`, both versions ship the same logic): every extraction interprets an absolute path as relative, strips the drive/UNC component, and removes `.`/`..` path segments *before* joining onto the destination —
```python
arcname = os.path.splitdrive(arcname)[1]
invalid_path_parts = ('', os.path.curdir, os.path.pardir)
arcname = os.path.sep.join(x for x in arcname.split(os.path.sep)
                           if x not in invalid_path_parts)
```
This has been zipfile's behavior since Python 3.6.2 (the ticket's own claim, confirmed by reading the shipped source rather than trusting memory) — a `"../../.bashrc"` entry cannot escape via `zipfile.ZipFile.extractall`/`extract` regardless of whether `_safe_names` runs first. `download_and_stage` (`afk_clicker.py:903-906`) confirms the zip branch calls `_safe_names(zf.namelist(), staged)` then `zf.extractall(staged)` — plain `extractall`, no per-member re-implementation, so it gets zipfile's own sanitization for free.

Tarfile is the opposite story, and `_safe_tar_members`'s own docstring (`afk_clicker.py:828-836`) already says so accurately: `extractall(filter="data")` (the safe default) only exists from Python 3.12 and is only the *default* from 3.14; on 3.11 (a real, currently-supported interpreter per this repo's own reasoning, even though CI itself pins 3.12) the argument doesn't exist, and a bare `extractall()` "silently restores every hole" — verified in that same docstring by writing a real symlink to `/etc/passwd` to disk. `download_and_stage`'s tar branch (`afk_clicker.py:907-916`) does its own per-member extraction with an explicit `filter="data"`/`TypeError` fallback specifically because of this gap.

So `_safe_names`'s docstring, shared by both branches, currently claims a risk for zipfile that has not been true for eight years, while correctly (if implicitly, via its caller) protecting tar where the risk is real. This is exactly the ticket's ask: not a behavior change, a docstring that names which half of the check is defense-in-depth and which half closes an actual hole.

`tests/test_updater.py:287`'s comment on `test_an_entry_escaping_the_directory_is_refused` — `# zipfile writes the member name as given; "../.." lands outside.` — repeats the identical, now-corrected misconception in test code. A `grep` across `afk_clicker.py` and `tests/*.py` for this phrasing (`"zipfile writes"`, `"zipfile and tarfile"`, `"lands outside"`, `"as given"`) finds only these two occurrences — nothing else needs the same correction.

### Item 3 — `afk_clicker.py:3402-3436`, `check_update`/`_check_worker`, verified against current `main`
```python
def check_update(self):
    self._pending = None                                    # main thread
    self.settings_item.set_state(has_update=False)
    if self._settings_open:
        self.update_button.command = self.check_update
    self._set_update_state("Checking…", enabled=False)
    threading.Thread(target=self._check_worker, daemon=True).start()

def _check_worker(self):
    ...
    self._pending = (tag, asset, release)                   # worker thread
    self._ui(self._offer_update, tag)
```
`check_update()` is reachable from exactly one production call site (`self.update_button = Button(up, "Check for updates", self.check_update, s, ...)`, `afk_clicker.py:3058`), and `_set_update_state("Checking…", enabled=False)` disables that button *before* the worker thread is even started — so, as the ticket itself notes, no click reaches this while a check is already running. `check_update()` is never called anywhere else in the production code (a `grep` for `check_update(` confirms only the button wiring and this method's own reassignment of `update_button.command` back to itself).

The latent bug the ticket describes needs two direct, overlapping calls to `check_update()` — reachable today only by a caller that bypasses the button (a test, or a future second call site such as an autocheck-on-startup feature). If that happens: call A clears `_pending`/starts worker A; call B (started before A's worker finishes) again clears `_pending`/starts worker B; if worker A is slower and lands after worker B, worker A's `self._pending = (tagA, ...)` (line 3436) overwrites worker B's already-correct, already-applied state with a stale offer, and `self._ui(self._offer_update, tagA)` repaints the button/sidebar with the older release. This is the identical failure shape this same file already treated as a genuine, worth-fixing product race for `_poll_games`/`_apply_scan` (`afk_clicker.py:3845-3920`, G#39/GH#69/PR #70): "each scan is stamped with a monotonically increasing sequence number... handed back to `_apply_scan()`, which drops any result older than the newest one already applied." The dedicated regression test for that fix, `AnOlderScanResultDoesNotOverwriteANewerOne` (`tests/test_ui.py:4129-4217`), documents the same reasoning: "This is a genuine product race... not just a test-hermeticity gap... so unlike every other round of this fix it is closed in `afk_clicker.py` itself."

A second, narrower issue, separate from supersession: `self._pending = (tag, asset, release)` at line 3436 runs directly inside `_check_worker`, on the background thread, not gated through `self._ui()`/`_drain_ui()` — unlike `_poll_seq`/`_poll_applied_seq`, which `_apply_scan`'s own docstring states are "only ever touched from the main thread." `self._pending` is a plain tuple, not a Tk object, so this doesn't trip `docs/CODING-GUIDELINES.md`'s literal "only the main thread may touch Tk" rule — but it is the same class of unguarded cross-thread write the rest of this file goes out of its way to avoid for shared state that feeds Tk-visible output (`_pending` feeds `_offer_update`'s button/sidebar text).

**Judgment call, stated for the record:** test-only, or a real guard too? Real guard, following the existing `_poll_seq`/`_apply_scan` idiom exactly (see Proposed approach). Rejected alternative: a regression test only, documenting today's clobber as expected behavior. Rejected because (a) this project's own precedent for the identical bug shape (G#39) explicitly treated "an older worker's result overwrites a newer one's" as a real product race worth closing at the source, not a test-only gap, once it was identified — there is no principled reason to treat this occurrence differently just because its current trigger (two direct `check_update()` calls) needs a caller the button doesn't provide yet; (b) a test proving the clobber is real would have to assert the *wrong* outcome (stale data winning) to pass against today's code, which is a worse artifact to carry in the suite than the small, idiom-matching fix; (c) the fix is genuinely cheap — one counter, one changed method signature, one new small gate method, mirroring code already in this file — and it closes the separate off-main-thread write as a side effect, for free.

### Item 4 — `afk_clicker.py:1265-1337`, `Store.save()`, verified call sites
```python
def save(self):
    try:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)
        os.replace(tmp, self.path)     # atomic: never leave a half-written file
    except OSError:
        pass                           # read-only home is not worth crashing over
```
`Store.save()` is the single chokepoint for every persisted change — a `grep` for `\.save()`/`put_game(` across `afk_clicker.py` finds exactly five call sites, all inside `AfkAutoclicker`: `_apply_appearance` (`afk_clicker.py:3071`, Theme changed), `_apply_ui_scale` (`afk_clicker.py:3128`, UI scale changed), `_select` (`afk_clicker.py:3358`, a game selected with `persist=True`), `Store.put_game` (`afk_clicker.py:1337`, called from `_persist()`, `afk_clicker.py:3377` — itself wired to every numeric/text field's `"write"` trace, `afk_clicker.py:2932`, so this fires on every keystroke in an open game's settings), and `apply_hotkey` (`afk_clicker.py:4094`, a hotkey applied). None of the five checks `save()`'s return value today because there isn't one — every failure is swallowed identically, silently, everywhere.

Before the Settings page existed there was little persisted state a user could visually cross-check against disk; now Theme and UI scale are both directly, persistently visible in Settings → Appearance (`afk_clicker.py:2973-3005`, `self.appearance_var`/`self.ui_scale_var`, initialized from `self.store.data` at build time), so a save that silently fails leaves the in-memory value (and the UI showing it) correct for the running session but reverts on the next restart with no signal that happened — exactly what the ticket names.

`docs/CODING-GUIDELINES.md`'s "Failure behaviour" section is explicit and directly on point: "Say what went wrong and what would fix it... A read-only install directory gets named as such rather than producing a silent no-op." The existing precedent for *how* this file names a failure to the user is `_hotkey_error` (`afk_clicker.py:4060-4065`): repaint a specific, already-visible label (`hotkey_label`) with the failure text plus a `print(..., file=sys.stderr)`, no dialog, no blocking. There is no existing generic toast/snackbar mechanism in this codebase to reuse.

The one real constraint: `_persist()`/`put_game()` fires on every keystroke in a game's numeric fields (`afk_clicker.py:2932`), so if the config directory is read-only, `save()` will keep failing on every one of those keystrokes for as long as the condition lasts. A message that re-announces itself on every failed save would be exactly the kind of noise `docs/CODING-GUIDELINES.md`'s comment/failure discipline argues against.

**Judgment call, stated for the record:** surface a single, non-repeating, non-blocking notice, not silence and not a per-failure message. Concretely: `Store.save()` returns `True`/`False` instead of `None`; `AfkAutoclicker` tracks whether the *last* save attempt it saw succeeded or failed (a plain bool, e.g. `self._save_failed`), updates it at all five call sites, and paints/clears a notice in the Appearance pane only when that value actually *changes* (success → failure, or failure → success) — so a run of keystroke-triggered failures repaints nothing after the first one, and a later successful save silently clears it. Rejected alternatives: (a) log-only (`print(..., file=sys.stderr)` alone, no UI) — rejected because a stderr line is invisible to anyone running a packaged build outside a terminal, which is the whole population `docs/CODING-GUIDELINES.md`'s failure-naming rule exists for; (b) leave it exactly as-is and only document why — rejected because the guideline is not a soft aspiration here, it names this precise scenario ("a read-only install directory") as the thing that must not produce "a silent no-op," and the fix is cheap; (c) a sidebar-wide indicator via `SettingsItem.set_state` (the same widget the update-offer dot uses) — rejected as a wider change than warranted: that widget's contract is specifically "an update is waiting," and widening it to a second, unrelated meaning is a real (if small) design decision belonging to a future cycle if ever wanted, not bundled quietly into this one. Because the notice is a new, small visible element inside the Appearance pane, **ux-designer is needed, lightly**, for its exact wording, color, and placement within the existing `card(self.appearance_pane, s)` layout (`afk_clicker.py:2981-3005`) — not for anything else in this cycle.

## Proposed approach

### Item 1 — `afk_clicker.py:781-798`, `fetch_checksums`
Add a hex check alongside the existing length check, without a new import (no `re`/`string` currently imported at module level — `prefer zero new surface`):
```python
_HEX_CHARS = "0123456789abcdef"
...
def fetch_checksums(asset, timeout=30):
    ...
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            digest = parts[0].lower()
            if all(c in _HEX_CHARS for c in digest):
                sums[parts[1].lstrip("*").strip()] = digest
    return sums
```
(`_HEX_CHARS` can live as a small module-level constant near `CHECKSUM_ASSET`, or be inlined as a literal in the `all(...)` call — developer's call, either is one line of real cost.) No signature change, no caller changes.

### Item 2 — `afk_clicker.py:813-826` and `tests/test_updater.py:287`
Rewrite `_safe_names`'s docstring to state the split found above:
```python
def _safe_names(names, destination):
    """
    Reject any archive entry that would land outside the destination.

    zipfile's own extraction (extractall/extract, both branches below) has
    stripped ".."/"."/drive-letter/absolute-path components before joining
    onto the destination since Python 3.6.2 -- verified by reading the
    installed zipfile._extract_member source on both this sandbox's 3.11.2
    and this project's CI/release-pinned 3.12. The check below is defense
    in depth for zip: real security, not dependent on trusting a name string
    it never gets a chance to misuse.

    tarfile is the one that actually needs this: extractall(filter="data")
    -- the argument that closes the identical hole -- only exists from
    Python 3.12 and is only the default from 3.14. On 3.11 a bare
    extractall() silently restores every hole a crafted archive can hide
    (see _safe_tar_members's own docstring for the verified symlink escape).
    """
```
No change to the function body (still `os.path.realpath`/`startswith` per entry), `_safe_tar_members`, or `download_and_stage` — this item is prose-only. `tests/test_updater.py:287`'s comment becomes:
```python
        # zipfile's own extraction already strips ".."/drive components
        # (Python 3.6.2+) -- this check is defense in depth for zip and the
        # actual guard for tar (afk_clicker.py:_safe_names's own docstring).
```
No assertion in that test changes.

### Item 3 — `afk_clicker.py:2273-2277`, `:3402-3436`
Add a monotonically increasing counter next to the existing `_poll_seq` pair, and route `_check_worker`'s result through a main-thread gate exactly like `_apply_scan`:
```python
        self._check_seq = 0            # bumped once per check_update() call,
                                        # compared in _apply_check() -- see there
```
```python
    def check_update(self):
        self._pending = None
        self._check_seq += 1
        seq = self._check_seq
        self.settings_item.set_state(has_update=False)
        if self._settings_open:
            self.update_button.command = self.check_update
        self._set_update_state("Checking…", enabled=False)
        threading.Thread(target=self._check_worker, args=(seq,), daemon=True).start()

    def _check_worker(self, seq):
        try:
            release = latest_release()
        except NoReleases:
            self._ui(self._set_update_state, "No releases published yet", True)
            return
        if release is None:
            self._ui(self._set_update_state, "GitHub unreachable", True, BAD)
            return
        tag = release.get("tag_name", "")
        if not is_newer(tag):
            self._ui(self._set_update_state, f"Up to date · {__version__}", True)
            return
        asset = pick_asset(release)
        if asset is None:
            self._ui(self._set_update_state, f"{tag}: no build for this OS", True, BAD)
            return
        self._ui(self._apply_check, seq, tag, asset, release)

    def _apply_check(self, seq, tag, asset, release):
        # Main-thread gate, mirroring _apply_scan()'s stale-scan guard
        # (G#39/GH#69, afk_clicker.py:3905-...): an orphaned older worker
        # (started by a check_update() call a newer one has already
        # superseded) must not overwrite self._pending/the offer state with
        # a stale release once a newer check has moved past it. Also the
        # only place self._pending is ever written now -- always from here,
        # always on the main thread via _ui()/_drain_ui(), never directly
        # from _check_worker's own background thread.
        if seq != self._check_seq:
            return
        self._pending = (tag, asset, release)
        self._offer_update(tag)
```
`_offer_update(tag)` itself is unchanged — same signature, same body, still reads `self._pending`/`tag` the same way; it is simply invoked one level further down the same `_ui()`-marshaled callback chain than before.

### Item 4 — `afk_clicker.py:1322-1330`, plus its five call sites
```python
    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self.path)     # atomic: never leave a half-written file
            return True
        except OSError:
            return False                   # read-only home is not worth crashing over
```
`AfkAutoclicker.__init__` gains one flag next to `self._pending`:
```python
        self._save_failed = False      # last self.store.save() outcome seen by
                                        # _note_save() -- see there
```
A new method, called from all five existing call sites in place of the bare `self.store.save()`:
```python
    def _note_save(self, ok):
        """Every direct caller of self.store.save()/put_game() routes its
        result through here (docs/CODING-GUIDELINES.md "Failure behaviour":
        name a read-only config directory instead of a silent no-op). Only
        acts on a *change* in outcome -- a run of keystroke-driven _persist()
        failures while a directory stays read-only repaints nothing after
        the first one, and a later successful save clears the notice -- so
        this never re-announces the same, still-ongoing failure.
        """
        if ok == (not self._save_failed):
            return
        self._save_failed = not ok
        self._paint_save_notice()

    def _paint_save_notice(self):
        # Appearance-pane-local, mirroring _set_update_state()'s own
        # if-not-open-remember-and-return pattern: the flag survives
        # regardless of which pane is currently showing (a hotkey apply or a
        # game-field edit can fail to save while sitting on a different
        # tab), and gets painted the next time Appearance is (re)built too,
        # via _build_settings()'s own tail. See docs/design.md for wording/
        # placement.
        if not (self._settings_open and self._settings_tab == "appearance"):
            return
        ...  # widget text/color set here; exact shape per docs/design.md
```
`_build_settings()` calls `_paint_save_notice()` once at its own tail (same place `_build_ui()`'s tail already applies `update_button`'s idle-vs-real state, per that method's own docstring) so a failure that happened while Appearance wasn't open is reflected the moment it's opened. Every one of the five existing call sites changes from `self.store.save()` to:
```python
        self._note_save(self.store.save())
```
(`_select`'s `persist` branch, `_apply_appearance`, `_apply_ui_scale`, `apply_hotkey`) or, for `Store.put_game`/`_persist()`, from `self.store.put_game(self.current, values)` to `self._note_save(self.store.put_game(self.current, values))` — `put_game` itself also returns `save()`'s bool (one-line change, `afk_clicker.py:1335-1337`).

## Affected areas
- `afk_clicker.py`: one new module-level constant or inline literal (item 1, ~line 796); one docstring rewrite (item 2, ~lines 813-826); one new instance attribute, one changed method signature, one new small method, one changed call (item 3, ~lines 2273-2277, 3402-3436); one changed return path, one new instance attribute, two new methods, five changed call sites (item 4, ~lines 1322-1337, 2277, 3071, 3128, 3358, 3377, 4094, plus `_build_settings`'s tail ~line 3067).
- `tests/test_updater.py`: one extended test case (item 1, `test_parses_sha256sum_output`) and one corrected comment (item 2, ~line 287).
- `tests/test_ui.py`: two existing direct `_check_worker` call sites updated to pass `seq` explicitly (item 3, ~lines 3460, 3483), one new regression test class/method for the overlapping-workers race (item 3), one new test class covering `Store.save()`'s return value and the Appearance-pane notice (item 4).
- `docs/design.md`: needed, lightly — item 4's Appearance-pane notice only (wording, color, placement inside the existing card at `afk_clicker.py:2981-3005`). Nothing else in this cycle has a visual/layout component: item 1 is a parsing guard, item 2 is docstrings/comments, item 3 is an internal ordering guard with no new or changed widget.
- All four items stay inside `afk_clicker.py` (application logic) plus its own two test files — a single architectural layer, matching `docs/history/ac-10-spec.md`'s own precedent for a multi-item review-residue cycle. No split needed; this is one developer dispatch.

## Edge cases
- **Item 1**: an all-hex 64-character token that happens to be wrong (a corrupted download's real, but incorrect, digest) is unaffected — it still parses into `sums` and still fails later at `download_and_stage`'s `actual != expected` check, unchanged from today. Uppercase hex digests (already exercised by `test_parses_sha256sum_output`'s `digest.upper()` case) still pass, since the hex check runs against the already-lowered string.
- **Item 2**: the docstring change does not touch `_safe_tar_members`'s own verified-symlink-escape claim, which stays exactly as accurate as it already was — only `_safe_names`'s shared docstring (read by both the zip and tar call sites) changes.
- **Item 3**: a chord of exactly one in-flight worker (today's only reachable case) is unaffected — `_apply_check`'s `seq != self._check_seq` guard is always true (equal) for a lone check, so `_offer_update`/`_pending` land exactly as before, at the same point in the same callback chain. `install_update`/`_install_worker` (`afk_clicker.py:3454-3501`), which read `self._pending` directly, are untouched — they still read whatever `_apply_check` most recently set, same as before.
- **Item 4**: `_apply_appearance`/`_apply_ui_scale`/`apply_hotkey` all apply their in-memory change and rebuild/repaint *before* the ticket's own concern (disk divergence) becomes visible — this cycle does not change that ordering or add a blocking confirmation; the notice is purely informational, painted after the fact. A save that fails once and then succeeds on the very next attempt (a transient failure) clears the notice the next time Appearance is painted, exactly as it was shown — no lingering "used to fail" state.

## Acceptance criteria
- [ ] Given a SHA256SUMS blob containing a line with a 64-character non-hex token (e.g. `"g" * 64 + "  garbage.zip"`), when `fetch_checksums` parses it, then the returned dict does not contain `"garbage.zip"` — extends `tests/test_updater.py::Checksums::test_parses_sha256sum_output`.
- [ ] Given the same test's existing valid lowercase and uppercase 64-hex-character lines, `fetch_checksums` still returns them exactly as before (`digest`/`digest.upper()` both map to the lowered `digest` value) — no regression from the new check.
- [ ] Given `afk_clicker.py:813-826`'s `_safe_names` docstring after this change, it states that zipfile's own extraction already strips `..`/drive/absolute-path components since Python 3.6.2 (naming this project's CI/release-pinned Python version) and that this check is defense-in-depth for zip but the real guard for tar — no executable line in `_safe_names`, `_safe_tar_members`, or `download_and_stage` changes.
- [ ] Given `tests/test_updater.py:287`'s comment on `test_an_entry_escaping_the_directory_is_refused`, it no longer repeats the corrected misconception — no assertion in that test changes.
- [ ] Given `check_update()` called once (today's only real call path), the full existing updater-offer test suite (`test_a_fresh_check_supersedes_a_superseded_offer`, `test_offer_lands_through_a_real_worker_thread_with_settings_closed`, `test_offer_lands_through_a_real_worker_thread_with_settings_open`, and every other passing test touching `check_update`/`_check_worker`/`_pending`) still passes, with `tests/test_ui.py:3460`/`3483`'s direct `_check_worker` calls updated to pass the current `seq` (`self.ui._check_seq`) explicitly.
- [ ] New deterministic regression test (mirroring `AnOlderScanResultDoesNotOverwriteANewerOne`'s `threading.Event`-forced-ordering technique, not a timing gamble): given an older check's worker is blocked mid-flight, a newer check starts and its worker lands first, and the older worker is then released and lands last, `self._pending` and the offer state reflect only the newer check's result — the older worker's stale result is dropped, not applied.
- [ ] Sabotage-verify per this repo's convention: temporarily revert the `seq != self._check_seq` guard in `_apply_check` and confirm the new overlapping-workers test above fails; restore afterward.
- [ ] Given `Store.save()` after this change, it returns `True` on a successful write (unchanged on-disk behavior) and `False` on an `OSError` (still swallowed, still never raises) — verified via a monkeypatched `os.replace`/`open` raising `OSError` (this repo's monkeypatch-and-restore style, no `unittest.mock`, matching `tests/test_ui.py`'s `DetectOsTheme` class), not real filesystem permission bits (unreliable across the Linux/Windows/macOS CI matrix and under a root-run container).
- [ ] Given a simulated save failure while Settings → Appearance is open (or the next time it is opened after one), a single, non-blocking notice is visible in the Appearance pane naming that settings could not be saved.
- [ ] Given two or more further save failures occur (e.g. successive keystroke-driven `_persist()` calls) while the notice is already showing, it is not re-painted/re-flashed — same visible state throughout.
- [ ] Given a save then succeeds again, the notice is cleared the next time the Appearance pane is (re)painted.
- [ ] Given all five of `Store.save()`'s call sites (`_apply_appearance`, `_apply_ui_scale`, `_select`'s persist branch, `_persist()`/`put_game`, `apply_hotkey`), each routes its result through `_note_save()` — verified by triggering a failure via each of the five paths in turn and confirming the notice appears from any of them.
- [ ] Sabotage-verify per this repo's convention: temporarily make `_note_save`'s change-detection unconditional (always repaint) and confirm a new test asserting "no repaint on a second consecutive failure" fails; restore afterward.
- [ ] Full existing suite still passes: `DISPLAY=:99 <venv>/bin/python -m unittest discover -s tests -t .` (Xvfb `:99` already running; never two Tk processes on one display), reporting no fewer than the documented 375 `OK (skipped=10)` baseline, plus the new tests added by this cycle.
- [ ] No file other than `afk_clicker.py`, `tests/test_updater.py`, `tests/test_ui.py`, and (for item 4's notice) `docs/design.md` is touched. No new file added to the repo tree other than this `docs/spec.md`/the design doc/the implementation and test-review docs this cycle's own pipeline produces.

## Open questions
None blocking. Two judgment calls made without a further human decision point, stated in full under Background/current state:
- **Item 3**: a real ordering guard (the `_check_seq`/`_apply_check` gate), not a test-only documentation of the current clobber — the rejected alternative and reasoning are under item 3's own "Judgment call" paragraph above.
- **Item 4**: a single, change-triggered, Appearance-pane-local notice (not silence, not a per-failure message, not a sidebar-wide indicator) — the three rejected alternatives (log-only, leave-as-is-and-document, widen `SettingsItem`) and reasoning are under item 4's own "Judgment call" paragraph above. ux-designer is needed, lightly, for this notice's exact wording/color/placement only.

## Risk / rollback notes
- Item 1 only narrows what `fetch_checksums` accepts as a digest string — every previously-accepted valid line is still accepted; a line rejected by this change was already guaranteed to fail the later digest comparison, so no legitimate release is affected.
- Item 2 is prose-only; zero behavior change; zero rollback risk.
- Item 3 only changes internal sequencing/gating of an already-idle-by-default code path (no update-check is ever running unless the user clicks the button); the one behavior change (a previously-unreachable clobber can no longer happen) is a strict narrowing, not a new capability.
- Item 4 changes `Store.save()`'s return type from implicit `None` to an explicit bool — every existing caller that ignores the return value (the one `Store(...).save()` call inside `selftest()`, `afk_clicker.py:275`) is unaffected, since Python discards an unused return value silently either way.
- Rollback for any/all of the four items is a single revert of this cycle's commit; no persisted-state, schema, or on-disk format change anywhere in this diff — `settings.json`'s shape and every existing field are untouched.
