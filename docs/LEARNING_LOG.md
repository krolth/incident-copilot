# Learning Log

Short entries, newest first. This becomes your interview material, so record the *why*.

Template:

## YYYY-MM-DD: <what I worked on>
- **Decision:** what I chose (e.g. chunk size 800, overlap 100)
- **Why:** my reasoning at the time
- **Evidence:** what I measured or saw
- **Surprise / failure:** what didn't work, and what I think caused it
- **Next:** what I'll try

## 2026-10-24: offline harness built (with Claude)
- **Decision:** categories defined by which runbook action fixes them; `bad_change` wins whenever a recent change is the trigger.
- **Why:** makes ground truth unambiguous and the judge's job narrower.
- **Evidence:** 34 offline tests pass against a scripted fake model; fake runs are stamped and kept in `results_fake/`.
- **Surprise / failure:** first key-evidence metric required citing hundreds of repeated log lines; changed it to one item for "any key log line".
- **Next:** wire the real model, smoke test one scenario, then run the full evaluation.
