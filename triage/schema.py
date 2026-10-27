"""Typed data shared by every approach, the tools, and the evaluation.

All three approaches (fixed pipeline, single agent, multi-agent) must return a TriageResult,
so scoring never depends on which approach produced it.

Note on structured output: fields deliberately have no defaults. Some providers' strict
JSON-schema modes reject optional fields; if one rejects a schema, simplify it here first.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, get_args

from pydantic import BaseModel, Field


class Category(str, Enum):
    bad_change = "bad_change"
    dependency_saturation = "dependency_saturation"
    resource_leak = "resource_leak"
    traffic_spike = "traffic_spike"
    infra_failure = "infra_failure"
    expired_credential = "expired_credential"
    insufficient_evidence = "insufficient_evidence"


CATEGORY_DEFINITIONS = """\
Root-cause categories (pick the one that decides which runbook action fixes it):
- bad_change: a deploy or configuration change introduced the fault. Choose this whenever a recent
  change is the trigger, even if the visible mechanism is saturation, retries, or a leak. Action: revert it.
- dependency_saturation: a shared dependency (database, cache, store) is overloaded by load that was
  NOT introduced by a recent change (batch jobs, cold caches, slow queries). Action: throttle or shed that load.
- resource_leak: a resource (memory, file descriptors, disk, connections) grows steadily with no recent
  change as the trigger. Action: capture diagnostics, then reclaim it one instance at a time (game servers:
  cordon and drain or migrate first, never a bare restart).
- traffic_spike: legitimate demand exceeds provisioned capacity. Action: scale out or shed load.
- infra_failure: a host, network, DNS, or upstream provider failure. Action: drain/replace the node or fail over.
- expired_credential: a certificate, token, or key expired or was revoked. Action: rotate it.
- insufficient_evidence: the available data cannot support any single conclusion. Say so instead of guessing,
  and escalate with the findings collected so far.
"""

RUNBOOK_INDEX = """\
Runbooks (cite the id in recommended_runbook):
- RB-01 Revert a bad deploy or configuration change
- RB-02 Mitigate dependency saturation (retry storms, pool exhaustion, cold caches, heavy batch load)
- RB-03 Contain a resource leak (restart, capture diagnostics)
- RB-04 Respond to a traffic spike beyond capacity (scale out, shed load)
- RB-05 Drain and replace a failed node
- RB-06 Rotate an expired certificate or credential
- RB-07 Handle a network, DNS, or upstream provider failure (fail over, contact provider)
- RB-08 Escalate with insufficient evidence (page a service engineer with findings)
"""

# A Literal (not str) so structured output can only emit a bare id. With str, a model wrote
# "RB-01 Revert a bad deploy..." and exact-match scoring marked the right runbook wrong.
RunbookId = Literal["RB-01", "RB-02", "RB-03", "RB-04", "RB-05", "RB-06", "RB-07", "RB-08"]
RUNBOOK_IDS = list(get_args(RunbookId))


class Alert(BaseModel):
    id: str
    service: str
    symptom: str
    fired_at: str  # ISO-8601 UTC
    severity: Literal["low", "medium", "high"]
    dependencies: list[str]

    def as_text(self) -> str:
        deps = ", ".join(self.dependencies) if self.dependencies else "none listed"
        return (
            f"ALERT {self.id}\nservice: {self.service}\nsymptom: {self.symptom}\n"
            f"fired_at: {self.fired_at}\nseverity: {self.severity}\ndepends_on: {deps}"
        )


class TriageResult(BaseModel):
    category: Category = Field(description="Root-cause category; use insufficient_evidence if the data cannot support one.")
    component: str = Field(description="The failing service, host, or credential, e.g. 'matchmaking'; 'unknown' if insufficient_evidence.")
    summary: str = Field(description="Two to four sentences: what is wrong and why, grounded in the evidence.")
    evidence_ids: list[str] = Field(description="Ids copied exactly from tool output that support the diagnosis, e.g. L0231, D2, M:svc:metric:1h, K:RB-01#0.")
    recommended_runbook: RunbookId = Field(description="The runbook id only, e.g. RB-01.")
    recommended_action: str = Field(description="The concrete next action for the on-call engineer, one or two sentences.")
    confidence: Literal["low", "medium", "high"]


# ---- multi-agent messages ------------------------------------------------------------------

WorkerName = Literal["logs", "metrics", "knowledge"]


class WorkerAssignment(BaseModel):
    worker: WorkerName
    question: str = Field(description="A specific question for this specialist to answer from its tools.")


class Plan(BaseModel):
    assignments: list[WorkerAssignment]


class Observation(BaseModel):
    text: str
    evidence_ids: list[str]


class Finding(BaseModel):
    worker: WorkerName
    summary: str = Field(description="What this specialist concluded, in two or three sentences.")
    observations: list[Observation]
    confidence: Literal["low", "medium", "high"]


class Synthesis(BaseModel):
    decision: Literal["answer", "follow_up"]
    follow_ups: list[WorkerAssignment] = Field(description="Questions for specialists if decision is follow_up; otherwise an empty list.")
    result: TriageResult | None = Field(description="The final result if decision is answer; otherwise null.")


# ---- judge -------------------------------------------------------------------------------------

class JudgeVerdict(BaseModel):
    action_alignment: int = Field(description="0 = wrong or unsafe action, 1 = partly right, 2 = matches the reference action.")
    evidence_support: int = Field(description="0 = diagnosis unsupported by the cited evidence, 1 = partly, 2 = fully supported.")
    reasoning: str
