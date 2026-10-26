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
from pathlib import Path

from triage.scenarios import all_scenarios

# Diagnosis-style queries (what an agent searches AFTER forming a hypothesis), labeled by runbook.
# The alert-symptom mode below is mostly ill-posed for choosing settings: most alerts describe a
# symptom that does not name the root cause, so no chunk size can retrieve the right runbook from it.
QUERIES_PATH = Path(__file__).with_name("retrieval_queries.json")


def load_diagnosis_queries(path: Path = QUERIES_PATH) -> list[dict]:
    return json.loads(path.read_text())["queries"]


def _score(retriever, items: list[tuple[str, str, str]], k: int) -> dict:
    """items: (row id, query, expected runbook id)."""
    rows = []
    for row_id, query, want in items:
        docs = [h.doc_id for h in retriever.search(query, max(k, 10))]
        rank = docs.index(want) + 1 if want in docs else None
        rows.append({"scenario": row_id, "expected": want, "rank": rank, "hit": rank is not None and rank <= k,
                     "top": docs[:k]})
    n = len(rows)
    return {"k": k, "n": n, "hit_at_k": round(sum(r["hit"] for r in rows) / n, 3),
            "mrr": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3), "rows": rows}


def retrieval_eval(retriever, k: int = 4, query_of=lambda a: a.symptom) -> dict:
    """Search with alert text for each answerable scenario (what the fixed pipeline does)."""
    return _score(retriever, [(sc.id, query_of(sc.alert), sc.truth.runbook)
                              for sc in all_scenarios() if sc.truth.answerable], k)


def diagnosis_eval(retriever, k: int = 4, queries: list[dict] | None = None) -> dict:
    """Search with the labeled diagnosis-style queries; use this one to compare index settings."""
    qs = queries if queries is not None else load_diagnosis_queries()
    return _score(retriever, [(q["id"], q["query"], q["runbook"]) for q in qs], k)


if __name__ == "__main__":
    from triage.knowledge.index import load_index
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist-dir", default="chroma_db")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--full-alert", action="store_true", help="query with the full alert text instead of just the symptom")
    ap.add_argument("--diagnosis", action="store_true", help="use the labeled diagnosis-style queries")
    a = ap.parse_args()
    if a.diagnosis:
        r = diagnosis_eval(load_index(a.persist_dir), a.k)
    else:
        q = (lambda al: al.as_text()) if a.full_alert else (lambda al: al.symptom)
        r = retrieval_eval(load_index(a.persist_dir), a.k, q)
    for row in r["rows"]:
        print(f"{row['scenario']:42s} expected {row['expected']}  rank={row['rank']}  top={row['top']}")
    print(json.dumps({k: v for k, v in r.items() if k != "rows"}))
