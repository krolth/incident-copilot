"""Run scenarios x approaches x repeats, score and judge each run, and write the results.

  python -m triage.evals.runner --runs 3                 real model (needs LLM_MODEL, JUDGE_MODEL, keys, built index)
  python -m triage.evals.runner --fake                   offline plumbing check with the scripted oracle -> results_fake/
  python -m triage.evals.runner --fake --fake-mode wrong

Output directory contains runs.jsonl (one record per run: result, trace, score, judge, judge latency), meta.json
(start/end time and wall-clock, git commit, prompts hash, model names, scenario fingerprint, settings). --resume skips runs already in runs.jsonl,
so a rate-limit crash costs only the unfinished runs. Fake output is stamped and kept in its own folder:
it must never be quoted as a result.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from triage.approaches import APPROACHES
from triage.approaches.common import BACKOFF_BASE_S, BACKOFF_CAP_S, MAX_RETRIES, MAX_STEPS, WORKER_STEPS, UsageTracker, execute
from triage.env import Trace
from triage.evals.judge import judge_run
from triage.evals.scoring import load_pricing, score_run
from triage.scenarios import all_scenarios, fingerprint, is_dev
from triage.testing.fake_llm import FAKE_BANNER, oracle_llm


REPO = Path(__file__).resolve().parents[2]


def code_version() -> dict:
    """Which code and prompts produced a batch: commit, uncommitted changes, and a hash of the prompt text the
    models receive (prompts are what is tuned between dev batches, so they get their own fingerprint). Hashes the
    rendered constants, not prompts.py, because the prompts embed category definitions from schema.py."""
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    import triage.prompts as P
    prompts = json.dumps({k: v for k, v in vars(P).items() if k.isupper() and isinstance(v, (str, dict))},
                         sort_keys=True).encode()
    status = git("status", "--porcelain")
    return {"git_commit": git("rev-parse", "--short", "HEAD") or None,
            "git_dirty": None if status is None else bool(status),
            "prompts_sha256": hashlib.sha256(prompts).hexdigest()[:12]}


def run_all(out_dir: str, approaches: list[str], scenario_ids: list[str] | None, runs: int, *, fake: bool = False,
            fake_mode: str = "correct", persist_dir: str = "chroma_db", judge: bool = True, parallel: int = 2,
            resume: bool = False, max_steps: int = MAX_STEPS, worker_steps: int = WORKER_STEPS,
            model_name: str = "") -> list[dict]:
    from triage.knowledge.index import build_index, load_index
    from triage.llm import describe, get_judge_llm, get_llm

    started, t0 = dt.datetime.now(dt.timezone.utc), time.perf_counter()
    version = code_version()  # taken at start: files may change while a long batch runs
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runs_path = out / "runs.jsonl"
    if runs_path.exists() and not resume and not fake:
        # every real run is evaluation data, including failures: never overwrite it silently
        raise SystemExit(f"{runs_path} already has runs. Use --resume to add to it, or --out for a new folder.")
    scenarios = [s for s in all_scenarios() if not scenario_ids or s.id in scenario_ids or any(s.id.startswith(x) for x in scenario_ids)]
    if not scenarios:
        raise SystemExit(f"no scenarios match {scenario_ids}")

    if fake:
        print(f"*** {FAKE_BANNER} ***")
        retriever = build_index(tempfile.mkdtemp() + "/chroma", include_corpus=False, embeddings_kind="hash")
        model_name = "fake-oracle"
        llm_for = lambda sc: oracle_llm(sc, fake_mode)  # noqa: E731
        judge_llm_for = lambda sc: oracle_llm(sc, "correct")  # noqa: E731
        (out / "FAKE_RUN_NOT_EVALUATION_DATA.txt").write_text(FAKE_BANNER + "\n")
    else:
        retriever = load_index(persist_dir)
        llm = get_llm()
        jl = get_judge_llm() if judge else None
        llm_for = lambda sc: llm  # noqa: E731
        judge_llm_for = lambda sc: jl  # noqa: E731
        model_name = model_name or describe()["model"]

    pricing = load_pricing()
    done: set[tuple] = set()
    records: list[dict] = []
    if resume and runs_path.exists():
        for line in runs_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                records.append(r)
                done.add((r["scenario_id"], r["approach"], r["run_idx"]))

    jobs = [(sc, a, i) for sc in scenarios for a in approaches for i in range(runs) if (sc.id, a, i) not in done]
    lock = threading.Lock()
    f = open(runs_path, "a" if resume else "w")

    def work(job):
        sc, app, i = job
        rec = execute(APPROACHES[app], app, sc, llm_for(sc), retriever, i, {"max_steps": max_steps, "worker_steps": worker_steps}).to_json()
        rec["score"] = score_run(sc, rec, model_name, pricing)
        rec["judge"] = None
        if judge and rec["result"] is not None:
            jtrace = Trace()
            jtracker = UsageTracker(jtrace)
            jt0 = time.perf_counter()
            try:
                rec["judge"] = judge_run(judge_llm_for(sc), sc, rec, jtracker)
            except Exception as exc:  # noqa: BLE001
                rec["judge_error"] = f"{type(exc).__name__}: {exc}"
            # kept even when the judge failed: evaluation overhead (tokens, retries) is reported separately
            rec["judge_latency_s"] = round(time.perf_counter() - jt0, 3)
            rec["judge_usage"] = jtracker.as_dict()
            rec["judge_trace"] = jtrace.events
        rec["fake"] = fake
        rec["difficulty"] = sc.difficulty
        rec["dev"] = is_dev(sc.id)  # prompts were tuned on it
        with lock:
            records.append(rec)
            f.write(json.dumps(rec) + "\n")
            f.flush()
            print(f"[{len(records)}/{len(jobs) + len(done)}] {sc.id} {app} #{i} "
                  f"{'ERROR ' + rec['error'][:80] if rec['error'] else rec['result']['category']} "
                  f"cat_ok={rec['score']['category_correct']} agent={rec['latency_s']:.0f}s judge={rec.get('judge_latency_s', 0):.0f}s",
                  flush=True)  # flush: progress must show up when stdout is redirected to a file
        return rec

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        list(pool.map(work, jobs))
    f.close()

    finished = dt.datetime.now(dt.timezone.utc)
    meta = {"timestamp": finished.isoformat(), "started_at": started.isoformat(), "finished_at": finished.isoformat(),
            # this invocation only: a --resume batch adds its own wall-clock to the earlier one's
            "wall_clock_s": round(time.perf_counter() - t0, 1), "runs_this_invocation": len(jobs), **version,
            "fake": fake, "fake_mode": fake_mode if fake else None,
            "model": model_name, "judge_model": "fake-oracle" if fake else describe()["judge_model"],
            "embeddings": "hash" if fake else describe()["embeddings"], "scenario_fingerprint": fingerprint(),
            "llm_settings": None if fake else {k: describe()[k] for k in ("provider", "reasoning", "judge_reasoning", "num_ctx")},
            "retry_policy": {"max_retries": MAX_RETRIES, "backoff_base_s": BACKOFF_BASE_S, "backoff_cap_s": BACKOFF_CAP_S},
            "approaches": approaches, "runs_per_cell": runs, "max_steps": max_steps,
            "worker_steps": worker_steps,
            "scenarios": [s.id for s in scenarios], "note": FAKE_BANNER if fake else ""}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--approaches", nargs="+", default=list(APPROACHES), choices=list(APPROACHES))
    ap.add_argument("--scenarios", nargs="*", help="scenario ids or prefixes (default: all)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", help="output dir (default results/ or results_fake/)")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--fake-mode", default="correct", choices=["correct", "wrong", "bad_citation", "loop"])
    ap.add_argument("--persist-dir", default="chroma_db")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max-steps", type=int, default=MAX_STEPS, help="single-agent step cap")
    ap.add_argument("--worker-steps", type=int, default=WORKER_STEPS, help="step cap per multi-agent worker")
    a = ap.parse_args()
    run_all(a.out or ("results_fake" if a.fake else "results"), a.approaches, a.scenarios, a.runs, fake=a.fake,
            fake_mode=a.fake_mode, persist_dir=a.persist_dir, judge=not a.no_judge, parallel=a.parallel,
            resume=a.resume, max_steps=a.max_steps, worker_steps=a.worker_steps)


if __name__ == "__main__":
    main()
