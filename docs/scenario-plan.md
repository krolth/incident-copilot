# Scenario plan (on the Fianchetto system card)

Answer key for rewriting `triage/scenarios/defs.py` against `docs/system.md`. **Never index this file**: the
knowledge base must not contain the answers. Agreed with the owner on 2026-10-25.

**Principles**
- Ground truth is the *mitigation* an on-call engineer should apply now. The real fix (isolation, code fix, better
  monitoring) is a follow-up and is not scored.
- Not every incident is a puzzle. Difficulty tiers, 6 scenarios each, and the report breaks results down by tier:
  - **easy:** no distractor; the obvious read of the evidence is right.
  - **medium:** one natural coincidence (an unrelated deploy, a victim that looks like the cause, one hot host).
  - **hard:** real misdirection, or the right answer is to abstain.
- Categories are balanced for coverage, not weighted by real-world frequency (changes cause most real outages, so
  bad_change gets the most slots). Say so in the write-up.

**Category mix (18):** bad_change 6, dependency_saturation 2, resource_leak 2, traffic_spike 2,
expired_credential 1, infra_failure 2, insufficient_evidence 3.

| Slot | Tier | Category / runbook | Incident | Distractor or trap |
|---|---|---|---|---|
| s01 | medium | bad_change / RB-01 | matchmaking deploy (retries without backoff, bigger pool) causes a retry storm on `redis-live` | redis-live looks like the failing dependency |
| s02 | easy | bad_change / RB-01 | new game-server version leaks memory; only hosts on the new version grow | none for the diagnosis; the test is the mitigation: cordon and drain, not restart (restart aborts games and the leak returns) |
| s03 | medium | traffic_spike / RB-04 | a top streamer goes live: logins and queue joins up 4x; the allocator balances by game count, so the streamer's host (thousands of spectators) runs hot | the one hot game-server host looks like a failing node |
| s04 | easy | expired_credential / RB-06 | `*.play.fianchetto.example` wildcard cert expires: API healthy, every game connection fails the TLS handshake | none |
| s05 | medium | infra_failure / RB-05 | anticheat burst starves a shared Kubernetes node (no CPU limits); pods on that node degrade, rest of the fleet fine. Mitigation: cordon and drain that node | rolling back the service that alerted (its pods happen to be on that node) |
| s06 | hard | dependency_saturation / RB-02 | the accounts login query's plan flips (stale statistics / generic plan) as the users table grows; chess-db CPU saturates, logins slow | an unrelated accounts deploy the same morning |
| s07 | hard | bad_change / RB-01 | bad matchmaking config push (rating band width) via `cfgpush`; not in deploy history, only in the `config-agent` log | deploy history is empty, so "no change" |
| s08 | easy | infra_failure / RB-07 | DNS resolution to the identity provider fails; social logins fail, password logins fine | none |
| s09 | medium | resource_leak / RB-03 | game servers don't close dead WebSockets after the heartbeat timeout; `open_fds` and memory grow over days, no deploy | an unrelated deploy elsewhere; "restart all hosts" aborts games |
| s10 | medium | dependency_saturation / RB-02 | `redis-cache` restarts cold; leaderboard reads stampede chess-db | chess-db is what alarms, so it looks like the database is the problem |
| s11 | hard | insufficient_evidence / RB-08 | logs (or metrics) missing for 20 minutes covering the onset | guessing from the only visible deploy |
| s12 | hard | insufficient_evidence / RB-08 | alert cleared before triage, a few unexplained errors | same |
| s13 | easy | bad_change / RB-01 | accounts deploy throws errors on every login; only new pods affected | none |
| s14 | easy | bad_change / RB-01 | gateway rate-limit config push returns 429 to normal players; the push is in the `config-agent` log right at onset | none |
| s15 | medium | bad_change / RB-01 | game-server version mishandles clocks in bullet only; other time controls fine | errors are a small share of all games, so overall metrics look mildly degraded |
| s16 | easy | traffic_spike / RB-04 | weekly arena (Friday 19:00 UTC) pushes matchmaking to its autoscaling max | none |
| s17 | hard | resource_leak / RB-03 | game checkpoints in `redis-live` stop expiring (TTL not set); redis-live memory grows for days until eviction makes it slow; no deploy | the alert is game-server move latency, far from the cause |
| s18 | hard | insufficient_evidence / RB-08 | a matchmaking config push and an unhealthy node start in the same minute; the evidence supports both equally | picking either one. **Owner to confirm this is fair, not just ambiguous** |

**Changes this causes elsewhere:** the design doc's "12 incidents" becomes 18; a full evaluation is 18 × 3 approaches ×
3 runs = 162 runs (CLAUDE.md says about 108); scenarios get a `difficulty` field and the report a by-tier breakdown.
