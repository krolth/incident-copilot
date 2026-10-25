"""LLM-as-judge for the two things string matching cannot grade: is the recommended ACTION right,
and does the CITED EVIDENCE support the diagnosis. The judge is itself validated against human labels
(triage/evals/labels.py): until agreement is measured, judge scores are unproven.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from triage.approaches.common import UsageTracker, structured_call
from triage.prompts import JUDGE_SYSTEM
from triage.scenarios.model import Scenario
from triage.schema import JudgeVerdict


def build_judge_input(sc: Scenario, rec: dict) -> str:
    res = rec["result"]
    cited = [i.strip("[] ") for i in res["evidence_ids"]]
    evidence = "\n".join(f"- {i}: {rec['evidence'].get(i, '(never shown to the agent, or not a log/deploy/metric/passage id)')}" for i in cited) or "(nothing cited)"
    t = sc.truth
    ref = (f"Reference category: {t.category.value}\nReference runbook: {t.runbook}\nReference action: {t.reference_action}"
           if t.answerable else
           "This incident is UNANSWERABLE from the available data. The correct behavior is to say the evidence is insufficient and escalate with findings (runbook RB-08).")
    return (f"{ref}\n\nAgent answer:\ncategory: {res['category']}\ncomponent: {res['component']}\nsummary: {res['summary']}\n"
            f"recommended_runbook: {res['recommended_runbook']}\nrecommended_action: {res['recommended_action']}\n\n"
            f"Evidence the agent cited (text as shown to the agent):\n{evidence}")


def judge_run(judge_llm, sc: Scenario, rec: dict, tracker: UsageTracker | None = None) -> dict | None:
    """Pass a tracker to keep the judge's tokens and retries (the runner stores them with the run)."""
    if rec.get("result") is None:
        return None
    tracker = tracker or UsageTracker()
    v = structured_call(judge_llm, JudgeVerdict, [SystemMessage(content=JUDGE_SYSTEM), HumanMessage(content=build_judge_input(sc, rec))], tracker)
    return {"action_alignment": max(0, min(2, v.action_alignment)), "evidence_support": max(0, min(2, v.evidence_support)),
            "reasoning": v.reasoning}
