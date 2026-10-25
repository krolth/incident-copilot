"""Approach B: one ReAct agent with all four tools."""
from __future__ import annotations

from triage.approaches.common import UsageTracker
from triage.approaches.react import run_react
from triage.env import TOOL_NAMES, Environment
from triage.prompts import AGENT_SYSTEM
from triage.schema import Alert, TriageResult


def run(alert: Alert, env: Environment, llm, tracker: UsageTracker, cfg: dict) -> TriageResult:
    answer, _msgs, _steps = run_react(llm, AGENT_SYSTEM, alert.as_text(), env.tools(TOOL_NAMES, agent="single"),
                                      TriageResult, tracker, cfg["max_steps"])
    return answer
