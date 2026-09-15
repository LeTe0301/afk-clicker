# Spec: Ask to send the update log when an in-app update didn't finish (G#36 / GH#64)

Branch: `feature/ac-36/send-update-log-prompt`

## Summary
At startup, if the previous in-app update attempt's `update.log` shows it
died part-way (or silently relaunched the old build), show the person a
one-off dialog with a redacted preview of what would be sent, and let them
open a prefilled GitHub issue in their browser to report it.

## Goals
- Detect, at app startup, an in-app update that did not finish.
- Show the person exactly what will be sent before sending anything.
- Let them open a prefilled GitHub issue (`Send via GitHub`), dismiss, or
  open the log's folder, without ever sending anything automatically.
- Ask about a given failed attempt once (until dismissed/sent), not on
  every launch.

## Non-goals
- No server/telemetry of any kind — the only network use is the person's
  own browser loading a GitHub URL they explicitly chose to open.
- No automatic sending. The app never opens a browser, and never uploads
  or transmits the log, without the person clicking `Send via GitHub`.
- No change to the update/swap mechanism itself (`launch_swap_script`,
  the wait/copy/relaunch steps, `.cmd`/`.sh` structure) beyond the one
  additive log field described below. This is a read-only consumer of
  `update.log`, not a rework of how updates are applied.
