# Design: Content fills the available vertical space (story #24, Feature 4 of 5)

## Summary

Each of the four tab panes (`hotkey_pane`, `clicking_pane`, `appearance_pane`, `updates_pane`) gets a live-measured top/bottom spacer pair that distributes the pane's leftover vertical space by centering content within each pane. This halves the largest dead band from ~630px to ~315px on single-card panes (Hotkey, Appearance, Updates), improving the visual balance without scrolling or interaction with rebuild machinery. The spacer split ratio `FILL_TOP_SHARE = 0.5` trades visual consistency for proportional margin reduction: tab switches show varying margin sizes tied to content height, but the largest single empty band is genuinely reduced as the ticket's acceptance criterion requires.

## Key design decision: FILL_TOP_SHARE = 0.5 (vertical centering)

**Why 0.5 and not other values:**

The ticket requires the dead band to be "materially smaller, not merely relocated." A top/bottom spacer pair can only distribute the available extra space; it cannot eliminate it. The three candidate approaches are:

1. **Small top share (0.2)** — relocates 20% of space above, leaves 80% below. For Hotkey with 630px extra: 126px top, 504px bottom. The largest band stays massive (504px, 80% of extra).

2. **Centering (0.5)** — splits space equally. For Hotkey with 630px extra: 315px top, 315px bottom. The largest band is halved (315px, 50% of extra). This satisfies the "materially smaller" criterion.

3. **Other splits (0.3, 0.4, etc.)** — any asymmetry increases the largest single band. At 0.3: 189px top, 441px bottom (441px is worse than 315px). Only 0.5 minimizes the maximum.

**Why inter-card spacing (distributing slack between cards) won't help:**
Three of the four panes are single-card panes (Hotkey, Appearance, Updates) with no inter-card gaps to distribute into. Inter-card spacing helps only Clicking, which is already the *least* affected pane (320px extra, vs. 630px on single-card panes). The mechanism solves the problem where it does not exist and is inert where the problem is worst.

**Why growing cards is not viable:**
A Hotkey card holding one row (`Toggle / Not set / Record / Apply`) stretched to 700px tall to consume the space would produce a visually broken layout far worse than empty space.

**Therefore:** Within any mechanism that does not invent content, `FILL_TOP_SHARE = 0.5` is the best available answer. It halves the largest single band, the measurable outcome the ticket's acceptance criterion asks for.

**Floor case (default minimum window):** Extra space is zero or negligible, both spacers stay ~0, content sits exactly as today — a true no-op.

## Residual limitation: still a large empty band

A centered 315px empty band on a ~720px pane is 44% of the pane's height. This feature **halves** the dead band, not eliminates it. The story's own wording ("no large dead band") is stronger than what a spacer-only mechanism can deliver. This is a material improvement—the largest band goes from 630px to 315px—but it remains visually present. The acceptance criterion is satisfied by the reduction, not by the absence of empty space.

## Design trade-off: tab-switch visual rhythm

Centering produces proportionally different margins across the four panes:

| Pane | Natural height | Extra space | Top spacer | Bottom spacer | Margin ratio |
|---|---|---|---|---|---|
| Hotkey | 90px | 630px | **315px** | 315px | 44% top, 44% bottom |
| Clicking+Eating | 400px | 320px | **160px** | 160px | 22% top, 22% bottom |
| Appearance | 90px | 630px | **315px** | 315px | 44% top, 44% bottom |
| Updates | 90px | 630px | **315px** | 315px | 44% top, 44% bottom |

**Visual effect:** When the user clicks from Hotkey to Clicking, margins shrink approximately 2×. When clicking back to Hotkey, they expand 2×. This is a discrete, noticeable change in the pane's visual "tightness." It occurs because Clicking's content is 4× taller than Hotkey's, leaving proportionally less extra space to distribute.

This is the price of halving the largest single dead band. There is no split value that both halves the band and keeps margins constant across tabs—the margin size is determined by `(pane_height - content_height)`, which varies naturally with content.

## States and visual design

### Hotkey pane (short, single card)

**At minimum window size (minh = 690 * s ≈ 465px at s=0.675):**
```
┌─────────────────────────┐
│ Games · Hotkey | Clicking│  (tab bar)
│                         │
│ (spacer: ~0-1px top)    │
│ ┌─────────────────────┐ │
│ │ Hotkey  ·  shared   │ │
│ │ ┌─────────────────┐ │ │  (one card: ~90px tall)
│ │ │ Toggle: Not set │ │ │
│ │ │ [Record] [Apply]│ │ │
│ │ └─────────────────┘ │ │
│ └─────────────────────┘ │
│ (spacer: ~0-1px bottom) │  (no visible dead band)
└─────────────────────────┘
```

