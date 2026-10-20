# Review protocol — one pass, in depth

Every pull request gets **one** in-depth review before merge, by the `reviewer`
agent in PR mode. The lenses below are the checklist for that single pass — not
separate reviews. Each is a different way of looking at the same diff; a change
that survives one can still fail the next, which is why they are listed
separately rather than blurred into "review the code".

Depth is the point. One lens examined properly, with something actually run,
beats ten passes that each re-read the diff. The ten-round loop this document
used to describe existed to refine the reviewer agent itself, not as a
per-pull-request procedure.

**Every lens produces exactly one verdict:**

| Verdict | Meaning |
|---|---|
| `PASS` | Nothing found under this lens. |
| `CONCERN` | Worth fixing, does not block a merge on its own. |
| `BLOCKER` | Must be fixed before merge. |

A verdict without evidence is not a verdict. Quote the file and line, or say
what you ran. **"Looks fine" is not a review** — if a lens genuinely has
nothing to examine (no threading in the diff, say), state that explicitly:
`PASS — no threaded code touched`. Saying so is a real answer; skipping it
silently is not.

The three reference documents are the standard. Where this protocol and a
reference document disagree, the reference document wins:

- `docs/TECHSTACK.md` — constraints that were paid for once already
- `docs/CODING-GUIDELINES.md` — how the code is written and why
- `docs/ROADMAP.md` — what is planned, and what is explicitly not

---

## 1. Ticket fidelity

Does the change do what the ticket says, and only that?