- No persistent "unresolved update failure" indicator in Settings →
  Updates. One startup dialog is the only surface (see "Where it
  appears" for why); dismissing it is a real, final "no" for that
  attempt, not a snooze.
- No GitHub API calls, no OAuth, no creating the issue on the person's
  behalf — always the plain prefilled `github.com/.../issues/new` URL
  opened in their own already-authenticated (or not) browser.
- No fix for logs written by already-installed older builds that predate
  this feature (see "Edge cases" — they lack the new `version=` field but
  are still handled by the `done`-only rule).

## Background / current state
- `update.log` is written by `write_swap_script` (`afk_clicker.py:855`) at
  `os.path.join(os.path.dirname(config_path()), "update.log")`
  (`config_path()` at `:994`; the join happens in `_install_worker` at
  `:3067`). Truncated fresh per attempt. Each line is timestamped
  (`%DATE% %TIME%` on Windows, `$(date '+%Y-%m-%d %H:%M:%S')` on
  Linux/macOS) and step-named: `start pid=… staged="…" target="…"
  relaunch="…"`, `wait finished after N iterations`, `copy exit code N`,
  `relaunch attempted`, and — **only when the copy step's exit code was a
  success** — `done`. Full history of that log's design: `docs/history/ac-35-spec.md`.
- `_install_worker` (`afk_clicker.py:3048`) stages the update and already
  has the target release's tag in scope (`tag, asset, release =
  self._pending`, `:3049`) at the exact point it calls `write_swap_script`
  (`:3068`) — the version the log doesn't currently record but easily
  could.
- No auto-check-on-launch exists today; `check_update()` only runs when
  the person clicks the button (`afk_clicker.py:2987`, wired at
  `_build_settings`'s `:2643`). This feature is unrelated to that check —
  it never contacts GitHub's API and needs no network until the person
  clicks `Send via GitHub`.
- Settings → Updates UI: `_build_settings` (`:2521`), `update_button`/
  `version_label` built at `:2640-2645`, replayed on rebuild via
  `self._update_text` (`:1960`, replay mechanism noted at `:2261-2269`).
  This feature's dialog is deliberately **not** part of that rebuildable
  pane (see "Where it appears").
- `Store` (`afk_clicker.py:1004`) persists a fixed key set
  (`self.data = {"games": …, "hotkey": …, "selected": …, "appearance": …,
  "ui_scale": …}`, `:1009`) and only loads keys already in that dict
  (`:1015`). This feature adds no new key here (see "Asking once, without
  new settings state" below) — deliberately, to keep "zero new surface."
- **No `tk.Toplevel`/`messagebox` exists anywhere in this codebase today**
  (confirmed by search) — every other piece of UI is either the sidebar/
  content-pane system or a rebuilt Settings pane. This feature is the
  first one-off dialog. Flagged here as a deliberate, called-out deviation
  from "reuse the existing pattern": a Settings-pane notice was considered
  and rejected (see "Where it appears") because nothing here needs to
  survive a theme/scale rebuild or coexist with the persistent Settings
  UI — it needs to interrupt once, at launch, and then never exist again
  for that attempt. ux-designer should style it with the app's existing
  palette/constants (`BG`, `INK`, `CARD`, `ACCENT`, `MUTED`, `BAD`) and
  existing widgets (`Button`, `Row`, `card`) rather than inventing new
  chrome, but the container itself (a `Toplevel`) is new.
- Windows OEM code page: `cmd`'s `echo … > file` redirection writes bytes
  in the console's OEM code page (e.g. CP437/CP850), not UTF-8 — the log
  can't be assumed to decode as UTF-8 on Windows. No existing code in this
  file currently reads `update.log` back (only writes it), so there's no
  established decode convention to follow yet; this spec sets one (see
  "Edge cases").

## Proposed approach

### 1. One additive field in the log: the target version
`write_swap_script(staged, target, relaunch, log_path, target_version=None)`
gains a 5th, **keyword, default-`None`** parameter (not a new required
positional — unlike `log_path` in ac-35, omitting it is a legitimate,
meaningful state: "version unknown," not "logging silently disabled").
Default `None` means the 5 existing call sites in `tests/test_updater.py`
(`:368`, `:393`, `:497`, `:584`, `:743`) and their exact-line-content
assertions (`SwapScriptWindowsCmdText`, `SwapScriptLogLifecycle`) need no
change at all; only `_install_worker` (`:3068`) is updated to pass
`target_version=tag` (the raw `"vX.Y.Z"` string already in scope from
`self._pending`).

When given, the `start` line gains a trailing ` version="{target_version}"`
(both `.cmd` and `.sh`); when omitted, the line is byte-identical to
today. This lets startup detection tell "the relaunch silently ran the
old build" apart from "the copy/relaunch genuinely finished" — a `done`
line alone can't distinguish those two, and that gap is exactly the kind
of silent failure this feature exists to catch. Cost: one field, one
existing call site touched, zero test churn.

### 2. Detection at startup (no network)
New module-level helpers (near `write_swap_script`/`launch_swap_script`,
same file):
- `read_update_log(log_path)` — returns the decoded text, or `None` if the
  file doesn't exist. See "Edge cases" for the decode strategy and a size
  cap.
- `update_log_status(log_path, current_version=__version__)` — returns one
  of `"ok"` (no log, or log ends with `done` and either has no
  `version="…"` field or its version matches `current_version`),
  `"incomplete"` (log exists, has no trailing `done` line), or
  `"wrong_version"` (log ends with `done`, has a `version="…"` field, and
  it does **not** match `current_version`, i.e. the relaunch didn't
  actually land the new build). Both `"incomplete"` and `"wrong_version"`
  are "failed" for this feature's purposes.

Called once, from `AfkAutoclicker.__init__`'s tail, via
`self.root.after_idle(self._maybe_offer_log_report)` — **not** from
`_build_ui`/`_rebuild_ui`, so a later theme/UI-scale rebuild never
re-triggers it (see "Background" on why this sidesteps the
rebuild-replay machinery entirely). `after_idle` so the main window
paints first; this never blocks startup and needs no network.

### 3. Asking once, without new settings state
On `Send via GitHub` or `Dismiss`, rename `update.log` to
`update.log.reported` via `os.replace` (best-effort, wrapped in
`try/except OSError`, same "not worth crashing over" posture as
`Store.save()` at `:1069`). This is the sole "seen" marker — no new
`Store` key, no new schema. Consequences, all intentional:
- `Open log folder` alone does **not** rename anything, so the person can
  still act on the same prompt afterward.
- If the dialog is never actioned (window closed via the OS close button,
  app killed, crash) the same `update.log` is still there next launch, no
  `done`/version match, so the prompt reappears — correct: "ask once per
  failed attempt" means once per distinct attempt until it's actually
  dismissed or sent, not "only the first time ever."
- The next successful update calls `write_swap_script` again, which
  always truncates-and-recreates the literal `update.log` path regardless
  of any `.reported` sibling sitting next to it (pre-existing lifecycle,
  unchanged) — so a fresh attempt always gets a fresh, unprompted-for log,
  and a stale `.reported` file is simply inert leftover, never read again.
- If a still-unactioned failed log is overwritten by a *new* update
  attempt before the person deals with it, that evidence is lost — this
  is the existing "truncated, not appended" contract from ac-35, not
  something this feature changes.

### 4. Where it appears
A single `tk.Toplevel`, built and shown once by `_maybe_offer_log_report`
when `update_log_status(...)` is not `"ok"`, transient to `self.root`
(`transient(self.root)`), not a persistent Settings pane and not a
blocking `wait_window` grab — the person can move it aside or close it
like any other window; there is nothing else demanding their attention at
launch (clicking/hotkeys haven't started yet), so a startup interruption
here is low-cost, unlike interrupting mid-session. Rejected alternative:
a permanent Settings → Updates banner — considered, but it depends on the
person opening Settings, which defeats "proactively surface a silent
failure," and doubles the surface (two places needing the same
preview/consent UI) for no real benefit given the app is normally used
AFK, not tended to in Settings.

### 5. Preview + consent
The dialog shows, top to bottom:
- A one-line explanation ("The last update didn't finish" /
  "The last update relaunched the old version" depending on status).
- A read-only, scrollable preview of the **exact** issue title and body
  that would be sent (built by `build_issue_report`, see below).
- A checkbox, **unchecked by default** (i.e. redacted by default):
  "Show full local paths" — when off, every occurrence of the home
  directory (`os.path.expanduser("~")`, matched case-insensitively on
  Windows since Windows paths are case-insensitive) in the preview/body
  is replaced with `~`. Default redacted directly addresses the ticket's
  own concern (the log embeds `C:\Users\<name>\...`); the checkbox exists
  because the raw paths are still occasionally useful to double-check
  before sending, not because redaction should be optional by default.
- Three actions: **Send via GitHub** (primary; opens the browser, then
  marks the attempt as seen per §3), **Dismiss** (marks as seen, no
  browser), **Open log folder** (opens `os.path.dirname(log_path)` in the
  platform file manager — `os.startfile` on Windows, `open` on macOS,
  `xdg-open` on Linux; does not mark as seen).

### 6. Issue body
`build_issue_report(current_version, target_version, log_text, redact=True)`
returns `(title, body)`:
- **Title:** `f"In-app update didn't finish (v{current_version})"` when
  `target_version` is unknown (no `version=` field — an older-format
  log), else `f"Update from v{current_version} to {target_version} didn't
  finish"`.
- **Body:**
  ```
  **App version:** {current_version}
  **Target version:** {target_version or "unknown (older log format)"}
  **OS:** {platform.platform()} ({sys.platform})

  ```
  update.log
  {log tail, redacted if requested}
  ```
  ```
  (`platform.platform()` — stdlib, not yet imported in this file; add
  `import platform` alongside the existing stdlib imports at the top.)
- **URL:** `f"https://github.com/{GITHUB_REPO}/issues/new?" +
  urllib.parse.urlencode({"title": title, "body": body})`.
- **Length cap: no official GitHub-documented number for the `issues/new`
  query-string form exists** (searched; GitHub's documented 65,536-char
  limit is the issue *body* via the REST/GraphQL API, not the web form's
  URL — the practical failure mode for an over-long URL is an HTTP 414 or
  a silently truncated/broken link before the API limit is ever reached).
  Using the long-standing cross-browser/cross-OS-safe convention of
  **2000 characters for the whole URL** (under the ~2083-character legacy
  Internet Explorer cap that most URL-shortening/link-building tooling
  still targets for universal compatibility) as a conservative, explicit
  assumption — proceeding under this number; flagged under "Open
  questions" since it's a judgment call, not a documented spec, though a
  sensible default exists either way.
  - Because the log's own format is compact (5-6 short lines per
    "Background"), this cap is realistically only ever hit by a corrupt
    or unexpectedly huge log (see "Edge cases"), not by a normal failure.
  - Truncation: read at most the log's **last 4000 raw characters**
    (tail — the failure is always at or after the last logged step, per
    the log's own append-in-order format) before building the body; if
    the fully-encoded URL still exceeds the cap, keep shrinking the tail
    (drop oldest lines first) and re-encode until it fits, prefixing the
    kept portion with `"… (truncated — see update.log locally for the
    full file) …"`.

### 7. Opening the browser
`webbrowser.open(url)` (new stdlib import). No special handling needed
for a frozen PyInstaller build on any of the three platforms — it shells
out to the OS's own browser launcher (`os.startfile`-equivalent on
Windows, `open`/`xdg-open` under the hood), which needs nothing from the
Python/PyInstaller environment itself. `webbrowser.open` returns `False`
(and rarely raises) rather than blocking if it can't find a controller;
wrap in `try/except Exception`, and on `False`/an exception, don't
silently fail — show a small inline fallback in the same dialog: the raw
URL in a read-only entry plus a `Copy link` button
(`self.root.clipboard_clear(); self.root.clipboard_append(url)`, the
same clipboard primitive Tk already exposes, no new dependency).

