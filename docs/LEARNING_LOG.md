# Learning Log

Short entries, newest first. This becomes your interview material, so record the *why*.

Template:

## YYYY-MM-DD: <what I worked on>
- **Decision:** what I chose (e.g. chunk size 800, overlap 100)
- **Why:** my reasoning at the time
- **Evidence:** what I measured or saw
- **Surprise / failure:** what didn't work, and what I think caused it
- **Next:** what I'll try

## 2026-10-27: full local evaluation (162 runs; details in `docs/run-log.md`)
- **Evidence:** held-out category accuracy fixed 21/45, single 21/45, multi 22/45. No difference between
  approaches; multi costs ~8x the tokens and ~9x the latency of fixed. Dev accuracy was 67 to 89%, so the
  prompts fit the dev scenarios: held-out is the honest number.
- **Surprise:** the approaches differ by tier, not in total. Fixed is best on easy/medium and never abstains
  correctly (0/9 on s11, s12, s18); both agents get 8/9 there. Agency buys calibrated abstention, not diagnosis.
- **Surprise / failure:** the most common wrong answer for every approach is a false abstention (10 to 15 of 45
  non-abstain runs). Traces show narrow searches (short deploy window, keyword filters that miss the key line),
  then "insufficient evidence". The agents abstain correctly *and* wrongly: they abstain a lot.
- **Surprise:** s03, s07 and s14 are 0/9 for every approach; s14 is easy-tier. In s07 one multi run saw every key
  item and still abstained, so it is reasoning, not retrieval.
- **Not changed:** ground truth and prompts stay frozen (rule 2). Metric names being discoverable only through an
  error message is a tool limitation shared by all approaches; noted for the write-up, not fixed after the fact.
- **Did we expect multi to win?** No prediction was written down before the run; the design doc asks the question
  without one, so the write-up must not claim one after the fact. Multi has no extra tools by design (same four
  tools, same data): the only variable is control flow.
- **Why it could have won:** every specialist always looks at its area (knowledge searched 45/54 runs vs single's
  2/54); each worker has a short, focused context; the coordinator can ask for a follow-up round.
- **Why it didn't (hypotheses from the traces, to check in the failure analysis):**
  - *Handoff loss:* the coordinator reads workers' summaries, not raw evidence. s07 multi #1 had every key item
    and still abstained: more coverage, same decision.
  - *Splitting separates the signals triage needs together:* e.g. "error-rate metric high before the first ERROR
    log line" (s11) needs logs and metrics in one head; the logs and metrics workers each hold half.
  - *Routing is one more step that can fail:* in dev the coordinator asked the logs worker about deploys it
    cannot see (fixed with the roster, but it is still a step).
  - *Model limit:* gpt-oss:20b at low reasoning; each coordination step is another chance to slip.
- **Framing for the write-up:** with this model, splitting the investigation bought coverage but not better
  decisions; the bottleneck is synthesis. Agency did pay off in one place: calibrated abstention (agents 8/9, fixed
  0/9). A null result at 8x tokens and 9x latency is a finding, not a failure.
- **Next:** hand labels before reading the judge columns; read the remaining runs and test the hypotheses above
  (failure taxonomy); optionally re-run on a stronger hosted model (OpenAI config, cost estimate first) to separate
  "model limit" from "architecture": if multi still doesn't pull ahead there, it is the architecture.

## 2026-10-27: dev tuning closed; prompts frozen for the full local run
- **Decision:** stop tuning after dev5. Last dev numbers (dev scenarios only, not results): fixed 9/9, single 7/9,
  multi 6/9. The remaining misses are model limits (ignoring the explicit bad_change tie-break rule; treating a
  system-card dependency as proof of saturation), not routing or plumbing bugs, and more rounds on three
  scenarios risk fitting the prompts to them.
- **Changes from dev tuning, all general:** log histogram, step caps 12 (single) and 8 (worker), worker roster
  in the coordinator prompts, four prompt rules, `resource_leak` definition aligned with RB-03.
- **Run:** 18 scenarios × 3 approaches × 3 repeats = 162, local, one at a time (estimated ~4 h). Owner approved.

## 2026-10-26: first dev tuning round (details per batch in `docs/run-log.md`)
- **Surprise / failure:** the s11 log gap was invisible: `search_logs` showed 20 lines and hid the rest, so no
  agent could have seen it. **Decision:** add a count histogram to `search_logs` (like the bar chart above Kibana
  hits), starting at log retention so the start of generated data doesn't read as a gap. A tool fix, not a
  scenario change; no real results existed yet.
- **Surprise:** even with the histogram, 0 of 18 s11 runs noticed the gap: agents always filter by ERROR or a
  keyword, and in those views the gap's end looks like an error onset. Left as it is: that cross-check (metric
  elevated before the first ERROR line) is what a hard scenario should test.
