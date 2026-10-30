# Incident Copilot: instructions for Claude Code (BUILD MODE)

This is a capstone for an AI Engineering cohort (RAG & Agents). The teacher allows full AI assistance.
You may write and change code. The owner still has to understand it and defend it in a demo, so:
explain non-obvious choices in short code comments or in `docs/LEARNING_LOG.md`, and prefer simple code.

## What this is
An agent that triages ops alerts. Given an alert it investigates with four tools (logs, metrics,
deploys, runbook/postmortem search) and returns a typed `TriageResult` (root-cause category,
component, evidence ids, runbook, action, confidence), or abstains (`insufficient_evidence`).
The research question: does a multi-agent design beat a single agent, and both beat a fixed pipeline,
and at what cost? All data is synthetic or public. No employer data, ever.

Approaches: `fixed` (A, code chooses what to look at), `single` (B, one ReAct agent, 4 tools),
`multi` (C, coordinator + logs/metrics/knowledge workers, max one follow-up round).

## Layout
- `triage/schema.py` typed results; `triage/prompts.py` all prompts
- `triage/scenarios/` 18 deterministic incidents on the Fianchetto system (`defs.py`; plan in `docs/scenario-plan.md`, system in `docs/system.md`), engine (`model.py`). Ground truth lives here.
- `triage/env.py` the 4 tools over a scenario; records `seen_ids` and `evidence`
- `triage/knowledge/` runbooks (invented, RB-01..08), loader (runbooks + system card + icco/danluu corpus; never `docs/scenario-plan.md`), Chroma index, embeddings
- `triage/approaches/` `fixed.py`, `single_agent.py`, `multi_agent.py`, `react.py` (LangGraph loop, step cap), `common.py`
- `triage/llm.py` provider switch via env vars; `.env.example` lists them
- `triage/evals/` `scoring.py` (deterministic), `judge.py` (LLM judge), `labels.py` (human labels + kappa), `retrieval_eval.py`, `runner.py`, `report.py`
- `triage/testing/fake_llm.py` scripted fake model for offline tests
- `ingest/` corpus downloaders (output goes to git-ignored `corpus/`)
- `tests/` pytest; must stay green
- `site/` the static presentation website (GitHub Pages): `index` findings, `console` run replay on the architecture, `results`, `method`. `python site/build_data.py` regenerates `site/data/*.js` from `results/` and `results_openai/`; rerun it after any new batch so the site never shows stale or invented numbers
- `docs/run-log.md` one entry per real-model batch (what changed, settings, results, runtime, traces read); add one after every batch

## Commands
```
git config core.hooksPath .githooks                                    # once per clone: blocks commits of .env or key-shaped strings
pip install -r requirements.txt
pytest -q
python ingest/fetch_icco.py && python ingest/fetch_danluu.py          # corpus (git-ignored)
python -m triage.knowledge.index                                       # build chroma_db (needs EMBEDDINGS=ollama|local|openai)
python -m triage.evals.retrieval_eval --k 4 --diagnosis               # labeled queries; drop --diagnosis for alert-symptom queries
python -m triage.evals.runner --fake --runs 1                          # plumbing check, writes results_fake/
python -m triage.evals.runner --scenarios s01 --approaches single --runs 1   # first real smoke test
python -m triage.evals.runner --runs 3 --parallel 2                    # full evaluation -> results/
python -m triage.evals.report results
python -m triage.evals.labels export results/runs.jsonl labels.csv     # blind sheet; judge scores go to labels.judge.csv
python -m triage.evals.grade labels.csv                                 # score the sheet one run at a time (resumable)
python -m triage.evals.labels agreement labels.csv
```

## Rules (do not break these)
1. **Never fabricate results.** Numbers in docs come only from `results/` produced by a real model run.
   Fake runs (`results_fake/`) are plumbing tests and must never be quoted.
2. **Ground truth is frozen once real results exist.** Do not edit `GroundTruth`, scenario data, or
   rubric to fit results. If a scenario is genuinely wrong, log it in `docs/LEARNING_LOG.md`, fix it, and
   re-run everything (the scenario fingerprint in `meta.json` shows when results are stale).
3. Tests stay green. Add a test with each behavior change. Run `pytest -q` before saying you are done.
4. Do not commit `.env`, `corpus/`, `chroma_db/`, or `results*/` without being asked. Never print API keys. The repo is meant to be public: `.githooks/pre-commit` blocks key-shaped strings, and `site/` is deployed to GitHub Pages by `.github/workflows/pages.yml` on every push to main.
5. Keep `docs/design-doc` claims true. If the code diverges from the design doc, say so and tell the owner.
6. Never use real employer incidents, names, or data.
7. Report honestly: n=18 incidents (6 per difficulty tier) is small; runbooks were written by the scenario author, so
   retrieval-assisted accuracy is an upper bound. Say both in the write-up.
8. Money: ask before launching a full run (about 162 runs; multi-agent is the expensive one). Use `--scenarios` and `--runs 1` first.

## Known untested-in-sandbox items (verify first, in this order)
1. `triage/llm.py` against the real provider; check `with_structured_output` accepts `TriageResult`, `Plan`, `Finding`, `Synthesis` (schemas have no defaults on purpose; if a strict-schema provider rejects one, simplify `schema.py`).
2. Real embeddings in `triage/knowledge/embeddings.py` (`local` and `openai`).
3. `ingest/fetch_danluu.py --fetch-pages` (page fetching was blocked in the sandbox).
4. Token usage counts (`UsageTracker`) populate for the chosen provider; if tokens show 0, fix there.
5. Fill `pricing.json` with the real model prices, or cost shows n/a.

## Sunday plan
1. Set up `.env`, install, `pytest -q`.
2. Smoke test one scenario with `single`; read the trace in `results/runs.jsonl`. Tune `prompts.py` on the dev scenarios only (`DEV_SCENARIOS` in `triage/scenarios/__init__.py`: s01, s08, s11), not on all 18; the report gives held-out accuracy separately.
3. Fetch corpus, build index with real embeddings, run `retrieval_eval`; try chunk sizes 600/900/1400 and record the table.
4. Run the full evaluation (3 repeats), generate the report.
5. Export ~20 labels, label them by hand BEFORE looking at the judge columns, compute agreement.
6. Failure analysis: read every run in "Runs to read by hand", write the failure taxonomy.
7. README (4 to 5 pages), then the 3-minute demo script.