### 8. Edge cases
- **Log unreadable / garbled encoding.** `read_update_log` opens the file
  in binary, decodes `utf-8` with `errors="replace"` (never raises).
  Windows OEM-code-page bytes that aren't valid UTF-8 (e.g. an accented
  character in a username) render as `�` rather than crashing or hanging
  the dialog — acceptable for a diagnostic tail; documented as a known
  limitation rather than solved with code-page detection (would need a
  new `ctypes`/`win32api` dependency this project doesn't otherwise use).
- **Log absurdly large** (corruption, e.g. an infinite-loop bug in a
  future script version writing per-iteration lines forever).
  `read_update_log` reads at most the **last 1 MiB** of the file via
  `os.path.getsize` + a seek from the end, never loading the whole file —
  bounds memory regardless of what caused the bloat.
- **No network needed for detection or preview** — only `Send via GitHub`
  ever touches the network, and even then only via the person's own
  browser, not this process.
- **Linux/macOS `.sh` path.** Detection, decode, and the dialog are
  identical — `update.log`'s format and location are already
  platform-uniform (ac-35's "both script variants write it, same path,
  same step names").
- **Running from source (no PyInstaller build).** Nothing ever writes
  `update.log` outside `_install_worker`'s frozen-only install flow, so
  detection naturally finds no file and no-ops — no `is_frozen()` guard
  needed. Rare corner case, not solved: a dev machine whose source
  checkout points `config_path()` at the same directory a previously
  installed frozen build used (identical computation, not
  frozen-vs-source-dependent) would still see a stale prompt from that
  other install — acceptable, matches this being a stable,
  install-location-independent signal by design.
- **Older-format logs** (written by an already-installed pre-this-feature
  build, i.e. any log with no `version="…"` field). Handled by the
  `done`-only rule (`update_log_status` returns `"ok"`/`"incomplete"`,
  never `"wrong_version"`, when the field is absent) — see "Non-goals."
- **Successful update, log ends with `done`, version matches (or
  version field absent).** `update_log_status` returns `"ok"` — no
  dialog, no behavior change from today.
- **Duplicate/concurrent:** only one `AfkAutoclicker` exists per process
  (existing single-instance-per-launch assumption throughout this file),
  and `_maybe_offer_log_report` runs once per launch from `__init__` —
  no concurrency concern.
- **Redaction correctness:** the checkbox toggling must update the
  *preview text* live (not just future sends) — the whole point is
  "show what gets sent," so what's on screen when `Send via GitHub` is
  clicked must be what's actually sent (i.e. the URL is always built from
  the checkbox's current state at click time, not cached from dialog
  open).

## Affected areas
- `afk_clicker.py`:
  - New `import platform`, `import webbrowser`, `import urllib.parse`
    (the last may already be covered by the existing `urllib.request`
    import — confirm and add only if `urllib.parse` isn't already
    reachable).
  - `write_swap_script` (`:855`) — new `target_version=None` keyword
    param; `.cmd`/`.sh` `start` line templates gain the optional
    ` version="{target_version}"` suffix.
  - `_install_worker` (`:3048`, call at `:3068`) — pass
    `target_version=tag`.
  - New module-level functions near `write_swap_script`:
    `read_update_log`, `update_log_status`, `build_issue_report`.
  - `AfkAutoclicker.__init__` (`:1894`) — schedule
    `self.root.after_idle(self._maybe_offer_log_report)` at the tail.
  - New `AfkAutoclicker` methods: `_maybe_offer_log_report`,
    `_show_update_log_dialog` (or similar — naming is the developer's
    call, consistent with this file's existing method-naming style),
    handlers for Send/Dismiss/Open-folder/Copy-link.
- `tests/test_updater.py` — new unit tests for `read_update_log`,
  `update_log_status` (all three states, including the `version=`
  mismatch case), `build_issue_report` (title/body shape, redaction,
  the length cap and truncation behavior), and `write_swap_script`'s new
  optional field (both presence and byte-identical absence).
- `tests/test_ui.py` — new tests driving the dialog end to end under
  Xvfb (see "Tests" below); likely a new test class alongside the
  existing Settings/Updates-adjacent ones.
- No data model / schema changes (`Store` untouched, per "zero new
  surface").
- No changes to `.github/workflows/ci.yml` or `release.yml`.

## Acceptance criteria
- [ ] Given no `update.log` at the settings-directory path, when the app
      starts, then no dialog appears and `_maybe_offer_log_report` is a
      no-op.
- [ ] Given an `update.log` ending in `done` with no `version=` field (or
      a `version=` field matching `__version__`), when the app starts,
      then no dialog appears.
- [ ] Given an `update.log` with no trailing `done` line, when the app
      starts, then the dialog appears, `update_log_status` returns
      `"incomplete"`.
- [ ] Given an `update.log` ending in `done` whose `version="…"` field
      does not match `__version__`, when the app starts, then the dialog
      appears, `update_log_status` returns `"wrong_version"`.
- [ ] Given the dialog is open, when the "Show full local paths" checkbox
      is unchecked (default), then every occurrence of the home directory
      in the visible preview is shown as `~`; when checked, the original
      absolute paths are shown instead — and the URL built on `Send via
      GitHub` matches whichever state is currently checked.
- [ ] Given `Send via GitHub` is clicked, then `webbrowser.open` is called
      with a URL whose `body`/`title` query values, once URL-decoded,
      exactly match the dialog's currently-visible preview text, and
      `update.log` is renamed to `update.log.reported` afterward.
- [ ] Given `Dismiss` is clicked, then no browser is opened,
      `update.log` is renamed to `update.log.reported`, and relaunching
      the app afterward (with no new update attempt) shows no dialog.
- [ ] Given `Open log folder` is clicked, then the log's directory is
      opened via the platform's file-manager call and `update.log` is
      **not** renamed — a subsequent `Send via GitHub`/`Dismiss` in the
      same dialog session still works.
- [ ] Given `webbrowser.open` returns `False` or raises, then the dialog
      shows the fallback URL text and a working `Copy link` control
      instead of silently failing.
- [ ] Given a log whose raw content, once encoded into the full
      `issues/new` URL, would exceed 2000 characters, then the body sent
      is truncated (oldest lines dropped first, truncation marker
      present) such that the final encoded URL is at or under the cap.
- [ ] Given `write_swap_script` is called without `target_version` (every
      existing test call site), then the generated script's `start` line
      is byte-identical to today's (no `version=` suffix) and every
      existing `SwapScriptWindowsCmdText`/`SwapScriptLogLifecycle`
      assertion still passes unmodified.
- [ ] Given `write_swap_script` is called with `target_version="v0.7.0"`,
      then the `start` line contains `version="v0.7.0"` on both the
      `.cmd` and `.sh` variants.
- [ ] Given a log file larger than 1 MiB, then `read_update_log` returns
      only its tail (bounded read, not the whole file) without raising.
- [ ] Given a log file containing non-UTF-8 bytes, then `read_update_log`
      returns a string (using `errors="replace"`) without raising.

## Open questions
**Resolved 2026-09-15.** Leo chose the **startup dialog** (section 4) over a
Settings badge + Updates-pane notice, knowing it is the app's first `Toplevel`
and that window-manager behaviour (focus, stacking, transient) is only really
observable on Windows/macOS CI. The orchestrator accepted the three defaults
below as written (2000-char cap, redacted-with-opt-out, include
`wrong_version`).

1. **2000-character URL cap** — no authoritative GitHub-specific number
   exists for the `issues/new` web-form URL (see "Issue body" above for
   what was actually found vs. assumed). Proceeding under the
   conservative, widely-used 2000-character convention; flagging for
   Leo in case there's a preference for a different (larger/smaller)
   number, though the log's own compact format means this will rarely
   matter in practice.
2. **Redaction toggle vs. hard-coded redaction** — defaulting to
   redacted-with-an-opt-out-checkbox rather than always-redacted or
   never-redacted. Proceeding under this default; flag if Leo would
   rather the toggle not exist at all (always redact, full stop) or
   always show full paths (no redaction).
3. **Whether `"wrong_version"` (silent-relaunch-of-old-build) detection
   is worth the small `write_swap_script` signature change**, versus
   shipping only the simpler `done`-only rule the ticket named as the
   floor. Proceeding under "yes, include it" — it's additive, backward
   compatible (default `None`, zero test churn at the 5 existing call
   sites), and closes a real gap the `done`-only rule can't (a relaunch
   that silently starts the old build still logs `done`). Flag if Leo
   would rather keep this cycle to the simpler floor and defer version
   tracking.

## Risk / rollback notes
- Purely additive: new functions, one new optional parameter with a
  backward-compatible default, one new startup hook, one new dialog. A
  `git revert` of the commit fully removes it; no schema, no migration,
  no change to how updates are actually applied.
- Worst-case failure mode is cosmetic: a dialog that doesn't appear when
  it should (miss) or appears once when it shouldn't (false positive on
  a log parsed wrong) — neither can affect the click-automation or
  hotkey machinery, since this code path never touches `Controller`,
  `hk_listener`, or any worker thread.
- `os.replace` marking a log as `.reported` is atomic and best-effort
  (`try/except OSError`, matching `Store.save()`'s existing posture) — a
  failure to rename (e.g. read-only settings dir) just means the prompt
  reappears next launch, not a crash.
