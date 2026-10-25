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
    assert "NOT EVALUATION DATA" in build_report(str(out))


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
