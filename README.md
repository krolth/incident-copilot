# Incident Copilot

Triage ops alerts with RAG over runbooks and public postmortems plus log, metric and deploy tools,
and measure whether a multi-agent design beats a single agent and a fixed pipeline.

Capstone for the AI Engineering "RAG & Agents" cohort. All incidents are synthetic; the postmortem
corpus is public (icco/postmortems, danluu/post-mortems). No employer data.

## Status
Offline harness complete and tested (34 tests). **Real-model results: none yet.** This README's results
section is filled in only from a real run (see `CLAUDE.md`, Sunday plan).

## Design in one paragraph
18 deterministic incidents on one fictional chess platform (15 answerable, 3 unanswerable; 6 easy, 6 medium, 6 hard) generate logs, metrics and deploys on demand.
Four tools expose them like production systems would: `search_logs`, `get_metrics`, `get_recent_deploys`,
`search_knowledge` (ChromaDB over 8 runbooks plus postmortems). Three approaches share one typed output:
A fixed pipeline, B single ReAct agent, C coordinator with logs/metrics/knowledge specialists.
Incidents contain traps: red-herring deploys, a config push missing from deploy history, a slow leak
visible only in a 7-day window, an expected batch job beside a real DNS failure, conflicting signals,
and two cases where the right answer is "not enough evidence".

## Evaluation
- Deterministic: root-cause category, component, runbook, abstention correctness, citation validity
  (cited ids must have been shown by a tool), key-evidence coverage, tokens, cost, latency, tool calls.
- LLM judge (a different model than the agent) for action alignment and evidence support, validated
  against ~20 hand labels (exact agreement and Cohen's kappa).
- Retrieval evaluated separately (hit@k, MRR) and across chunk sizes.
- 3 repeats per cell to expose run-to-run variance.

## Limitations (stated up front)
- 18 incidents (6 per tier) is a small sample; differences of one incident are noise.
- Runbooks and scenarios share an author, so retrieval-assisted accuracy is an upper bound.
- Simulated tools return clean text; real Elasticsearch/Grafana output is messier.

## Run it
See `CLAUDE.md` for commands. Quick check, no keys needed: `pip install -r requirements.txt && pytest -q`.

## Layout
`triage/` library, `ingest/` corpus downloaders, `tests/`, `docs/LEARNING_LOG.md` decision log.
