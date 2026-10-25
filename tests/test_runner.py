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
