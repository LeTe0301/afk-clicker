# Session handoff

<!-- Rewritten (not appended) by every session at wrap-up — see session-lifecycle.md in
     admin/agent-knowledge. Keep exactly these six sections. -->

Updated: 2026-10-20 by the repo-hygiene agent (admin/afk-clicker#68)

## State

`main` is at `8d5255f` on both `github` and `origin`. The last product work, G#63–G#67,
is merged and closed (2026-10-11). The open tickets — G#59, G#39, G#46, G#47 — are waiting
on real hardware or on a decision by Leo (`backlog.md`). Earlier session handoffs, up to
2026-10-11, are still in `backlog.md`, under "Session handoff — …".

## In flight

| Branch | Worktree | PR | Gitea | GitHub |
|---|---|---|---|---|
| `feature/afk-68/repo-hygiene` | `~/worktrees/afk-68` | see GitHub issue #121 | admin/afk-clicker#68 | #121 |

## Verified

| Command | Result |
|---|---|
| `python afk_clicker.py --selftest` (CT110, Xvfb) | exit 0 |
| `unittest -v tests.test_hotkey` / `tests.test_updater` / `tests.test_ui` (CT110, each on its own Xvfb) | 39 OK / 78 OK (5 skipped) / 483 OK |
| `AFK_SLOW_TESTS=1 unittest -v tests.test_chords_slow` (CT110, own Xvfb) | 5 OK |

## Not verified and why

- The combined `unittest discover -s tests -t .` in one process fails on CT110 from
  `test_ui.SettingsNavigation` onward and then hangs; each module passes alone, and CI is
  green. Not attributed (pynput 1.8.2 in the CT110 venv vs the pinned 1.7.7 is one
  candidate). `xvfb-run` does not work on CT110 (`xauth` missing).
- PyInstaller builds — not installed on CT110, and Windows and macOS builds exist only on
  their own CI runners.

## Next steps

1. Review and merge the hygiene PR (admin/afk-clicker#68 / GitHub #121).

## Questions for Leo

none
