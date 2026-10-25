"""The 12 simulated incidents. ALL DATA IS SYNTHETIC: invented services, hosts, and numbers.

Rules for editing this file:
  * Ground truths are fixed BEFORE any agent run. After you have real results, changing a scenario
    changes its fingerprint (printed in every run summary) and invalidates earlier results.
  * If you must change one anyway, re-run everything and note the change in docs/LEARNING_LOG.md.

Each scenario carries a `trap`: what makes it misleading. 10 are answerable; 2 (S11, S12) have no
defensible root cause, so the correct output is category insufficient_evidence.
"""
from __future__ import annotations

from triage.schema import Alert, Category
from triage.scenarios.model import (
    Deploy, GroundTruth, LogBuilder, Metric, Scenario, assign_deploy_ids, healthy_service, ramp, spike, step,
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
           metrics: dict, lb: LogBuilder, deploys: list[Deploy], now_min: int = 5) -> Scenario:
    return Scenario(id=sid, title=title, alert=alert, truth=truth, trap=trap, metrics=metrics,
                    logs=lb.finalize(), deploys=assign_deploy_ids(deploys), now_min=now_min)


# S01 ------------------------------------------------------------------------------------------
def s01_retry_storm_after_deploy() -> Scenario:
    seed = 1000
    lb = LogBuilder(seed)
    mm = ["mm-01", "mm-02", "mm-03", "mm-04"]
    ss = ["ss-01", "ss-02"]
    _routine(lb, "matchmaking-svc", mm, 2.0, end_s=-7 * M)
    _routine(lb, "inventory-api", ["inv-01", "inv-02"])
    lb.repeat("session-store", "INFO", "health check ok host={host}", -3 * H, 5 * M, 1.0, ss)
    lb.event(-7 * M, "matchmaking-svc", "INFO",
             "deployment 2026.03.14-3 started: retry policy max_attempts=5 backoff=none, pool_size=200", "mm-01", key=True)
    lb.repeat("matchmaking-svc", "ERROR", "upstream connect timeout to session-store (attempt {a}/5) policy=no-backoff host={host}",
              -5 * M, 5 * M, 18, mm, key=True, a=(1, 5))
    lb.repeat("matchmaking-svc", "WARN", "retry budget exhausted for session-store, failing request host={host}",
              -4 * M, 5 * M, 6, mm, key=True)
    lb.repeat("session-store", "WARN", "slow response {ms} ms for GET session (queue depth {q}) host={host}",
              -330, 5 * M, 10, ss, ms=(300, 900), q=(40, 200))
    metrics = {
        "matchmaking-svc": healthy_service(seed + 10, rps=900, p99=180, cpu=38, mem=55, err=0.3),
        "session-store": healthy_service(seed + 20, rps=2600, p99=12, cpu=40, mem=60, err=0.05),
        "inventory-api": healthy_service(seed + 30, rps=500, p99=60),
    }
    metrics["matchmaking-svc"]["latency_p99_ms"].add(ramp(-6, -1, 2300))
    metrics["matchmaking-svc"]["error_rate_pct"].add(ramp(-6, -2, 16.5))
    metrics["matchmaking-svc"]["cpu_pct"].add(ramp(-6, -3, 40))
    metrics["session-store"]["request_rate_rps"].add(ramp(-7, -4, 9000))
    metrics["session-store"]["latency_p99_ms"].add(ramp(-6, -3, 90))
    metrics["session-store"]["cpu_pct"].add(ramp(-6, -3, 40))
    metrics["session-store"]["error_rate_pct"].add(ramp(-5, -2, 0.8))
    deploys = [
        Deploy(-7, "matchmaking-svc", "2026.03.14-3",
               "Raise connection pool size from 20 to 200; change upstream retry policy to 5 attempts with no backoff", key=True),
        Deploy(-1300, "inventory-api", "2026.03.13-2", "Update item catalog cache TTL"),
    ]
    truth = GroundTruth(Category.bad_change, ["matchmaking-svc"], "RB-01",
                        "Roll back matchmaking-svc 2026.03.14-3 (restore retry backoff and pool size) and confirm session-store load drops.",
                        key_metrics=["session-store:request_rate_rps"], key_docs=["RB-01"])
    return _build("s01-retry-storm-after-deploy", "Retry storm after a deploy",
                  _alert(1, "matchmaking-svc", "p99 latency above 2000 ms for 5 minutes", "2026-03-14T14:05:00Z", "high",
                         ["session-store", "inventory-api"]),
                  truth, "The dependency (session-store) shows timeouts and slowness, but it is overloaded BY the changed service's retries; "
                         "session-store's request rate jumps while matchmaking's client traffic is flat.",
                  metrics, lb, deploys)


