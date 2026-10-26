# Learning Log

Short entries, newest first. This becomes your interview material, so record the *why*.

Template:

## YYYY-MM-DD: <what I worked on>
- **Decision:** what I chose (e.g. chunk size 800, overlap 100)
- **Why:** my reasoning at the time
- **Evidence:** what I measured or saw
- **Surprise / failure:** what didn't work, and what I think caused it
- **Next:** what I'll try

## 2026-10-25: a concrete system to ground everything (Fianchetto)
- **Surprise / failure:** the starter runbooks and scenarios were generic: about 25 service names across 12
  scenarios, each scenario its own little world, nothing saying what is stateful. "Revert the deploy" reads the same
  for a stateless API and a game server holding live games, which real runbooks never would.
- **Decision:** one fictional online chess platform (`docs/system.md`): gateway, accounts, matchmaking, stateful
  game servers (players connect directly over WebSocket), leaderboards, stats, anticheat, Postgres, two Redis
  clusters. Runbooks rewritten against it, mitigation first, branching where stateful and stateless differ.
- **Decision:** 18 scenarios (was 12) in three difficulty tiers of 6 (`docs/scenario-plan.md`, never indexed).
- **Why tiers:** all 12 starter scenarios had a deliberate trap. That favours the approaches that look more (B, C) by
  construction; the real question is also whether C is worth its cost on ordinary incidents. 4 per tier would be
  noise (one scenario = 25 points), so 6 per tier.
- **Decision:** ground truth is the mitigation to apply now; root cause and real fix are follow-ups, not scored.
- **Trade-off:** categories stay balanced for coverage, not weighted by real frequency (changes cause most outages;
  bad_change gets 6 of 18). Runbooks were written knowing the scenarios, so retrieval-assisted accuracy is an upper
  bound.
- **Next:** rewrite `defs.py`, index the system card, chunk runbooks by heading, redo the retrieval queries.

## 2026-10-25: corpus, chunk size, and how to evaluate retrieval
- **Corpus:** 242 icco postmortems + 240 danluu entries; 164 danluu URLs duplicate icco, so the index holds 326
  documents (8 runbooks + 318 unique postmortems). `--fetch-pages` skipped: the loader never reads the pages.
- **Surprise / failure:** the planned eval (search with the alert symptom, is the right runbook in the top 4?) can't
  choose a chunk size. Most alerts describe a symptom that doesn't name the cause ("5xx above 40%" says nothing about
  an expired certificate), so only the 4 alerts that do name it ever hit: 0.4 is the ceiling at every size.
  RB-04 (traffic spike) shows up for almost every symptom query because it mentions CPU, latency and errors generically.
- **Decision:** choose settings with 25 labeled diagnosis-style queries (`triage/evals/retrieval_queries.json`, about
  3 per runbook): what an agent searches after forming a hypothesis. Drafted by Claude, owner review pending; not edited
  after seeing results. Keep the symptom number as its own metric: it predicts what the fixed pipeline (A) retrieves.
- **Evidence** (nomic-embed-text, overlap 120, k=4, hit@4 / MRR):

  | chunk size | chunks | diagnosis queries (n=25) | alert symptom (n=10) | full alert text (n=10) |
  |---|---|---|---|---|
  | 600 | 1212 | 0.92 / 0.833 | 0.4 / 0.35 | 0.4 / 0.327 |
  | 900 | 804 | 0.88 / 0.813 | 0.4 / 0.275 | 0.2 / 0.188 |
  | 1400 | 554 | 0.84 / 0.763 | 0.4 / 0.25 | 0.2 / 0.237 |

- **Decision:** chunk size 600 (new default), k=4. At 600, hit@k on diagnosis queries is 0.76/0.88/0.92/0.92 for
  k=1/2/3/4 and flat after; 4 leaves a margin without more noise in the prompt.
- **Surprise:** nomic's documented `search_query:`/`search_document:` prefixes made it worse at 600 (0.80 / 0.748
  diagnosis, 0.3 / 0.183 symptom), so no prefixes.
