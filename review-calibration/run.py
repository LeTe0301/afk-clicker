#!/usr/bin/env python3
"""
Calibration harness for the review agent.

    run.py --list                     what the ten cases are, without spoilers
    run.py --case 03                  the material a reviewer gets
    run.py --key 03                   the answer key -- graders only
    run.py --score 03 report.md       a worksheet for grading one report
    run.py --tally results.json       the score across cases

The split matters: --case must be safe to paste in front of the agent being
calibrated, and --key must never be. They are separate commands so that
mixing them up takes an act of will rather than a typo.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "cases")

ROW = re.compile(r"^\|\s*(\d\d-[a-z])\s*\|\s*(\d+)\s*\|\s*(\w+)\s*\|\s*(.+?)\s*\|\s*$", re.M)
TRAP = re.compile(r"^\|\s*(\d\d-[x-z])\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", re.M)


def case_ids():
    return sorted(d for d in os.listdir(CASES) if d.isdigit())


def read(case, name):
    with open(os.path.join(CASES, case, name), encoding="utf-8") as fh:
        return fh.read()


def answer(case):
    """
    Decode the key.

    Stored base64 rather than plain Markdown because the first calibration run
    leaked one: the agent grepped the repo for a symbol that appears in a case
    and the plaintext answer matched. Asking people not to grep is not a
    control; making the file unmatchable is.
    """
    import base64
    lines = [l for l in read(case, "ANSWER.b64").splitlines()
             if l and not l.startswith("#")]
    return base64.b64decode("".join(lines)).decode("utf-8")


def defects(case):
    """[(id, round, severity, text)] from the answer key."""
    return [m.groups() for m in ROW.finditer(answer(case))]


def traps(case):
    return [m.groups() for m in TRAP.finditer(answer(case))]


def cmd_list():
    print(f"{'case':<6}{'defects':<9}{'blockers':<10}{'traps':<7}first line of the PR")
    for case in case_ids():
        found = defects(case)
        blockers = sum(1 for d in found if d[2] == "BLOCKER")
        title = next(l for l in read(case, "PR.md").splitlines() if l.startswith("# "))
        print(f"{case:<6}{len(found):<9}{blockers:<10}{len(traps(case)):<7}{title[2:]}")


def cmd_case(case):
    print(f"===== review-calibration/cases/{case}/PR.md =====\n")
    print(read(case, "PR.md"))
    print(f"\n===== review-calibration/cases/{case}/feature.py =====\n")
    print(read(case, "feature.py"))


def cmd_key(case):
    print(answer(case))


def cmd_score(case, report_path):
    """
    A worksheet, not a verdict.

    The keyword hint is deliberately weak -- it exists to point a grader at the
    right paragraph, never to decide. A scorer that matched on keywords would
    reward a report that name-drops the right nouns without understanding, and
    that is precisely the failure mode this suite is meant to detect.
    """
    with open(report_path, encoding="utf-8") as fh:
        report = fh.read().lower()

    print(f"# Scoring worksheet — case {case}\n")
    print(f"Report: {report_path}\n")
    print("Mark each: FOUND / PARTIAL / MISSED. The hint is a pointer, not a verdict.\n")
    print(f"| id | round | severity | hint | verdict | defect |")
    print(f"|---|---|---|---|---|---|")
    for did, rnd, sev, text in defects(case):
        words = [w for w in re.findall(r"[a-z_]{5,}", text.lower())][:6]
        hit = sum(1 for w in words if w in report)
        hint = "·" * hit or "—"
        print(f"| {did} | {rnd} | {sev} | {hint} | | {text[:90]} |")
    print("\n## False positives\n")
    print("Anything the report flags that is not above. These two are planted:\n")
    for tid, looks, why in traps(case):
        print(f"- **{tid}** — {looks} → {why}")
    print("\n## Result line to append to results.json\n")
    print(json.dumps({"case": case, "found": [], "partial": [], "missed": [],
                      "false_positives": []}, indent=2))


def cmd_tally(path):
    with open(path, encoding="utf-8") as fh:
        results = json.load(fh)
    total_d = total_f = total_p = total_fp = 0
    print(f"{'case':<6}{'found':<8}{'partial':<9}{'missed':<8}{'false+':<8}score")
    for r in results:
        found = defects(r["case"])
        n = len(found)
        f, p, fp = len(r["found"]), len(r["partial"]), len(r["false_positives"])
        missed = n - f - p
        # A partial counts as half; a false positive costs a full defect,
        # because a reviewer that flags everything is as useless as one that
        # flags nothing.
        score = max(0.0, (f + 0.5 * p - fp) / n) if n else 0.0
        total_d += n; total_f += f; total_p += p; total_fp += fp
        print(f"{r['case']:<6}{f:<8}{p:<9}{missed:<8}{fp:<8}{score:.0%}")
    overall = max(0.0, (total_f + 0.5 * total_p - total_fp) / total_d) if total_d else 0.0
    print(f"\n{total_d} planted defects across {len(results)} cases — overall {overall:.0%}")
    print("\nEvery miss is a gap in docs/REVIEW-PROTOCOL.md, not a mark against")
    print("the agent. Turn it into a sharper question there, then run again.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--case", metavar="NN")
    g.add_argument("--key", metavar="NN")
    g.add_argument("--score", nargs=2, metavar=("NN", "REPORT"))
    g.add_argument("--tally", metavar="RESULTS.JSON")
    args = ap.parse_args()

    if args.list:
        cmd_list()
    elif args.case:
        cmd_case(args.case.zfill(2))
    elif args.key:
        cmd_key(args.key.zfill(2))
    elif args.score:
        cmd_score(args.score[0].zfill(2), args.score[1])
    elif args.tally:
        cmd_tally(args.tally)


if __name__ == "__main__":
    sys.exit(main())