# S02 ------------------------------------------------------------------------------------------
def s02_memory_growth_new_version() -> Scenario:
    seed = 2000
    lb = LogBuilder(seed)
    old = [f"pr-{i:02d}" for i in (1, 2, 4, 5, 6, 8, 10, 11, 12)]
    new = ["pr-03", "pr-07", "pr-09"]
    lb.repeat("presence-svc", "INFO", "heartbeat ok version=2026.03.20-4 heap={h}% host={host}", -3 * H, 5 * M, 1.5, old, h=(52, 61))
    lb.repeat("presence-svc", "INFO", "heartbeat ok version=2026.03.21-1 heap={h}% host={host}", -150 * M, 5 * M, 1.5, new, key=True, h=(66, 93))
    lb.repeat("presence-svc", "ERROR", "gc overhead: heap 94% after full GC version=2026.03.21-1 host={host}", -60 * M, 5 * M, 2, new, key=True)
    lb.event(-30 * M, "presence-svc", "ERROR", "OOMKilled: container restarted (count=2) version=2026.03.21-1", "pr-03", key=True)
    lb.event(-12 * M, "presence-svc", "ERROR", "OOMKilled: container restarted (count=1) version=2026.03.21-1", "pr-07", key=True)
    _routine(lb, "session-store", ["ss-01", "ss-02"], 0.5)
    metrics = {
        "presence-svc": healthy_service(seed + 10, rps=1500, p99=90, cpu=42, mem=55),
        "session-store": healthy_service(seed + 20, rps=2200, p99=12),
    }
    metrics["presence-svc"]["memory_pct"].add(ramp(-150, 0, 18))
    metrics["presence-svc"]["memory_pct_max_host"] = Metric(62, noise=1.0, seed=seed + 40, unit="%", hi=100).add(ramp(-150, -5, 33))
    metrics["presence-svc"]["error_rate_pct"].add(ramp(-20, 0, 1.2))
    deploys = [Deploy(-150, "presence-svc", "2026.03.21-1",
                      "Staged rollout to 3 of 12 hosts: adds in-memory presence history cache (no size bound)", key=True),
               Deploy(-2000, "session-store", "2026.03.19-2", "Tune eviction settings")]
    truth = GroundTruth(Category.bad_change, ["presence-svc"], "RB-01",
                        "Roll back presence-svc to 2026.03.20-4 on the three upgraded hosts; restarting alone only delays the growth.",
                        key_metrics=["presence-svc:memory_pct_max_host"], key_docs=["RB-01"])
    return _build("s02-memory-growth-new-version", "Memory growth on hosts running a new version",
                  _alert(2, "presence-svc", "memory above 90% on 3 of 12 hosts", "2026-03-21T09:40:00Z", "medium", ["session-store"]),
                  truth, "Looks like a classic leak (restart it), but only the three hosts on the new version are affected; "
                         "the right fix is rollback, which needs the staged-rollout deploy to be noticed.",
                  metrics, lb, deploys)


