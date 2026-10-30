# Run log

One entry per batch of real-model runs, newest first: what changed since the last batch, settings, results,
runtime, what the traces showed, and what was changed because of it. Decisions and their reasoning go in
`LEARNING_LOG.md`; this file is the per-batch record behind them.

**Dev batches** (`results_dev*`) run only the dev scenarios (s01, s08, s11) to tune prompts and tools. They are
not evaluation results and must not be quoted as such. Results folders are git-ignored; the numbers below are
copied from their `report.md`.

All batches so far: agent `gpt-oss:20b` (reasoning low), judge `qwen3.8:27b` (thinking off), embeddings
`nomic-embed-text`, scenario fingerprint `d7ec9b24e672`, `--parallel 1`, all local on Ollama, so cost is shadow
pricing only.

Runtime before 2026-10-26 15:00 was not recorded by the runner. For these entries, start is the results folder's
creation time and end is the last write to its `runs.jsonl` (reconstructed, marked "rec."); "judge + overhead"
is wall-clock minus summed agent latency, valid only because the batches ran one run at a time. From the next
batch on, `meta.json` records start, end, wall-clock, judge latency per run, git commit and a prompts hash.

## 2026-10-29 · results_openai · FULL EVALUATION on a hosted model (gpt-6.1-terra)

- **Changed since `results`:** only the agent model: `gpt-6.1-terra` (OpenAI, `reasoning_effort=low`) instead of
  `gpt-oss:20b`. Same frozen prompts (`b6f1da57e141`), step caps (12 / 8), judge (`qwen3.8:27b`, local), embeddings
  (`nomic-embed-text`, local), scenarios (`d7ec9b24e672`). No re-tuning for the new model. Owner approved, ≤ $10.
- **Code:** commit `a9cf7b6`, clean. Run in two phases into one folder: all 54 cells × 1 run, then repeats 2 and 3
  (`--resume`), so a spending cap ($9.50, `--max-cost-usd`) could only cut repeats, never whole scenarios.
  `meta_phase1.json` is phase 1; `meta.json` (and the report header) is phase 2 only. **n:** 162, none skipped.
- **Runtime (recorded):** 20:53 to 23:45 PDT; wall-clock 57.6 + 114.5 = 172.1 min; agent 65.3 min, judge
  106.7 min (phase 2: report header; phase 1 not in it). Mean agent latency: fixed 4.6 s, single 20.0 s, multi 48.0 s.
- **Cost:** agent API spend $7.77 at list price (fixed $0.26, single $1.91, multi $5.60; `priced_spend_usd` in
  `meta.json` covers both phases). Ignores the cached-input discount, so real billing is lower; check the OpenAI
  dashboard. The judge is local and not in this figure. Smoke test before it (`results_openai_smoke`, s01 × 3, plumbing only): $0.15.

| approach | category acc | held-out (n=45) | dev (n=9) | easy | medium | hard | false abstain | judge action | judge evidence | key cited | tool calls | tokens in/out | cost/run | latency s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed | 18/54 (33%) | 9/45 (20%) | 100% | 33% | 17% | 50% | 36/45 | 0.76 | 1.48 | 24% | 10.1 | 3337/289 | $0.0048 | 4.6 |
| single | 51/54 (94%) | 42/45 (93%) | 100% | 100% | 100% | 83% | 0/45 | 1.67 | 1.91 | 79% | 16.7 | 30263/1013 | $0.0353 | 20.0 |
| multi | 36/54 (67%) | 28/45 (62%) | 89% | 89% | 44% | 67% | 18/45 | 1.22 | 1.74 | 58% | 59.3 | 74434/5862 | $0.1037 | 48.0 |

"False abstain": `insufficient_evidence` on one of the 45 runs that have a real cause.

- **Headline:** with a stronger model the approaches separate. Held-out: single 42/45, multi 28/45, fixed 9/45
  (Fisher, runs treated as independent: single vs multi p≈0.0007, multi vs fixed p≈0.0001). The repeats of one
  scenario are not independent, so also at scenario level: single beats multi on 8 scenarios, multi beats single on
  1 (s18); sign test p≈0.04 (held-out only: 7 vs 1, p≈0.07). Multi costs ~3x single and is slower.
- **Run-to-run variance:** fixed 0.0 pts, single 0.0, multi 7.9 (61%, 61%, 78%).
- **Single: every miss is s18** (0/3, all bad_change). All three runs read the `cs-53001` allocator change
  (least_games → least_cpu at 15:05) as causing the "missing CPU samples" warnings that follow it. **Owner to
  review:** is that a fair causal reading of the scenario (then s18 is not balanced), or a confident wrong guess?
