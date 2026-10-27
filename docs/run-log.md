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
