"""The simulated incidents. ALL DATA IS SYNTHETIC: invented services, hosts, and numbers.

All 18 incidents happen on Fianchetto, the fictional chess platform in docs/system.md, and follow
docs/scenario-plan.md (difficulty tier, category, distractor). Hosts and services match the system card.

Rules for editing this file:
  * Ground truths are fixed BEFORE any agent run. After you have real results, changing a scenario
    changes its fingerprint (printed in every run summary) and invalidates earlier results.
  * If you must change one anyway, re-run everything and note the change in docs/LEARNING_LOG.md.

Each scenario carries a `trap`: what makes it misleading (for easy ones, why it is not). 15 are answerable;
3 (S11, S12, S18) have no defensible root cause, so the correct output is category insufficient_evidence.
"""
from __future__ import annotations

from triage.schema import Alert, Category
from triage.scenarios.model import (
    Deploy, GroundTruth, LogBuilder, Metric, Scenario, assign_deploy_ids, daily, healthy_service, ramp, spike,
    step,
)

M, H = 60, 3600  # seconds per minute / hour


def _alert(n: int, service: str, symptom: str, fired_at: str, severity: str, deps: list[str]) -> Alert:
    return Alert(id=f"ALR-{n:04d}", service=service, symptom=symptom, fired_at=fired_at,
                 severity=severity, dependencies=deps)


def _routine(lb: LogBuilder, service: str, hosts: list[str], per_min: float = 1.0,
             start_s: int = -3 * H, end_s: int = 300) -> None:
    """Background INFO noise so real signal has to be found among ordinary lines."""
    lb.repeat(service, "INFO", "request completed in {ms} ms host={host}", start_s, end_s, per_min, hosts, ms=(20, 240))


def _build(sid: str, title: str, alert: Alert, truth: GroundTruth, trap: str,
           metrics: dict, lb: LogBuilder, deploys: list[Deploy], difficulty: str, now_min: int = 5) -> Scenario:
    return Scenario(id=sid, title=title, alert=alert, truth=truth, trap=trap, metrics=metrics,
                    logs=lb.finalize(), deploys=assign_deploy_ids(deploys), difficulty=difficulty, now_min=now_min)


# Fianchetto host names (docs/system.md)
MM = [f"matchmaking-{i}" for i in range(1, 5)]
GW = [f"gateway-{i}" for i in range(1, 9)]
GS = [f"gs-{i:02d}" for i in range(1, 11)]
RL = [f"redis-live-{i}" for i in range(1, 4)]
ST = [f"stats-{i}" for i in range(1, 5)]
AC = [f"accounts-{i}" for i in range(1, 5)]