# S03 ------------------------------------------------------------------------------------------
def s03_event_traffic_spike() -> Scenario:
    seed = 3000
    lb = LogBuilder(seed)
    gw = [f"gw-{i:02d}" for i in range(1, 11)]
    _routine(lb, "api-gateway", gw, 3.0, end_s=-35 * M)
    _routine(lb, "store-ui", ["ui-01", "ui-02"], 0.5)
    lb.event(-35 * M, "live-ops-svc", "INFO", "event 'Spring Festival' went live; push notification sent to 4.2M players", "lo-01", key=True)
    lb.repeat("api-gateway", "WARN", "autoscaler: desired_replicas=24 capped at max_replicas=10", -25 * M, 5 * M, 1, ["gw-01"], key=True)
    lb.repeat("api-gateway", "WARN", "rate limit applied: 429 returned to client class=anonymous host={host}", -12 * M, 5 * M, 8, gw, key=True)
    lb.repeat("api-gateway", "ERROR", "upstream timeout after {ms} ms host={host}", -8 * M, 5 * M, 6, gw, ms=(900, 3000))
    metrics = {
        "api-gateway": healthy_service(seed + 10, rps=4000, p99=90, cpu=40, mem=48, err=0.2),
        "matchmaking-svc": healthy_service(seed + 20, rps=900, p99=180),
        "store-svc": healthy_service(seed + 30, rps=700, p99=110),
    }
    g = metrics["api-gateway"]
    g["request_rate_rps"].add(ramp(-30, -8, 9500))
    g["cpu_pct"].add(ramp(-30, -8, 52))
    g["latency_p99_ms"].add(ramp(-20, -5, 700))
    g["error_rate_pct"].add(ramp(-15, -3, 3.0))
    deploys = [Deploy(-70, "store-ui", "2026.04.02-1", "Update seasonal banner assets"),
               Deploy(-4300, "api-gateway", "2026.03.30-2", "Upgrade TLS library")]
    truth = GroundTruth(Category.traffic_spike, ["api-gateway"], "RB-04",
                        "Raise the autoscaler max_replicas above 10 and scale out api-gateway; shed anonymous traffic if needed.",
                        key_metrics=["api-gateway:request_rate_rps"], key_docs=["RB-04"])
    return _build("s03-event-traffic-spike", "Legitimate traffic spike beyond autoscaler cap",
                  _alert(3, "api-gateway", "CPU above 90% across all instances for 10 minutes", "2026-04-02T18:20:00Z", "high",
                         ["matchmaking-svc", "store-svc"]),
                  truth, "A store-ui deploy an hour earlier and visible 429s invite a rollback or an attack theory; "
                         "the demand curve and the autoscaler cap explain everything.",
                  metrics, lb, deploys)


# S04 ------------------------------------------------------------------------------------------
def s04_expired_certificate() -> Scenario:
    seed = 4000
    lb = LogBuilder(seed)
    inv = ["inv-01", "inv-02", "inv-03"]
    _routine(lb, "inventory-api", inv, 2.0, end_s=-2 * M)
    _routine(lb, "ledger-svc", ["led-01", "led-02"], 1.0, end_s=-2 * M)
    lb.event(-6 * 24 * H, "cert-monitor", "WARN",
             "certificate ledger-svc.internal expires in 7d (notAfter=2026-04-09T03:00:00Z)", "cm-01")
    lb.event(-H, "cert-monitor", "WARN",
             "certificate ledger-svc.internal expires in 1h (notAfter=2026-04-09T03:00:00Z)", "cm-01", key=True)
    lb.repeat("inventory-api", "ERROR",
              "TLS handshake failed connecting to ledger-svc: x509: certificate has expired or is not yet valid (notAfter=2026-04-09T03:00:00Z) host={host}",
              -2 * M, 5 * M, 30, inv, key=True)
    metrics = {
        "inventory-api": healthy_service(seed + 10, rps=500, p99=70, cpu=30, mem=50),
        "ledger-svc": healthy_service(seed + 20, rps=200, p99=45, cpu=25, mem=44),
        "session-store": healthy_service(seed + 30, rps=2200, p99=12),
    }
    metrics["inventory-api"]["error_rate_pct"].add(step(-2, 62))
    metrics["inventory-api"]["latency_p99_ms"].add(step(-2, -30))
    metrics["ledger-svc"]["request_rate_rps"].add(step(-2, -198))
    metrics["ledger-svc"]["cpu_pct"].add(step(-2, -18))
    deploys = [Deploy(-360, "inventory-api", "2026.04.08-4", "Schema migration: add column items.region_code"),
               Deploy(-14000, "ledger-svc", "2026.03.30-1", "Update audit log format")]
    truth = GroundTruth(Category.expired_credential, ["ledger-svc", "ledger"], "RB-06",
                        "Renew and install the ledger-svc.internal TLS certificate, then reload ledger-svc and any clients that cache it.",
                        key_metrics=["ledger-svc:request_rate_rps"], key_docs=["RB-06"])
    return _build("s04-expired-certificate", "Expired internal TLS certificate",
                  _alert(4, "inventory-api", "5xx error rate above 40% for 3 minutes", "2026-04-09T03:01:00Z", "high",
                         ["ledger-svc", "session-store"]),
                  truth, "A schema-migration deploy six hours earlier tempts a rollback; the failure starts at the exact second "
                         "the certificate expires and is a connection error, not load.",
                  metrics, lb, deploys)


