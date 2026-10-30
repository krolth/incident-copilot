"""Export the real evaluation results into the data files the website reads.

  python site/build_data.py

Reads results/ (gpt-oss:20b, local) and results_openai/ (gpt-6.1-terra, hosted) and the scenario engine, and writes
site/data/site.js (topology, scenarios, summary tables) and site/data/runs_<model>.js (every run, with its tool
calls for the replay). Numbers on the site come only from these files, so they trace back to real runs.
The data is written as JavaScript (window.SITE = ...) rather than JSON so the pages also work opened from disk.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from triage.scenarios import all_scenarios  # noqa: E402

OUT = ROOT / "site" / "data"
MODELS = [  # (key, results folder, label, where it ran)
    ("local", "results", "gpt-oss:20b", "local, on a Mac via Ollama"),
    ("terra", "results_openai", "gpt-6.1-terra", "hosted, OpenAI API"),
]
APPROACHES = ["fixed", "single", "multi"]
ABSTAIN = {"s11", "s12", "s18"}

# The Fianchetto architecture (docs/system.md). x/y are grid positions the pages scale to the drawing.
NODES = [
    # id, label, detail, layer, x, y
    ("clients", "Players & spectators", "web and mobile clients", "edge", 0, 2),
    ("dns", "DNS", "dns-01, dns-02", "edge", 1, 0),
    ("edge", "Edge / TLS", "*.play.fianchetto.example", "edge", 1, 2),
    ("gateway", "gateway", "HTTPS API, rate limits", "service", 2, 1),
    ("game-server", "game-server fleet", "gs-01..gs-10, live games (WSS)", "service", 2, 3.4),
    ("accounts", "accounts", "logins, social sign-in", "service", 3, 0),
    ("matchmaking", "matchmaking", "queues and pairing", "service", 3, 1),
    ("leaderboards", "leaderboards", "ladder pages", "service", 3, 2),
    ("stats", "stats", "ratings, game stats", "service", 3, 3),
    ("anticheat", "anticheat", "move analysis", "service", 3, 4),
    ("identity-provider", "identity provider", "external, social login", "external", 4, -0.2),
    ("redis-live", "redis-live", "queues, game checkpoints, streams", "store", 4, 1.3),
    ("redis-cache", "redis-cache", "read cache", "store", 4, 2.5),
    ("chess-db", "chess-db", "Postgres, users and games", "store", 4, 3.7),
    ("k8s", "Kubernetes nodes", "node-01..node-12", "platform", 1, 4.6),
    ("config", "Config & ops", "cfgpush, config-agent, ops-automation", "platform", 2, 4.9),
    ("telemetry", "Telemetry", "log-agent, metrics pipeline", "platform", 3, 5.4),
]
EDGES = [
    ("clients", "edge"), ("edge", "gateway"), ("edge", "game-server"), ("gateway", "accounts"),
    ("gateway", "matchmaking"), ("gateway", "leaderboards"), ("gateway", "stats"), ("accounts", "identity-provider"),
    ("accounts", "chess-db"), ("matchmaking", "redis-live"), ("game-server", "redis-live"), ("game-server", "chess-db"),
    ("redis-live", "stats"), ("redis-live", "leaderboards"), ("redis-live", "anticheat"), ("stats", "chess-db"),
    ("stats", "redis-cache"), ("leaderboards", "redis-cache"), ("leaderboards", "chess-db"), ("anticheat", "chess-db"),
    ("dns", "accounts"), ("matchmaking", "game-server"),
]

# What actually broke, per scenario, drawn from the scenario answer key (docs/scenario-plan.md). "cause" is red;
# "victim" is where the symptom shows; "ambiguous" marks the two equally supported causes of s18.
TRUTH_NODES = {
    "s01": {"cause": ["matchmaking"], "victim": ["redis-live"]},
    "s02": {"cause": ["game-server"]},
    "s03": {"cause": ["clients"], "victim": ["game-server", "matchmaking"]},
    "s04": {"cause": ["edge"], "victim": ["game-server"]},
    "s05": {"cause": ["k8s"], "victim": ["accounts"]},
    "s06": {"cause": ["chess-db"], "victim": ["accounts"]},
    "s07": {"cause": ["config"], "victim": ["matchmaking"]},
    "s08": {"cause": ["dns"], "victim": ["accounts"]},
    "s09": {"cause": ["game-server"]},
    "s10": {"cause": ["redis-cache"], "victim": ["chess-db", "leaderboards"]},
    "s11": {"cause": [], "gap": ["telemetry"]},
    "s12": {"cause": []},
    "s13": {"cause": ["accounts"]},
    "s14": {"cause": ["config"], "victim": ["gateway"]},
    "s15": {"cause": ["game-server"]},
    "s16": {"cause": ["clients"], "victim": ["matchmaking"]},
    "s17": {"cause": ["redis-live"], "victim": ["game-server"]},
    "s18": {"cause": [], "ambiguous": ["config", "k8s"]},
}

# Tool "service" arguments and log sources that are not a box of their own.
SERVICE_NODE = {"config-agent": "config", "ops-automation": "config", "cfgpush": "config", "kubelet": "k8s",
                "log-agent": "telemetry", "dns": "dns", "identity-provider": "identity-provider"}
NODE_IDS = {n[0] for n in NODES}

# Free-text "component" from an agent's answer -> boxes. First match groups win in this order.
BLAME_PATTERNS = [
    ("edge", r"certif|wildcard|play\.fianchetto|\btls\b"),
    ("dns", r"\bdns|resolver"),
    ("k8s", r"node-\d|kubelet|kubernetes"),
    ("identity-provider", r"identity"),
    ("redis-live", r"redis-live"),
    ("redis-cache", r"redis-cache|\bcache\b"),
    ("chess-db", r"chess-db|db-0\d|replica|postgres"),
    ("config", r"config|cfgpush|rate.?limit"),
    ("game-server", r"game.?server|\bgs-\d"),
    ("matchmaking", r"matchmaking"),
    ("accounts", r"accounts"),
    ("gateway", r"gateway"),
    ("leaderboards", r"leaderboard"),
    ("stats", r"\bstats\b"),
    ("anticheat", r"anticheat"),
]


def blamed_nodes(component: str | None, category: str | None) -> list[str]:
    if not component or category == "insufficient_evidence":
        return []
    text = component.lower().replace("‑", "-").replace("‐", "-")
    hits = [node for node, pat in BLAME_PATTERNS if re.search(pat, text)]
    if "edge" in hits:  # "game-server serving certificate" blames the certificate, not the servers
        hits = [h for h in hits if h != "game-server"]
    return hits


def service_node(service: str) -> str | None:
    s = (service or "").strip()
    if s in NODE_IDS or s in SERVICE_NODE:
        return SERVICE_NODE.get(s, s)
    hits = blamed_nodes(s.replace("_", "-").replace("feature-flag", "config"), None)  # hosts: gs-04, node-07, db-02
    return hits[0] if hits else None  # "" (all services) and search_knowledge light no single box


def short(sid: str) -> str:
    return sid[:3]


def r2(x: float) -> float:
    return round(x, 2)


def scenario_data(sc) -> dict:
    # Metric panels: 6 hours at 4-minute steps and 7 days at 2-hour steps, ending at the time of triage.
    now = sc.now_min
    windows = {"6h": (360, 4), "7d": (10080, 120)}
    metrics = {}
    for svc, ms in sc.metrics.items():
        for name, m in ms.items():
            metrics[f"{svc}:{name}"] = {
                "service": svc, "metric": name, "unit": m.unit,
                **{w: [r2(m.value(now - span + i * step)) for i in range(span // step + 1)] for w, (span, step) in windows.items()},
            }
    seen, key_logs = set(), []
    for line in sorted((l for l in sc.logs if l.key), key=lambda l: l.t):
        template = re.sub(r"\d+", "#", line.message)
        if template not in seen:
            seen.add(template)
            key_logs.append({"id": line.id, "t": line.t, "service": line.service, "level": line.level,
                             "host": line.host, "message": line.message})
    truth = TRUTH_NODES[short(sc.id)]
    return {
        "id": sc.id, "short": short(sc.id), "title": sc.title, "difficulty": sc.difficulty, "now_min": now,
        "alert": sc.alert.model_dump(), "alert_node": service_node(sc.alert.service),
        "truth": {"category": sc.truth.category.value, "runbook": sc.truth.runbook,
                  "reference_action": sc.truth.reference_action, "answerable": sc.truth.answerable,
                  "key_metrics": sc.truth.key_metrics, **truth},
        "trap": sc.trap, "metrics": metrics, "key_logs": key_logs[:8],
        "deploys": [{"id": d.id, "t_min": d.t_min, "service": d.service, "version": d.version,
                     "summary": d.summary, "key": d.key} for d in sc.deploys],
        "dev": short(sc.id) in ("s01", "s08", "s11"),
    }


def _assignments(v) -> list:
    return ast.literal_eval(v) if isinstance(v, str) else (v or [])  # older traces stored the list itself


def run_data(r: dict) -> dict:
    res = r.get("result") or {}
    sc = r["score"]
    tools = [e for e in r["trace"] if e["type"] == "tool"]
    steps = []
    ti = 0
    for e in r["trace"]:
        if e["type"] == "plan":
            steps.append({"kind": "plan", "assignments": _assignments(e["assignments"])})
        elif e["type"] == "follow_up":
            steps.append({"kind": "follow_up", "assignments": _assignments(e.get("assignments"))})
        elif e["type"] == "step_cap":
            steps.append({"kind": "step_cap", "agent": e.get("agent")})
        elif e["type"] == "tool":
            call = r["calls"][ti] if ti < len(r["calls"]) else {"args": {}}
            ti += 1
            args = call.get("args", {})
            steps.append({"kind": "tool", "agent": e.get("agent"), "tool": e["name"], "args": args,
                          "node": service_node(args.get("service", "")), "out": e.get("output_preview", "")[:500]})
    assert ti == len(tools)
    ids = res.get("evidence_ids") or []
    return {
        "s": short(r["scenario_id"]), "a": r["approach"], "i": r["run_idx"],
        "category": res.get("category"), "component": res.get("component"),
        "blamed": blamed_nodes(res.get("component"), res.get("category")),
        "summary": res.get("summary"), "action": res.get("recommended_action"), "runbook": res.get("recommended_runbook"),
        "confidence": res.get("confidence"), "error": (r.get("error") or "")[:200] or None,
        "cited": [{"id": i, "text": r["evidence"].get(i.strip("[] "), "")[:300]} for i in ids[:15]],
        "cited_more": max(0, len(ids) - 15),
        "ok": bool(sc["category_correct"]), "runbook_ok": bool(sc["runbook_correct"]),
        "key_seen": sc["key_seen"], "key_cited": sc["key_cited"], "cite_valid": sc["citation_valid_rate"],
        "tools": sc["tool_calls"], "llm_calls": sc["llm_calls"], "tok_in": sc["input_tokens"], "tok_out": sc["output_tokens"],
        "cost": sc["cost_usd"], "latency": r2(r["latency_s"]), "judge": r.get("judge"),
        "steps": steps,
    }


def summarise(runs: list[dict], scenarios: dict) -> dict:
    out = {}
    for a in APPROACHES:
        rs = [r for r in runs if r["a"] == a]
        held = [r for r in rs if not scenarios[r["s"]]["dev"]]
        nonab = [r for r in rs if r["s"] not in ABSTAIN]
        judged = [r for r in rs if r["judge"]]
        valid = [r["cite_valid"] for r in rs if r["cite_valid"] is not None]
        out[a] = {
            "n": len(rs), "correct": sum(r["ok"] for r in rs),
            "held_n": len(held), "held_correct": sum(r["ok"] for r in held),
            "dev_n": len(rs) - len(held), "dev_correct": sum(r["ok"] for r in rs) - sum(r["ok"] for r in held),
            "tiers": {t: {"n": len(x), "correct": sum(r["ok"] for r in x)}
                      for t in ("easy", "medium", "hard")
                      for x in [[r for r in rs if scenarios[r["s"]]["difficulty"] == t]]},
            "per_scenario": {s: sum(r["ok"] for r in rs if r["s"] == s) for s in scenarios},
            "abstain_cases": {"n": len(rs) - len(nonab), "correct": sum(r["ok"] for r in rs if r["s"] in ABSTAIN)},
            "false_abstain": sum(r["category"] == "insufficient_evidence" for r in nonab), "nonab_n": len(nonab),
            "knowledge_runs": sum(any(st.get("tool") == "search_knowledge" for st in r["steps"]) for r in rs),
            "cost_per_run": r2(mean(r["cost"] or 0 for r in rs) * 1000) / 1000,
            "cost_total": r2(sum(r["cost"] or 0 for r in rs)),
            "latency": r2(mean(r["latency"] for r in rs)), "tools": r2(mean(r["tools"] for r in rs)),
            "tok_in": round(mean(r["tok_in"] for r in rs)), "tok_out": round(mean(r["tok_out"] for r in rs)),
            "judge_action": r2(mean(r["judge"]["action_alignment"] for r in judged)) if judged else None,
            "judge_evidence": r2(mean(r["judge"]["evidence_support"] for r in judged)) if judged else None,
            "key_cited": r2(mean(r["key_cited"] or 0 for r in rs)), "cite_valid": r2(mean(valid)) if valid else None,
            "errors": sum(bool(r["error"]) for r in rs),
        }
    return out


def write_js(path: Path, var: str, obj) -> None:
    path.write_text(f"window.{var} = " + json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + ";\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scenarios = {short(s.id): scenario_data(s) for s in all_scenarios()}
    models, summary = [], {}
    for key, folder, label, where in MODELS:
        recs = [json.loads(l) for l in (ROOT / folder / "runs.jsonl").read_text().splitlines() if l.strip()]
        runs = [run_data(r) for r in recs]
        meta = json.loads((ROOT / folder / "meta.json").read_text())
        phase1 = ROOT / folder / "meta_phase1.json"
        wall = meta["wall_clock_s"] + (json.loads(phase1.read_text())["wall_clock_s"] if phase1.exists() else 0)
        models.append({"key": key, "label": label, "where": where, "runs": len(runs), "commit": meta["git_commit"],
                       "prompts": meta["prompts_sha256"], "judge": meta["judge_model"], "wall_clock_min": round(wall / 60, 1),
                       "finished": meta["finished_at"][:10]})
        summary[key] = summarise(runs, scenarios)
        write_js(OUT / f"runs_{key}.js", f"RUNS_{key.upper()}", runs)
    write_js(OUT / "site.js", "SITE", {
        "nodes": [dict(zip(("id", "label", "detail", "layer", "x", "y"), n)) for n in NODES],
        "edges": EDGES, "scenarios": scenarios, "models": models, "summary": summary, "approaches": APPROACHES,
    })
    for f in sorted(OUT.iterdir()):
        print(f"{f.relative_to(ROOT)}  {f.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