- **Multi: every miss is a false abstention (18/18), and they are not search failures.** In those runs the workers
  had seen 91% of the key evidence on average, more than in multi's correct runs (83%). Example s06 #0: the summary
  names the plan flip and the chess-db CPU rise (the right diagnosis), then abstains because "the trigger for the
  query-plan change is unknown". The coordinator demands more certainty than the answer needs.
- **Fixed: 36/45 false abstentions, apparently honest ones.** Its standard data window lacks the evidence (s02:
  "the data does not identify the two affected hosts"). gpt-oss guessed from the same window and was right 47% of
  the time; terra declines to guess. Fixed is right only on s01, s08, s13 and the three abstain cases (3/3 each).
- **Behaviour change with the model:** single searched the knowledge base in 54/54 runs (gpt-oss: 2/54, same
  prompt). Citations 100% valid for all three approaches; no retries, errors or step-cap hits.
- **Multi made 59 tool calls per run** (single 17): workers issue several calls per step. More looking, worse answers.
- **Not yet done:** hand labels (judge columns unvalidated); owner review of s18; read the multi coordinator's
  synthesis prompts against the single agent's for a wording difference that could explain the abstentions.

## 2026-10-26 · results · FULL EVALUATION, all 18 scenarios

- **Changed since dev5:** `resource_leak` definition aligned with RB-03 (`3e341fd`); prompts frozen (`0d1a715`).
- **Code:** commit `0d1a715`, clean; prompts `b6f1da57e141`. Single-agent cap 12, worker cap 8.
  **n:** 18 scenarios × 3 approaches × 3 repeats = 162. Owner approved.
- **Runtime (recorded):** 20:06 to 23:48 PDT, wall-clock 222.5 min (estimate was 230 to 270); agent 103.4 min,
  judge 119.1 min. Mean agent latency per run: fixed 9.6 s, single 22.1 s, multi 83.3 s. Exit 0, no crash.

| approach | category acc | held-out (n=45) | dev (n=9) | easy | medium | hard | judge action | judge evidence | citation valid | key cited | tokens in/out | latency s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed | 27/54 (50%) | 47% | 67% | 67% | 67% | 17% | 0.69 | 1.26 | 90% | 22% | 3031/448 | 9.6 |
| single | 29/54 (54%) | 47% | 89% | 56% | 44% | 61% | 0.63 | 1.31 | 86% | 18% | 22886/871 | 22.1 |
| multi | 30/54 (56%) | 49% | 89% | 39% | 67% | 61% | 0.72 | 1.25 | 86% | 24% | 25348/3668 | 83.3 |

- **Headline:** on held-out scenarios the three approaches are indistinguishable (21, 21 and 22 of 45). Multi costs
  ~8x the tokens and ~9x the latency of fixed for no measurable gain. Dev accuracy (67 to 89%) is well above
  held-out (47 to 49%): the prompts fit the dev scenarios, which is why held-out is the number to quote.
- **Run-to-run variance:** fixed 0.0 pts (identical every repeat), single 2.6, multi 7.9.
- **Where they differ is the tier, not the total:** fixed wins easy/medium but gets 17% on hard, because it never
  abstains correctly (s11, s12, s18: 0/9). Both agents get 8/9 or more on the abstain cases.
- **Dominant failure: false abstention.** `insufficient_evidence` on a scenario with a real cause: fixed 10/45,
  single 15/45, multi 12/45 non-abstain runs. It is the most common wrong answer for every approach.
- **0/9 for every approach:** s03 (traffic spike + one hot host), s07 (config push only in `config-agent` log),
  s14 (easy: gateway rate-limit push at onset). Also s02 (easy, canary memory leak) 1/9 total.
- **Traces read so far:**
  - s02 single #0: checked deploys with `window=1h` (the canary was 150 min earlier), searched logs at ERROR or
    for "Memory usage" (the lines say "memory 91% of limit"), never asked for `memory_pct_max_host` (fleet mean
    rises only 7 points). Narrow queries, then abstained. A real agent failure, not a scenario fault; but metric
    names are only discoverable from the error message of a wrong `get_metrics` call (tool design limitation,
    same for all approaches).
  - s14: the fixed pipeline never looks at `config-agent` (by design), so it cannot see the push. The agents
    looked at config logs in some runs (single 1/3, multi 3/3) and still answered traffic_spike or abstained.
  - s07 multi #1 saw all key evidence (key_seen 1.0) and still abstained: reasoning failure, not retrieval.
  - s04 fixed, all three: correct category, but cited 428 to 787 log ids it had not seen (it extrapolated the
    id sequence from a few lines). Shows as citation valid 1 to 2% on those runs and pulls fixed's average down.
