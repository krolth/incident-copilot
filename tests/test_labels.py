import csv
import json

from triage.approaches import APPROACHES
from triage.approaches.common import execute
from triage.evals.labels import agreement, export, judge_path
from triage.scenarios import get_scenario
from triage.testing.fake_llm import oracle_llm


def write_runs(tmp_path, retriever):
    recs = []
    for sid in ("s01", "s08"):
        for app in ("fixed", "single"):
            sc = get_scenario(sid)
            rec = execute(APPROACHES[app], app, sc, oracle_llm(sc, "correct"), retriever).to_json()
            rec["judge"] = {"action_alignment": 2, "evidence_support": 1}
            recs.append(rec)
    p = tmp_path / "runs.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs))
    return p


def test_label_sheet_is_blind_and_agreement_joins_judge(tmp_path, retriever):
    out = tmp_path / "labels.csv"
    assert export(str(write_runs(tmp_path, retriever)), str(out), n=4) == 4
    rows = list(csv.DictReader(open(out)))
    assert not any("judge" in col for col in rows[0])  # the labeller must not see the judge's scores
    assert judge_path(str(out)).exists()

    for r in rows:
        r["human_action"], r["human_evidence"] = "2", "1"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    a = agreement(str(out))
    assert a["n"] == 4 and a["action"]["exact"] == 1.0 and a["evidence"]["exact"] == 1.0


def test_label_sample_spreads_across_scenarios(tmp_path, retriever):
    out = tmp_path / "labels.csv"
    export(str(write_runs(tmp_path, retriever)), str(out), n=2)
    assert {r["key"][:3] for r in csv.DictReader(open(out))} == {"s01", "s08"}


def test_grader_saves_scores_and_resumes(tmp_path, retriever, monkeypatch):
    from triage.evals import grade
    out = tmp_path / "labels.csv"
    export(str(write_runs(tmp_path, retriever)), str(out), n=3)
    answers = iter(["2", "1", "7", "0", "?", "2", "q"])  # row 1 scored; bad input re-asked; quit during row 3
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    grade.main(str(out))
    rows = list(csv.DictReader(open(out)))
    assert [(r["human_action"], r["human_evidence"]) for r in rows] == [("2", "1"), ("0", "2"), ("", "")]
    answers = iter(["1", "1"])  # a second session only asks about the unscored row
    grade.main(str(out))
    assert list(csv.DictReader(open(out)))[2]["human_action"] == "1"
