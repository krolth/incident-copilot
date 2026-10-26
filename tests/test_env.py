from triage.env import Environment
from triage.scenarios import get_scenario


def env(retriever=None):
    return Environment(get_scenario("s01"), retriever)


def test_search_logs_returns_ids_and_tracks_seen():
    e = env()
    out = e.search_logs("matchmaking", "", "ERROR", "1h")
    assert "matching lines" in out and "[L" in out
    assert e.seen_ids and all(i.startswith("L") for i in e.seen_ids)
    assert e.calls[0]["tool"] == "search_logs"


def test_output_is_truncated_to_max_lines():
    e = env()
    out = e.search_logs("", "", "", "24h")
    shown = [l for l in out.splitlines() if l.startswith("[L")]
    assert len(shown) <= 20


def test_bad_arguments_give_helpful_errors():
    e = env()
    assert "Valid windows" in e.search_logs(window="2h")
    assert "Valid" in e.search_logs(level="LOUD")
    assert "Known services" in e.get_metrics("nope", "cpu_pct")
    assert "Available" in e.get_metrics("matchmaking", "nope")


def test_metrics_and_deploys():
    e = env()
    assert "[M:matchmaking:error_rate_pct:1h]" in e.get_metrics("matchmaking", "error_rate_pct", "1h")
    out = e.get_recent_deploys("", "24h")
    assert "[D" in out
    assert any(i.startswith("D") for i in e.seen_ids)


def test_search_knowledge_and_evidence_snippets(retriever):
    e = env(retriever)
    out = e.search_knowledge("revert a bad deploy", 3)
    assert "[K:RB-" in out
    assert any(k.startswith("K:") and v for k, v in e.evidence.items())


def test_knowledge_unavailable_message():
    assert "not available" in env().search_knowledge("x")


def test_tools_have_agent_label_baked_in():
    e = env()
    t = {x.name: x for x in e.tools(agent="logs")}
    t["search_logs"].invoke({"service": "matchmaking", "level": "ERROR"})
    assert e.calls[-1]["agent"] == "logs"
