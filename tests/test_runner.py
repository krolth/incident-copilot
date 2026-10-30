import json

from triage.evals.report import build_report
from triage.evals.runner import run_all


def test_fake_runner_end_to_end_and_banners(tmp_path):
    out = tmp_path / "fake"
    recs = run_all(str(out), ["fixed", "single"], ["s01", "s11"], 2, fake=True, parallel=2)
    assert len(recs) == 8
    assert (out / "FAKE_RUN_NOT_EVALUATION_DATA.txt").exists()
    meta = json.loads((out / "meta.json").read_text())
    assert meta["fake"] and meta["scenario_fingerprint"]
    report = build_report(str(out))
    assert "NOT EVALUATION DATA" in report
    # s01 is medium, s11 hard: both tiers get a column, and every record carries its tier
    assert "## By difficulty" in report and "| medium | hard |" in report
    assert {r["difficulty"] for r in recs} == {"medium", "hard"}


def test_dev_scenarios_are_flagged_and_reported_separately(tmp_path):
    out = tmp_path / "fake"
    recs = run_all(str(out), ["fixed"], ["s01", "s13"], 1, fake=True, parallel=1)
    assert {r["scenario_id"][:3]: r["dev"] for r in recs} == {"s01": True, "s13": False}
    report = build_report(str(out))
    assert "## Held out from prompt tuning" in report and "tuned on s01 only" in report
    assert "| fixed | 100% (n=2) | 100% (n=1) | 100% (n=1) |" in report


def test_batch_records_runtime_and_code_version(tmp_path):
    out = tmp_path / "fake"
    recs = run_all(str(out), ["fixed"], ["s13"], 1, fake=True, parallel=1, worker_steps=7)
    meta = json.loads((out / "meta.json").read_text())
    assert meta["wall_clock_s"] >= 0 and meta["started_at"] <= meta["finished_at"]
    assert len(meta["prompts_sha256"]) == 12 and meta["worker_steps"] == 7 and "git_commit" in meta
    assert recs[0]["judge_latency_s"] >= 0
    report = build_report(str(out))
    assert "wall-clock:" in report and "judge time" in report and "worker 7" in report


def test_resume_skips_finished_runs(tmp_path):
    out = str(tmp_path / "r")
    run_all(out, ["fixed"], ["s01"], 1, fake=True)
    again = run_all(out, ["fixed"], ["s01"], 2, fake=True, resume=True)
    assert len(again) == 2  # one reused, one new


def test_real_results_are_never_overwritten(tmp_path):
    import pytest
    out = tmp_path / "real"
    out.mkdir()
    (out / "runs.jsonl").write_text('{"kept": true}\n')
    with pytest.raises(SystemExit, match="--resume"):
        run_all(str(out), ["fixed"], ["s01"], 1, fake=False)
    assert (out / "runs.jsonl").read_text() == '{"kept": true}\n'


def test_judge_usage_and_retry_policy_are_recorded(tmp_path):
    out = tmp_path / "j"
    recs = run_all(str(out), ["fixed"], ["s01"], 1, fake=True)
    assert recs[0]["judge_usage"]["llm_calls"] == 1 and "judge_trace" in recs[0]
    assert json.loads((out / "meta.json").read_text())["retry_policy"]["max_retries"] == 3


def test_prompts_hash_covers_category_definitions(monkeypatch):
    import triage.prompts as P
    from triage.evals.runner import code_version
    before = code_version()["prompts_sha256"]
    monkeypatch.setattr(P, "RULES", P.RULES.replace("bad_change", "bad_change!"))
    assert code_version()["prompts_sha256"] != before


def test_spending_cap_stops_new_runs(tmp_path, monkeypatch):
    import triage.evals.runner as runner
    # price the fake model so its first run alone exceeds a 1-cent cap
    monkeypatch.setattr(runner, "load_pricing", lambda: {"fake-oracle": {"input_per_mtok": 1e4, "output_per_mtok": 1e4}})
    out = tmp_path / "capped"
    recs = run_all(str(out), ["fixed"], ["s01", "s08", "s13"], 1, fake=True, parallel=1, max_cost_usd=0.01)
    meta = json.loads((out / "meta.json").read_text())
    assert len(recs) == 1 and meta["runs_skipped_by_cap"] == 2 and meta["priced_spend_usd"] >= 0.01


def test_openai_reasoning_effort(monkeypatch):
    import pytest
    from triage.llm import _build
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-key")
    assert _build("openai", "some-model", None, "low").reasoning_effort == "low"
    with pytest.raises(ValueError):
        _build("openai", "some-model", None, False)


def test_spending_cap_counts_earlier_runs_on_resume(tmp_path, monkeypatch):
    import triage.evals.runner as runner
    monkeypatch.setattr(runner, "load_pricing", lambda: {"fake-oracle": {"input_per_mtok": 1e4, "output_per_mtok": 1e4}})
    out = str(tmp_path / "capped")
    run_all(out, ["fixed"], ["s01"], 1, fake=True, parallel=1)  # no cap: spends more than a cent
    recs = run_all(out, ["fixed"], ["s01", "s08"], 1, fake=True, parallel=1, resume=True, max_cost_usd=0.01)
    assert len(recs) == 1  # the s08 run is not started: the folder is already over the cap