- **Knowledge search:** single agent 2/54 runs (the prompt instruction does not work); multi 45/54; fixed 54/54.
- **Errors:** one multi run (s04 #1) failed with invalid JSON after all retries; counted as wrong.
- **Not yet done:** hand labels and judge agreement (judge columns are unvalidated until then); the remaining
  "Runs to read by hand".

## 2026-10-26 · results_dev5_roster · multi-agent only, worker roster in coordinator prompts

- **Changed since dev4:** the coordinator's planning and follow-up prompts name each specialist's exact tools and
  say only metrics sees deploys; workers say when a question needs data they cannot see (`bd00744`).
  Started before `3e341fd`, so it has the old `resource_leak` wording (no effect on these three scenarios).
- **Code:** commit `bd00744`, clean; prompts `cbbf5aa74e6c` (rendered-prompt hash; not comparable with earlier hashes).
  Worker cap 8. **n:** 9.
- **Runtime (recorded):** wall-clock 19.9 min; agent 12.0 min; judge 7.9 min.

| | category acc | judge action | judge evidence | citation valid | key cited | runs with a cap hit | tokens in/out | latency s |
|---|---|---|---|---|---|---|---|---|
| dev4 (no roster) | 3/9 | 0.44 | 1.00 | 92% | 21% | 5/9 | 28399/4163 | 95.3 |
| roster | 6/9 | 1.11 | 1.56 | 92% | 31% | 3/9 | 23071/3534 | 80.0 |

- **Per incident:** s01 2/3, s08 3/3, s11 1/3.
- **Routing:** the metrics worker checked deploys in 3/3 s01 runs (dev4: 1/3). Once (s01 #2) the coordinator still
  also asked logs about deploys, but metrics checked them too.
- **s01 #2 still wrong the same way as before:** saw D2, described the retry surge it caused, filed
  dependency_saturation. The model does not apply the explicit tie-break rule reliably.
- **New failure mode, s11 (two runs, dependency_saturation):** with no deploy to blame, the knowledge worker's
  system-card passages (K:SYS#8, #12: stats depends on chess-db and redis-cache) supplied a plausible saturation
  story, though no dependency metric was abnormal. The system card is doing what it should (describing the
  platform); the model treats "could cause this" as "did cause this".
- **Kept:** the roster. 3/9 to 6/9 is not significant at n=9, but the mechanism it targets (who checks deploys)
  changed as intended in the traces.

## 2026-10-26 · results_dev4_multi8 · multi-agent only, worker cap 5 → 8

- **Changed since dev3_new:** worker step cap 5 → 8 (owner approved). Prompts unchanged (`74a1ec17cf0c`, file hash).
- **Code:** commit `2476047`, clean. **n:** 3 scenarios × multi × 3 runs = 9.
- **Runtime (recorded):** wall-clock 20.5 min; agent 14.3 min; judge 6.2 min.

| | category acc | judge action | judge evidence | citation valid | runs with a cap hit | tool calls | tokens in/out | latency s |
|---|---|---|---|---|---|---|---|---|
| worker cap 5 (dev3_new) | 6/9 | 0.75 | 1.75 | 94% | 9/9 | 9.2 | 20718/10321 | 221.3 |
| worker cap 8 | 3/9 | 0.44 | 1.00 | 92% | 5/9 | 13.1 | 28399/4163 | 95.3 |

- **Per incident:** s01 0/3, s08 2/3, s11 1/3.
- **Accuracy fell, 6/9 to 3/9.** Not significant at n=9 (Fisher p≈0.35), but the misses are informative:
  - s01, all three: dependency_saturation. Only one run called `get_recent_deploys` at all; it found D2, described
    it as the cause, and still filed dependency_saturation, against the explicit rule "choose bad_change whenever a
    recent change is the trigger". The other two never looked for deploys (the routing problem, fixed in `bd00744`).
  - s11, two runs: bad_change. With more steps the metrics worker searched 7 days back and found the 3-day-old
    "Bump JSON library" deploy, the scenario's intended trap. More budget gave the trap more chances to work.
  - s08 #0: never saw the DNS logs; guessed "identity provider saturated".
- **Surprise:** runs got faster and output tokens fell by 60% (10,321 → 4,163). With cap 5 the cut-off workers'
  final reports were long; with room to finish they write shorter ones. Cap hits fell from 9/9 to 5/9 runs.
- **Found while reading:** the `resource_leak` definition still said "restart affected instances", contradicting
  RB-03 (fixed in `3e341fd`); and the prompts hash covered `prompts.py` only, missing `schema.py`'s category
  definitions (fixed in the same commit; hashes from `3e341fd` on are not comparable with earlier ones).
- **Kept:** cap 8. The cap is a budget, not a tuning knob: an approach should not be scored on being cut off.

## 2026-10-26 · results_dev3_old · baseline prompts, histogram, cap 12

- **Purpose:** the "before" arm of a prompt comparison; identical to dev3_new except `prompts.py`.
- **Prompts:** as of commit `b9513c0` (sha256 `1719c287fcea`). Tools: log histogram on. Single-agent cap 12, worker cap 5.
- **n:** 3 scenarios × 3 approaches × 3 runs = 27.
- **Runtime:** 13:09 to 14:03 PDT (rec.), wall-clock 54.3 min; agent 39.4 min; judge + overhead 14.9 min.

| approach | category acc | judge action | judge evidence | citation valid | step-cap hits (runs) | tokens in/out | latency s |
|---|---|---|---|---|---|---|---|
| fixed | 7/9 | 1.22 | 1.67 | 96% | 0 | 3315/323 | 8.0 |
| single | 8/9 | 1.33 | 1.56 | 89% | 2/9 | 18122/760 | 19.4 |
| multi | 5/9 | 0.75 | 1.25 | 96% | 7/9 | 23016/10998 | 235.3 |

- **Total:** 20/27. One multi run crashed (s08: invalid JSON after all retries). One single s08 run cited 20 invalid ids.
- **Knowledge search:** single 0/9 runs; multi 9/9 (its knowledge worker always runs).

## 2026-10-26 · results_dev3_new · new prompts, histogram, cap 12

- **Changed since dev2:** single-agent step cap 8 → 12; step-cap hits recorded and reported.
- **Prompts:** sha256 `74a1ec17cf0c` (the four rules below). Tools: log histogram on. Worker cap 5.
- **n:** 27.
- **Runtime:** 12:13 to 13:09 PDT (rec.), wall-clock 56.2 min; agent 37.6 min; judge + overhead 18.6 min.

| approach | category acc | judge action | judge evidence | citation valid | step-cap hits (runs) | tokens in/out | latency s |
|---|---|---|---|---|---|---|---|
| fixed | 9/9 | 1.67 | 1.78 | 100% | 0 | 3403/364 | 7.8 |
| single | 7/9 | 1.11 | 1.56 | 97% | 3/9 | 22542/819 | 21.7 |
| multi | 6/9 | 0.75 | 1.75 | 94% | 9/9 | 20718/10321 | 221.3 |

- **Total:** 21/27. One multi run crashed (s11: invalid JSON after all retries).
- **Knowledge search:** single 1/9 runs despite the new instruction; multi 9/9.
- **Comparison with dev3_old:** 21/27 vs 20/27; per approach fixed +2, multi +1, single −1. No measurable effect at
  this n. Invalid citations fell (single 97% vs 89% valid), the one rule that may have done something.
- **s11 (log gap):** 0 of 18 runs across both arms mention the gap. Every log search was ERROR- or keyword-filtered,
  and those views only hold lines after the gap, so the end of the gap looks like an ordinary error onset. Seeing it
  requires noticing that the error-rate metric is 5.7% for the whole window while ERROR logs start at 11:08. That
  cross-check is what a hard scenario is for: s11 is left as it is.
- **Multi workers:** the 5-step worker cap ended at least one worker in every run (usually after 4 tool calls,
  with `get_metrics` or `search_logs` pending). Open question for the owner.
- **Multi on s01:** 1/3 in both arms (blames redis-live, or "no recent change"). Read these traces before the full run.

## 2026-10-26 · results_dev2 · first prompt and tool changes

- **Changed since dev1:** `search_logs` returns a count histogram (gaps were hidden behind "N lines omitted");
  prompts gained four rules: cite only ids from tool output; check rate, errors and latency of a suspect dependency;
  telemetry gaps are evidence; the single agent must search the knowledge base before answering.
- **Settings:** single-agent cap 8, worker cap 5. **n:** 9 (1 run per cell).
- **Runtime:** 11:59 to 12:11 PDT (rec.), wall-clock 11.7 min; agent 5.7 min; judge + overhead 6.0 min.
- **Results:** fixed 3/3, single 2/3, multi 2/3. Misses: s01 multi (dependency_saturation, "no recent change
  detected"), s11 single (dependency_saturation).
- **Traces:** the single agent still never searched the knowledge base; in s11 it ran out of steps (7 tool calls,
  cut off at the cap of 8 with a call pending). Led to the cap change and the n=3 comparison.

## 2026-10-26 · results_dev1 · first real run on the dev scenarios

- **Code:** commit `b9513c0`, prompts `1719c287fcea`. Single-agent cap 8, worker cap 5. **n:** 9.
- **Runtime:** 11:46 to 11:57 PDT (rec.), wall-clock 11.7 min; agent 5.8 min; judge + overhead 5.9 min.
- **Results:** 9/9 category correct. Single agent: 8% key evidence cited, one run cited a tool name
  (`"search_logs"`) as evidence, judge evidence 1.0.
- **Traces:** the single agent never searched the knowledge base, so its actions missed runbook steps ("do not scale
  redis-live", "show social login unavailable"). No approach checked the redis-live request rate in s01 or noticed
  the s11 log gap; the gap was not visible in tool output at all.
