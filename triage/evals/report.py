"""Summarize a results directory into report.md: per-approach table, per-incident matrix,
run-to-run variance, and a list of failures to read by hand (the failure analysis starts there).

  python -m triage.evals.report results
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _fmt(x, pct=False, nd=2):
    if x is None:
        return "n/a"
    return f"{x * 100:.0f}%" if pct else f"{x:.{nd}f}"


def build_report(out_dir: str) -> str:
    d = Path(out_dir)
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
    recs = [json.loads(l) for l in (d / "runs.jsonl").read_text().splitlines() if l.strip()]
    by_app = defaultdict(list)
    for r in recs:
        by_app[r["approach"]].append(r)
    L: list[str] = []
    if meta.get("fake"):
        L += ["> **FAKE MODEL RUN: NOT EVALUATION DATA.** Produced by a scripted oracle to test the plumbing.", ""]
    L += [f"# Results: {out_dir}", "",
          f"- model: `{meta.get('model')}`  judge: `{meta.get('judge_model')}`  embeddings: `{meta.get('embeddings')}`",
          f"- scenario fingerprint: `{meta.get('scenario_fingerprint')}`  runs per cell: {meta.get('runs_per_cell')}  timestamp: {meta.get('timestamp')}", ""]

    L += ["## By approach", "",
          "| approach | runs | valid | category acc | abstention ok | runbook acc | judge action (0-2) | judge evidence (0-2) | citation valid | key evidence cited | tool calls | LLM calls | retries/run | tokens in/out | cost/run | latency s |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for app in sorted(by_app):
        rs = by_app[app]
        s = [r["score"] for r in rs]
        j = [r["judge"] for r in rs if r.get("judge")]
        L.append("| " + " | ".join([
            app, str(len(rs)), _fmt(_mean([x["valid"] for x in s]), True), _fmt(_mean([x["category_correct"] for x in s]), True),
            _fmt(_mean([x["abstention_correct"] for x in s]), True), _fmt(_mean([x["runbook_correct"] for x in s]), True),
            _fmt(_mean([x["action_alignment"] for x in j])), _fmt(_mean([x["evidence_support"] for x in j])),
            _fmt(_mean([x["citation_valid_rate"] for x in s]), True), _fmt(_mean([x["key_cited"] for x in s]), True),
            _fmt(_mean([x["tool_calls"] for x in s]), nd=1), _fmt(_mean([x["llm_calls"] for x in s]), nd=1),
            _fmt(_mean([x.get("retries", 0) for x in s]), nd=2),
            f"{_mean([x['input_tokens'] for x in s]):.0f}/{_mean([x['output_tokens'] for x in s]):.0f}",
            ("$" + _fmt(_mean([x["cost_usd"] for x in s]), nd=4)) if _mean([x["cost_usd"] for x in s]) is not None else "n/a",
            _fmt(_mean([x["latency_s"] for x in s]), nd=1)]) + " |")
    L += ["", "retries/run: model calls re-tried after an error (empty or invalid reply, server error); see `with_retries`.",
          "Judge columns are only meaningful once judge/human agreement has been measured (`python -m triage.evals.labels agreement`).", ""]

    # variance across repeats: accuracy of each repeat index, then spread
    L += ["## Run-to-run variance (category accuracy per repeat)", "", "| approach | per-repeat accuracy | std dev |", "|---|---|---|"]
    for app in sorted(by_app):
        per = defaultdict(list)
        for r in by_app[app]:
            per[r["run_idx"]].append(r["score"]["category_correct"])
        accs = [sum(v) / len(v) for _, v in sorted(per.items())]
        L.append(f"| {app} | {', '.join(f'{a * 100:.0f}%' for a in accs)} | {(st.pstdev(accs) * 100 if len(accs) > 1 else 0):.1f} pts |")
    L.append("")

    # per-incident matrix
    scs = sorted({r["scenario_id"] for r in recs})
    apps = sorted(by_app)
    L += ["## Per incident (correct category / runs)", "", "| incident | " + " | ".join(apps) + " |", "|---|" + "---|" * len(apps)]
    for sid in scs:
        cells = []
        for app in apps:
            rs = [r for r in by_app[app] if r["scenario_id"] == sid]
            cells.append(f"{sum(r['score']['category_correct'] for r in rs)}/{len(rs)}")
        L.append(f"| {sid} | " + " | ".join(cells) + " |")
    L.append("")

    # failures to read
    L += ["## Runs to read by hand", ""]
    bad = [r for r in recs if not r["score"]["category_correct"] or r["error"] or r["score"]["invalid_citations"]]
    if not bad:
        L.append("None.")
    for r in sorted(bad, key=lambda r: (r["scenario_id"], r["approach"], r["run_idx"])):
        why = []
        if r["error"]:
            why.append("error: " + r["error"][:100])
        else:
            if not r["score"]["category_correct"]:
                why.append(f"category {r['result']['category']}")
            if r["score"]["invalid_citations"]:
                why.append(f"{r['score']['invalid_citations']} invalid citation(s)")
        L.append(f"- `{r['scenario_id']}` {r['approach']} #{r['run_idx']}: " + "; ".join(why))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "results"
    text = build_report(out)
    (Path(out) / "report.md").write_text(text)
    print(text)
