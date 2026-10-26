from triage.scenarios import all_scenarios, fingerprint, get_scenario
from triage.schema import Category, RUNBOOK_IDS


def test_eighteen_scenarios_with_unique_ids():
    sc = all_scenarios()
    assert len(sc) == 18 and len({s.id for s in sc}) == 18
    assert [s.id[:3] for s in sc] == [f"s{i:02d}" for i in range(1, 19)]


def test_three_unanswerable_and_ground_truth_consistent():
    sc = all_scenarios()
    assert sum(not s.truth.answerable for s in sc) == 3
    for s in sc:
        assert s.truth.runbook in RUNBOOK_IDS
        assert (s.truth.category == Category.insufficient_evidence) == (not s.truth.answerable)


def test_deterministic():
    assert fingerprint() == fingerprint()


def test_log_ids_unique_and_sorted():
    for s in all_scenarios():
        ids = [l.id for l in s.logs]
        assert len(ids) == len(set(ids))
        assert [l.t for l in s.logs] == sorted(l.t for l in s.logs)


def test_answerable_have_key_evidence():
    for s in all_scenarios():
        if s.truth.answerable:
            assert s.key_log_ids(), s.id


def test_prefix_lookup():
    assert get_scenario("s04").id.startswith("s04")


def test_six_scenarios_per_difficulty_tier():
    from triage.scenarios.model import DIFFICULTIES
    tiers = [s.difficulty for s in all_scenarios()]
    assert {t: tiers.count(t) for t in DIFFICULTIES} == {"easy": 6, "medium": 6, "hard": 6}


def test_category_mix_matches_the_plan():
    from collections import Counter
    mix = Counter(s.truth.category.value for s in all_scenarios())
    assert mix == {"bad_change": 6, "dependency_saturation": 2, "resource_leak": 2, "traffic_spike": 2,
                   "expired_credential": 1, "infra_failure": 2, "insufficient_evidence": 3}
