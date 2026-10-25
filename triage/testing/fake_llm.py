"""Fake chat models for OFFLINE TESTS ONLY.

Nothing produced with these is evaluation data. They exist to prove the plumbing (tools, graph loops,
parallel workers, scoring, runner, reports) works before any real model is paid for.

FakeChat   a BaseChatModel whose behavior comes from a policy object
OraclePolicy  answers from a scenario's ground truth (mode 'correct'), or deliberately wrong ('wrong'),
              or with an unseen citation ('bad_citation'), or never stops calling tools ('loop')
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.output_parsers import PydanticOutputParser

from triage.env import ID_RE
from triage.scenarios.model import Scenario
from triage.schema import (Category, Finding, JudgeVerdict, Observation, Plan, Synthesis, TriageResult,
                           WorkerAssignment)

FAKE_BANNER = "FAKE MODEL RUN: NOT EVALUATION DATA"


def _text(messages: list[BaseMessage]) -> str:
    return "\n".join(m.content if isinstance(m.content, str) else json.dumps(m.content) for m in messages)


class FakeChat(BaseChatModel):
    policy: Any
    bound_tools: list = []
    out_schema: Any = None

    @property
    def _llm_type(self) -> str:
        return "fake-chat"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self.model_copy(update={"bound_tools": [getattr(t, "name", str(t)) for t in tools]})

    def with_structured_output(self, schema, **kwargs):  # noqa: ANN001
        return self.model_copy(update={"out_schema": schema}) | PydanticOutputParser(pydantic_object=schema)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001
        if self.out_schema is not None:
            obj = self.policy.structured(self.out_schema, messages)
            msg = AIMessage(content=obj.model_dump_json())
        else:
            msg = self.policy.chat(messages, self.bound_tools)
        msg.usage_metadata = {"input_tokens": max(1, len(_text(messages)) // 4),
                              "output_tokens": max(1, len(str(msg.content) + json.dumps(msg.tool_calls)) // 4),
                              "total_tokens": 0}
        return ChatResult(generations=[ChatGeneration(message=msg)])


class OraclePolicy:
    def __init__(self, scenario: Scenario, mode: str = "correct") -> None:
        assert mode in ("correct", "wrong", "bad_citation", "loop")
        self.sc, self.mode, self._n = scenario, mode, 0

    # ---- chat (tool-calling turns) --------------------------------------------------------------
    def chat(self, messages: list[BaseMessage], tool_names: list[str]) -> AIMessage:
        n_tool_msgs = sum(isinstance(m, ToolMessage) for m in messages)
        if tool_names and (n_tool_msgs == 0 or self.mode == "loop"):
            svc, calls = self.sc.alert.service, []
            for name in tool_names[:2]:
                args = {"search_logs": {"service": svc, "level": "ERROR", "window": "1h"},
                        "get_metrics": {"service": svc, "metric": "error_rate_pct", "window": "1h"},
                        "get_recent_deploys": {"service": "", "window": "24h"},
                        "search_knowledge": {"query": self.sc.alert.symptom, "k": 4}}[name]
                self._n += 1
                calls.append({"name": name, "args": args, "id": f"call_{self._n}"})
            return AIMessage(content="", tool_calls=calls)
        return AIMessage(content="Investigation complete.")

    # ---- typed answers ----------------------------------------------------------------------------
    def _key_ids(self, messages: list[BaseMessage]) -> list[str]:
        t = self.sc.truth
        key = self.sc.key_log_ids() | self.sc.key_deploy_ids()
        found = []
        for i in dict.fromkeys(ID_RE.findall(_text(messages))):
            if i in key or any(i.startswith(f"M:{k}") for k in t.key_metrics) or any(i.startswith(f"K:{d}#") for d in t.key_docs):
                found.append(i)
        return found[:6]

    def _triage(self, messages: list[BaseMessage]) -> TriageResult:
        t = self.sc.truth
        category = t.category if t.answerable else Category.insufficient_evidence
        runbook, action = t.runbook, t.reference_action
        if self.mode == "wrong":
            category = next(c for c in Category if c != t.category)
            runbook, action = "RB-08", "Escalate to a service engineer."
        ids = self._key_ids(messages)
        if self.mode == "bad_citation":
            ids = ids + ["L9999"]
        return TriageResult(category=category, component=t.component_aliases[0] if t.answerable else "unknown",
                            summary=f"{FAKE_BANNER}. Scripted from ground truth.", evidence_ids=ids,
                            recommended_runbook=runbook, recommended_action=action, confidence="high")

    def structured(self, schema, messages: list[BaseMessage]):  # noqa: ANN001
        if schema is TriageResult:
            return self._triage(messages)
        if schema is Plan:
            return Plan(assignments=[WorkerAssignment(worker=w, question=self.sc.alert.symptom)
                                     for w in ("logs", "metrics", "knowledge")])
        if schema is Finding:
            head = _text(messages[:1])
            worker = "logs" if "LOGS" in head else "metrics" if "METRICS" in head else "knowledge"
            ids = list(dict.fromkeys(ID_RE.findall(_text(messages))))[:8]
            return Finding(worker=worker, summary=f"{FAKE_BANNER}.",
                           observations=[Observation(text="scripted observation", evidence_ids=ids)], confidence="medium")
        if schema is Synthesis:
            return Synthesis(decision="answer", follow_ups=[], result=self._triage(messages))
        if schema is JudgeVerdict:
            return JudgeVerdict(action_alignment=2, evidence_support=2, reasoning=FAKE_BANNER)
        raise TypeError(f"OraclePolicy does not know schema {schema}")


def oracle_llm(scenario: Scenario, mode: str = "correct") -> FakeChat:
    return FakeChat(policy=OraclePolicy(scenario, mode))