- **Decision:** single-agent step cap 8 → 12; it cut off half the single-agent runs mid-investigation. Every cap
  hit is now recorded (`step_cap_hits`). Even at 12 it binds in 3 of 9 runs.
- **Evidence (prompt A/B, dev only, n=27 per arm):** four new prompt rules gave 21/27 correct vs 20/27 without them;
  no measurable effect. The instruction to search the knowledge base moved the single agent from 0/9 to 1/9 runs.
  Kept anyway: they are correct general rules and cost nothing, and invalid citations fell (single 97% vs 89%).
- **Finding to write up:** the single agent almost never uses RAG; it picks the runbook from the list in the prompt.
  Not forced in code, since that would change what approach B is.
- **Mistake (mine, Claude's):** I first said multi-agent workers got the same 8 steps as the single agent; they have
  their own cap of 5 (`worker_steps`), which binds in every multi run. Owner decision pending.
- **Decision:** batches now record start/end, wall-clock, judge latency per run, git commit and a prompts hash.
  The first dev batches lacked these; their run-log times are reconstructed from file timestamps and say so.

## 2026-10-26: dev scenarios for prompt tuning
- **Decision:** tune `prompts.py` on s01 (medium, bad_change), s08 (easy, infra_failure) and s11 (hard, abstain) only.
- **Why:** one per tier and three different categories. s01 was already read in the first smoke traces, so making it
  dev keeps that exposure inside the dev set. s11 because abstaining is the behaviour most likely to need prompt work.
- **Consequence:** every run records `dev`; the report adds held-out accuracy (15 incidents), the number to quote.

## 2026-10-26: retrieval on the new runbooks; section chunking rejected; system card indexed
- **Decision:** retrieval queries rewritten (v2, 25 queries, about 3 per runbook) in Fianchetto vocabulary, since v1
  named services that no longer exist. Frozen before any run; owner review pending. v1 numbers are not comparable.
- **Hypothesis:** chunking runbooks by `##` section (one idea per chunk) would beat fixed 600-char chunks.
- **Evidence** (nomic-embed-text, postmortems at 600/120 in every row, k=4; scratch ablation, not agent eval data):

  | runbook chunking, system card | diagnosis hit@1 / hit@4 / MRR (n=25) | alert symptom hit@4 (n=15) | full alert hit@4 / MRR (n=15) |
  |---|---|---|---|
  | fixed 600, no card | 0.60 / 0.84 / 0.727 | 0.40 | 0.533 / 0.432 |
  | by section, no card | 0.60 / 0.76 / 0.686 | 0.333 | not run |
  | by section, card | 0.60 / 0.76 / 0.686 | 0.333 | not run |
  | **fixed 600, card (chosen)** | 0.52 / 0.84 / 0.670 | 0.40 | 0.467 / 0.405 |

- **Surprise / failure:** sections were worse, not better: four queries dropped out of the top 4. Several sections of
  one runbook fill the top-k slots (q02's top 4 was RB-01 three times), and short sections ("When to use", "Do not")
  carry little to match. Two queries in 25 is not significant, but nothing supports the extra code, so it was removed.
- **Decision:** index the system card (sections 1-12, no status preamble, no decisions section, no diagram) with
  fixed chunks. hit@4 is unchanged; it costs rank-1 hits (0.60 to 0.52) and one full-alert hit, and appears in 12 of
  25 top-4 lists. Kept because the agent reads all 4 passages, and the card holds what the mitigation depends on (what
  is stateful, that `cfgpush` changes are not in deploy history). A test checks the answer key is never loaded.
- **Misses (chosen index):** q01 (deploy, new-version pods only: RB-05 node runbook wins), q04 (migration: postmortems
  win), q23 (logs missing), q25 (two causes): RB-08's language is generic and real postmortems outrank it.
- **Next:** owner reviews the v2 queries; revisit only if hand-read traces show the agent missing runbooks.

## 2026-10-26: 18 scenarios rewritten on Fianchetto
- **Decision:** `defs.py` rewritten to the plan: 6 easy, 6 medium, 6 hard; 15 answerable, 3 abstain. Each scenario
  carries a `difficulty` field; the report adds a by-tier table (descriptive only, n=6 per tier).
- **Owner review:** s18 (config push and NIC flap in the same minute) confirmed as a fair abstain case, not just
  ambiguous; s05's node-to-pod mapping via kubelet log lines confirmed realistic. s07's matchmaking logs say only
  "no opponent found" (the first draft named the band width and gave the answer away).
- **Evidence:** fake-model plumbing check 54/54 (not eval data); every key log and key metric is reachable by tools.
- **Caveat:** runbooks hint at some scenarios (s03, s05, s17); covered by the upper-bound note.

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
