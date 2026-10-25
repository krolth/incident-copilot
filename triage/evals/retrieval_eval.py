"""Retrieval evaluation, separate from the agents: for each answerable incident, does the expected
runbook appear in the top-k passages when searching with the alert text?

Report hit@k and mean reciprocal rank. Use it to compare chunk sizes and embedding models, and to see
how much the postmortem corpus dilutes runbook retrieval. NOTE: the runbooks were written by the
scenario author, so this measures retrieval on a friendly knowledge base; say so in the write-up.
Never report numbers measured with EMBEDDINGS=hash.
"""
from __future__ import annotations

import argparse
import json

from triage.scenarios import all_scenarios


def retrieval_eval(retriever, k: int = 4, query_of=lambda a: a.symptom) -> dict:
    rows = []
    for sc in all_scenarios():
        if not sc.truth.answerable:
            continue
        hits = retriever.search(query_of(sc.alert), max(k, 10))
        docs = [h.doc_id for h in hits]
        want = sc.truth.runbook
        rank = docs.index(want) + 1 if want in docs else None
        rows.append({"scenario": sc.id, "expected": want, "rank": rank, "hit": rank is not None and rank <= k,
                     "top": docs[:k]})
    n = len(rows)
    return {"k": k, "n": n, "hit_at_k": round(sum(r["hit"] for r in rows) / n, 3),
            "mrr": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3), "rows": rows}


if __name__ == "__main__":
    from triage.knowledge.index import load_index
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist-dir", default="chroma_db")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--full-alert", action="store_true", help="query with the full alert text instead of just the symptom")
    a = ap.parse_args()
    q = (lambda al: al.as_text()) if a.full_alert else (lambda al: al.symptom)
    r = retrieval_eval(load_index(a.persist_dir), a.k, q)
    for row in r["rows"]:
        print(f"{row['scenario']:42s} expected {row['expected']}  rank={row['rank']}  top={row['top']}")
    print(json.dumps({k: v for k, v in r.items() if k != "rows"}))
