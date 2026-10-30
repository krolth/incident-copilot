"""Human labels to validate the judge.

  python -m triage.evals.labels export results/runs.jsonl labels.csv     # ~20 runs, round-robin across approaches
  (fill human_action and human_evidence with 0, 1 or 2 by reading each row)
  python -m triage.evals.labels agreement labels.csv                    # agreement and Cohen's kappa

The judge's scores go to a separate file (labels.judge.csv) so the labeller never sees them: a label made after
seeing the judge's score is not independent of it.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

from triage.scenarios import get_scenario

MAX_CITED_SHOWN = 15  # one s04 run cited 787 ids; the rest are summarised as a count


def judge_path(labels_path: str) -> Path:
    p = Path(labels_path)
    return p.with_name(p.stem + ".judge" + p.suffix)


def export(runs_path: str, out_path: str, n: int = 20, seed: int = 7) -> int:
    recs = [json.loads(l) for l in Path(runs_path).read_text().splitlines() if l.strip()]
    recs = [r for r in recs if r.get("judge")]
    rng = random.Random(seed)
    rng.shuffle(recs)
    by_app: dict[str, list] = {}
    for r in recs:
        by_app.setdefault(r["approach"], []).append(r)
    # Round-robin across approaches; within each, take the run whose scenario has the fewest picks so far, so 20
    # labels cover all 18 scenarios instead of clustering on whichever ones the shuffle favoured.
    picked: list[dict] = []
    per_scenario: Counter = Counter()
    while len(picked) < min(n, len(recs)) and any(by_app.values()):
        for app in sorted(by_app):
            if by_app[app] and len(picked) < n:
                r = min(by_app[app], key=lambda x: per_scenario[x["scenario_id"]])
                by_app[app].remove(r)
                per_scenario[r["scenario_id"]] += 1
                picked.append(r)
    rng.shuffle(picked)
    with open(out_path, "w", newline="") as f, open(judge_path(out_path), "w", newline="") as fj:
        w, wj = csv.writer(f), csv.writer(fj)
        w.writerow(["key", "scenario", "reference_action", "answer_category", "answer_action", "answer_summary",
                    "cited_evidence", "human_action", "human_evidence"])
        wj.writerow(["key", "judge_action", "judge_evidence"])
        for r in picked:
            sc = get_scenario(r["scenario_id"])
            res = r["result"]
            key = f"{r['scenario_id']}|{r['approach']}|{r['run_idx']}"
            ids = res["evidence_ids"]
            cited = [r["evidence"].get(i.strip("[] "), i) for i in ids[:MAX_CITED_SHOWN]]
            if len(ids) > MAX_CITED_SHOWN:
                cited.append(f"... and {len(ids) - MAX_CITED_SHOWN} more ids")
            w.writerow([key, sc.title, sc.truth.reference_action, res["category"], res["recommended_action"],
                        res["summary"], " | ".join(cited), "", ""])
            wj.writerow([key, r["judge"]["action_alignment"], r["judge"]["evidence_support"]])
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
    judge = {r["key"]: r for r in csv.DictReader(open(judge_path(path)))}
    rows = [r | {k: v for k, v in judge[r["key"]].items() if k != "key"} for r in csv.DictReader(open(path))
            if r["human_action"].strip() != "" and r["human_evidence"].strip() != ""]
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
