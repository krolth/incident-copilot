import pytest

from triage.approaches import APPROACHES
from triage.approaches.common import execute
from triage.scenarios import all_scenarios, get_scenario
from triage.testing.fake_llm import oracle_llm


@pytest.mark.parametrize("approach", list(APPROACHES))
def test_each_approach_returns_valid_result_with_oracle(approach, retriever):
    sc = get_scenario("s01")
    rec = execute(APPROACHES[approach], approach, sc, oracle_llm(sc), retriever)
    assert rec.error is None and rec.result["category"] == "bad_change"
    assert rec.usage["llm_calls"] >= 1 and rec.calls


def test_multi_runs_each_worker_with_only_its_tools(retriever):
    sc = get_scenario("s01")
    rec = execute(APPROACHES["multi"], "multi", sc, oracle_llm(sc), retriever)
    by_agent = {}
    for c in rec.calls:
        by_agent.setdefault(c["agent"], set()).add(c["tool"])
    assert by_agent["logs"] <= {"search_logs"}
    assert by_agent["metrics"] <= {"get_metrics", "get_recent_deploys"}
    assert by_agent["knowledge"] <= {"search_knowledge"}


def test_step_cap_stops_a_looping_agent(retriever):
    sc = get_scenario("s01")
    rec = execute(APPROACHES["single"], "single", sc, oracle_llm(sc, "loop"), retriever, cfg={"max_steps": 3})
    assert rec.error is None and rec.result is not None
    assert len(rec.calls) <= 3 * 2
    assert [e for e in rec.trace if e["type"] == "step_cap"]  # recorded, so the report can count it


def test_failure_is_recorded_not_raised(retriever):
    sc = get_scenario("s01")

    def boom(*a, **k):
        raise RuntimeError("provider down")

    rec = execute(boom, "boom", sc, oracle_llm(sc), retriever)
    assert rec.result is None and "provider down" in rec.error


def test_fixed_pipeline_never_uses_long_windows(retriever):
    sc = get_scenario("s09")
    rec = execute(APPROACHES["fixed"], "fixed", sc, oracle_llm(sc), retriever)
    assert all(c["args"].get("window", "1h") in ("1h", "24h") for c in rec.calls if c["tool"] != "search_knowledge")
    assert not any("7d" in i for i in rec.seen_ids)


def test_worker_roster_names_each_workers_real_tools():
    from triage.approaches.multi_agent import WORKER_TOOLS
    from triage.prompts import PLAN_SYSTEM, SYNTH_SYSTEM, WORKER_ROSTER
    for worker, tools in WORKER_TOOLS.items():
        assert f"- {worker} ({', '.join(tools)})" in WORKER_ROSTER
    assert WORKER_ROSTER in PLAN_SYSTEM and WORKER_ROSTER in SYNTH_SYSTEM
