# Story: themes that follow the system, and a Settings tab

Gitea `admin/afk-clicker#17`, GitHub #20. Full ticket:
`/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/story17.md`.
Visual reference: the "Chosen" section of
`/tmp/claude-1000/-home-dev-projects-afk-clicker/ed6c1377-1c57-496d-b75f-a6e73ec855d5/scratchpad/theme-board.html`
(`THEMES` array entries `deepslate`/`quartz`, and the combined `deepslate-q`/
`quartz-pair` reference pair at the bottom of that array — those are the
authoritative hex/CSS-var source for every color and radius decision below).

*As someone who runs the clicker next to a game for hours, I want the window
to match my system's light or dark mode, and a Settings tab for how the app
looks and updates, so it fits my desktop and I stop hunting for global options
among per-game ones.*

Claude-mem was unreachable in this environment (no `mem-search`/CLI found under
`~/.claude-mem` or on `PATH`), so this breakdown is grounded only in this
worktree's `docs/*.md`, the ticket, the mock, and direct reads of
`afk_clicker.py` — not cross-session history. Nothing here contradicts
anything committed on `main`, so this is a gap to note, not a blocker.

## Re-cut of the suggested seams

The original 5-seam guess (schema version / palette+shapes / OS detection /
tabs+Settings / UI scale) is re-cut to **4 features**, dropping the
schema-version seam as its own feature (see Decision 0). Net effect: one fewer
dispatch cycle than the original guess, with the same total scope.

1. **Theme data + Quartz shape language** (was seam b)
2. **OS light/dark detection** (was seam c)
3. **Tab navigation + Settings tab** (was seam d, absorbs the settings-key
   additions that seam a would have gated)
4. **UI scale** (was seam e)

Each is one architectural layer (the Tk UI in `afk_clicker.py`, one file) —
skill 11's split trigger (schema *and* API *and* edge function *and* several
screens all in one dispatch) doesn't apply to any of them, so none of the four
need further splitting themselves.

## Decision 0 — no standalone "settings schema version" feature

**Rejected:** building a general schema-version field/migration framework as
a prerequisite feature before touching `settings.json`.

**Why:** `Store.__init__` (`afk_clicker.py:598-607`) already tolerates
unknown-shape input by construction — `self.data` starts as a fixed dict of
known keys (`{"games": {}, "hotkey": None, "selected": None}`) and
`self.data.update({k: v for k, v in loaded.items() if k in self.data})` only
ever pulls in keys that dict already defines. An old `settings.json` missing a
key added later simply keeps that key's built-in default — exactly how
`"hotkey"`/`"selected"` already behave for a pre-hotkey-feature file, no
version number involved. Adding `"theme"` and `"ui_scale"` as two more
top-level keys with defaults in that same dict (Feature 3 and Feature 4,
respectively) is the identical shape of change, and `ac-15`'s
`docs/spec.md` already set the precedent for "one narrow, self-contained,
commented `if`, not a general mechanism" for exactly this kind of additive
change (its `Store.__init__` migration for `click_ms: 510 → 650`). A schema
version earns its cost only when a change alters the *shape or meaning* of an
existing key — which is what the Macros story (`#13`, `git show 71ee024` on
`feature/ac-13/story-macros-tab`) is actually in that situation for, not this
one. Building version machinery now, for a problem this story doesn't have,
is speculative surface this story doesn't need — `_conventions.md` §3: "prefer
zero new surface."

**Not fully closed:** `ROADMAP.md` still lists "Settings schema version" as
open pre-1.0 work, and this story doesn't resolve it — it just doesn't need
to. Flagged under Open questions below in case there's a reason to want it
landed regardless (e.g. as insurance ahead of Macros), but my recommendation
is to leave `ROADMAP.md`'s item exactly as-is and let Macros (#13) be the
trigger, since that's the first change actually reshaping existing data.

## Cross-cutting decisions (apply to Features 2-4; Feature 1 has no switching yet)