**At tall window (e.g., 1000px height at s=1):**
```
┌─────────────────────────┐
│ Games · Hotkey | Clicking│  (tab bar)
│                         │
│ (spacer: ~315px top)    │
│ ┌─────────────────────┐ │
│ │ Hotkey  ·  shared   │ │
│ │ ┌─────────────────┐ │ │  (one card: ~90px)
│ │ │ Toggle: Not set │ │ │
│ │ │ [Record] [Apply]│ │ │
│ │ └─────────────────┘ │ │
│ └─────────────────────┘ │
│                         │
│ (spacer: ~315px bottom) │  (equal margin above and below)
│                         │
└─────────────────────────┘
```

**Spacing** (computed at s=1, tall window):
- Pane height: ~720px
- Card natural height: ~90px
- Extra space: ~630px
- Top spacer (50%): 315px
- Bottom spacer (50%): 315px
- Largest continuous empty band: 315px (44% of pane)

**At s=0.675 (worst-case compound scale), tall window:**
- Pane height: ~486px
- Card natural height: ~60px
- Extra space: ~426px
- Top spacer: 213px
- Bottom spacer: 213px
- Largest band: 213px (44% of pane)

**Spacer styling:**
- Both spacers: `bg=BG` (the same background as the pane itself) — true empty margin, no visible chrome, matching the spec's "no visual restyle" scope (Feature 5 owns chrome).
- `height=0` at construction, set dynamically by `_fill_pane()` on every recompute.

### Clicking pane (tall, 2–3 cards including optional Eating)

**At minimum window size:**
```
┌─────────────────────────┐
│ Games · Hotkey | Clicking│  (tab bar)
│                         │
│ (spacer: ~0-1px top)    │
│ ┌─────────────────────┐ │
│ │ Interval:       650 │ │
│ │ Random jitter:    0 │ │
│ │ Auto-stop:        0 │ │  (Clicking card: ~180px)
│ │ Mouse button: [Left]│ │
│ └─────────────────────┘ │
│ ┌─────────────────────┐ │
│ │ Eating              │ │
│ │ ┌─────────────────┐ │ │  (Eating card: ~150px, Minecraft only)
│ │ │ [P&E] [Hold] [...] │ │
│ │ │ Eat every:     75 │ │
│ │ │ Hold for:      2  │ │
│ │ └─────────────────┘ │ │
│ └─────────────────────┘ │
│ (spacer: ~0-1px bottom) │  (no dead band at floor)
└─────────────────────────┘
```

**At tall window (same s=1, 1000px):**
```
┌─────────────────────────┐
│ Games · Hotkey | Clicking│
│                         │
│ (spacer: ~160px top)    │  (smaller than Hotkey because content is taller)
│ ┌─────────────────────┐ │
│ │ Interval:       650 │ │
│ │ Random jitter:    0 │ │
│ │ Auto-stop:        0 │ │
│ │ Mouse button: [Left]│ │
│ └─────────────────────┘ │
│ ┌─────────────────────┐ │
│ │ Eating              │ │
│ │ ┌─────────────────┐ │ │
│ │ │ [P&E] [Hold] [...] │ │
│ │ │ Eat every:     75 │ │
│ │ │ Hold for:      2  │ │
│ │ └─────────────────┘ │ │
│ └─────────────────────┘ │
│                         │
│ (spacer: ~160px bottom) │  (same 50/50 split, smaller margins overall)
│                         │
└─────────────────────────┘
```

**Spacing** (computed at s=1, tall window):
- Pane height: ~720px
- Natural height (Clicking + Eating): ~400px
- Extra space: ~320px
- Top spacer (50%): 160px
- Bottom spacer (50%): 160px
- Largest continuous empty band: 160px (22% of pane)

**Key observation:** Clicking's margins (160px each) are smaller than Hotkey's (315px each) because Clicking's content is taller. The 50/50 split is preserved, but the absolute margin sizes differ proportionally to content height. This creates the 2× margin variation when switching tabs.

### Appearance and Updates panes (each short, single card)

**At tall window:** Like Hotkey—content centered with 315px margins above and below. Each pane is measured independently, so if their card heights differ slightly, their margin split still follows 50/50 but the absolute sizes may vary (e.g., if Appearance's card is 95px and Updates' is 85px, Appearance gets 625px extra and Updates gets 635px, leading to slightly different margin sizes).

## Mechanics: placement and trigger points

### Spacer placement and recompute function

Per spec §1, each pane is wrapped with top/bottom spacers at construction:

