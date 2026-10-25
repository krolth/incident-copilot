"""Human labels to validate the judge.

  python -m triage.evals.labels export results/runs.jsonl labels.csv     # ~20 stratified runs, blank human columns
  (fill human_action and human_evidence with 0, 1 or 2 by reading each row; do NOT look at the judge columns first)
  python -m triage.evals.labels agreement labels.csv                    # agreement and Cohen's kappa
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

from triage.scenarios import get_scenario


def export(runs_path: str, out_path: str, n: int = 20, seed: int = 7) -> int:
    recs = [json.loads(l) for l in Path(runs_path).read_text().splitlines() if l.strip()]
    recs = [r for r in recs if r.get("judge")]
    rng = random.Random(seed)
    rng.shuffle(recs)
    by_app: dict[str, list] = {}
    for r in recs:
        by_app.setdefault(r["approach"], []).append(r)
    picked: list[dict] = []
    while len(picked) < min(n, len(recs)) and any(by_app.values()):  # round-robin across approaches
        for app in sorted(by_app):
            if by_app[app] and len(picked) < n:
                picked.append(by_app[app].pop())
    rng.shuffle(picked)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "scenario", "reference_action", "answer_category", "answer_action", "answer_summary",
                    "cited_evidence", "human_action", "human_evidence", "judge_action", "judge_evidence"])
        for r in picked:
            sc = get_scenario(r["scenario_id"])
            res = r["result"]
            cited = " | ".join(r["evidence"].get(i.strip("[] "), i) for i in res["evidence_ids"])
            w.writerow([f"{r['scenario_id']}|{r['approach']}|{r['run_idx']}", sc.title, sc.truth.reference_action,
                        res["category"], res["recommended_action"], res["summary"], cited, "", "",
                        r["judge"]["action_alignment"], r["judge"]["evidence_support"]])
    return len(picked)


def cohen_kappa(a: list[int], b: list[int]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(a) | set(b))
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def agreement(path: str) -> dict:
    rows = [r for r in csv.DictReader(open(path)) if r["human_action"].strip() != "" and r["human_evidence"].strip() != ""]
    out = {"n": len(rows)}
    for dim in ("action", "evidence"):
        h = [int(r[f"human_{dim}"]) for r in rows]
        j = [int(r[f"judge_{dim}"]) for r in rows]
        out[dim] = {"exact": round(sum(x == y for x, y in zip(h, j)) / len(rows), 3) if rows else None,
                    "within_1": round(sum(abs(x - y) <= 1 for x, y in zip(h, j)) / len(rows), 3) if rows else None,
                    "kappa": cohen_kappa(h, j)}
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "export":
        print(f"wrote {export(sys.argv[2], sys.argv[3])} rows to {sys.argv[3]}")
    elif len(sys.argv) == 3 and sys.argv[1] == "agreement":
        print(json.dumps(agreement(sys.argv[2]), indent=2))
    else:
        print(__doc__)