**Decision — live apply is via in-place UI rebuild, not per-widget recolor,
and not a full process restart.**
`afk_clicker.py`'s widgets read the ten palette names as plain module
globals at construction time (`bg=BG`, `fill=CARD`, …) with no theme
reference stored on `self` — confirmed by grep, every `Button`/`Segmented`/
`StatusPill`/`GameItem`/`Row`/`NumBox`/`card()` call site does this. Three
options for making a Settings-tab Appearance/scale change visible:
  - **(A) Per-widget live recolor.** Every widget class would need a stored
    theme reference plus a `retheme()` method that re-`itemconfig`s every
    canvas item it owns. Most new code, most places a color can be missed
    (a widget that doesn't update is a visible, easy-to-ship bug), no
    existing precedent for "reconfigure everything" anywhere in this file.
    Rejected.
  - **(B) Full process restart**, the way `_quit_for_update` already does for
    a binary swap (`afk_clicker.py:1273-1280`, spawns a swap script and calls
    `self.on_close()`). Simple and already-proven for "big change, needs a
    clean re-init," but "System" mode wouldn't reflect a running app's OS flip
    until the user manually relaunches, undercutting the entire "follow the
    system" premise the moment it matters. Rejected as the *default*, but
    noted as the fallback if in-place rebuild turns out riskier in practice
    than expected (see Open questions).
  - **(C) In-place rebuild.** Extract the widget-construction body of
    `AfkAutoclicker.__init__` (everything from `root.title(...)` onward) into
    a `self._build_ui()` method; applying a theme/scale change destroys
    `root`'s direct children (`for w in root.winfo_children(): w.destroy()`)
    and calls `self._build_ui()` again, reusing the already-loaded
    `self.store`/`self.profiles`/`self.current` state already held on `self`.
    Background state — `self.worker`, `self.hk_listener`, the click-loop
    thread — lives outside the widget tree entirely (confirmed:
    `AfkAutoclicker.__init__` sets `self.worker = None`/`self.hk_listener =
    None` before any widget is built, and `start()`/`stop()` never reach into
    widget internals except through `_ui()`), so a widget-tree rebuild does
    not interrupt a running clicker or drop the hotkey listener. **Chosen.**
    Cheaper than (B) (no subprocess, no losing the in-memory worker/listener
    state), more contained than (A) (one rebuild path instead of N retheme
    methods).
  - This extraction is **not** done in Feature 1 — nothing in Feature 1
    switches anything at runtime, so adding `_build_ui()`/`_rebuild_ui()`
    there would be unused scaffolding (`_conventions.md` §3: no speculative
    abstraction). It belongs to Feature 3, the first feature that actually
    needs to reapply a change without restarting.

**Decision — OS light/dark is detected once at process start; no runtime
polling for the OS flipping while the app runs.**
`ROADMAP.md`'s own "Detection cost" item already flags the *existing* 5 s
X11 window-tree walk (`_poll_games`, `afk_clicker.py:1288-1292`) as a laptop
battery cost worth solving, not extending. Adding a second poll loop — for a
purely cosmetic follow of the OS's light/dark switch — on top of an
already-flagged cost is compounding a known problem for something with a much
easier honest answer: pick the theme once at launch, matching what "System"
means to most desktop apps that don't run a live watcher (most do not). A
user who flips their OS mid-session sees the app catch up next launch, or
immediately if they open Settings and pick a concrete Light/Dark (Feature 3)
rather than System. Rejected alternative: register a native OS
change-notification callback per platform (a Windows message hook,
`NSDistributedNotificationCenter` on macOS, a D-Bus signal from the portal on
Linux) instead of polling — genuinely lower-cost than polling, but three new,
platform-specific, non-polling integration points is a lot of new surface for
a currently-not-requested "sees it live" guarantee; flagged as a possible
future `ROADMAP.md` item, not built here.

**Decision — platform detection fails safe to Dark (Deepslate), uniformly.**
Windows: `winreg` read of
`HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize` \
`AppsUseLightTheme` (0 = dark, 1 = light) — stdlib, no new dependency.
macOS: `defaults read -g AppleInterfaceStyle` via `subprocess`, mirroring the
existing `osascript` subprocess pattern in `_window_titles()`
(`afk_clicker.py:696-702`, including its `timeout=5`); Apple's own convention
is that light mode has **no** key at all, so a clean "key not found" *is*
light, not a failure — only a subprocess error/timeout/unexpected exit is the
failure case. Linux: `gsettings get org.gnome.desktop.interface color-scheme`
(GNOME/GTK's `prefer-dark`/`default`/`prefer-light`), falling back to
`gsettings get org.gnome.desktop.interface gtk-theme` containing "dark" for
older GNOME — no new dependency, and consistent with `TECHSTACK.md`'s
X11/GNOME framing for this project. On every platform: any exception, a
missing binary/registry key that isn't the documented "light" case above, a
timeout, or unparseable output all resolve to **Dark** — this is what the app
already ships as today (a single dark look), so an undetectable OS is the
least-surprising possible regression: the app looks exactly like it did
before this story shipped, never a broken or half-themed state.

## Feature 1 — Theme data + Quartz shape language

**Spec:** this worktree's `docs/spec.md` (written now, full detail).

One line: palette constants become a `THEMES` dict holding both Deepslate and
Quartz color sets, the app keeps shipping Deepslate-only (no switching yet),
and every relevant widget picks up Quartz's shapes (pill buttons, pill
segmented control, pill status, radius-12 borderless cards and sidebar rows).

**Depends on:** nothing new — builds on `main` at `dfb9a0b`, expected to need
a rebase once `#14` (resizable window, focus) and `#15` (Minecraft 650 ms
default) land, since both touch `AfkAutoclicker.__init__`/`afk_clicker.py`
directly.

## Feature 2 — OS light/dark detection

One line: at startup, detect the OS's light/dark setting per the three
platform branches and uniform fail-safe above, and select `THEMES["dark"]`
or `THEMES["light"]` accordingly — no manual override yet (that's Feature 3),
no runtime re-detection (see Decision above).

**Scope:** a `detect_os_theme()` function (or similarly named, developer's
call) beside `_window_titles()`/`detect_running`, called once during
`AfkAutoclicker.__init__` before any color-dependent widget is built, setting
which `THEMES[...]` entry is active for that run.

**Acceptance criteria (draft, refined in Feature 2's own spec):**
- Given Windows registry `AppsUseLightTheme = 0`, when the app starts, then
  `THEMES["dark"]` is active; `= 1` selects `THEMES["light"]`.
- Given `defaults read -g AppleInterfaceStyle` returns `Dark`, when the app
  starts on macOS, then `THEMES["dark"]` is active; a `CalledProcessError`
  (key absent — light mode) selects `THEMES["light"]`.
- Given `gsettings get org.gnome.desktop.interface color-scheme` returns
  `'prefer-dark'`, when the app starts on Linux, then `THEMES["dark"]` is
  active; any other clean value, or `gsettings` missing/erroring/timing out,
  selects the documented fail-safe.
- Given any platform's detection raises, times out, or returns something
  none of the above branches recognize, when the app starts, then
  `THEMES["dark"]` is active and startup does not raise.
- Given `THEMES["light"]` is active, when any widget is constructed, then its
  colors come from `THEMES["light"]`, not the dark set — i.e. the `THEMES`
  object built in Feature 1 is genuinely wired to something, not just present.

**Non-goals:** manual override UI (Feature 3), runtime OS-change polling
(Decision above), any change to Feature 1's shapes.

**Depends on:** Feature 1 (needs `THEMES["dark"]`/`THEMES["light"]` to exist
and to be the sole source colors are read from).

## Feature 3 — Tab navigation + Settings tab

One line: add the tab mechanism the Macros story (`#13`) already asks to
reuse ("a second tab beside the clicker settings" — `git show 71ee024` on
`feature/ac-13/story-macros-tab`), and a first Settings tab holding
Appearance (System/Light/Dark, overriding Feature 2's auto-pick and
persisted as a new `"theme"` key in `settings.json`) and Updates (the
`self.update_button`/`self.version_label` pair moved out of the sidebar
bottom, `afk_clicker.py:1017-1038`, into the Settings tab, reusing
`_set_update_state`/`_offer_update`/`check_update` unchanged — PR #19's
checksum work also flows through `_set_update_state`, so this is a pure
relocation of the widgets, not new update logic). The global hotkey stays on
the game pages, unchanged — already decided per the ticket, nothing in this
feature touches `Hotkey`/`HotkeyWatcher`/the hotkey card in `_build_content`.

Introduces the `_build_ui()`/`_rebuild_ui()` extraction from the
cross-cutting Decision above — this is the feature that actually needs it,
since picking System/Light/Dark in Settings has to visibly repaint the
window without a restart.

**Depends on:** Feature 1 (theme shapes/colors to rebuild into), Feature 2
(System option needs OS detection to resolve against).

**Acceptance criteria (draft):**
- Given the Settings tab's Appearance control set to Light (or Dark), when
  applied, then the window rebuilds using `THEMES["light"]`/`["dark"]`
  without a process restart, and the choice is persisted in `settings.json`
  under a new `"theme"` key (`"system" | "light" | "dark"`).
- Given Appearance is `"system"` (the default for a fresh install, matching
  the ticket's "follow the OS... by default"), when the app starts, then
  Feature 2's detection result is used, same as before this feature existed.
- Given the sidebar today, when this feature ships, then "Check for updates"
  and the version label are no longer present at the sidebar bottom, and
  appear in the Settings tab instead, with identical behavior (`check_update`
  → `_check_worker` → `_offer_update`/`_set_update_state` flow unchanged).
- Given the game pages (Minecraft/Global/custom profiles), when this feature
  ships, then the hotkey card (`Toggle`/`Record`/`Apply`) is still there,
  unmoved — a non-regression check that "the global hotkey stays on the game
  pages" wasn't accidentally violated by the tab restructuring.
- Given a `settings.json` with no `"theme"` key (pre-this-feature file), when
  the app starts, then it behaves exactly as `"system"` would (Decision 0 —
  no migration needed, the key's absence is its own valid default).

**Non-goals:** any Macros content itself (`#13` builds that later against
this tab mechanism); UI scale (Feature 4); per-game settings tab restructuring
(only the two named things — Appearance, Updates — move).

## Feature 4 — UI scale

One line: a size choice in the Settings tab, on top of the DPI scaling the
app already computes (`self.s = root.tk.call("tk","scaling") / 1.333`,
`afk_clicker.py:969`), persisted as a new `"ui_scale"` key in
`settings.json`, applied via Feature 3's rebuild mechanism (multiplies into
`self.s` before `_build_ui()` reruns).

**Depends on:** Feature 3 (Settings tab surface, rebuild mechanism).

**Acceptance criteria (draft):**
- Given a UI scale choice (e.g. Small/Normal/Large — exact steps decided in
  Feature 4's own spec) other than the default, when applied, then every
  widget's size, font and radius scale by that factor on top of the existing
  DPI factor, without a restart (same rebuild path as Feature 3).
- Given a `settings.json` with no `"ui_scale"` key, when the app starts, then
  behavior is identical to today (factor of 1.0 on top of DPI scaling).
- Given the window is manually resized (`#14`'s resizability) at a non-default
  UI scale, when a game profile is switched, then layout doesn't break —
  non-regression against `#14`'s minsize/resize behavior.

**Non-goals:** persisting window size/position (explicitly out of `#14`'s
scope already, unchanged here); per-monitor DPI re-detection at runtime.

## Open questions

1. **In-place rebuild (Decision, chosen "C") vs. full restart (rejected
   "B") for applying a theme/scale change.** My recommendation is firm (C),
   but it's the single biggest new mechanism this story adds and the one
   most likely to surface an edge case only a human notices in practice (a
   widget that doesn't get cleanly torn down, a stale `after()` job — see
   `CODING-GUIDELINES.md`'s "cancel every pending `after()` job on close").
   If Feature 3's implementation turns out messier than expected, falling
   back to "changes apply next launch, Settings says so" is a legitimate,
   much cheaper downgrade — flagging now so it's a known fallback, not a
   surprise mid-build.
2. **Whether to land `ROADMAP.md`'s "Settings schema version" anyway**, even
   though Decision 0 argues this story doesn't need it. Recommendation:
   leave it for Macros (`#13`) to trigger, since that's the change actually
   reshaping data, not this one.
3. **UI scale's exact steps** (Small/Normal/Large? A numeric slider? Some
   other granularity?) — left to Feature 4's own spec, once Features 1-3 are
   built and there's a real Settings tab to design it into; no value in
   guessing now.
