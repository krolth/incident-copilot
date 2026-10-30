"""Interactive grader for a label sheet: shows one run at a time and asks for the two scores.

  python -m triage.evals.grade labels.csv

Saves after every answer, so you can quit (q) and pick up where you left off. Rows that already have both
scores are skipped. It never reads the judge's file (labels.judge.csv), and it hides which approach produced
the answer, so neither can colour your score.
"""
from __future__ import annotations

import csv
import shutil
import sys
import textwrap
from pathlib import Path

from triage.scenarios import get_scenario

RUBRIC = """\
ACTION    2 = leads to the same mitigation as the reference
          1 = partly right or incomplete
          0 = wrong, unsafe, or missing
EVIDENCE  2 = the cited evidence fully supports what the agent CLAIMED (even if the claim is wrong)
          1 = partly supports it
          0 = does not support it, or nothing relevant is cited"""

BOLD, DIM, RESET = ("\033[1m", "\033[2m", "\033[0m") if sys.stdout.isatty() else ("", "", "")


def wrap(text: str, indent: str = "  ", first: str | None = None) -> str:
    width = min(100, shutil.get_terminal_size().columns)
    return "\n".join(textwrap.fill(p, width, initial_indent=first or indent, subsequent_indent=indent) or indent
                     for p in text.splitlines() or [""])


def show(row: dict, pos: int, total: int) -> None:
    sc = get_scenario(row["key"].split("|")[0])
    print("\n" + "=" * 72)
    print(f"{BOLD}Run {pos} of {total}: {sc.title}{RESET}  {DIM}({sc.difficulty}){RESET}")
    print(f"\n{BOLD}ALERT{RESET}")
    print(wrap(sc.alert.as_text()))
    print(f"\n{BOLD}REFERENCE ACTION (correct mitigation){RESET}")
    print(wrap(row["reference_action"]))
    print(f"\n{BOLD}AGENT'S ANSWER{RESET}")
    print(f"  category: {row['answer_category']}")
    print(f"  action:\n{wrap(row['answer_action'], '    ')}")
    print(f"  summary:\n{wrap(row['answer_summary'], '    ')}")
    print(f"\n{BOLD}CITED EVIDENCE{RESET}")
    for item in [i for i in row["cited_evidence"].split(" | ") if i.strip()] or ["(nothing cited)"]:
        print(wrap(item, "    ", first="  - ")[:2000])


def ask(prompt: str) -> str:
    while True:
        a = input(prompt).strip().lower()
        if a in ("0", "1", "2", "s", "q", "?"):
            return a
        print("  type 0, 1 or 2 (s = skip, q = save and quit, ? = rubric)")


def score(prompt: str) -> str:
    while True:
        a = ask(prompt)
        if a != "?":
            return a
        print(RUBRIC)


def main(path: str) -> None:
    p = Path(path)
    rows = list(csv.DictReader(open(p)))
    fields = list(rows[0])
    todo = [i for i, r in enumerate(rows) if not (r["human_action"].strip() and r["human_evidence"].strip())]
    print(f"{len(rows) - len(todo)} of {len(rows)} already scored; {len(todo)} to go.\n")
    print(RUBRIC)
    for n, i in enumerate(todo, 1):
        show(rows[i], len(rows) - len(todo) + n, len(rows))
        print()
        a = score(f"{BOLD}action score{RESET} (0/1/2, s skip, q quit, ? rubric): ")
        if a in ("s", "q"):
            if a == "q":
                break
            continue
        e = score(f"{BOLD}evidence score{RESET} (0/1/2, s skip, q quit, ? rubric): ")
        if e in ("s", "q"):
            if e == "q":
                break
            continue
        rows[i]["human_action"], rows[i]["human_evidence"] = a, e
        with open(p, "w", newline="") as f:  # save after every row
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    left = sum(not (r["human_action"].strip() and r["human_evidence"].strip()) for r in rows)
    print(f"\nSaved. {len(rows) - left} of {len(rows)} scored." + ("" if left else " All done."))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
    else:
        main(sys.argv[1])
