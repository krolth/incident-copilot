import pytest
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

import triage.approaches.common as common
from triage.approaches import APPROACHES
from triage.approaches.common import UsageTracker, backoff_s, execute, structured_call, with_retries
from triage.env import Trace
from triage.scenarios import get_scenario
from triage.schema import TriageResult
from triage.testing.fake_llm import FakeChat, OraclePolicy

VALID = dict(category="bad_change", component="matchmaking", summary="s", evidence_ids=["D2"],
             recommended_action="revert", confidence="high")


def test_runbook_must_be_a_bare_id():
    assert TriageResult(**VALID, recommended_runbook="RB-01").recommended_runbook == "RB-01"
    with pytest.raises(ValidationError):
        TriageResult(**VALID, recommended_runbook="RB-01 Revert a bad deploy or configuration change")


def test_backoff_is_exponential_capped_and_jittered(monkeypatch):
    monkeypatch.setattr(common.random, "uniform", lambda lo, hi: hi)  # take the top of each jitter range
    assert [backoff_s(a) for a in range(7)] == [1, 2, 4, 8, 16, 30, 30]
    monkeypatch.setattr(common.random, "uniform", lambda lo, hi: lo)
    assert backoff_s(3) == 0  # full jitter: anywhere from 0 up to the cap


def flaky(fail_times: int):
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise ConnectionError(f"server down #{calls['n']}")
        return "ok"
    return call, calls


def test_recovers_after_three_failures_and_traces_each_retry(no_backoff_sleep):
    trace = Trace()
    tracker = UsageTracker(trace)
    call, calls = flaky(3)
    assert with_retries(call, tracker, where="agent_step") == "ok"
    assert calls["n"] == 4 and tracker.as_dict()["retries"] == 3 and len(no_backoff_sleep) == 3
    retries = [e for e in trace.events if e["type"] == "retry"]
    assert [e["attempt"] for e in retries] == [1, 2, 3]
    assert all(e["where"] == "agent_step" and "server down" in e["error"] for e in retries)


def test_fourth_failure_fails_the_call():
    tracker = UsageTracker(Trace())
    call, calls = flaky(4)
    with pytest.raises(ConnectionError):
        with_retries(call, tracker, where="x")
    assert calls["n"] == 4 and tracker.retries == 3


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


def test_structured_call_retries_and_names_the_schema():
    trace = Trace()
    tracker = UsageTracker(trace)
    out = structured_call(FlakyStructured(), TriageResult, [HumanMessage(content="x")], tracker)
    assert out.recommended_runbook == "RB-01" and tracker.retries == 1
    (retry,) = [e for e in trace.events if e["type"] == "retry"]
    assert retry["where"] == "TriageResult" and "bad json" in retry["error"]


class ServerErrorOnce(OraclePolicy):
    """Like Ollama failing to parse gpt-oss's tool call on the first tool-loop step."""

    def __init__(self, sc):  # noqa: ANN001
        super().__init__(sc)
        self.failed = False

    def chat(self, messages, tool_names):  # noqa: ANN001
        if not self.failed:
            self.failed = True
            raise RuntimeError("error parsing tool call: raw='{\", \"observations\"...'")
        return super().chat(messages, tool_names)


def test_tool_loop_survives_a_server_error(retriever):
    sc = get_scenario("s01")
    rec = execute(APPROACHES["single"], "single", sc, FakeChat(policy=ServerErrorOnce(sc)), retriever)
    assert rec.error is None and rec.result["category"] == "bad_change"
    assert rec.usage["retries"] == 1 and rec.usage["llm_errors"] == 1
    assert any(e["type"] == "retry" and e["where"] == "agent_step" for e in rec.trace)