# S05 ------------------------------------------------------------------------------------------
def s05_failing_cache_node() -> Scenario:
    seed = 5000
    lb = LogBuilder(seed)
    nodes = [f"cache-node-0{i}" for i in range(1, 5)]
    _routine(lb, "cache-svc", nodes, 3.0, end_s=-25 * M)
    lb.repeat("cache-svc", "INFO", "request completed in {ms} ms host={host}", -25 * M, 5 * M, 2.0, ["cache-node-01", "cache-node-02", "cache-node-04"], ms=(1, 9))
    lb.event(-25 * M, "host-agent", "ERROR", "blk_update_request: I/O error, dev nvme0n1, sector 118737920", "cache-node-03", key=True)
    lb.event(-21 * M, "host-agent", "ERROR", "EXT4-fs error: remounting filesystem read-only", "cache-node-03", key=True)
    lb.repeat("cache-svc", "ERROR", "read timeout after 800 ms host={host}", -20 * M, 5 * M, 6, ["cache-node-03"], key=True)
    lb.repeat("load-balancer", "WARN", "health check flapping target=cache-node-03 (3 of last 10 failed)", -18 * M, 5 * M, 1, ["lb-01"], key=True)
    metrics = {
        "cache-svc": healthy_service(seed + 10, rps=2500, p99=25, cpu=35, mem=60, err=0.1),
        "session-store": healthy_service(seed + 20, rps=2200, p99=12),
    }
    metrics["cache-svc"]["error_rate_pct"].add(ramp(-20, -8, 7.5))
    metrics["cache-svc"]["latency_p99_ms"].add(ramp(-20, -8, 900))
    metrics["cache-svc"]["cpu_pct"].add(step(-20, -3))
    deploys = [Deploy(-180, "cache-svc", "2026.04.16-1", "Bump client library to 4.1.2")]
    truth = GroundTruth(Category.infra_failure, ["cache-node-03"], "RB-05",
                        "Drain cache-node-03 from the load balancer and replace the node; its disk reports I/O errors.",
                        key_metrics=[], key_docs=["RB-05"])
    return _build("s05-failing-cache-node", "Single failing cache host",
                  _alert(5, "cache-svc", "error rate above 7% and p99 latency above 800 ms", "2026-04-16T22:15:00Z", "medium", ["session-store"]),
                  truth, "A client-library deploy three hours earlier is a plausible suspect; every error comes from one host "
                         "and that host logs disk I/O faults.",
                  metrics, lb, deploys)