```python
FILL_TOP_SHARE = 0.5

self.hotkey_pane = tk.Frame(body, bg=BG)
self.hotkey_pane.pack(fill="both", expand=True)

top_spacer = tk.Frame(self.hotkey_pane, bg=BG, height=0)
top_spacer.pack(fill="x")

# ... existing section/card/row construction ...

bottom_spacer = tk.Frame(self.hotkey_pane, bg=BG, height=0)
bottom_spacer.pack(fill="x")

self._hotkey_fill = (top_spacer, bottom_spacer)  # stored for explicit calls
self.hotkey_pane.bind("<Configure>",
    lambda e: self._fill_pane(self.hotkey_pane, top_spacer, bottom_spacer))
```

The `_fill_pane()` function (per spec §1) recomputes:
```python
def _fill_pane(self, pane, top_spacer, bottom_spacer):
    if not pane.winfo_exists():
        return
    top_spacer.config(height=0)
    bottom_spacer.config(height=0)
    pane.update_idletasks()
    if not pane.winfo_exists():
        return
    available = pane.winfo_height()
    natural = sum(c.winfo_reqheight() for c in pane.winfo_children()
                  if c.winfo_ismapped() and c not in (top_spacer, bottom_spacer))
    extra = max(0, available - natural)
    top_spacer.config(height=int(extra * FILL_TOP_SHARE))  # 0.5 * extra
    bottom_spacer.config(height=extra - int(extra * FILL_TOP_SHARE))
```

### Trigger points (per spec §2)

1. **Live window resize:** `<Configure>` binding on each pane fires continuously as the window is dragged taller/shorter. Each call is idempotent and cheap (no widget teardown, only `Frame.config(height=...)`).

2. **Tab switch:** When `_set_content_tab()` or `_set_settings_tab()` is called, the newly visible pane receives a `<Configure>` event (via Tk's `pack()` call) carrying the current window size. Add one explicit `_fill_pane()` call at the tail of each toggle method for belt-and-suspenders (no dependence on Tk's event dispatch timing).

