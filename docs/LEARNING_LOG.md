# Learning Log

Short entries, newest first. This becomes your interview material, so record the *why*.

Template:

## YYYY-MM-DD: <what I worked on>
- **Decision:** what I chose (e.g. chunk size 800, overlap 100)
- **Why:** my reasoning at the time
- **Evidence:** what I measured or saw
- **Surprise / failure:** what didn't work, and what I think caused it
- **Next:** what I'll try

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