# S06 ------------------------------------------------------------------------------------------
def s06_batch_job_exhausts_db_pool() -> Scenario:
    seed = 6000
    lb = LogBuilder(seed)
    api = ["ord-01", "ord-02", "ord-03"]
    _routine(lb, "orders-api", api, 2.0, end_s=-9 * M)
    _routine(lb, "auth-svc", ["auth-01", "auth-02"], 0.5)
    lb.event(-15 * M, "batch-scheduler", "INFO", "batch job 'weekly-sales-rollup' started (user=analytics_batch)", "bs-01", key=True)
    lb.repeat("orders-db", "WARN",
              "slow query {ms} ms user=analytics_batch: SELECT region, SUM(total) FROM orders o JOIN order_items i ON o.id=i.order_id GROUP BY region",
              -14 * M, 5 * M, 4, ["orders-db-01"], key=True, ms=(20000, 60000))
    lb.repeat("orders-api", "ERROR", "timeout acquiring connection from pool (size=40, waiting={w}) host={host}", -9 * M, 5 * M, 14, api, w=(30, 90))
    metrics = {
        "orders-api": healthy_service(seed + 10, rps=800, p99=150, cpu=30, mem=50, err=0.2),
        "orders-db": healthy_service(seed + 20, rps=1800, p99=8, cpu=30, mem=62),
        "auth-svc": healthy_service(seed + 30, rps=600, p99=40),
    }
    metrics["orders-api"]["error_rate_pct"].add(ramp(-9, -2, 12))
    metrics["orders-api"]["latency_p99_ms"].add(ramp(-10, -2, 4500))
    metrics["orders-db"]["connections_in_use"] = Metric(120, noise=6, seed=seed + 41, hi=500).add(ramp(-12, -3, 370))
    metrics["orders-db"]["cpu_pct"].add(ramp(-14, -4, 62))
    metrics["orders-db"]["slow_queries_per_min"] = Metric(1, noise=0.5, seed=seed + 42).add(ramp(-14, -5, 40))
    deploys = [Deploy(-1000, "orders-api", "2026.04.22-2", "Add order search endpoint")]
    truth = GroundTruth(Category.dependency_saturation, ["orders-db", "weekly-sales-rollup", "analytics_batch"], "RB-02",
                        "Pause or kill the weekly-sales-rollup queries on orders-db and re-run the job off-peak or against a replica.",
                        key_metrics=["orders-db:slow_queries_per_min"], key_docs=["RB-02"])
    return _build("s06-batch-job-exhausts-db-pool", "Batch job saturates the shared database",
                  _alert(6, "orders-api", "5xx above 12%: database connection pool exhausted", "2026-04-23T13:12:00Z", "high",
                         ["orders-db", "auth-svc"]),
                  truth, "The service's own logs only show pool-exhaustion symptoms; the cause is a scheduled analytics job "
                         "visible in the database's slow-query log and the scheduler. A new endpoint shipped yesterday is unrelated.",
                  metrics, lb, deploys)


# S07 ------------------------------------------------------------------------------------------
def s07_config_push_not_in_deploys() -> Scenario:
    seed = 7000
    lb = LogBuilder(seed)
    lobby = ["lob-01", "lob-02", "lob-03"]
    _routine(lb, "lobby-svc", lobby, 2.0, end_s=-11 * M)
    _routine(lb, "session-store", ["ss-01", "ss-02"], 0.5)
    lb.event(-11 * M, "config-pusher", "INFO",
             "applied change set cs-48213 to flags: region_routing.eu-west.enabled=false (previous=true) by auto-rollout bot", "cfg-01", key=True)
    lb.event(-630, "feature-flag-svc", "INFO", "flag update propagated version=7712", "ff-01", key=True)
    lb.repeat("lobby-svc", "ERROR", "no route for region=eu-west (region_routing.eu-west.enabled=false) host={host}", -11 * M, 5 * M, 12, lobby, key=True)
    metrics = {
        "lobby-svc": healthy_service(seed + 10, rps=700, p99=140, cpu=33, mem=50, err=0.2),
        "feature-flag-svc": healthy_service(seed + 20, rps=300, p99=15),
        "session-store": healthy_service(seed + 30, rps=2200, p99=12),
    }
    metrics["lobby-svc"]["error_rate_pct"].add(step(-11, 29.5))
    metrics["lobby-svc"]["latency_p99_ms"].add(step(-11, 320))
    deploys = [Deploy(-4300, "lobby-svc", "2026.04.28-1", "Improve lobby list pagination")]
    truth = GroundTruth(Category.bad_change, ["region_routing", "feature-flag", "config", "cs-48213", "lobby-svc"], "RB-01",
                        "Revert config change set cs-48213 (restore region_routing.eu-west.enabled=true) through the config pusher.",
                        key_metrics=[], key_docs=["RB-01"])
    return _build("s07-config-push-not-in-deploys", "Bad configuration push that is not in the deploy list",
                  _alert(7, "lobby-svc", "5xx above 30% for players in region eu-west", "2026-04-30T09:50:00Z", "high",
                         ["feature-flag-svc", "session-store"]),
                  truth, "The 24h deploy list is empty, which suggests no recent change; the change is only visible in the config pusher's logs.",
                  metrics, lb, deploys)


