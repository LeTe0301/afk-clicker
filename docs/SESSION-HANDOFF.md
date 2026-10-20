# Session handoff

<!-- Rewritten (not appended) by every session at wrap-up — see session-lifecycle.md in
     admin/agent-knowledge. Keep exactly these six sections. -->

Updated: 2026-10-20 by the repo-hygiene agent (admin/afk-clicker#68)

## State

`main` is at `8d5255f` on both `github` and `origin`. The last product work, G#63–G#67,
is merged and closed (2026-10-11). The open tickets — G#59, G#39, G#46, G#47 — are waiting
on real hardware or on a decision by Leo (`backlog.md`). Earlier session handoffs, up to
2026-10-11, stay in `backlog.md`, under "Session handoff — …" (Leo, 2026-10-20).

## In flight

| Branch | Worktree | PR | Gitea | GitHub |
|---|---|---|---|---|
| `feature/afk-68/repo-hygiene` | `~/worktrees/afk-68` | #122 (review: MERGE, wording round done) | admin/afk-clicker#68 | #121 |

## Verified

| Command | Result |
|---|---|
| `python afk_clicker.py --selftest` (CT110, Xvfb) | exit 0 |
| `unittest -v tests.test_hotkey` / `tests.test_updater` / `tests.test_ui` (CT110, each on its own Xvfb) | 39 OK / 78 OK (5 skipped) / 483 OK |
| `AFK_SLOW_TESTS=1 unittest -v tests.test_chords_slow` (CT110, own Xvfb) | 5 OK |
| Combined `unittest discover -s tests -t . -v` in one process (CT110, PR #122 review) | 605 OK (10 skipped) in 2 of 3 runs |

## Not verified and why

- The combined `unittest discover -s tests -t .` in one process **intermittently wedges**
  on CT110 (2 of 2 author runs, 1 of 3 review runs). The cause is a lock wedge in the
  game-scan path, not pynput: the shared Xlib connection is closed without
  `_x11_display_lock`, a scan thread stalls holding it, and every later UI test's settle
  fails — G#69 / GH#123. Workaround: run the test modules separately. `xvfb-run` does not work on
  CT110 (`xauth` missing).
- PyInstaller builds — not installed on CT110, and Windows and macOS builds exist only on
  their own CI runners.

## Next steps

1. Leo merges PR #122 (merge commit message carries `Closes #121`); close Gitea #68 by
   hand, since Gitea does not see the GitHub merge.
2. Follow-ups: the scan-lock wedge (G#69 / GH#123); `-maxclients 2048` in `release.yml`
   and pinning `softprops/action-gh-release` to a full commit SHA (G#70 / GH#124).

## Questions for Leo

None open. Answered by Leo on 2026-10-20:

- **Release gate for this desktop app:** before approving the `release` environment gate,
  click through the CI-built Windows artifact by hand.
- **`docs/history/` file names** keep the `ac-<n>-…` scheme.
- **Old session handoffs** stay in `backlog.md`.
- **Gitea `admin/afk-clicker`** stays issues-only (its git repo is a placeholder).