- **Misses at 600:** q09 (slow memory growth), q16 (one load-balancer target flapping), and partly q01, q02, q05,
  q24: real postmortems outrank the runbook. That's corpus dilution, which is the point of having the corpus.
- **Caveat for the write-up:** the runbooks and the queries were both written on this side, so 0.92 is an upper bound.

## 2026-10-25: judge thinking off
- **Decision:** `JUDGE_REASONING=false` for qwen3.8:27b, provisionally.
- **Evidence:** re-judged the 4 smoke runs that produced a result (not eval data): thinking on averaged 148 s per
  verdict, off 32 s (~85% fewer output tokens); verdicts identical on 4/4. Speed is ~8 tok/s either way, 100% GPU,
  no memory pressure, so the model itself is the limit.
- **Why provisional:** 4 runs (3 easy correct ones) can't show judge quality holds. The ~20 hand labels decide; if
  agreement is weak, re-judge with thinking on (runs keep their full result, so agents need not re-run).

## 2026-10-25: gpt-oss structured-output failures, retries, reasoning effort
- **Surprise / failure:** the multi-agent smoke run on s01 died in a worker. gpt-oss:20b on Ollama fails three ways,
  intermittently: (1) empty reply after hidden reasoning, (2) malformed JSON, (3) the Ollama server raising
  "error parsing tool call", which crashed the ReAct loop because nothing caught it there.
- **Evidence:** replayed the final `Finding` call on 6 saved worker histories (scratch experiment, not eval data):
  default reasoning failed 10/120 (8.3%); `reasoning="low"` failed 0/120 (Fisher p ~ 0.002), and used ~25% fewer
  output tokens. `method="function_calling"` failed 30/30 with this model.
- **Decision:** `LLM_REASONING=low` for the agent, same for every approach (recorded in `meta.json`). Judge keeps its
  default until its speed and agreement with hand labels are measured.
- **Trade-off:** low effort may make the agent investigate less thoroughly. That is part of the configuration being
  tested, not a bias between approaches; state it in the write-up.
- **Decision:** every model call (tool-loop steps and typed answers) retries up to 3 times with exponential backoff and
  full jitter (1, 2, 4 s caps, max 30 s); only then does the run fail. Web APIs fail transiently too.
- **Why it's still honest:** each retry is a trace event and `retries` is a report column; failed runs stay in
  `runs.jsonl`; the runner now refuses to overwrite real results; judge tokens and retries are stored per run.

## 2026-10-25: local models via Ollama, and how to price them
- **Decision:** agent `gpt-oss:20b`, judge `qwen3.8:27b`, embeddings `nomic-embed-text`, all on Ollama (M4 Pro, 48 GB).
- **Why:** agent is a mixture-of-experts model (~3.6B active), so 108+ runs stay fast; judge is a different family
  (self-preference bias) and makes few calls, so it can be the slower, stronger model. Ollama embeddings avoid torch.
- **Decision:** price local models at a shadow rate: median per-token price across hosted providers of the same
  open-weight model (OpenRouter, 2026-10-25; ranges stored in `pricing.json`). Not $0.
- **Why:** internal compute has an opportunity cost, $0 breaks comparison with later API runs, and per-token pricing
  keeps the cost difference between approaches proportional to tokens. Hardware amortization and GPU-hour pricing were
  rejected: they measure this Mac, not the approach (latency is reported separately anyway).
- **Decision:** set Ollama `num_ctx` explicitly (32768) and load `.env` in code.
- **Why:** Ollama silently drops the start of an over-long prompt, which would corrupt ReAct histories without an error.
- **Next:** smoke test; check Ollama input-token counts aren't undercounted when it reuses its prompt cache.

## 2026-10-24: offline harness built (with Claude)
- **Decision:** categories defined by which runbook action fixes them; `bad_change` wins whenever a recent change is the trigger.
- **Why:** makes ground truth unambiguous and the judge's job narrower.
- **Evidence:** 34 offline tests pass against a scripted fake model; fake runs are stamped and kept in `results_fake/`.
- **Surprise / failure:** first key-evidence metric required citing hundreds of repeated log lines; changed it to one item for "any key log line".
- **Next:** wire the real model, smoke test one scenario, then run the full evaluation.