# S08 ------------------------------------------------------------------------------------------
def s08_dns_failure_with_benign_batch() -> Scenario:
    seed = 8000
    lb = LogBuilder(seed)
    co = ["chk-01", "chk-02", "chk-03"]
    _routine(lb, "checkout-svc", co, 2.0, end_s=-8 * M)
    _routine(lb, "pricing-svc", ["prc-01", "prc-02"], 0.5)
    lb.event(-45 * M, "batch-scheduler", "INFO",
             "nightly job 'ledger-reconcile' started (scheduled 01:45 UTC, expected duration 2h)", "bs-01")
    lb.repeat("batch-reporting", "WARN", "high cpu: job ledger-reconcile running host={host}", -40 * M, 5 * M, 0.5, ["br-01"])
    lb.repeat("dns-resolver", "WARN", "upstream forwarder 10.8.0.2 timeout; SERVFAIL for api.payments-provider.example host={host}",
              -9 * M, 5 * M, 10, ["dns-01", "dns-02"], key=True)
    lb.repeat("checkout-svc", "ERROR", "payment authorization failed: could not resolve host api.payments-provider.example (EAI_AGAIN) host={host}",
              -8 * M, 5 * M, 14, co, key=True)
    metrics = {
        "checkout-svc": healthy_service(seed + 10, rps=400, p99=220, cpu=35, mem=50, err=0.4),
        "pricing-svc": healthy_service(seed + 20, rps=500, p99=40),
        "batch-reporting": healthy_service(seed + 30, rps=5, p99=300, cpu=20),
        "dns-resolver": healthy_service(seed + 40, rps=1500, p99=6, cpu=15),
    }
    metrics["checkout-svc"]["error_rate_pct"].add(ramp(-8, -4, 26))
    metrics["checkout-svc"]["latency_p99_ms"].add(ramp(-8, -4, 4800))
    metrics["batch-reporting"]["cpu_pct"].add(ramp(-45, -40, 45))
    metrics["dns-resolver"]["servfail_rate_pct"] = Metric(0.1, noise=0.05, seed=seed + 51, hi=100).add(step(-9, 38))
    deploys = [Deploy(-600, "pricing-svc", "2026.05.06-3", "Round displayed prices to two decimals")]
    truth = GroundTruth(Category.infra_failure, ["dns", "resolver"], "RB-07",
                        "Fail over to the secondary DNS resolver and contact the network/DNS team; checkout-svc itself needs no change.",
                        key_metrics=["dns-resolver:servfail_rate_pct"], key_docs=["RB-07"])
    return _build("s08-dns-failure-with-benign-batch", "DNS failure next to an expected batch job",
                  _alert(8, "checkout-svc", "payment authorization failures above 25%", "2026-05-07T02:30:00Z", "high",
                         ["payments-provider", "pricing-svc"]),
                  truth, "Two anomalies at once: a nightly reconcile job with high CPU (expected, started earlier) and the real DNS failure "
                         "that lines up with the first errors. Agents can disagree about which one matters.",
                  metrics, lb, deploys)


# S09 ------------------------------------------------------------------------------------------
def s09_slow_fd_leak_no_deploy() -> Scenario:
    seed = 9000
    lb = LogBuilder(seed)
    chat = [f"chat-0{i}" for i in range(1, 7)]
    _routine(lb, "chat-svc", chat, 2.0, end_s=-20 * M)
    _routine(lb, "presence-svc", ["pr-01", "pr-02"], 0.5)
    lb.event(-45 * M, "chat-svc", "WARN", "open fd count 61000/65535", "chat-02", key=True)
    lb.repeat("chat-svc", "ERROR", "accept4: too many open files (limit=65535) host={host}", -20 * M, 5 * M, 12, chat, key=True)
    metrics = {
        "chat-svc": healthy_service(seed + 10, rps=1200, p99=80, cpu=36, mem=58, err=0.2),
        "presence-svc": healthy_service(seed + 20, rps=1500, p99=90),
        "session-store": healthy_service(seed + 30, rps=2200, p99=12),
    }
    metrics["chat-svc"]["open_fds_pct"] = Metric(40, noise=0.25, seed=seed + 41, hi=100, unit="%").add(ramp(-10080, -5, 56))
    metrics["chat-svc"]["error_rate_pct"].add(ramp(-25, -5, 6.5))
    deploys = [Deploy(-3000, "presence-svc", "2026.05.12-1", "Adjust heartbeat interval")]
    truth = GroundTruth(Category.resource_leak, ["chat-svc"], "RB-03",
                        "Capture an open-descriptor listing, then restart chat-svc instances one at a time; file a defect with the 7-day growth rate.",
                        key_metrics=["chat-svc:open_fds_pct:7d"], key_docs=["RB-03"])
    return _build("s09-slow-fd-leak-no-deploy", "Slow file-descriptor leak with no recent change",
                  _alert(9, "chat-svc", "'too many open files' errors; error rate above 6%", "2026-05-14T16:40:00Z", "medium",
                         ["presence-svc", "session-store"]),
                  truth, "No deploy explains it and the one-hour view looks flat near the limit; the leak only shows as a steady climb over seven days.",
                  metrics, lb, deploys)


