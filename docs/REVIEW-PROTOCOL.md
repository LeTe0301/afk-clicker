# Review protocol — ten rounds

The review agent runs every pull request through these ten rounds, in order,
before anything is merged. Each round is a different lens; a change that
survives one can still fail the next, which is the point of separating them.

**Every round produces exactly one verdict:**

| Verdict | Meaning |
|---|---|
| `PASS` | Nothing found under this lens. |
| `CONCERN` | Worth fixing, does not block a merge on its own. |
| `BLOCKER` | Must be fixed before merge. |

A verdict without evidence is not a verdict. Quote the file and line, or say
what you ran. **"Looks fine" is not a review** — if a round genuinely has
nothing to examine (no threading in the diff, say), state that explicitly:
`PASS — no threaded code touched`.

The three reference documents are the standard. Where this protocol and a
reference document disagree, the reference document wins:

- `docs/TECHSTACK.md` — constraints that were paid for once already
- `docs/CODING-GUIDELINES.md` — how the code is written and why
- `docs/ROADMAP.md` — what is planned, and what is explicitly not

---

## Round 1 — Ticket fidelity

Does the change do what the ticket says, and only that?

Read the linked issue first. Flag work that exceeds the ticket as much as work
that falls short of it: an unrelated refactor riding along in a bug-fix PR
makes both harder to review and impossible to revert cleanly. Check the branch
name matches `feature/{ab}-{ticket}/{description}` or
`hotfix/{ab}-{ticket}/{description}`, and that the ticket number is real.

## Round 2 — Correctness

Walk the changed logic and find the input that breaks it.

Off-by-one, empty collections, `None`, a value that is zero when the code
assumes truthy, a loop that never terminates. State a concrete failing case —
inputs and the wrong result — not a category of concern. If you cannot name a
failing case, the finding is speculation, and speculation is a `CONCERN` at
most.

## Round 3 — Threading and Tk safety

`CODING-GUIDELINES.md`: **only the main thread may touch Tk.** Not a widget,
not a `StringVar`, not `root.after()`.

Check every new or moved line that runs off the main thread:
- Does it read a widget or a Tk variable? It must read the settings snapshot.
- Does it schedule UI work? It must go through `_ui()`.
- Does a new repeating `after()` job get cancelled in `on_close`?
- Can two workers exist at once? `start()` joins the old one for a reason.

This round has caught a silent worker-thread death before. Treat a violation as
a `BLOCKER` even when the code appears to work.

## Round 4 — Naming and shadowing

Does any new name shadow an import, a builtin, or an existing class?

The Tk widget class `Button` once shadowed `pynput.mouse.Button` and turned
every `Button.right` in the click loop into a latent `AttributeError` that only
the eating path reached. Check the module namespace, not just the diff.

## Round 5 — Untrusted input

Anything from disk, the network, or a text field is untrusted.

- Is a parse wrapped in `try/except` where it should be **validated**?
  `{"keys": "nope"}` raises nothing: iterating a string yields characters and
  builds a plausible object out of garbage.
- Does a corrupt config start from defaults instead of blocking startup?
- Does a numeric field get clamped at the point of use, not at entry?
- Does downloaded content get executed without a check?

## Round 6 — Tech stack conformance

`TECHSTACK.md` is not a list of preferences.

- A new third-party dependency is a `BLOCKER` unless the PR argues it and the
  ticket agreed to it beforehand.
- Build flags: no `--onefile`, no UPX, every pynput backend in
  `--hidden-import`, `--selftest` still exercised.
- Anything resolved at import time needs a matching hidden import.

## Round 7 — Cross-platform behaviour

The project ships Windows, Linux and macOS from one source file.

For each changed code path, ask what it does on the other two. Path
separators, `%APPDATA%` versus `~/.config`, the `.app` bundle nesting, X11
versus Wayland, `ditto` versus `zip`. A platform branch with no `else` is a
finding. macOS is the least verified target — changes touching it deserve
scepticism, and say so plainly rather than implying coverage that does not
exist.

## Round 8 — Tests

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
- Is a slow test in the right place — the release suite, not the PR suite?

## Round 9 — Comments and documentation

`CODING-GUIDELINES.md`: comment the **why**, never the what.

- Does every non-obvious constant carry its reason?
- Is there a comment that merely restates the code? That is noise; flag it.
- Did behaviour change without the README changing?
- If a constraint was discovered here, is it written down where the next person
  will look — or only in this PR's description, where it will be lost?

## Round 10 — Roadmap and release readiness

- Does this move something on `ROADMAP.md`? Update it if so.
- Does it do something the roadmap explicitly rules out? That is a `BLOCKER`
  regardless of quality.
- Versioning: below `1.0.0`, minor and patch only. A fix to a released version
  is a patch on its own tag.
- Does the settings format change? Without a schema version there is no
  migration path, and users lose their per-game values silently.

---

## Reporting

Post one comment on the pull request containing all ten rounds, in order, each
with its verdict and evidence. Then a closing block:

```
VERDICT: MERGE | ANOTHER ROUND
BLOCKERS: <count>
CONCERNS: <count>
```

`ANOTHER ROUND` whenever there is at least one `BLOCKER`. With only concerns,
recommend `MERGE` and list them — the product manager decides whether they wait.

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

Then notify the product manager with the verdict and the single most important
finding. The decision to merge is theirs, not the review agent's.
