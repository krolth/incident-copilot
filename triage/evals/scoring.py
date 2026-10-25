"""Deterministic scoring of one run against its scenario's ground truth. No model involved.

Metrics per run:
  valid               the run produced a TriageResult (no exception)
  category_correct    category matches ground truth (unanswerable incidents expect insufficient_evidence)
  abstention_correct  abstained exactly when the incident is unanswerable
  component_correct   named component matches an accepted alias (answerable incidents only)
  runbook_correct     recommended runbook matches the reference runbook
  citation_valid_rate share of cited evidence ids that the agent was actually shown (None if it cited nothing)
  invalid_citations   count of cited ids never shown by any tool (fabricated or mis-copied)
  key_seen / key_cited  share of the scenario's key evidence items (see key_evidence) the agent saw / cited
  input_tokens, output_tokens, llm_calls, tool_calls, latency_s, cost_usd
"""
from __future__ import annotations

import json
from pathlib import Path

from triage.scenarios.model import Scenario
from triage.schema import Category


def _norm(i: str) -> str:
    return i.strip().strip("[]").strip()


def key_evidence(sc: Scenario) -> list[tuple[str, object]]:
    """Evidence 'items' the diagnosis should rest on. Key log lines are numerous and repetitive, so they
    form ONE item (any key log line counts); each key deploy, key metric and key runbook is its own item."""
    t = sc.truth
    items: list[tuple[str, object]] = []
    if sc.key_log_ids():
        items.append(("anyof", frozenset(sc.key_log_ids())))
    items += [("exact", i) for i in sorted(sc.key_deploy_ids())]
    items += [("prefix", f"M:{k}") for k in t.key_metrics] + [("prefix", f"K:{d}#") for d in t.key_docs]
    return items


def _hit(kind: str, matcher, ids: set[str]) -> bool:
    if kind == "anyof":
        return bool(matcher & ids)
    return matcher in ids if kind == "exact" else any(i.startswith(matcher) for i in ids)


def load_pricing(path: str | Path = "pricing.json") -> dict:
    p = Path(path)
    return json.loads(p.read_text()).get("models", {}) if p.exists() else {}


def cost_usd(usage: dict, model: str, pricing: dict) -> float | None:
    price = pricing.get(model) or {}
    if price.get("input_per_mtok") is None or price.get("output_per_mtok") is None:
        return None
    return round((usage.get("input_tokens", 0) * price["input_per_mtok"] + usage.get("output_tokens", 0) * price["output_per_mtok"]) / 1e6, 6)


def score_run(sc: Scenario, rec: dict, model: str = "", pricing: dict | None = None) -> dict:
    t = sc.truth
    res = rec.get("result")
    out: dict = {"valid": res is not None, "tool_calls": len(rec.get("calls", [])), "latency_s": rec.get("latency_s", 0.0),
                 "input_tokens": rec.get("usage", {}).get("input_tokens", 0), "output_tokens": rec.get("usage", {}).get("output_tokens", 0),
                 "llm_calls": rec.get("usage", {}).get("llm_calls", 0), "cost_usd": cost_usd(rec.get("usage", {}), model, pricing or {})}
    key = key_evidence(sc)
    seen = set(rec.get("seen_ids", []))
    out["key_seen"] = round(sum(_hit(k, m, seen) for k, m in key) / len(key), 3) if key else None
    if res is None:
        out.update(category_correct=False, abstention_correct=False, component_correct=None, runbook_correct=False,
                   citation_valid_rate=None, invalid_citations=0, key_cited=0.0)
        return out
    expected = t.category if t.answerable else Category.insufficient_evidence
    out["category_correct"] = res["category"] == expected.value
    out["abstention_correct"] = (res["category"] == Category.insufficient_evidence.value) == (not t.answerable)
    comp = res["component"].lower()
    out["component_correct"] = any(a.lower() in comp for a in t.component_aliases) if t.answerable else None
    out["runbook_correct"] = res["recommended_runbook"] == t.runbook
    cited = {_norm(i) for i in res["evidence_ids"] if _norm(i)}
    bad = [i for i in cited if i not in seen]
    out["citation_valid_rate"] = round((len(cited) - len(bad)) / len(cited), 3) if cited else None
    out["invalid_citations"] = len(bad)
    out["key_cited"] = round(sum(_hit(k, m, cited) for k, m in key) / len(key), 3) if key else None
    return out
