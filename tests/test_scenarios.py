from triage.scenarios import all_scenarios, fingerprint, get_scenario
from triage.schema import Category, RUNBOOK_IDS


def test_twelve_scenarios_with_unique_ids():
    sc = all_scenarios()
    assert len(sc) == 12 and len({s.id for s in sc}) == 12


def test_two_unanswerable_and_ground_truth_consistent():
    sc = all_scenarios()
    assert sum(not s.truth.answerable for s in sc) == 2
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