Read the linked Gitea issue (`admin/afk-clicker#n`) and its GitHub mirror
first — the two numbers differ (`backlog.md` writes them **G#** / **GH#**).
Flag work that exceeds the ticket as much as work that falls short of it: an
unrelated refactor riding along in a bug-fix PR makes both harder to review and
impossible to revert cleanly. Check the branch name matches
`feature/afk-{ticket}/{description}` or `hotfix/afk-{ticket}/{description}` —
or an older `ac-{ticket}` name opened before 2026-10-20 — and that the ticket
number is real.

## 2. Correctness

Walk the changed logic and find the input that breaks it.

Off-by-one, empty collections, `None`, a value that is zero when the code
assumes truthy, a loop that never terminates. State a concrete failing case —
inputs and the wrong result — not a category of concern. If you cannot name a
failing case, the finding is speculation, and speculation is a `CONCERN` at
most.

## 3. Security and access

There is no server and no account here. The boundary is what the program
downloads and executes, and the one write token in the release pipeline.

- **The updater** downloads a release archive over HTTPS and then executes it.
  Does the change keep the `SHA256SUMS` check before anything is extracted, the
  refusal of a release that publishes no checksums, and the refusal of archive
  entries that escape the staging directory (`ROADMAP.md`, "Update integrity")?
- **Anything from the network that reaches `write_swap_script`** is validated
  at the source, not escaped downstream. A GitHub release tag once flowed
  unvalidated into the generated swap script — a command injection
  (`docs/history/README.md`, G#36).
- **Workflows:** an `${{ }}` expression inside a `run:` script is pasted in as
  text before the shell parses it, so inputs go through `env:`. Permissions are
  declared per job and only `publish` holds `contents: write`; an action that
  holds a write token is pinned (`release.yml`).
- Secrets in code, logs, the bundle or a URL are a `BLOCKER`.

Is there a test proving the *refusal* — a tampered archive, an escaping entry,
a hostile tag — and not only the success?

## 4. Untrusted input and failure behaviour

Anything from disk, the network, or a text field is untrusted.

- Is a parse wrapped in `try/except` where it should be **validated**?
  `{"keys": "nope"}` raises nothing: iterating a string yields characters and
  builds a plausible object out of garbage.
- Does a corrupt config start from defaults instead of blocking startup?
- Does a numeric field get clamped at the point of use, not at entry?
- Does downloaded content get executed without a check?

Then the failure path (`CODING-GUIDELINES.md`, "Failure behaviour"): does a
failure say what went wrong and what would fix it — "GitHub unreachable" and
"no release published" are different problems? Does every exit path leave
nothing half-done: no mouse button or key still held (`_release_right()` and
`MacroRunner` release in a `finally`), no `settings.json.tmp` left behind
(G#41)?

## 5. Tests

**First, mechanically: is there a test at all?** Name the file and the test, or
write `no test`. This question comes first because the calibration run showed
it is the one that gets skipped when the code has louder problems — three
missing-test findings were walked past in changes that had a threading bug or a
crash to look at instead. A loud defect is not a reason to stop counting.

Then: every fix lands with a test that fails without it.

- Does the test actually fail if you revert the fix? Say whether you checked.
- Does it assert a property, or does it assert the harness? Under Xvfb, XTEST
  delivers every synthetic press **twice** — exact fire counts across several
  presses measure the harness.
- Do network tests skip cleanly offline rather than failing?
- Is a slow test in the right place — the release suite (`AFK_SLOW_TESTS=1`),
  not the PR suite?
- Did you run the suite (the commands are in `AGENTS.md`), and what was the
  result? Say which platforms the evidence covers — a local Linux run is not
  the Windows or macOS result; the PR's CI matrix is.

## 6. Tech stack conformance

`TECHSTACK.md` is not a list of preferences.

- A new third-party dependency is a `BLOCKER` unless the PR argues it and the
  ticket agreed to it beforehand.
- Build flags: no `--onefile`, no UPX, every pynput backend in
  `--hidden-import`, `--selftest` still exercised.
- Anything resolved at import time needs a matching hidden import.
- The PyInstaller `--name "AFK Farm Clicker"` stays: every installed copy's
  swap script relaunches that exact path (`release.yml`,
  `docs/history/ac-33-implementation.md`).

## 7. Comments and documentation

`CODING-GUIDELINES.md`: comment the **why**, never the what.

- Does every non-obvious constant carry its reason?
- Is there a comment that merely restates the code? That is noise; flag it.
- Did behaviour change without the README or `AGENTS.md` changing?
- If a constraint was discovered here, is it written down where the next person
  will look — or only in this PR's description, where it will be lost?
- Does a comment cite a per-cycle doc (`docs/spec.md`, `docs/test-review.md`,
  …)? Those are never committed; the citation must point at the archived copy
  in `docs/history/` (`docs/history/README.md`).

## 8. Scope, roadmap and release readiness

- Does this move something on `ROADMAP.md`? Update it if so.
- Does it do something the roadmap explicitly rules out? That is a `BLOCKER`
  regardless of quality.
- Versioning: below `1.0.0`, minor and patch only. A fix to a released version
  is a patch on its own tag. The version source is `afk_clicker.py`'s
  `__version__`, which must match the `release/{version}` branch.
- Does the settings format change? Without a `SETTINGS_VERSION` bump and a
  migration in `_SETTINGS_MIGRATIONS` there is no migration path, and users
  lose their per-game values silently.

## Simplicity (ponytail-review)

Run `ponytail:ponytail-review` on the diff and fold its findings into one
verdict here: reinvented standard library, unneeded dependencies, speculative
abstraction, dead flexibility. Judge each finding yourself — a cut that would
break a test convention or an acceptance criterion is not a finding.

## Domain lenses

### Threading and Tk safety

`CODING-GUIDELINES.md`: **only the main thread may touch Tk.** Not a widget,
not a `StringVar`, not `root.after()`.

Check every new or moved line that runs off the main thread:
- Does it read a widget or a Tk variable? It must read the settings snapshot.
- Does it schedule UI work? It must go through `_ui()`.
- Does a new repeating `after()` job get cancelled in `on_close`?
- Can two workers exist at once? `start()` joins the old one for a reason.

This lens has caught a silent worker-thread death before. Treat a violation as
a `BLOCKER` even when the code appears to work.

### Naming and shadowing

Does any new name shadow an import, a builtin, or an existing class?

The Tk widget class `Button` once shadowed `pynput.mouse.Button` and turned
every `Button.right` in the click loop into a latent `AttributeError` that only
the eating path reached. Check the module namespace, not just the diff.

### Cross-platform behaviour

The project ships Windows, Linux and macOS from one source file.

For each changed code path, ask what it does on the other two. Path
separators, `%APPDATA%` versus `~/.config`, the `.app` bundle nesting, X11
versus Wayland, `ditto` versus `zip`. A platform branch with no `else` is a
finding. macOS is the least verified target — changes touching it deserve
scepticism, and say so plainly rather than implying coverage that does not
exist.

---

## Reporting

Post **one** comment on the pull request: every lens in order, each with its
verdict and evidence, then:

```
VERDICT: MERGE | ANOTHER ROUND
BLOCKERS: <count>
CONCERNS: <count>
MOST IMPORTANT: <one sentence>
```

`ANOTHER ROUND` whenever there is at least one `BLOCKER`. It means **this pull
request needs more work, and then a fresh review of what changed** — never
re-reviewing the same diff a second time. When the fix lands, review the
changed code in depth and say explicitly which lenses the change could not have
affected. With only concerns, recommend `MERGE` and list them — the product
manager decides whether they wait.

**Say where you were uncertain.** A finding you are sure of and a finding you
are guessing at look identical in a list, and the difference is what tells the
reader whether to go and check. If a severity was a judgement call, say it was.
If you could not reproduce something, say that rather than softening the wording
until it sounds reproduced.

**Disclose anything that compromised the review.** If you saw something you
should not have — an answer, a spoiler, a previous reviewer's notes — say so,
even where it costs you. A review whose provenance is unclear is worth less
than a shorter one that is clean, and the first calibration run was salvaged
only because the agent volunteered two such disclosures unprompted.

Then notify the product manager (Leo) with the verdict and the single most
important finding. The decision to merge is his, not the review agent's.
