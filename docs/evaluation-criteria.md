# Evaluation Criteria

Incident Triage Copilot · Sharad Cornejo Altuzar · Capstone project, AI Engineering cohort (RAG & Agents)

Companion documents: [Problem Definition](problem-definition.md) · [Data Processing](data-processing.md) · [System Design](design-doc.md) · [Results site](https://krolth.github.io/incident-copilot/)

## Experiment design

| Choice | Setting | Why |
|---|---|---|
| Designs compared | fixed pipeline, single ReAct agent, multi-agent (coordinator + logs, metrics and knowledge specialists) | the research question |
| Incidents | 18: 6 easy, 6 medium, 6 hard; 3 of them have no single answer | coverage of every category and of abstention |
| Repeats | 3 runs per incident and design | model output varies; report run-to-run variance |
| Models | `gpt-oss:20b` (local) and `gpt-6.1-terra` (hosted), both at low reasoning effort | does the answer depend on the model? |
| Runs | 18 × 3 × 3 = 162 per model, 324 in all | |
| Held out | prompts tuned on s01, s08 and s11 only (one per tier); headline numbers use the other 15 | tuning on the test set would inflate accuracy |
| Frozen | prompts, step caps (12 single agent, 8 per specialist) and ground truth fixed before the full runs | the two models see identical conditions |

Each run gets the same alert, the same four tools over the same data, and must return the same typed answer, so
scoring never depends on which design produced it. Every run is saved as a JSON trace (every model call, tool call,
token count and the answer) for cost and failure analysis.

## Metrics

Scored by code unless marked as judged.

| Metric | Exactly how it is scored | Type |
|---|---|---|
| **Root-cause accuracy** (headline) | the answer's `category` equals the ground-truth category; on the 3 incidents with no single answer, the correct category is `insufficient_evidence` | code |
| Abstention correctness | the answer abstains if and only if the incident has no single answer | code |
| Runbook accuracy | `recommended_runbook` equals the incident's runbook | code |
| Citation validity | share of cited ids that appeared in that run's tool output | code |
| Key evidence seen / cited | share of the incident's key evidence items the agent saw in tool output, and cited in its answer. Key log lines are many and repetitive, so any one of them counts as the log item; each key deploy, metric and runbook is its own item | code |
| Action alignment, 0 to 2 | does the recommended action lead to the same mitigation as the reference action? | LLM judge |
| Evidence support, 0 to 2 | does the cited evidence support the stated diagnosis? | LLM judge |
| Tokens, cost, latency, tool calls, model calls, retries, step-cap hits | counted from the run trace | code |
| Retrieval hit rate | hit@k and MRR of the knowledge base on 25 labeled diagnosis queries (see [Data Processing](data-processing.md)) | code |

The failing component is recorded with every answer and shown on the results site, and a loose name match is
computed, but it is not part of the headline: free-text component names ("chess-db replica", "db-02") make exact
scoring unreliable.

Results are reported for all 18 incidents, for the 15 held-out incidents, by difficulty tier, and per repeat.

## The LLM judge

The judge is a different model family from either agent (`qwen3.8:27b`, local, thinking off), to reduce
self-preference bias. It sees the reference category, runbook and action (or, for the 3 incidents with no single answer, that
abstaining is correct), the agent's full answer, and the text of each piece of evidence it cited, and scores:

- **Action alignment:** 2 if the recommended action would lead to the same mitigation as the reference; 1 if partly
  right or incomplete; 0 if wrong, unsafe or missing.
- **Evidence support:** 2 if the cited evidence fully supports the stated diagnosis; 1 if partly; 0 if it does not, or
  nothing relevant is cited. A wrong diagnosis can still be well supported; this scores support, not correctness.

**Validation against a human expert.** The judge is checked against hand labels from an incident-response
practitioner (the project owner) before its scores are quoted:

- About 20 runs, sampled round-robin across the three designs and spread over all 18 incidents.
- Labelled blind: the labelling tool hides which design produced the answer and never shows the judge's scores, which
  are kept in a separate file.
- Agreement is reported as exact match, within one point, and Cohen's kappa, for each of the two scores.
- The judge's scores are used in conclusions only if agreement is substantial (Cohen's kappa of at least 0.6);
  otherwise they are reported as unvalidated and the conclusions rest on the code-scored metrics.

## Statistics

- **Run level:** Fisher's exact test on correct versus wrong runs (45 held-out runs per design).
- **Incident level:** the three repeats of one incident are not independent tries, so designs are also compared
  incident by incident: on how many incidents did one design get more runs right than the other? A two-sided sign test
  on those counts.
- With 18 incidents, per-tier results (6 incidents each) are read as descriptive only.

## Cost

- **Hosted model:** OpenAI list price per token (standard tier, retrieved 2026-10-29). The cached-input discount is
  ignored, so reported cost is an upper bound.
- **Local models:** priced at a shadow rate, the median price across hosting providers serving the same open model
  (OpenRouter, retrieved 2026-10-25), not at $0. Local compute has a cost, and $0 would make the two runs incomparable.
- Prices are stored in `pricing.json`; a run with an unpriced model shows cost as n/a rather than a guess.
- Latency is wall-clock agent time per run, reported separately from cost.

## Failure analysis

Every run the report flags (wrong category, a crash, or any invalid citation) is read in full, and the failures are
grouped into a taxonomy in the README: for example abstaining with the evidence in hand, missing a change outside the
searched window, or blaming a victim instead of the cause.

## Known limits

- **Small sample.** 18 incidents; repeats of one incident are correlated.
- **Retrieval is an upper bound.** The runbooks were written by the same person as the incidents, so they fit better
  than real runbooks would.
- **Two models, one setting each.** Low reasoning effort for both; prompts were tuned on the local model's dev runs.
- **Prompt inconsistency found after freezing:** the runbook index the agents see summarises RB-03 as "restart, capture
  diagnostics", while the `resource_leak` definition says never to restart game servers bare. Prompts stayed frozen so
  both runs are comparable; it is noted here rather than fixed.
- **Synthetic data.** The platform, incidents and telemetry are invented; no employer data is used.
