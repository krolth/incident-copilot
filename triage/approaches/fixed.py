"""Approach A: fixed pipeline. The code decides what to look at; the model only diagnoses.

Always collects the same data (alert service: ERROR logs, 5 metrics, deploys, plus knowledge search and
ERROR logs of each dependency), all in the default short windows, then makes one model call. It cannot
follow a lead: no long-window trend check, no query refinement. That is the baseline being tested.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from triage.approaches.common import UsageTracker, structured_call
from triage.env import Environment
from triage.prompts import FIXED_SYSTEM
from triage.schema import Alert, TriageResult

METRICS = ("error_rate_pct", "latency_p99_ms", "cpu_pct", "memory_pct", "request_rate_rps")


def collect(alert: Alert, env: Environment) -> str:
    parts = [env.search_logs(alert.service, "", "ERROR", "1h", "fixed")]
    for dep in alert.dependencies:
        parts.append(env.search_logs(dep, "", "ERROR", "1h", "fixed"))
    parts += [env.get_metrics(alert.service, m, "1h", "fixed") for m in METRICS]
    parts.append(env.get_recent_deploys(alert.service, "24h", "fixed"))
    parts.append(env.search_knowledge(alert.symptom, 4, "fixed"))
    return "\n\n".join(parts)


def run(alert: Alert, env: Environment, llm, tracker: UsageTracker, cfg: dict) -> TriageResult:
    data = collect(alert, env)
    user = f"{alert.as_text()}\n\nCollected data:\n\n{data}"
    return structured_call(llm, TriageResult, [SystemMessage(content=FIXED_SYSTEM), HumanMessage(content=user)], tracker)
