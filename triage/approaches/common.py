"""Shared plumbing for all approaches: usage tracking, structured calls, and the RunRecord."""
from __future__ import annotations

import random
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

from triage.env import Environment, Trace
from triage.scenarios.model import Scenario
from triage.schema import TriageResult


# Model steps for the single agent's ReAct loop (multi-agent workers have their own `worker_steps`, WORKER_STEPS).
# 8 cut off half the single-agent dev runs mid-investigation (2026-10-26); every cap hit is recorded and reported.
MAX_STEPS = 12
WORKER_STEPS = 8  # per multi-agent worker ReAct loop; 5 cut off a worker in every multi dev run (2026-10-26)


class UsageTracker(BaseCallbackHandler):
    """Sums token usage and counts model calls across every LLM call in a run (thread-safe)."""

    def __init__(self, trace: Trace | None = None) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.llm_calls = 0
        self.retries = 0  # model calls re-tried after an error (see with_retries)
        self.llm_errors = 0  # calls the provider/server failed outright (no tokens are reported for these)
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

    def on_llm_error(self, error, **kwargs) -> None:  # noqa: ANN001
        with self._lock:
            self.llm_errors += 1

    def as_dict(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "llm_calls": self.llm_calls,
                "retries": self.retries, "llm_errors": self.llm_errors}


# Retry policy for EVERY model call (tool-loop steps and typed answers alike). Model servers fail
# transiently: Ollama sometimes cannot parse gpt-oss's tool call, a model returns an empty reply, a web API
# rate-limits or goes down. One such blip should not decide a run, so a call is retried up to MAX_RETRIES
# times; only then does it fail the run (which is still recorded, as a failed run). Every retry is written
# to the trace, so nothing is hidden: retries are reported per run.
MAX_RETRIES = 3
BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 30.0


def backoff_s(attempt: int) -> float:
    """Exponential backoff with full jitter: uniform(0, min(cap, base * 2**attempt)).

    Jitter spreads out parallel runs that failed together, so they don't all hit the server again at once.
    """
    return random.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2 ** attempt))


def with_retries(call, tracker: UsageTracker, where: str):
    """Run call(); on any exception wait (backoff_s) and retry, up to MAX_RETRIES times, then re-raise."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - provider, server and parser errors vary; all are retried
            if attempt == MAX_RETRIES:
                raise
            wait = backoff_s(attempt)
            with tracker._lock:  # multi-agent workers share one tracker across threads
                tracker.retries += 1
            if tracker.trace:
                tracker.trace.add(type="retry", where=where, attempt=attempt + 1, wait_s=round(wait, 2),
                                  error=f"{type(exc).__name__}: {exc}"[:500])
            time.sleep(wait)


def structured_call(llm, schema, messages: list[BaseMessage], tracker: UsageTracker):
    """Call the model for a typed answer, retrying failures (see with_retries)."""
    runnable = llm.with_structured_output(schema)

    def once():
        out = runnable.invoke(messages, {"callbacks": [tracker]})
        if out is None:
            raise ValueError("model returned no structured output")
        return out

    return with_retries(once, tracker, where=schema.__name__)


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
    cfg = {"max_steps": MAX_STEPS, **(cfg or {})}
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
