# Problem Definition

Incident Triage Copilot · Sharad Cornejo Altuzar · Capstone project, AI Engineering cohort (RAG & Agents)

Companion documents: [Data Processing](data-processing.md) · [Evaluation Criteria](evaluation-criteria.md) · [System Design](design-doc.md) · [Results site](https://krolth.github.io/incident-copilot/)

## The problem

When an automated alert fires on a live service, the on-call engineer's first job is triage: work out what is
actually broken, pick the mitigation that stops the damage now, and know when the data does not support a
conclusion yet. Most of that time goes into the same moves: read the alert, check the failing service's errors
and metrics, look for a recent change, check its dependencies, remember what fixed it last time.

This project builds an agent that does that first pass before a human is paged, and asks one design question
about it: **is it better to give one agent all the tools, or to split the work across a team of specialist agents?**

## Task

**Input:** one alert from a simulated platform, for example `accounts: login p99 above 3000 ms; chess-db CPU above 90%`,
with its service, time, severity and the dependencies it lists. The system can query four tools:

| Tool | Returns |
|---|---|
| `search_logs` | matching log lines from a service, filtered by level, keyword and time window |
| `get_metrics` | a metric series for a service over a window (15 minutes to 7 days) |
| `get_recent_deploys` | the deploy history for a window |
| `search_knowledge` | passages from 8 runbooks, the platform's system card and 318 public postmortems (RAG) |

**Output:** one typed result (validated with Pydantic, identical for every design):

| Field | Meaning |
|---|---|
| `category` | the root-cause category (below), or `insufficient_evidence` |
| `component` | the failing service, host or credential |
| `summary` | two to four sentences: what is wrong and why |
| `evidence_ids` | the log lines, metrics, deploys and passages that support it, by id |
| `recommended_runbook` | one of RB-01 to RB-08 |
| `recommended_action` | the concrete next step for the on-call engineer |
| `confidence` | low, medium or high |

## Root-cause categories

Categories are defined by **which mitigation fixes them**, so the category decides the first action. A recent
change wins ties: if a deploy or config push triggered the fault, it is `bad_change` even if the visible mechanism
is saturation or a leak, because the fix is to revert it.

| Category | Definition | Mitigation (runbook) |
|---|---|---|
| `bad_change` | a deploy or configuration change introduced the fault | revert it (RB-01) |
| `dependency_saturation` | a shared database, cache or store is overloaded by load no recent change introduced | throttle or shed that load (RB-02) |
| `resource_leak` | memory, file descriptors, disk or connections grow steadily with no change as the trigger | capture diagnostics, then reclaim one instance at a time (RB-03) |
| `traffic_spike` | legitimate demand exceeds provisioned capacity | scale out or shed load (RB-04) |
| `infra_failure` | a host, network, DNS or upstream provider fails | drain or replace the node (RB-05), or fail over (RB-07) |
| `expired_credential` | a certificate, token or key expired or was revoked | rotate it (RB-06) |
| `insufficient_evidence` | the data cannot support any single conclusion | escalate with the findings so far (RB-08) |

Abstaining is a real answer, not a failure: three incidents are built so that it is the correct one.

## The incidents

18 incidents on one fictional system, **Fianchetto**, an online chess platform (gateway, accounts, matchmaking,
leaderboards, stats, anticheat, a stateful game-server fleet, redis-live, redis-cache and a Postgres database; see
`docs/system.md`). Each has a known root cause and a reference mitigation, written before any model ran. All data is
synthetic.

They come in three difficulty tiers of six:

- **Easy:** no distractor; the obvious reading of the evidence is right.
- **Medium:** one natural coincidence, such as an unrelated deploy, or a victim that looks like the cause.
- **Hard:** real misdirection, or no single answer, so the right call is to abstain.

The agent sees only the alert column below; the title is for people.

| Id | Tier | Alert the agent receives | Title |
|---|---|---|---|
| s01 | medium | matchmaking: queue join error rate above 15% for 5 minutes | Matchmaking retry storm on redis-live after a deploy |
| s02 | easy | game-server: memory above 90% on 2 of 10 hosts | Memory growth on the game-server canary hosts |
| s03 | medium | game-server: move delivery p99 above 150 ms for 5 minutes | A streamer goes live: demand spike and one hot game server |
| s04 | easy | game-server: games started per minute more than 90% below forecast for 2 minutes | Expired game-server wildcard certificate |
| s05 | medium | accounts: login p99 above 2000 ms for 10 minutes | Anticheat starves a shared Kubernetes node |
| s06 | hard | accounts: login p99 above 3000 ms; chess-db CPU above 90% | Login query plan flips to a sequential scan |
| s07 | hard | matchmaking: queue wait p95 above 60 s for 5 minutes | Matchmaking config push that is not in deploy history |
| s08 | easy | accounts: social login success rate below 60% for 5 minutes | DNS resolver failure breaks social login |
| s09 | medium | game-server: 'too many open files' on gs-04; new game connections refused | Game servers leak WebSocket file descriptors |
| s10 | medium | leaderboards: p99 latency above 3000 ms; chess-db replica CPU above 95% | Cold redis-cache after a maintenance reboot |
| s11 | hard | stats: error rate above 5% for 5 minutes | Stats errors during a 20-minute log gap (no single answer) |
| s12 | hard | leaderboards: p99 latency above 1500 ms for 3 minutes | Transient leaderboards blip that cleared before triage (no single answer) |
| s13 | easy | accounts: login error rate above 40% for 3 minutes | Accounts deploy fails every login on new pods |
| s14 | easy | gateway: 429 responses above 20% of requests for 5 minutes | Gateway rate-limit config push throttles normal players |
| s15 | medium | game-server: platform-aborted games above 0.05% for 15 minutes | Game-server version aborts bullet games |
| s16 | easy | matchmaking: queue join p99 above 2000 ms for 2 minutes | Weekly arena pushes matchmaking to its autoscaling cap |
| s17 | hard | game-server: move delivery p99 above 150 ms for 10 minutes | redis-live fills up with checkpoints that never expire |
| s18 | hard | matchmaking: queue join error rate above 8% for 5 minutes | Config push and a flapping node in the same minute (no single answer) |

Categories are balanced for coverage, not weighted by how often they happen in production (changes cause most real
outages, so `bad_change` gets the most incidents: 6 of 18).

## Research question

Does a **coordinator with specialist agents** (logs, metrics, knowledge) beat a **single agent with the same tools**
on root-cause accuracy, do both beat a **fixed pipeline** that always reads the same data, and what does each cost in
tokens, latency and dollars?

The three designs share the tools, the data and the output schema, so control flow is the only variable. The
comparison is repeated on two models (one small local, one hosted) to see whether the answer depends on the model.

## Scope

**In scope:** triage of a single alert to a category, component, runbook and first action; abstaining when the data
does not support an answer; the cost and latency of each design.

**Out of scope:** applying the fix, multi-alert correlation, live Elasticsearch, Grafana or chat-ops integrations,
and any real company data or incidents.

**Assumptions:** the alert is real (not a false positive from broken monitoring, except where telemetry gaps are the
point, as in s11); the tools return the same data an engineer would see; runbooks exist for every category.