# S10 ------------------------------------------------------------------------------------------
def s10_cold_cache_thundering_herd() -> Scenario:
    seed = 10000
    lb = LogBuilder(seed)
    api = ["cat-01", "cat-02", "cat-03"]
    _routine(lb, "catalog-api", api, 2.0, end_s=-14 * M)
    lb.event(-15 * M, "ops-automation", "INFO", "maintenance task 'cache-flush' executed on catalog-cache (FLUSHALL) by scheduled job nightly-maint", "oa-01", key=True)
    lb.event(-15 * M + 2, "catalog-cache", "INFO", "flushall completed: keys=0", "cc-01", key=True)
    lb.repeat("catalog-api", "WARN", "cache miss ratio {r}%, falling back to database host={host}", -14 * M, 5 * M, 6, api, key=True, r=(92, 99))
    lb.repeat("catalog-db", "WARN", "high load: {q} concurrent queries, cpu {c}%", -13 * M, 5 * M, 4, ["cdb-01"], key=True, q=(380, 520), c=(93, 99))
    lb.repeat("catalog-api", "ERROR", "request timed out after 3000 ms host={host}", -10 * M, 5 * M, 8, api)
    metrics = {
        "catalog-api": healthy_service(seed + 10, rps=2000, p99=90, cpu=35, mem=52, err=0.2),
        "catalog-db": healthy_service(seed + 20, rps=1200, p99=10, cpu=28, mem=64),
        "catalog-cache": healthy_service(seed + 30, rps=9000, p99=2, cpu=20),
    }
    metrics["catalog-cache"]["hit_ratio_pct"] = Metric(96, noise=0.6, seed=seed + 41, hi=100, unit="%").add(step(-15, -93))
    metrics["catalog-db"]["cpu_pct"].add(ramp(-15, -12, 68))
    metrics["catalog-api"]["latency_p99_ms"].add(ramp(-14, -9, 3200))
    metrics["catalog-api"]["error_rate_pct"].add(ramp(-10, -4, 7))
    deploys = [Deploy(-500, "catalog-api", "2026.05.20-2", "Improve log format")]
    truth = GroundTruth(Category.dependency_saturation, ["catalog-db", "catalog-cache", "cache"], "RB-02",
                        "Throttle catalog-api read traffic and let the cache warm gradually (do not restart clients); confirm hit ratio and database CPU recover.",
                        key_metrics=["catalog-cache:hit_ratio_pct"], key_docs=["RB-02"])
    return _build("s10-cold-cache-thundering-herd", "Cold cache after a maintenance flush",
                  _alert(10, "catalog-api", "p99 latency above 3000 ms; database CPU above 95%", "2026-05-21T02:20:00Z", "high",
                         ["catalog-db", "catalog-cache"]),
                  truth, "The database looks like the culprit; its load is the effect. Traffic is normal and the trigger is a "
                         "scheduled cache flush that is only visible in automation logs and the hit-ratio metric.",
                  metrics, lb, deploys)


