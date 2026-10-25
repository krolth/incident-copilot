from triage.approaches import APPROACHES
from triage.approaches.common import execute
from triage.evals.labels import cohen_kappa
from triage.evals.scoring import cost_usd, score_run
from triage.scenarios import all_scenarios, get_scenario
from triage.testing.fake_llm import oracle_llm


def run(sid, mode, retriever, approach="single"):
    sc = get_scenario(sid)
    rec = execute(APPROACHES[approach], approach, sc, oracle_llm(sc, mode), retriever).to_json()
    return sc, rec, score_run(sc, rec)


def test_correct_oracle_scores_correct_on_every_scenario(retriever):
    for sc in all_scenarios():
        rec = execute(APPROACHES["single"], "single", sc, oracle_llm(sc), retriever).to_json()
        s = score_run(sc, rec)
        assert s["category_correct"] and s["abstention_correct"] and s["runbook_correct"], sc.id
        assert s["invalid_citations"] == 0, sc.id


def test_wrong_oracle_scores_wrong(retriever):
    _, _, s = run("s01", "wrong", retriever)
    assert not s["category_correct"] and not s["runbook_correct"]


def test_fabricated_citation_is_detected(retriever):
    _, _, s = run("s01", "bad_citation", retriever)
    assert s["invalid_citations"] == 1 and s["citation_valid_rate"] < 1


def test_abstention_scoring(retriever):
    _, _, s = run("s11", "correct", retriever)
    assert s["abstention_correct"]
    _, _, s = run("s11", "wrong", retriever)
    assert not s["abstention_correct"]
    _, _, s = run("s01", "wrong", retriever)
    assert s["abstention_correct"] is True or s["abstention_correct"] is False  # defined, not None


def test_failed_run_scores_as_failure():
    sc = get_scenario("s01")
    s = score_run(sc, {"result": None, "calls": [], "usage": {}, "seen_ids": []})
    assert not s["valid"] and not s["category_correct"]


def test_cost_requires_listed_prices():
    assert cost_usd({"input_tokens": 1000, "output_tokens": 1000}, "m", {}) is None
    assert cost_usd({"input_tokens": 1_000_000, "output_tokens": 0}, "m", {"m": {"input_per_mtok": 2.0, "output_per_mtok": 8.0}}) == 2.0


def test_kappa():
    assert cohen_kappa([0, 1, 2, 2], [0, 1, 2, 2]) == 1.0
    assert cohen_kappa([], []) is None
