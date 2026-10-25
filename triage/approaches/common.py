"""Shared plumbing for all approaches: usage tracking, structured calls, and the RunRecord."""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import asdict, dataclass, field

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

from triage.env import Environment, Trace
from triage.scenarios.model import Scenario
from triage.schema import TriageResult


class UsageTracker(BaseCallbackHandler):
    """Sums token usage and counts model calls across every LLM call in a run (thread-safe)."""

    def __init__(self, trace: Trace | None = None) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.llm_calls = 0
        self.retries = 0  # structured calls re-asked after a parse/validation failure
        self.trace = trace
        self._lock = threading.Lock()

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: ANN001
        i = o = 0
        for gens in response.generations:
            for g in gens:
                msg = getattr(g, "message", None)
                um = getattr(msg, "usage_metadata", None) or {}
                i += um.get("input_tokens", 0)
                o += um.get("output_tokens", 0)
        with self._lock:
            self.input_tokens += i
            self.output_tokens += o
            self.llm_calls += 1
        if self.trace:
            self.trace.add(type="llm", input_tokens=i, output_tokens=o)

    def as_dict(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "llm_calls": self.llm_calls,
                "retries": self.retries}


def structured_call(llm, schema, messages: list[BaseMessage], tracker: UsageTracker, retries: int = 1):
    """Call the model for a typed answer; retry once on a parse/validation failure.

    Each retry is counted and written to the trace: it costs tokens and is itself a signal about the model.
    """
    runnable = llm.with_structured_output(schema)
    last: Exception | None = None
    for attempt in range(retries + 1):
        if attempt:
            with tracker._lock:  # multi-agent workers share one tracker across threads
                tracker.retries += 1
            if tracker.trace:
                tracker.trace.add(type="retry", schema=schema.__name__, error=f"{type(last).__name__}: {last}"[:500])
        try:
            out = runnable.invoke(messages, {"callbacks": [tracker]})
            if out is not None:
                return out
            last = ValueError("model returned no structured output")
        except Exception as exc:  # noqa: BLE001 - provider and parser errors vary; the retry covers them
            last = exc
    raise last  # type: ignore[misc]


@dataclass
class RunRecord:
    scenario_id: str
    approach: str
    run_idx: int
    result: dict | None = None
    error: str | None = None
    seen_ids: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    trace: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def execute(fn, approach: str, scenario: Scenario, llm, retriever, run_idx: int = 0, cfg: dict | None = None) -> RunRecord:
    """Run one approach on one scenario and capture everything needed to score and audit it."""
    cfg = {"max_steps": 8, **(cfg or {})}
    trace = Trace()
    tracker = UsageTracker(trace)
    env = Environment(scenario, retriever, trace)
    rec = RunRecord(scenario.id, approach, run_idx)
    t0 = time.perf_counter()
    try:
        result: TriageResult = fn(scenario.alert, env, llm, tracker, cfg)
        rec.result = result.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - a failed run is data, not a crash
        rec.error = f"{type(exc).__name__}: {exc}"
        trace.add(type="error", detail=traceback.format_exc()[-1500:])
    rec.latency_s = round(time.perf_counter() - t0, 3)
    rec.seen_ids = sorted(env.seen_ids)
    rec.calls = env.calls
    rec.evidence = dict(env.evidence)
    rec.usage = tracker.as_dict()
    rec.trace = trace.events
    return rec
