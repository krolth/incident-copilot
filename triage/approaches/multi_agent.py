"""Approach C: coordinator + three specialists, at most one follow-up round.

plan -> workers (logs, metrics, knowledge) run in parallel, each a ReAct agent with ONLY its own tools
-> synthesize -> (optional single follow-up round) -> final answer.
The coordinator never touches tools; it only sees what the specialists report.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import HumanMessage, SystemMessage

from triage.approaches.common import UsageTracker, structured_call
from triage.approaches.react import run_react
from triage.env import Environment
from triage.prompts import FINALIZE_PROMPT, PLAN_SYSTEM, SYNTH_SYSTEM, WORKER_FINAL, WORKER_SYSTEM
from triage.schema import Alert, Finding, Plan, Synthesis, TriageResult, WorkerAssignment

WORKER_TOOLS = {
    "logs": ("search_logs",),
    "metrics": ("get_metrics", "get_recent_deploys"),
    "knowledge": ("search_knowledge",),
}


def _run_worker(a: WorkerAssignment, alert: Alert, env: Environment, llm, tracker: UsageTracker, max_steps: int) -> Finding:
    user = f"{alert.as_text()}\n\nYour question: {a.question}"
    finding, _m, _s = run_react(llm, WORKER_SYSTEM[a.worker], user, env.tools(WORKER_TOOLS[a.worker], agent=a.worker),
                                Finding, tracker, max_steps, final_prompt=WORKER_FINAL)
    finding.worker = a.worker  # the label is ours, not the model's
    return finding


def _run_workers(assignments: list[WorkerAssignment], alert, env, llm, tracker, max_steps) -> list[Finding]:
    # one assignment per worker; if the plan repeats a worker, keep the first
    unique = list({a.worker: a for a in assignments}.values())
    with ThreadPoolExecutor(max_workers=max(1, len(unique))) as pool:
        futures = [pool.submit(_run_worker, a, alert, env, llm, tracker, max_steps) for a in unique]
        return [f.result() for f in futures]


def _format_findings(findings: list[Finding]) -> str:
    out = []
    for f in findings:
        obs = "\n".join(f"  - {o.text} (evidence: {', '.join(o.evidence_ids) or 'none'})" for o in f.observations)
        out.append(f"[{f.worker}] confidence={f.confidence}\n{f.summary}\n{obs}")
    return "\n\n".join(out)


def run(alert: Alert, env: Environment, llm, tracker: UsageTracker, cfg: dict) -> TriageResult:
    max_steps = cfg.get("worker_steps", 5)
    plan = structured_call(llm, Plan, [SystemMessage(content=PLAN_SYSTEM), HumanMessage(content=alert.as_text())], tracker)
    if not plan.assignments:  # a model that plans nothing gets the default plan rather than a failed run
        plan = Plan(assignments=[WorkerAssignment(worker=w, question=alert.symptom) for w in WORKER_TOOLS])
    env.trace.add(type="plan", assignments=[a.model_dump() for a in plan.assignments])
    findings = _run_workers(plan.assignments, alert, env, llm, tracker, max_steps)

    def synthesize(final_round: bool) -> Synthesis:
        note = "This is the FINAL round: you must answer." if final_round else "You may answer or ask one round of follow-ups."
        user = f"{alert.as_text()}\n\nSpecialist findings:\n\n{_format_findings(findings)}\n\n{note}"
        return structured_call(llm, Synthesis, [SystemMessage(content=SYNTH_SYSTEM), HumanMessage(content=user)], tracker)

    syn = synthesize(final_round=False)
    if syn.decision == "follow_up" and syn.follow_ups:
        env.trace.add(type="follow_up", assignments=[a.model_dump() for a in syn.follow_ups])
        findings += _run_workers(syn.follow_ups, alert, env, llm, tracker, max_steps)
        syn = synthesize(final_round=True)
    if syn.result is not None:
        return syn.result
    # the model said "answer" (or ran out of rounds) without a result: ask once, directly
    user = f"{alert.as_text()}\n\nSpecialist findings:\n\n{_format_findings(findings)}\n\n{FINALIZE_PROMPT}"
    return structured_call(llm, TriageResult, [SystemMessage(content=SYNTH_SYSTEM), HumanMessage(content=user)], tracker)