# S01 (medium) ---------------------------------------------------------------------------------
def s01_retry_storm_after_deploy() -> Scenario:
    seed = 1000
    lb = LogBuilder(seed)
    _routine(lb, "matchmaking", MM, 2.0, end_s=-7 * M)
    _routine(lb, "gateway", GW, 3.0)
    for n, host in enumerate(MM):  # rolling deploy: one pod a minute
        lb.event(-9 * M + n * 60, "matchmaking", "INFO",
                 "starting matchmaking 2026.03.14-3: redis client max_attempts=5 backoff=none pool_size=200", host, key=True)
    lb.repeat("matchmaking", "ERROR", "redis-live timeout after 50 ms (attempt {a}/5, backoff=none) op=ZADD queue:blitz host={host}",
              -7 * M, 5 * M, 18, MM, key=True, a=(1, 5))
    lb.repeat("matchmaking", "WARN", "retry budget exhausted for redis-live, failing queue join host={host}",
              -6 * M, 5 * M, 6, MM, key=True)
    lb.repeat("redis-live", "WARN", "slowlog: command took {us} us, connected_clients={c} host={host}",
              -7 * M, 5 * M, 8, RL, us=(12000, 60000), c=(2400, 3300))
    lb.repeat("game-server", "WARN", "checkpoint write to redis-live slow: {ms} ms game=g-{g} host={host}",
              -6 * M, 5 * M, 5, GS, ms=(80, 400), g=(100000, 999999))
    metrics = {
        "matchmaking": healthy_service(seed + 10, rps=900, p99=60, cpu=35, mem=50, err=0.2),
        "redis-live": healthy_service(seed + 20, rps=25000, p99=2, cpu=35, mem=55, err=0.01),
        "game-server": healthy_service(seed + 30, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
        "gateway": healthy_service(seed + 40, rps=3000, p99=80, cpu=40, mem=45),
    }
    mm, rl = metrics["matchmaking"], metrics["redis-live"]
    mm["error_rate_pct"].add(ramp(-7, -3, 15.5))
    mm["latency_p99_ms"].add(ramp(-7, -2, 1800))
    mm["cpu_pct"].add(ramp(-7, -3, 25))
    mm["queue_wait_p95_s"] = Metric(4, noise=0.6, seed=seed + 11, unit="s").add(ramp(-7, -2, 38))
    rl["request_rate_rps"].add(ramp(-9, -5, 70000))
    rl["latency_p99_ms"].add(ramp(-7, -3, 45))
    rl["cpu_pct"].add(ramp(-7, -3, 50))
    metrics["game-server"]["move_latency_p99_ms"] = Metric(60, noise=4, seed=seed + 31, unit="ms").add(ramp(-7, -3, 140))
    deploys = [
        Deploy(-9, "matchmaking", "2026.03.14-3",
               "Redis client: raise pool size from 20 to 200; retry failed calls up to 5 times without backoff", key=True),
        Deploy(-1500, "leaderboards", "2026.03.13-2", "Add weekly ladder endpoint"),
    ]
    truth = GroundTruth(Category.bad_change, ["matchmaking"], "RB-01",
                        "Roll back matchmaking 2026.03.14-3 (deploy rollback; stateless, about 5 minutes) to restore retry "
                        "backoff and the pool size of 20; confirm redis-live request rate and checkpoint latency return to "
                        "baseline. Do not scale or restart redis-live.",
                        key_metrics=["redis-live:request_rate_rps"], key_docs=["RB-01"])
    return _build("s01-retry-storm-after-deploy", "Matchmaking retry storm on redis-live after a deploy",
                  _alert(1, "matchmaking", "queue join error rate above 15% for 5 minutes", "2026-03-14T19:05:00Z", "high",
                         ["redis-live", "game-server"]),
                  truth, "redis-live is slow and game servers report slow checkpoints, so redis-live looks like the failing "
                         "dependency; it is the victim. Its request rate tripled while gateway traffic stayed flat, starting "
                         "with matchmaking's deploy.",
                  metrics, lb, deploys, "medium")


# S02 (easy) -----------------------------------------------------------------------------------
def s02_memory_growth_new_version() -> Scenario:
    seed = 2000
    lb = LogBuilder(seed)
    new = ["gs-03", "gs-07"]
    old = [h for h in GS if h not in new]
    _routine(lb, "matchmaking", MM, 2.0)
    lb.repeat("game-server", "INFO", "heartbeat ok version=2026.03.20-4 heap={h}% host={host}", -3 * H, 5 * M, 4, old, h=(48, 58))
    lb.repeat("game-server", "INFO", "heartbeat ok version=2026.03.21-1 heap={h}% host={host}", -150 * M, 5 * M, 1, new,
              key=True, h=(62, 91))
    lb.repeat("game-server", "WARN", "gc pause {ms} ms, heap {h}% after full GC version=2026.03.21-1 host={host}",
              -60 * M, 5 * M, 2, new, key=True, ms=(300, 1400), h=(86, 93))
    for host in new:
        lb.event(-3 * M, "game-server", "WARN",
                 "memory 91% of limit; at the current growth rate the process is OOM-killed in about 20 min "
                 "(1,850 live games on this host)", host, key=True)
    metrics = {
        "game-server": healthy_service(seed + 10, rps=6000, p99=40, cpu=45, mem=55, err=0.05),
        "matchmaking": healthy_service(seed + 20, rps=900, p99=60, cpu=35, mem=50),
        "redis-live": healthy_service(seed + 30, rps=25000, p99=2, cpu=35, mem=55, err=0.01),
    }
    gs = metrics["game-server"]
    gs["memory_pct"].add(ramp(-150, 0, 7))
    gs["memory_pct_max_host"] = Metric(58, noise=1.0, seed=seed + 11, unit="%", hi=100).add(ramp(-150, -2, 33))
    gs["active_games"] = Metric(30000, noise=300, seed=seed + 12)
    deploys = [Deploy(-150, "game-server", "2026.03.21-1",
                      "Canary on gs-03 and gs-07: keep full move history in memory for spectator replay; "
                      "checkpoint format unchanged (v7)", key=True),
               Deploy(-1400, "leaderboards", "2026.03.20-1", "Cache ladder pages for 30 s")]
    truth = GroundTruth(Category.bad_change, ["game-server", "gs-03", "gs-07", "2026.03.21-1", "canary"], "RB-01",
                        "Revert the game-server canary 2026.03.21-1: keep 2026.03.20-4 as the current version so new games "
                        "go only to old-version hosts, cordon gs-03 and gs-07, and migrate their games now (OOM in about "
                        "20 minutes is sooner than a drain; checkpoint format unchanged), then reinstall the old version. "
                        "Do not just restart the hosts.",
                        key_metrics=["game-server:memory_pct_max_host"], key_docs=["RB-01"])
    return _build("s02-memory-growth-new-version", "Memory growth on the game-server canary hosts",
                  _alert(2, "game-server", "memory above 90% on 2 of 10 hosts", "2026-03-21T20:40:00Z", "high",
                         ["redis-live", "matchmaking"]),
                  truth, "None for the diagnosis (easy tier): only the two canary hosts grow, starting with the canary deploy. "
                         "The test is the mitigation: restarting aborts 1,850 live games per host and the leak returns; "
                         "a drain is too slow for 20 minutes of headroom, so migrate.",
                  metrics, lb, deploys, "easy")


# S03 (medium) ---------------------------------------------------------------------------------
def s03_streamer_traffic_spike() -> Scenario:
    seed = 3000
    lb = LogBuilder(seed)
    _routine(lb, "gateway", GW, 3.0)
    lb.repeat("accounts", "INFO", "login ok method={m} host={host}", -3 * H, 5 * M, 6, AC, m=(1, 2))
    lb.event(-22 * M, "accounts", "INFO",
             "signup surge: 1,840 signups in 5 min with referrer=stream (usual ~60)", "accounts-1", key=True)
    lb.repeat("matchmaking", "WARN", "hpa: desired replicas {d} capped at max_replicas=16", -15 * M, 5 * M, 1,
              ["matchmaking-1"], key=True, d=(21, 26))
    lb.repeat("game-server", "INFO", "move applied game=g-{g} in {ms} ms host={host}", -3 * H, 5 * M, 20, GS,
              g=(100000, 999999), ms=(8, 60))
    lb.repeat("game-server", "WARN", "spectators on game g-771204 = {n}; broadcast fan-out lagging {ms} ms host={host}",
              -18 * M, 5 * M, 6, ["gs-06"], key=True, n=(6200, 11800), ms=(150, 900))
    lb.repeat("game-server", "WARN", "move delivery p99 {ms} ms (players {p}, spectators {s}) host={host}",
              -14 * M, 5 * M, 3, ["gs-06"], key=True, ms=(180, 640), p=(7400, 7900), s=(9000, 15000))
    metrics = {
        "gateway": healthy_service(seed + 10, rps=3000, p99=80, cpu=40, mem=45),
        "accounts": healthy_service(seed + 20, rps=60, p99=120, cpu=30, mem=45),
        "matchmaking": healthy_service(seed + 30, rps=900, p99=60, cpu=35, mem=50),
        "game-server": healthy_service(seed + 40, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
    }
    metrics["gateway"]["request_rate_rps"].add(ramp(-25, -8, 7000))
    metrics["accounts"]["request_rate_rps"].add(ramp(-25, -10, 180))
    metrics["matchmaking"]["request_rate_rps"].add(ramp(-22, -8, 2600))
    metrics["matchmaking"]["cpu_pct"].add(ramp(-22, -10, 50))
    metrics["matchmaking"]["queue_wait_p95_s"] = Metric(4, noise=0.6, seed=seed + 31, unit="s").add(ramp(-15, -5, 14))
    gs = metrics["game-server"]
    gs["active_games"] = Metric(30000, noise=300, seed=seed + 41).add(ramp(-22, -5, 6000))
    gs["move_latency_p99_ms"] = Metric(60, noise=4, seed=seed + 42, unit="ms").add(ramp(-18, -6, 210))
    gs["cpu_pct_max_host"] = Metric(55, noise=2, seed=seed + 43, unit="%", hi=100).add(ramp(-20, -8, 43))
    gs["connections_max_host"] = Metric(8200, noise=150, seed=seed + 44).add(ramp(-20, -8, 14000))
    deploys = [Deploy(-75, "stats", "2026.04.02-1", "Add opening statistics to the profile page"),
               Deploy(-4300, "gateway", "2026.03.30-2", "Upgrade TLS library")]
    truth = GroundTruth(Category.traffic_spike, ["streamer", "spectat", "gs-06", "matchmaking", "game-server"], "RB-04",
                        "Real demand from a streamer going live: cap spectators per game (spectate.max_per_game) and cordon "
                        "gs-06 so it gets no new games, raise matchmaking's autoscaling maximum above 16, and pause "
                        "anticheat-backfill if it is running. Do not drain or restart gs-06.",
                        key_metrics=["gateway:request_rate_rps"], key_docs=["RB-04"])
    return _build("s03-streamer-traffic-spike", "A streamer goes live: demand spike and one hot game server",
                  _alert(3, "game-server", "move delivery p99 above 150 ms for 5 minutes", "2026-04-02T18:20:00Z", "high",
                         ["matchmaking", "redis-live"]),
                  truth, "One game-server host (gs-06) is far hotter than the rest, which looks like a failing node; it carries "
                         "a streamer's game with thousands of spectators, because the allocator balances by game count. "
                         "Logins, signups and queue joins all rose together: it is demand.",
                  metrics, lb, deploys, "medium")


# S04 (easy) -----------------------------------------------------------------------------------
def s04_expired_certificate() -> Scenario:
    seed = 4000
    lb = LogBuilder(seed)
    _routine(lb, "gateway", GW, 3.0)
    _routine(lb, "matchmaking", MM, 2.0)
    # games that were already connected keep playing: their TLS sessions predate the expiry
    lb.repeat("game-server", "INFO", "move applied game=g-{g} in {ms} ms host={host}", -3 * H, 5 * M, 20, GS,
              g=(100000, 999999), ms=(8, 60))
    for n, host in enumerate(GS):
        lb.event(-2 * M + n, "game-server", "WARN",
                 "serving certificate *.play.fianchetto.example expired at 2026-04-09T03:00:00Z (notAfter); "
                 "new connections will fail", host, key=True)
    lb.repeat("game-server", "ERROR",
              "http: TLS handshake error from 198.51.100.{ip}:{port}: remote error: tls: bad certificate host={host}",
              -2 * M, 5 * M, 60, GS, key=True, ip=(2, 254), port=(30000, 65000))
    lb.repeat("matchmaking", "WARN", "ticket expired unused: player never connected to gs-{n:02d} within 15 s host={host}",
              -100, 5 * M, 40, MM, n=(1, 10))
    metrics = {
        "game-server": healthy_service(seed + 10, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
        "matchmaking": healthy_service(seed + 20, rps=900, p99=60, cpu=35, mem=50),
        "gateway": healthy_service(seed + 30, rps=3000, p99=80, cpu=40, mem=45),
    }
    gs = metrics["game-server"]
    gs["tls_handshake_errors_per_min"] = Metric(0.5, noise=0.4, seed=seed + 11).add(step(-2, 7000))
    gs["active_games"] = Metric(30000, noise=300, seed=seed + 12).add(ramp(-2, 5, -20000))
    gs["request_rate_rps"].add(ramp(-2, 5, -4000))
    gs["cpu_pct"].add(ramp(-2, 5, -20))
    metrics["matchmaking"]["games_started_per_min"] = Metric(3600, noise=120, seed=seed + 21).add(step(-2, -3560))
    deploys = [Deploy(-5000, "stats", "2026.04.05-1", "Speed up the player history page")]
    truth = GroundTruth(Category.expired_credential, ["play.fianchetto", "wildcard", "game-server", "game server"], "RB-06",
                        "Install the renewed *.play.fianchetto.example wildcard certificate on every game-server host and "
                        "reload the TLS listener (no restart, so running games stay up); verify handshakes, then add "
                        "expiry monitoring.",
                        key_metrics=["game-server:tls_handshake_errors_per_min"], key_docs=["RB-06"])
    return _build("s04-expired-certificate", "Expired game-server wildcard certificate",
                  _alert(4, "game-server", "games started per minute more than 90% below forecast for 2 minutes",
                         "2026-04-09T03:02:00Z", "high", ["matchmaking", "redis-live"]),
                  truth, "None by design (easy tier): every game server logs the expiry and the handshake errors begin at "
                         "the exact expiry time. Games already in progress continue, so the API and move traffic look "
                         "only partly degraded.",
                  metrics, lb, deploys, "easy")


# S05 (medium) ---------------------------------------------------------------------------------
def s05_anticheat_starves_node() -> Scenario:
    seed = 5000
    lb = LogBuilder(seed)
    healthy_acc = ["accounts-1", "accounts-3", "accounts-4"]
    _routine(lb, "gateway", GW, 3.0)
    lb.repeat("accounts", "INFO", "POST /login 200 in {ms} ms host={host}", -3 * H, 5 * M, 6, healthy_acc, ms=(40, 160))
    lb.repeat("accounts", "INFO", "POST /login 200 in {ms} ms host=accounts-2", -3 * H, -16 * M, 2, ["accounts-2"], ms=(40, 160))
    lb.repeat("accounts", "WARN", "POST /login 200 in {ms} ms (slow) host=accounts-2", -16 * M, 5 * M, 4, ["accounts-2"],
              key=True, ms=(2200, 6800))
    lb.repeat("accounts", "ERROR", "POST /login 504 upstream timeout after 8000 ms host=accounts-2", -12 * M, 5 * M, 3,
              ["accounts-2"], key=True)
    lb.event(-18 * M, "anticheat", "INFO", "analysis burst: 6,400 games queued after arena (engine depth 22)", "anticheat-7")
    lb.repeat("kubelet", "WARN", "node-07 CPU 100%: top consumers anticheat-7 ({a} cores), anticheat-8 ({b} cores), "
              "accounts-2 (0.3 cores), gateway-5 (0.4 cores); pods throttled host={host}",
              -16 * M, 5 * M, 1, ["node-07"], key=True, a=(7, 8), b=(6, 8))
    lb.repeat("gateway", "WARN", "slow upstream accounts: {ms} ms host=gateway-5", -15 * M, 5 * M, 2, ["gateway-5"], ms=(900, 4000))
    metrics = {
        "accounts": healthy_service(seed + 10, rps=60, p99=120, cpu=30, mem=45, err=0.1),
        "gateway": healthy_service(seed + 20, rps=3000, p99=80, cpu=40, mem=45),
        "anticheat": healthy_service(seed + 30, rps=60, p99=2000, cpu=60, mem=55),
    }
    metrics["accounts"]["latency_p99_ms"].add(ramp(-16, -10, 5200))
    metrics["accounts"]["error_rate_pct"].add(ramp(-12, -8, 6))
    metrics["anticheat"]["cpu_pct"].add(ramp(-18, -14, 35))
    metrics["anticheat"]["queue_depth"] = Metric(800, noise=50, seed=seed + 31).add(step(-18, 5600))
    deploys = [Deploy(-130, "accounts", "2026.04.16-1", "Show last login time on the profile page"),
               Deploy(-2200, "anticheat", "2026.04.15-2", "Engine update to depth 22 for blitz")]
    truth = GroundTruth(Category.infra_failure, ["node-07"], "RB-05",
                        "Cordon and drain node-07 so accounts-2 and gateway-5 reschedule onto healthy nodes, and scale "
                        "anticheat down or pause its analysis so it does not starve the next node; follow up with a "
                        "separate node pool and CPU limits for anticheat. Do not roll back accounts.",
                        key_metrics=["anticheat:cpu_pct"], key_docs=["RB-05"])
    return _build("s05-anticheat-starves-node", "Anticheat starves a shared Kubernetes node",
                  _alert(5, "accounts", "login p99 above 2000 ms for 10 minutes", "2026-04-16T22:15:00Z", "medium",
                         ["chess-db", "identity-provider"]),
                  truth, "accounts alerted and has a deploy two hours earlier, inviting a rollback; only accounts-2 is slow, "
                         "and it shares node-07 with two anticheat workers using all its CPU.",
                  metrics, lb, deploys, "medium")


# S06 (hard) -----------------------------------------------------------------------------------
def s06_login_query_plan_flip() -> Scenario:
    seed = 6000
    lb = LogBuilder(seed)
    _routine(lb, "gateway", GW, 3.0)
    lb.repeat("accounts", "INFO", "POST /login 200 in {ms} ms host={host}", -3 * H, -25 * M, 6, AC, ms=(40, 160))
    lb.repeat("accounts", "WARN", "POST /login 200 in {ms} ms (slow) host={host}", -25 * M, 5 * M, 8, AC, ms=(1800, 7000))
    lb.repeat("accounts", "ERROR", "POST /login 503: timeout acquiring db connection (pool 40, waiting {w}) host={host}",
              -15 * M, 5 * M, 6, AC, w=(20, 70))
    lb.repeat("chess-db", "WARN", "duration: {ms} ms  execute login_by_email: SELECT id, password_hash, mfa_secret FROM users "
              "WHERE lower(email) = $1 host={host}", -25 * M, 5 * M, 12, ["db-01"], key=True, ms=(1200, 6400))
    lb.repeat("chess-db", "INFO", "auto_explain: login_by_email plan: Seq Scan on users (rows={r}) Filter: lower(email) = $1 "
              "host={host}", -25 * M, 5 * M, 2, ["db-01"], key=True, r=(41200000, 41300000))
    lb.repeat("chess-db", "INFO", "auto_explain: login_by_email plan: Index Scan using users_lower_email_idx (rows=1) "
              "host={host}", -3 * H, -25 * M, 0.2, ["db-01"])
    lb.repeat("game-server", "WARN", "game record write slow: {ms} ms game=g-{g} host={host}", -20 * M, 5 * M, 3, GS,
              ms=(400, 1800), g=(100000, 999999))
    metrics = {
        "accounts": healthy_service(seed + 10, rps=60, p99=120, cpu=30, mem=45, err=0.1),
        "chess-db": healthy_service(seed + 20, rps=9000, p99=4, cpu=35, mem=70, err=0.01),
        "gateway": healthy_service(seed + 30, rps=3000, p99=80, cpu=40, mem=45),
        "game-server": healthy_service(seed + 40, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
    }
    metrics["accounts"]["latency_p99_ms"].add(ramp(-25, -15, 4400))
    metrics["accounts"]["error_rate_pct"].add(ramp(-15, -8, 9))
    db = metrics["chess-db"]
    db["cpu_pct"].add(ramp(-25, -18, 61))
    db["latency_p99_ms"].add(ramp(-25, -18, 900))
    db["connections"] = Metric(210, noise=8, seed=seed + 21, hi=500).add(ramp(-25, -12, 270))
    deploys = [Deploy(-240, "accounts", "2026.04.23-1", "Show last login time on the profile page"),
               Deploy(-2100, "stats", "2026.04.21-3", "Faster game history pagination")]
    truth = GroundTruth(Category.dependency_saturation, ["chess-db", "login_by_email", "users", "query plan", "db-01"], "RB-02",
                        "Take load off chess-db: run ANALYZE on users and, if login_by_email keeps the generic plan, have "
                        "Data on-call set plan_cache_mode = force_custom_plan for the accounts role; confirm with EXPLAIN "
                        "that users_lower_email_idx is used again and chess-db CPU returns to baseline. Do not roll back "
                        "accounts or add accounts pods.",
                        key_metrics=["chess-db:cpu_pct"], key_docs=["RB-02"])
    return _build("s06-login-query-plan-flip", "Login query plan flips to a sequential scan",
                  _alert(6, "accounts", "login p99 above 3000 ms; chess-db CPU above 90%", "2026-04-23T13:12:00Z", "high",
                         ["chess-db", "identity-provider"]),
                  truth, "accounts deployed this morning, and accounts is what alerts; but the deploy is four hours before the "
                         "onset and does not touch the login query. Nothing changed: the login query's plan switched from the "
                         "email index to a sequential scan of 41 million users, visible only in the database's own logs.",
                  metrics, lb, deploys, "hard")


# S07 (hard) -----------------------------------------------------------------------------------
def s07_config_push_not_in_deploys() -> Scenario:
    seed = 7000
    lb = LogBuilder(seed)
    _routine(lb, "gateway", GW, 3.0)
    _routine(lb, "stats", ST, 1.0)
    lb.repeat("matchmaking", "INFO", "paired players wait {ms} ms host={host}", -3 * H, -14 * M, 6, MM, ms=(800, 9000))
    for n, host in enumerate(MM):
        lb.event(-14 * M + n * 4, "config-agent", "INFO",
                 "config applied: matchmaking.rating_band.width 200 -> 20 (change cs-51870 by user eng-0412)", host, key=True)
    lb.repeat("matchmaking", "INFO", "paired players wait {ms} ms host={host}", -14 * M, 5 * M, 1.5, MM,
              key=True, ms=(20000, 90000))
    lb.repeat("matchmaking", "WARN", "queue wait {w} s exceeds 60 s: no opponent found (tc=blitz) host={host}",
              -10 * M, 5 * M, 10, MM, key=True, w=(61, 240))
    lb.repeat("gateway", "INFO", "POST /queue 202 re-queue after cancel host={host}", -11 * M, 5 * M, 12, GW)
    lb.event(-190 * M, "stats", "INFO", "starting stats 2026.04.30-2: rating deviation recomputed on read", "stats-1")
    metrics = {
        "matchmaking": healthy_service(seed + 10, rps=900, p99=60, cpu=35, mem=50, err=0.2),
        "gateway": healthy_service(seed + 20, rps=3000, p99=80, cpu=40, mem=45),
        "stats": healthy_service(seed + 30, rps=400, p99=90, cpu=30, mem=50),
        "game-server": healthy_service(seed + 40, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
    }
    mm = metrics["matchmaking"]
    mm["queue_wait_p95_s"] = Metric(4, noise=0.6, seed=seed + 11, unit="s").add(ramp(-14, -4, 85))
    mm["queue_length"] = Metric(1500, noise=60, seed=seed + 12).add(ramp(-14, -2, 9000))
    mm["games_started_per_min"] = Metric(3600, noise=120, seed=seed + 13).add(ramp(-14, -8, -2500))
    mm["request_rate_rps"].add(ramp(-12, -4, 380))  # players cancel and re-queue
    mm["cpu_pct"].add(ramp(-12, -4, 8))
    metrics["gateway"]["request_rate_rps"].add(ramp(-12, -4, 400))
    metrics["game-server"]["active_games"] = Metric(30000, noise=300, seed=seed + 41).add(ramp(-14, 5, -14000))
    deploys = [Deploy(-190, "stats", "2026.04.30-2", "Recompute rating deviation on read instead of nightly"),
               Deploy(-2900, "gateway", "2026.04.28-1", "Update TLS ciphers")]
    truth = GroundTruth(Category.bad_change, ["rating_band", "cs-51870", "config", "cfgpush", "matchmaking"], "RB-01",
                        "Revert config change cs-51870 with cfgpush revert (restore matchmaking.rating_band.width=200; "
                        "matchmaking is stateless, so it takes effect within a minute) and confirm queue wait and games "
                        "started recover. The stats deploy is unrelated.",
                        key_metrics=["matchmaking:queue_wait_p95_s"], key_docs=["RB-01"])
    return _build("s07-config-push-not-in-deploys", "Matchmaking config push that is not in deploy history",
                  _alert(7, "matchmaking", "queue wait p95 above 60 s for 5 minutes", "2026-04-30T19:20:00Z", "high",
                         ["redis-live", "game-server", "stats"]),
                  truth, "Deploy history shows no matchmaking change; the only recent deploy is a rating-related stats change, "
                         "which looks like it could break pairing. Rising re-queue traffic looks like a demand spike. Matchmaking "
                         "logs no errors: it is working as configured. The change is only in the config-agent log.",
                  metrics, lb, deploys, "hard")


# S08 (easy) -----------------------------------------------------------------------------------
def s08_dns_failure_social_login() -> Scenario:
    seed = 8000
    lb = LogBuilder(seed)
    _routine(lb, "gateway", GW, 3.0)
    lb.repeat("accounts", "INFO", "login ok method=password host={host}", -3 * H, 5 * M, 4, AC)
    lb.repeat("accounts", "INFO", "login ok method=social host={host}", -3 * H, -9 * M, 3, AC)
    lb.repeat("accounts", "INFO", "login ok method=social host={host}", -9 * M, 5 * M, 1.5, AC)
    lb.repeat("dns", "WARN", "upstream forwarder timeout; SERVFAIL for login.idp-provider.example host={host}",
              -9 * M, 5 * M, 10, ["dns-01"], key=True)
    lb.repeat("dns", "INFO", "resolved login.idp-provider.example in {ms} ms host={host}", -3 * H, 5 * M, 2, ["dns-02"], ms=(2, 30))
    lb.repeat("accounts", "ERROR", "social login failed: dial tcp: lookup login.idp-provider.example on dns-01: "
              "server misbehaving host={host}", -9 * M, 5 * M, 14, AC, key=True)
    metrics = {
        "accounts": healthy_service(seed + 10, rps=60, p99=120, cpu=30, mem=45, err=0.1),
        "gateway": healthy_service(seed + 20, rps=3000, p99=80, cpu=40, mem=45),
        "dns": healthy_service(seed + 30, rps=4000, p99=6, cpu=15, mem=30, err=0.02),
    }
    metrics["accounts"]["error_rate_pct"].add(ramp(-9, -6, 21))
    metrics["accounts"]["social_login_success_pct"] = Metric(99.5, noise=0.3, seed=seed + 11, unit="%", hi=100).add(step(-9, -51))
    metrics["dns"]["servfail_rate_pct"] = Metric(0.1, noise=0.05, seed=seed + 31, unit="%", hi=100).add(step(-9, 24))
    deploys = [Deploy(-3000, "leaderboards", "2026.05.05-1", "Show rating change next to ladder rank")]
    truth = GroundTruth(Category.infra_failure, ["dns", "dns-01", "resolver"], "RB-07",
                        "Take dns-01 out of rotation so lookups use dns-02 and page Edge on-call; until social login is "
                        "healthy again, show 'social login unavailable, use email and password'. accounts needs no change.",
                        key_metrics=["dns:servfail_rate_pct"], key_docs=["RB-07"])
    return _build("s08-dns-failure-social-login", "DNS resolver failure breaks social login",
                  _alert(8, "accounts", "social login success rate below 60% for 5 minutes", "2026-05-07T02:30:00Z", "high",
                         ["identity-provider", "chess-db"]),
                  truth, "None by design (easy tier): the resolution errors name dns-01, password logins are fine, and dns-02 "
                         "resolves the same name.",
                  metrics, lb, deploys, "easy")


# S09 (medium) ---------------------------------------------------------------------------------
def s09_websocket_fd_leak() -> Scenario:
    seed = 9000
    lb = LogBuilder(seed)
    _routine(lb, "matchmaking", MM, 2.0)
    lb.repeat("game-server", "INFO", "heartbeat timeout: player p-{p} disconnected from game g-{g} host={host}",
              -3 * H, 5 * M, 8, GS, p=(1000000, 9999999), g=(100000, 999999))
    lb.event(-45 * M, "game-server", "WARN", "open fds 61,200/65,536", "gs-04", key=True)
    lb.event(-30 * M, "game-server", "WARN", "open fds 59,800/65,536", "gs-09", key=True)
    lb.repeat("game-server", "ERROR", "accept4: too many open files (limit=65536); refusing new WebSocket host={host}",
              -12 * M, 5 * M, 12, ["gs-04"], key=True)
    lb.repeat("matchmaking", "WARN", "allocation to gs-04 failed: connection refused; retrying on another host host={host}",
              -10 * M, 5 * M, 4, MM)
    metrics = {
        "game-server": healthy_service(seed + 10, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
        "matchmaking": healthy_service(seed + 20, rps=900, p99=60, cpu=35, mem=50),
        "leaderboards": healthy_service(seed + 30, rps=800, p99=50, cpu=30, mem=40),
    }
    gs = metrics["game-server"]
    gs["open_fds_pct_max_host"] = Metric(38, noise=0.3, seed=seed + 11, unit="%", hi=100).add(ramp(-10080, -5, 62))
    gs["memory_pct"].add(ramp(-10080, 0, 18))
    gs["active_games"] = Metric(24000, noise=300, seed=seed + 12).add(daily(6000))
    gs["error_rate_pct"].add(ramp(-12, -8, 1.5))
    deploys = [Deploy(-300, "leaderboards", "2026.05.14-1", "Add country filter to ladders"),
               Deploy(-12500, "game-server", "2026.05.05-2", "Spectator chat moderation hooks")]
    truth = GroundTruth(Category.resource_leak, ["game-server", "gs-04", "file descriptor", "websocket", "fd"], "RB-03",
                        "Capture the open descriptor list on gs-04, then one host at a time (gs-04 and gs-09 first) cordon, "
                        "let games finish or migrate them, restart, and uncordon, checking the trend resets; file a defect "
                        "for sockets not closed after the heartbeat timeout. Do not restart all hosts at once.",
                        key_metrics=["game-server:open_fds_pct_max_host:7d"], key_docs=["RB-03"])
    return _build("s09-websocket-fd-leak", "Game servers leak WebSocket file descriptors",
                  _alert(9, "game-server", "'too many open files' on gs-04; new game connections refused", "2026-05-14T16:40:00Z",
                         "medium", ["matchmaking", "redis-live"]),
                  truth, "A leaderboards deploy five hours ago is the only recent change and is unrelated; the last game-server "
                         "deploy was nine days ago. The one-hour view looks flat near the limit; over seven days open fds climb "
                         "steadily on every host while active games follow the daily cycle.",
                  metrics, lb, deploys, "medium")


# S10 (medium) ---------------------------------------------------------------------------------
def s10_cold_redis_cache() -> Scenario:
    seed = 10000
    lb = LogBuilder(seed)
    LBD = ["leaderboards-1", "leaderboards-2", "leaderboards-3"]
    _routine(lb, "leaderboards", LBD, 2.0, end_s=-14 * M)
    _routine(lb, "gateway", GW, 3.0)
    lb.event(-15 * M, "ops-automation", "INFO", "maintenance: rebooted redis-cache-1 for kernel patch (window 02:00-03:00)",
             "ops-1", key=True)
    lb.event(-14 * M, "redis-cache", "INFO", "Ready to accept connections; keys=0 (persistence disabled)", "redis-cache-1", key=True)
    lb.repeat("leaderboards", "WARN", "cache miss for ladder {tc} page {pg}; querying chess-db replica host={host}",
              -14 * M, 5 * M, 10, LBD, key=True, tc=(1, 3), pg=(1, 40))
    lb.repeat("chess-db", "WARN", "duration: {ms} ms  SELECT player_id, rating FROM ratings WHERE time_control = $1 "
              "ORDER BY rating DESC LIMIT 50 OFFSET $2 host={host}", -13 * M, 5 * M, 8, ["db-02"], ms=(800, 4200))
    lb.repeat("leaderboards", "ERROR", "request timed out after 3000 ms host={host}", -10 * M, 5 * M, 6, LBD)
    metrics = {
        "leaderboards": healthy_service(seed + 10, rps=800, p99=50, cpu=30, mem=40, err=0.1),
        "redis-cache": healthy_service(seed + 20, rps=12000, p99=1, cpu=20, mem=60),
        "chess-db-replica": healthy_service(seed + 30, rps=2500, p99=6, cpu=28, mem=64),
        "gateway": healthy_service(seed + 40, rps=3000, p99=80, cpu=40, mem=45),
    }
    metrics["redis-cache"]["hit_ratio"] = Metric(0.96, noise=0.006, seed=seed + 21, hi=1).add(step(-15, -0.93))
    metrics["redis-cache"]["memory_pct"].add(step(-15, -58))
    metrics["chess-db-replica"]["cpu_pct"].add(ramp(-14, -11, 69))
    metrics["chess-db-replica"]["replication_lag_s"] = Metric(0.2, noise=0.1, seed=seed + 31, unit="s").add(ramp(-13, -2, 45))
    metrics["leaderboards"]["latency_p99_ms"].add(ramp(-14, -9, 3200))
    metrics["leaderboards"]["error_rate_pct"].add(ramp(-10, -4, 7))
    deploys = [Deploy(-500, "leaderboards", "2026.05.20-2", "Improve log format")]
    truth = GroundTruth(Category.dependency_saturation, ["redis-cache", "cache", "chess-db", "db-02", "replica"], "RB-02",
                        "Let redis-cache refill without restarting clients: rate-limit leaderboard reads at the gateway and "
                        "start leaderboard-rebuild early so ladders are served from cache; confirm hit ratio and replica CPU "
                        "recover. Do not roll back leaderboards or add pods.",
                        key_metrics=["redis-cache:hit_ratio"], key_docs=["RB-02"])
    return _build("s10-cold-redis-cache", "Cold redis-cache after a maintenance reboot",
                  _alert(10, "leaderboards", "p99 latency above 3000 ms; chess-db replica CPU above 95%", "2026-05-21T02:20:00Z",
                         "high", ["redis-cache", "chess-db"]),
                  truth, "The database replica is what alarms, and leaderboards deployed earlier; both are effects or noise. "
                         "Traffic is normal; the trigger is a maintenance reboot of redis-cache, visible in automation logs "
                         "and the hit ratio.",
                  metrics, lb, deploys, "medium")


# S11 (hard, unanswerable) ---------------------------------------------------------------------
def s11_log_pipeline_gap() -> Scenario:
    seed = 11000
    lb = LogBuilder(seed)
    _routine(lb, "stats", ST, 2.0, end_s=-22 * M)  # no stats logs from t = -22 to -2 min
    _routine(lb, "gateway", GW, 3.0)
    lb.event(-22 * M, "log-agent", "ERROR", "buffer full on stats hosts; dropping log batches until the shipper recovers", "log-1")
    lb.event(-2 * M, "log-agent", "INFO", "shipper recovered on stats hosts; 20 min of logs were not delivered", "log-1")
    lb.repeat("stats", "ERROR", "GET /players/history 500 internal error request_id={r} host={host}", -2 * M, 5 * M, 6, ST,
              r=(100000, 999999))
    metrics = {
        "stats": healthy_service(seed + 10, rps=400, p99=90, cpu=30, mem=50, err=0.2),
        "chess-db-replica": healthy_service(seed + 20, rps=2500, p99=6, cpu=28, mem=64),
        "gateway": healthy_service(seed + 30, rps=3000, p99=80, cpu=40, mem=45),
    }
    metrics["stats"]["error_rate_pct"].add(ramp(-18, -10, 5.5))
    metrics["stats"]["latency_p99_ms"].add(ramp(-18, -10, 300))
    deploys = [Deploy(-60, "accounts", "2026.05.28-1", "Rename profile settings tab"),
               Deploy(-4200, "stats", "2026.05.25-1", "Bump JSON library")]
    truth = GroundTruth(Category.insufficient_evidence, ["unknown"], "RB-08",
                        "State that the cause cannot be established because stats logs are missing from 22 to 2 minutes before "
                        "the alert, covering the onset; escalate to Data on-call with the metrics findings, and record the "
                        "log-agent gap as its own ticket.",
                        answerable=False, key_docs=["RB-08"])
    return _build("s11-log-pipeline-gap", "Stats errors during a 20-minute log gap (unanswerable)",
                  _alert(11, "stats", "error rate above 5% for 5 minutes", "2026-05-28T11:05:00Z", "medium",
                         ["chess-db", "redis-cache"]),
                  truth, "Metrics show the symptom, but stats logs are missing for the 20 minutes around the onset and the "
                         "remaining errors carry no detail. An accounts deploy an hour ago is the only visible change and is "
                         "unrelated. The right answer is that the evidence is insufficient.",
                  metrics, lb, deploys, "hard")


# S12 (hard, unanswerable) ---------------------------------------------------------------------
def s12_transient_self_resolved() -> Scenario:
    seed = 12000
    lb = LogBuilder(seed)
    LBD = ["leaderboards-1", "leaderboards-2", "leaderboards-3"]
    _routine(lb, "leaderboards", LBD, 1.5, end_s=35 * M)
    _routine(lb, "gateway", GW, 2.0, end_s=35 * M)
    for t, ms in ((-170, 1600), (-120, 1710), (-60, 1820), (10, 1690), (70, 1540)):
        lb.event(t, "leaderboards", "WARN", f"slow request {ms} ms", LBD[0])
    lb.event(-100, "leaderboards", "ERROR", "timeout calling redis-cache after 1000 ms", LBD[1])
    lb.event(-20, "leaderboards", "ERROR", "timeout calling redis-cache after 1000 ms", LBD[0])
    metrics = {
        "leaderboards": healthy_service(seed + 10, rps=800, p99=50, cpu=30, mem=40, err=0.1),
        "redis-cache": healthy_service(seed + 20, rps=12000, p99=1, cpu=20, mem=60),
        "gateway": healthy_service(seed + 30, rps=3000, p99=80, cpu=40, mem=45),
    }
    metrics["leaderboards"]["latency_p99_ms"].add(spike(-3, 6, 1700))
    metrics["leaderboards"]["error_rate_pct"].add(spike(-3, 6, 1.5))
    truth = GroundTruth(Category.insufficient_evidence, ["unknown"], "RB-08",
                        "Report that the anomaly resolved on its own with no identifiable cause; set a watch on leaderboards "
                        "latency and ask Data on-call to review if it recurs.",
                        answerable=False, key_docs=["RB-08"])
    return _build("s12-transient-self-resolved", "Transient leaderboards blip that cleared before triage (unanswerable)",
                  _alert(12, "leaderboards", "p99 latency above 1500 ms for 3 minutes", "2026-06-04T20:10:00Z", "low",
                         ["redis-cache", "chess-db"]),
                  truth, "A handful of redis-cache timeouts and a six-minute blip that resolved by itself. Nothing supports a "
                         "root cause.",
                  metrics, lb, [], "hard", now_min=35)


# S13 (easy) -----------------------------------------------------------------------------------
def s13_accounts_bad_deploy() -> Scenario:
    seed = 13000
    lb = LogBuilder(seed)
    new, old = ["accounts-1", "accounts-2"], ["accounts-3", "accounts-4"]
    _routine(lb, "gateway", GW, 3.0)
    lb.repeat("accounts", "INFO", "POST /login 200 in {ms} ms version=2026.05.11-3 host={host}", -3 * H, 5 * M, 4, old, ms=(40, 160))
    lb.repeat("accounts", "INFO", "POST /login 200 in {ms} ms version=2026.05.11-3 host={host}", -3 * H, -6 * M, 4, new, ms=(40, 160))
    for n, host in enumerate(new):
        lb.event(-6 * M + n * 60, "accounts", "INFO", "starting accounts 2026.05.12-1", host, key=True)
    lb.repeat("accounts", "ERROR", "POST /login 500: missing config key auth.refresh_token_ttl version=2026.05.12-1 host={host}",
              -6 * M, 5 * M, 20, new, key=True)
    metrics = {
        "accounts": healthy_service(seed + 10, rps=60, p99=120, cpu=30, mem=45, err=0.1),
        "gateway": healthy_service(seed + 20, rps=3000, p99=80, cpu=40, mem=45),
        "chess-db": healthy_service(seed + 30, rps=9000, p99=4, cpu=35, mem=70, err=0.01),
    }
    metrics["accounts"]["error_rate_pct"].add(ramp(-6, -4, 48))
    deploys = [Deploy(-6, "accounts", "2026.05.12-1", "Refresh tokens: read TTL from auth.refresh_token_ttl (renamed setting)", key=True)]
    truth = GroundTruth(Category.bad_change, ["accounts"], "RB-01",
                        "Roll back accounts 2026.05.12-1 with deploy rollback (stateless, about 5 minutes) and confirm login "
                        "errors stop; open a ticket for the change owner about the renamed config key.",
                        key_metrics=["accounts:error_rate_pct"], key_docs=["RB-01"])
    return _build("s13-accounts-bad-deploy", "Accounts deploy fails every login on new pods",
                  _alert(13, "accounts", "login error rate above 40% for 3 minutes", "2026-05-12T10:05:00Z", "high",
                         ["chess-db", "identity-provider"]),
                  truth, "None by design (easy tier): errors start with the deploy and only on the two pods running it.",
                  metrics, lb, deploys, "easy")


# S14 (easy) -----------------------------------------------------------------------------------
def s14_gateway_rate_limit_push() -> Scenario:
    seed = 14000
    lb = LogBuilder(seed)
    _routine(lb, "gateway", GW, 3.0)
    _routine(lb, "matchmaking", MM, 2.0)
    for n, host in enumerate(GW):
        lb.event(-7 * M + n * 3, "config-agent", "INFO",
                 "config applied: gateway.ratelimit.per_account.rps 20 -> 2 (change cs-52211 by user eng-0977)", host, key=True)
    lb.repeat("gateway", "WARN", "429 rate limited account=a-{a} route={r} limit=2 rps host={host}",
              -7 * M, 5 * M, 40, GW, key=True, a=(100000, 999999), r=(1, 4))
    metrics = {
        "gateway": healthy_service(seed + 10, rps=3000, p99=80, cpu=40, mem=45, err=0.2),
        "matchmaking": healthy_service(seed + 20, rps=900, p99=60, cpu=35, mem=50),
        "accounts": healthy_service(seed + 30, rps=60, p99=120, cpu=30, mem=45),
    }
    metrics["gateway"]["rate_limited_pct"] = Metric(0.3, noise=0.1, seed=seed + 11, unit="%", hi=100).add(step(-7, 31))
    metrics["matchmaking"]["request_rate_rps"].add(step(-7, -280))
    deploys = [Deploy(-1700, "stats", "2026.06.09-1", "Add accuracy graph to game review")]
    truth = GroundTruth(Category.bad_change, ["gateway", "ratelimit", "rate limit", "cs-52211", "config"], "RB-01",
                        "Revert config change cs-52211 with cfgpush revert (restore gateway.ratelimit.per_account.rps=20; "
                        "stateless, within a minute) and confirm 429s fall back to baseline.",
                        key_metrics=["gateway:rate_limited_pct"], key_docs=["RB-01"])
    return _build("s14-gateway-rate-limit-push", "Gateway rate-limit config push throttles normal players",
                  _alert(14, "gateway", "429 responses above 20% of requests for 5 minutes", "2026-06-10T17:07:00Z", "high",
                         ["accounts", "matchmaking"]),
                  truth, "None by design (easy tier): the config push lands on every gateway pod at the onset and the 429s "
                         "quote the new limit.",
                  metrics, lb, deploys, "easy")


# S15 (medium) ---------------------------------------------------------------------------------
def s15_bullet_clock_bug() -> Scenario:
    seed = 15000
    lb = LogBuilder(seed)
    new = ["gs-01", "gs-02", "gs-03", "gs-04", "gs-05", "gs-06"]
    _routine(lb, "matchmaking", MM, 2.0)
    lb.repeat("game-server", "INFO", "game g-{g} finished result={r} tc=blitz host={host}", -3 * H, 5 * M, 10, GS,
              g=(100000, 999999), r=(0, 2))
    for n, host in enumerate(new):
        lb.event(-150 * M + n * 15 * M, "game-server", "INFO", "starting game-server 2026.05.20-1", host, key=True)
    lb.repeat("game-server", "ERROR", "clock check failed tc=1+0: server clock ahead of client by {ms} ms; game g-{g} aborted "
              "version=2026.05.20-1 host={host}", -100 * M, 5 * M, 3, new, key=True, ms=(300, 1900), g=(100000, 999999))
    metrics = {
        "game-server": healthy_service(seed + 10, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
        "matchmaking": healthy_service(seed + 20, rps=900, p99=60, cpu=35, mem=50),
        "redis-live": healthy_service(seed + 30, rps=25000, p99=2, cpu=35, mem=55, err=0.01),
    }
    metrics["game-server"]["games_aborted_pct"] = Metric(0.02, noise=0.005, seed=seed + 11, unit="%").add(ramp(-140, -60, 0.34))
    metrics["game-server"]["error_rate_pct"].add(ramp(-140, -60, 0.3))
    deploys = [Deploy(-150, "game-server", "2026.05.20-1",
                      "Rolling out host by host: new clock synchronisation for low-latency time controls; checkpoint format "
                      "unchanged (v7)", key=True),
               Deploy(-900, "anticheat", "2026.05.19-4", "Lower flag threshold for bullet")]
    truth = GroundTruth(Category.bad_change, ["game-server", "2026.05.20-1", "clock"], "RB-01",
                        "Revert game-server 2026.05.20-1: mark 2026.05.13-2 as the current version so new games go to "
                        "old-version hosts, cordon the six upgraded hosts and drain them (bullet games last minutes; "
                        "checkpoint format unchanged, so migration is safe if needed), then reinstall the old version.",
                        key_metrics=["game-server:games_aborted_pct"], key_docs=["RB-01"])
    return _build("s15-bullet-clock-bug", "Game-server version aborts bullet games",
                  _alert(15, "game-server", "platform-aborted games above 0.05% for 15 minutes", "2026-05-20T21:30:00Z",
                         "medium", ["redis-live", "matchmaking"]),
                  truth, "Errors are a small share of all games and only one time control, so fleet metrics look mildly "
                         "degraded; an anticheat change for bullet is a tempting suspect. The aborts come only from hosts "
                         "already on the new version.",
                  metrics, lb, deploys, "medium")


# S16 (easy) -----------------------------------------------------------------------------------
def s16_weekly_arena_spike() -> Scenario:
    seed = 16000
    lb = LogBuilder(seed)
    _routine(lb, "gateway", GW, 3.0)
    lb.event(-4 * M, "matchmaking", "INFO", "arena 'Friday Blitz Arena' started: 41,200 players registered", "matchmaking-1", key=True)
    lb.repeat("matchmaking", "WARN", "hpa: desired replicas {d} capped at max_replicas=16", -3 * M, 5 * M, 1, ["matchmaking-1"],
              key=True, d=(22, 27))
    lb.repeat("matchmaking", "WARN", "queue join took {ms} ms (arena) host={host}", -3 * M, 5 * M, 12, MM, ms=(1800, 5200))
    metrics = {
        "matchmaking": healthy_service(seed + 10, rps=900, p99=60, cpu=35, mem=50),
        "gateway": healthy_service(seed + 20, rps=3000, p99=80, cpu=40, mem=45),
        "game-server": healthy_service(seed + 30, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
    }
    metrics["matchmaking"]["request_rate_rps"].add(ramp(-4, -2, 1800))
    metrics["matchmaking"]["cpu_pct"].add(ramp(-4, -2, 55))
    metrics["matchmaking"]["latency_p99_ms"].add(ramp(-4, -1, 3000))
    metrics["gateway"]["request_rate_rps"].add(ramp(-4, -2, 1900))
    metrics["game-server"]["active_games"] = Metric(30000, noise=300, seed=seed + 31).add(ramp(-4, 5, 5500))
    deploys = [Deploy(-1300, "leaderboards", "2026.05.28-2", "Arena standings page")]
    truth = GroundTruth(Category.traffic_spike, ["matchmaking", "arena"], "RB-04",
                        "Expected demand from the weekly arena: raise matchmaking's autoscaling maximum above 16 (about 28), "
                        "watch game-server capacity and boot hosts if active games approach 40,000, and pause "
                        "anticheat-backfill if it is running.",
                        key_metrics=["matchmaking:request_rate_rps"], key_docs=["RB-04"])
    return _build("s16-weekly-arena-spike", "Weekly arena pushes matchmaking to its autoscaling cap",
                  _alert(16, "matchmaking", "queue join p99 above 2000 ms for 2 minutes", "2026-05-29T19:04:00Z", "high",
                         ["redis-live", "game-server"]),
                  truth, "None by design (easy tier): the arena start and the autoscaling cap are both in the matchmaking logs.",
                  metrics, lb, deploys, "easy")


# S17 (hard) -----------------------------------------------------------------------------------
def s17_checkpoint_keys_without_ttl() -> Scenario:
    seed = 17000
    lb = LogBuilder(seed)
    _routine(lb, "matchmaking", MM, 2.0)
    lb.repeat("game-server", "INFO", "move applied game=g-{g} in {ms} ms host={host}", -3 * H, 5 * M, 20, GS,
              g=(100000, 999999), ms=(8, 60))
    lb.repeat("redis-live", "WARN", "used_memory {u} MB of maxmemory 16384 MB host={host}", -6 * H, 5 * M, 0.3, RL,
              key=True, u=(15900, 16380))
    lb.repeat("game-server", "WARN", "checkpoint write failed: OOM command not allowed when used memory > 'maxmemory'; "
              "retrying game=g-{g} host={host}", -14 * M, 5 * M, 10, GS, key=True, g=(100000, 999999))
    lb.repeat("game-server", "WARN", "move delivery delayed {ms} ms waiting for checkpoint game=g-{g} host={host}",
              -12 * M, 5 * M, 8, GS, ms=(150, 900), g=(100000, 999999))
    metrics = {
        "game-server": healthy_service(seed + 10, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
        "redis-live": healthy_service(seed + 20, rps=25000, p99=2, cpu=35, mem=55, err=0.01),
        "matchmaking": healthy_service(seed + 30, rps=900, p99=60, cpu=35, mem=50),
    }
    rl = metrics["redis-live"]
    rl["used_memory_pct"] = Metric(58, noise=0.4, seed=seed + 21, unit="%", hi=100).add(ramp(-10080, -14, 42))
    rl["keys_millions"] = Metric(4.1, noise=0.02, seed=seed + 22).add(ramp(-10080, -14, 3.6))
    rl["error_rate_pct"].add(ramp(-14, -10, 4))
    metrics["game-server"]["move_latency_p99_ms"] = Metric(60, noise=4, seed=seed + 11, unit="ms").add(ramp(-14, -8, 320))
    metrics["game-server"]["active_games"] = Metric(30000, noise=300, seed=seed + 12)
    deploys = [Deploy(-120, "gateway", "2026.06.16-1", "Tighten WebSocket upgrade header checks"),
               Deploy(-30000, "game-server", "2026.05.27-1", "Abort games whose players never connect")]
    truth = GroundTruth(Category.resource_leak, ["redis-live", "checkpoint", "ttl"], "RB-03",
                        "Free redis-live memory without flushing it: sample keys (MEMORY USAGE, TTL), delete or set TTLs on "
                        "checkpoint keys of finished or aborted games with a script, and confirm used memory falls and "
                        "checkpoint writes succeed; file a defect for checkpoints written without a TTL. Do not flush "
                        "redis-live or restart game servers.",
                        key_metrics=["redis-live:used_memory_pct:7d"], key_docs=["RB-03"])
    return _build("s17-checkpoint-keys-without-ttl", "redis-live fills up with checkpoints that never expire",
                  _alert(17, "game-server", "move delivery p99 above 150 ms for 10 minutes", "2026-06-16T20:25:00Z", "high",
                         ["redis-live", "matchmaking"]),
                  truth, "The alert is on game servers and the only recent change is a gateway WebSocket deploy two hours ago, "
                         "which sounds related. The cause is far from the alert: redis-live memory has climbed for a week (key "
                         "count with it) until writes started failing, visible only over 7 days.",
                  metrics, lb, deploys, "hard")


# S18 (hard, unanswerable) ---------------------------------------------------------------------
def s18_two_causes_same_minute() -> Scenario:
    seed = 18000
    lb = LogBuilder(seed)
    _routine(lb, "gateway", GW, 3.0)
    lb.repeat("matchmaking", "INFO", "allocated gs-{n:02d} for game g-{g} host={host}", -3 * H, 5 * M, 8, MM,
              n=(1, 10), g=(100000, 999999))
    for n, host in enumerate(MM):
        lb.event(-10 * M + n * 4, "config-agent", "INFO",
                 "config applied: matchmaking.allocator.strategy least_games -> least_cpu (change cs-53001 by user eng-0412)", host)
    lb.event(-10 * M, "kubelet", "WARN", "node-04 NIC reset (eth0 link down 3 s); pods on node: matchmaking-3, redis-live-2",
             "node-04")
    lb.repeat("kubelet", "WARN", "node-04 eth0 link flapping (rx errors {e}/s)", -9 * M, 5 * M, 1, ["node-04"], e=(40, 300))
    lb.repeat("matchmaking", "ERROR", "allocate game server: deadline exceeded after 2000 ms host={host}", -10 * M, 5 * M, 14, MM)
    lb.repeat("matchmaking", "WARN", "allocator: no CPU sample from {k} game servers in the last 10 s host={host}",
              -10 * M, 5 * M, 4, MM, k=(2, 6))
    lb.repeat("matchmaking", "WARN", "redis-live-2 connection reset by peer; reconnecting host={host}", -10 * M, 5 * M, 4, MM)
    metrics = {
        "matchmaking": healthy_service(seed + 10, rps=900, p99=60, cpu=35, mem=50, err=0.2),
        "redis-live": healthy_service(seed + 20, rps=25000, p99=2, cpu=35, mem=55, err=0.01),
        "game-server": healthy_service(seed + 30, rps=6000, p99=40, cpu=45, mem=60, err=0.05),
    }
    metrics["matchmaking"]["error_rate_pct"].add(ramp(-10, -6, 9))
    metrics["matchmaking"]["latency_p99_ms"].add(ramp(-10, -6, 1900))
    metrics["redis-live"]["error_rate_pct"].add(ramp(-10, -8, 0.6))
    truth = GroundTruth(Category.insufficient_evidence, ["unknown"], "RB-08",
                        "State that the cause is not established: config change cs-53001 (allocator strategy) and NIC resets on "
                        "node-04 began in the same minute and the evidence does not separate them. Apply mitigations safe "
                        "under both (revert cs-53001 and cordon and drain node-04) and page Play on-call with both "
                        "explanations.",
                        answerable=False, key_docs=["RB-08"])
    return _build("s18-two-causes-same-minute", "Config push and a flapping node in the same minute (unanswerable)",
                  _alert(18, "matchmaking", "queue join error rate above 8% for 5 minutes", "2026-06-18T15:15:00Z", "high",
                         ["redis-live", "game-server"]),
                  truth, "Both explanations fit: the new allocator strategy needs CPU samples it is missing, and the flapping "
                         "node hosts a redis-live shard every matchmaking pod uses. Errors are spread over all pods. Picking "
                         "either one as the cause is unsupported.",
                  metrics, lb, [], "hard")


_BUILDERS = [
    s01_retry_storm_after_deploy,
    s02_memory_growth_new_version,
    s03_streamer_traffic_spike,
    s04_expired_certificate,
    s05_anticheat_starves_node,
    s06_login_query_plan_flip,
    s07_config_push_not_in_deploys,
    s08_dns_failure_social_login,
    s09_websocket_fd_leak,
    s10_cold_redis_cache,
    s11_log_pipeline_gap,
    s12_transient_self_resolved,
    s13_accounts_bad_deploy,
    s14_gateway_rate_limit_push,
    s15_bullet_clock_bug,
    s16_weekly_arena_spike,
    s17_checkpoint_keys_without_ttl,
    s18_two_causes_same_minute,
]
