import pytest
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from triage.approaches.common import UsageTracker, structured_call
from triage.env import Trace
from triage.schema import TriageResult

VALID = dict(category="bad_change", component="matchmaking-svc", summary="s", evidence_ids=["D2"],
             recommended_action="revert", confidence="high")


def test_runbook_must_be_a_bare_id():
    assert TriageResult(**VALID, recommended_runbook="RB-01").recommended_runbook == "RB-01"
    with pytest.raises(ValidationError):
        TriageResult(**VALID, recommended_runbook="RB-01 Revert a bad deploy or configuration change")


class FlakyStructured:
    """Fails once, then answers: stands in for a model whose first structured reply doesn't validate."""

    def __init__(self) -> None:
        self.calls = 0

    def with_structured_output(self, schema):  # noqa: ANN001
        return self

    def invoke(self, messages, config):  # noqa: ANN001
        self.calls += 1
        if self.calls == 1:
            raise ValueError("bad json")
        return TriageResult(**VALID, recommended_runbook="RB-01")


def test_retries_are_counted_and_traced():
    trace = Trace()
    tracker = UsageTracker(trace)
    out = structured_call(FlakyStructured(), TriageResult, [HumanMessage(content="x")], tracker)
    assert out.recommended_runbook == "RB-01"
    assert tracker.as_dict()["retries"] == 1
    retry = [e for e in trace.events if e["type"] == "retry"]
    assert len(retry) == 1 and retry[0]["schema"] == "TriageResult" and "bad json" in retry[0]["error"]