3. **Eating toggle (Clicking pane only):** When `_select()` calls `eat_section.pack()` or `eat_section.pack_forget()`, no `<Configure>` fires (a mapped pane's children changing visibility does not trigger a parent `<Configure>`). Add an explicit guarded call:
   ```python
   if self._content_tab == "clicking":
       self._fill_pane(self.clicking_pane, *self._clicking_fill)
   ```
   This guard prevents reading stale geometry from a hidden pane.

## Pixel-level specifications

### FILL_TOP_SHARE constant

```python
FILL_TOP_SHARE = 0.5  # Top spacer gets 50% of leftover space (centering),
                      # bottom gets 50%.
                      # Placed with SIDEBAR_RAIL_W/CONTENT_W constants
                      # (around afk_clicker.py:160–161 area).
```

### Scaling at worst-case compound scale (s=0.675)

All measurements scale uniformly by `s`. Example for Hotkey at a tall window (1000px window height at s=1 → 675px at s=0.675):

- Pane's `winfo_height()` at s=1: ~720px (after accounting for title bar, tab bar, padding).
- Pane's `winfo_height()` at s=0.675: ~486px (all dimensions scale together).
- Hotkey card natural height at s=1: ~90px → at s=0.675: ~60px.
- Extra space at s=1: ~630px → at s=0.675: ~426px.
- Top spacer: 50% of 630px = 315px at s=1 → 213px at s=0.675.
- Bottom spacer: 50% of 630px = 315px at s=1 → 213px at s=0.675.

The proportions remain exact; no special-casing needed.

### No new constants needed

All spacer heights are computed from the pane's real `winfo_height()` and its children's `winfo_reqheight()`. There are no additional pixel constants beyond `FILL_TOP_SHARE = 0.5`.

## Component reuse

**Reused unchanged:**
- `card()`, `section()` — no changes.
- `Row`, `Button`, `Segmented`, `NumBox` — no changes.
- `pack()`/`pack_forget()` visibility toggle — exactly as Feature 2 already uses.
- Color tokens: all spacers are `bg=BG`, no new colors.
- `update_idletasks()` pattern — mirrors `card()`'s own `_redraw()` usage.

**New structures:**
- One `_fill_pane()` function (placed near `card()`/`section()` helpers, around line 1371).
- One constant `FILL_TOP_SHARE = 0.5` (placed with sidebar constants, around line 160).
- Four stored spacer-pair tuples: `self._hotkey_fill`, `self._clicking_fill`, `self._appearance_fill`, `self._updates_fill` (or one `self._pane_fills` dict — developer's choice on grouping).

## Accessibility and platform notes

### No change to touch targets or input handling
- Spacers are invisible (`bg=BG`) with no interactive elements — they are pure layout.
- All controls within cards retain their original dimensions and hit-boxes.
- No keyboard navigation affected — spacers carry no focusable elements.

### Color contrast
- Spacers are transparent (no chrome) — no contrast ratio applies.

### Scale interaction
- Worst-case compound scale (s=0.675): all spacer dimensions scale uniformly. Readability is unchanged because the spacers themselves have no text or icons.
- Interaction with existing bugs (G#23, macOS low-DPI): none — this feature's only input is a pane's actual measured geometry, which already scales correctly under G#23 and any future resolution to it.

### Platform-specific behavior
- No platform-specific code needed. `pack()`, `winfo_height()`, `<Configure>` binding all work identically across Linux, macOS, Windows.

## State transitions and edge cases

### Empty pane edge case
A pane with zero cards (not reachable today, but safe regardless): `natural = 0`, `extra = available`, spacers divide the full pane equally. Content would be just the section label centered vertically.

### Reentrant teardown
If `update_idletasks()` inside `_fill_pane()` reentrantly services a pending `_rebuild_ui()` that destroys the pane mid-computation, the two `winfo_exists()` guards (before and after `update_idletasks()`) catch it and return early. Same pattern as `card()`'s `_redraw()`.

### Resizing while a pane is hidden
If Hotkey is hidden (Clicking tab active) and the window is resized, `hotkey_pane`'s spacers go stale — they reflect the old window size. This is invisible (the pane isn't shown) and self-corrects on the next Clicking→Hotkey tab switch via the `<Configure>` event, per spec Empirical grounding #3.

### Game switch while Clicking is hidden
If Hotkey is active and the user switches games (toggling Eating visibility on the hidden Clicking pane), Clicking's spacers don't recompute (no explicit call needed because Clicking isn't active). This is harmless and invisible. Next Clicking-tab switch recomputes correctly.

### Minimum window size (floor case)
At the window's hard minimum (minh = 690 * s), the tallest pane (Clicking with Eating) has `extra ≈ 0` or small rounding, so both spacers are `≤ 1px` — a true no-op, exactly matching today's layout and proving the feature doesn't worsen the floor.

## Traceability to spec acceptance criteria

| Criterion | Design section |
|---|---|
| Floor case (minsize): tallest pane's spacers ≤ 1px | States: Minimum window; spacers calculated as max(0, available - natural) |
| Tall window: short pane's spacers > 0, sum to extra | States: Hotkey at tall window; math: top + bottom = int(extra × 0.5) + (extra - int(...)) = extra ✓ |
| Per-pane measurement, not per-page | States: all panes; each calls _fill_pane independently with its own winfo_height() |
| Dead band is materially smaller | Trade-off section: 630px → 315px (50% reduction) at short panes; ticket criterion satisfied |
| Eating toggle recomputes Clicking's margin | Mechanics: explicit guarded call in _select() after pack()/pack_forget() block |
| Hidden-tab guard prevents cross-pane writes | Mechanics: `if self._content_tab == "clicking"` condition |
| Live resize without rebuild | Mechanics: <Configure> binding, no _request_rebuild() call anywhere in _fill_pane |
| Full suite passes, new tests added | Test impact: deferred to spec's own test section (no design change) |

## Open question: window minimum height

The four panes are empty (315px bands) because the window's minimum height is fixed at `690 * s` regardless of content, and Feature 2's tab split turned one tall page into four short panes. Centering halves the empty band but does not eliminate it. A deeper product question, out of scope for this feature, is whether the window's minimum height should scale with the number and type of tabs visible, or whether a flat `690 * s` floor is the right constraint for this app's use case. This question belongs in the backlog, not here.

## Summary of design decisions

- **FILL_TOP_SHARE = 0.5 (centering):** Distributes extra space equally above and below content. This halves the largest single dead band (630px → 315px on single-card panes), satisfying the ticket's "materially smaller, not merely relocated" criterion. It is the only split value that minimizes the maximum band size.
- **Trade-off: 2× margin variation on tab switches:** Clicking pane has smaller margins (160px each) than Hotkey/Appearance/Updates (315px each) because its content is taller. This is unavoidable: halving the band requires centering, and centering requires margins proportional to content height.
- **Residual limitation: 315px is still large (44% of pane):** This feature improves the layout materially but does not eliminate the empty band. It is an improvement within the scope of a spacer-only mechanism, not a complete solution to empty panes.
- **No visible spacer chrome:** `bg=BG` frames — true empty margin, matching Feature 5's scope.
- **Independent per-pane measurement:** Each pane computes its own `available` and `natural`, never averaged or compared.
- **Three trigger points:** `<Configure>` binding (continuous resize), explicit call in tab-toggle methods (discrete tab switch), explicit guarded call in `_select()` (Eating visibility toggle).
- **Reuse of existing patterns:** `update_idletasks()` guard, `winfo_exists()` checks, `pack()`/`pack_forget()` visibility — all mirror established code.
- **Scale and DPI handling:** Uniform scaling by `s`; no special cases at worst-case compound scale (s=0.675).