# S11 (unanswerable) ---------------------------------------------------------------------------
def s11_log_pipeline_gap() -> Scenario:
    seed = 11000
    lb = LogBuilder(seed)
    _routine(lb, "auth-svc", ["auth-01", "auth-02"], 2.0, end_s=-12 * M)  # no auth-svc logs after t = -12 min
    _routine(lb, "user-db", ["udb-01"], 0.5)
    _routine(lb, "session-store", ["ss-01", "ss-02"], 0.5)
    lb.event(-12 * M, "log-shipper", "ERROR", "forwarder crashed: out of disk on log-agent host (auth-svc hosts affected)", "ls-01")
    metrics = {
        "auth-svc": healthy_service(seed + 10, rps=600, p99=40, cpu=30, mem=50, err=0.2),
        "user-db": healthy_service(seed + 20, rps=900, p99=8),
        "session-store": healthy_service(seed + 30, rps=2200, p99=12),
    }
    metrics["auth-svc"]["error_rate_pct"].add(ramp(-8, -5, 5.5))
    metrics["auth-svc"]["latency_p99_ms"].add(ramp(-8, -5, 160))
    deploys = [Deploy(-300, "billing-svc", "2026.05.28-1", "Adjust invoice rounding"),
               Deploy(-4200, "auth-svc", "2026.05.25-1", "Bump TLS library")]
    truth = GroundTruth(Category.insufficient_evidence, ["unknown"], "RB-08",
                        "State that the cause cannot be established because auth-svc logs are missing for the incident window; "
                        "escalate with the metrics findings and the log pipeline gap.",
                        answerable=False, key_docs=["RB-08"])
    return _build("s11-log-pipeline-gap", "Alert with a gap in log coverage (unanswerable)",
                  _alert(11, "auth-svc", "error rate above 5% for 5 minutes", "2026-05-28T11:05:00Z", "medium", ["user-db", "session-store"]),
                  truth, "Metrics show the symptom but the service's logs are missing for the whole window; a three-day-old deploy "
                         "is a tempting but unsupported cause. The right answer is to say the evidence is insufficient.",
                  metrics, lb, deploys)


# S12 (unanswerable) ---------------------------------------------------------------------------
def s12_transient_self_resolved() -> Scenario:
    seed = 12000
    lb = LogBuilder(seed)
    lead = ["lb-a1", "lb-a2"]
    _routine(lb, "leaderboard-svc", lead, 1.5, end_s=35 * M)
    _routine(lb, "cache-svc", ["cache-node-01", "cache-node-02"], 1.0, end_s=35 * M)
    for t, ms in ((-170, 1600), (-120, 1710), (-60, 1820), (10, 1690), (70, 1540)):
        lb.event(t, "leaderboard-svc", "WARN", f"slow request {ms} ms", lead[0])
    lb.event(-100, "leaderboard-svc", "ERROR", "timeout calling cache-svc after 1000 ms", lead[1])
    lb.event(-20, "leaderboard-svc", "ERROR", "timeout calling cache-svc after 1000 ms", lead[0])
    metrics = {
        "leaderboard-svc": healthy_service(seed + 10, rps=500, p99=110, cpu=30, mem=48, err=0.2),
        "session-store": healthy_service(seed + 20, rps=2200, p99=12),
        "cache-svc": healthy_service(seed + 30, rps=2500, p99=25),
    }
    metrics["leaderboard-svc"]["latency_p99_ms"].add(spike(-3, 6, 1700))
    metrics["leaderboard-svc"]["error_rate_pct"].add(spike(-3, 6, 1.5))
    truth = GroundTruth(Category.insufficient_evidence, ["unknown"], "RB-08",
                        "Report that the anomaly resolved on its own with no identifiable cause; set a watch and ask the service engineer to review if it recurs.",
                        answerable=False, key_docs=["RB-08"])
    return _build("s12-transient-self-resolved", "Transient spike that cleared before triage (unanswerable)",
                  _alert(12, "leaderboard-svc", "p95 latency above 1500 ms for 3 minutes", "2026-06-04T20:10:00Z", "low",
                         ["session-store", "cache-svc"]),
                  truth, "A handful of timeouts to the cache and a six-minute blip that resolved by itself. Nothing supports a root cause.",
                  metrics, lb, [], now_min=35)


_BUILDERS = [
    s01_retry_storm_after_deploy, s02_memory_growth_new_version, s03_event_traffic_spike, s04_expired_certificate,
    s05_failing_cache_node, s06_batch_job_exhausts_db_pool, s07_config_push_not_in_deploys,
    s08_dns_failure_with_benign_batch, s09_slow_fd_leak_no_deploy, s10_cold_cache_thundering_herd,
    s11_log_pipeline_gap, s12_transient_self_resolved,
]
