"""Scenario data model and deterministic generators for metrics and logs.

A Scenario is one simulated incident: an alert, the data an on-call engineer could query
(logs, metrics, deploys), and a ground truth that is written BEFORE any agent runs.

Time convention: t = 0 is the moment the alert fires. Logs use seconds, metrics use minutes.
Negative values are before the alert. Data is visible up to `now_min` minutes after the alert.
Everything is generated deterministically from seeds, so a scenario is identical on every run.
"""
from __future__ import annotations

import datetime as dt
import math
import random
import zlib
from dataclasses import dataclass, field
from typing import Callable

from triage.schema import Alert, Category

WINDOW_MINUTES = {"15m": 15, "1h": 60, "6h": 360, "24h": 1440, "7d": 10080}
LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")


# ---- metrics ---------------------------------------------------------------------------------

def _noise(seed: int, t_min: float) -> float:
    """Deterministic noise in [-1, 1], constant within each 30-second slot."""
    return (zlib.crc32(f"{seed}:{int(t_min * 2)}".encode()) / 2**32) * 2 - 1


Effect = Callable[[float], float]


def step(at: float, delta: float) -> Effect:
    return lambda t: delta if t >= at else 0.0


def window_step(at: float, until: float, delta: float) -> Effect:
    return lambda t: delta if at <= t < until else 0.0


def ramp(start: float, end: float, delta: float) -> Effect:
    """Linear rise from `start` to `end` (minutes), then holds at `delta`."""
    def f(t: float) -> float:
        if t <= start:
            return 0.0
        if t >= end:
            return delta
        return delta * (t - start) / (end - start)
    return f


def spike(at: float, duration: float, delta: float) -> Effect:
    return lambda t: delta if at <= t < at + duration else 0.0


def decay(at: float, delta: float, tau: float) -> Effect:
    return lambda t: delta * math.exp(-(t - at) / tau) if t >= at else 0.0


def daily(amp: float, peak_min: float = 0.0) -> Effect:
    """Gentle diurnal wave, period 24h, peaking at `peak_min` minutes relative to the alert."""
    return lambda t: amp * math.sin(2 * math.pi * (t - peak_min) / 1440 + math.pi / 2)


def sawtooth(period: float, amp: float) -> Effect:
    return lambda t: amp * ((t % period) / period)


class Metric:
    def __init__(self, base: float, noise: float = 0.0, lo: float = 0.0, hi: float | None = None,
                 seed: int = 0, unit: str = "") -> None:
        self.base, self.noise, self.lo, self.hi, self.seed, self.unit = base, noise, lo, hi, seed, unit
        self.effects: list[Effect] = []

    def add(self, effect: Effect) -> "Metric":
        self.effects.append(effect)
        return self

    def value(self, t_min: float) -> float:
        v = self.base + sum(e(t_min) for e in self.effects) + self.noise * _noise(self.seed, t_min)
        v = max(v, self.lo)
        return min(v, self.hi) if self.hi is not None else v


def healthy_service(seed: int, rps: float = 300, p99: float = 120, cpu: float = 35,
                    mem: float = 52, err: float = 0.15) -> dict[str, Metric]:
    """Standard metric set for a healthy service. Scenarios add effects to the faulty ones."""
    return {
        "error_rate_pct": Metric(err, noise=err * 0.3, seed=seed + 1, unit="%", hi=100),
        "latency_p99_ms": Metric(p99, noise=p99 * 0.06, seed=seed + 2, unit="ms"),
        "cpu_pct": Metric(cpu, noise=2.0, seed=seed + 3, unit="%", hi=100).add(daily(3.0)),
        "memory_pct": Metric(mem, noise=0.8, seed=seed + 4, unit="%", hi=100),
        "request_rate_rps": Metric(rps, noise=rps * 0.04, seed=seed + 5, unit="rps").add(daily(rps * 0.12)),
    }


# ---- logs, deploys ---------------------------------------------------------------------------

@dataclass
class LogLine:
    t: int  # seconds relative to the alert
    service: str
    level: str
    message: str
    host: str = ""
    key: bool = False  # part of the evidence that supports the true root cause
    id: str = ""


@dataclass
class Deploy:
    t_min: float
    service: str
    version: str
    summary: str
    key: bool = False
    id: str = ""


class LogBuilder:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.lines: list[LogLine] = []

    def event(self, t_s: int, service: str, level: str, message: str, host: str = "", key: bool = False) -> None:
        assert level in LEVELS, level
        self.lines.append(LogLine(t_s, service, level, message, host, key))

    def repeat(self, service: str, level: str, template: str, start_s: int, end_s: int, per_min: float,
               hosts: list[str] | None = None, key: bool = False, **ranges: tuple[int, int]) -> None:
        """Repeated lines. `template` may use {host}, {i}, and any name given in `ranges` as (lo, hi)."""
        assert level in LEVELS, level
        n = max(1, int((end_s - start_s) / 60 * per_min))
        for i in range(n):
            t = start_s + int((end_s - start_s) * (i + self.rng.random() * 0.8) / n)
            host = self.rng.choice(hosts) if hosts else ""
            vals = {name: self.rng.randint(lo, hi) for name, (lo, hi) in ranges.items()}
            self.lines.append(LogLine(t, service, level, template.format(host=host, i=i, **vals), host, key))

    def finalize(self) -> list[LogLine]:
        lines = sorted(self.lines, key=lambda l: l.t)
        for n, line in enumerate(lines):
            line.id = f"L{n:04d}"
        return lines


# ---- scenario --------------------------------------------------------------------------------

@dataclass
class GroundTruth:
    category: Category
    component_aliases: list[str]  # any of these (case-insensitive substring) counts as the right component
    runbook: str
    reference_action: str
    answerable: bool = True
    key_metrics: list[str] = field(default_factory=list)  # "service:metric"
    key_docs: list[str] = field(default_factory=list)  # runbook ids such as "RB-01"


@dataclass
class Scenario:
    id: str
    title: str
    alert: Alert
    truth: GroundTruth
    trap: str  # author's note: what makes this incident misleading
    metrics: dict[str, dict[str, Metric]]
    logs: list[LogLine]
    deploys: list[Deploy]
    now_min: int = 5  # data is visible up to this many minutes after the alert

    def abs_time(self, t_s: float) -> str:
        base = dt.datetime.fromisoformat(self.alert.fired_at.replace("Z", "+00:00"))
        return (base + dt.timedelta(seconds=t_s)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def fingerprint_payload(self) -> dict:
        """Everything that defines the scenario, for hashing. Changing it after results exist invalidates them."""
        sample = [round(m.value(t), 3) for svc in sorted(self.metrics) for name in sorted(self.metrics[svc])
                  for m in [self.metrics[svc][name]] for t in range(-120, self.now_min + 1, 15)]
        return {
            "id": self.id, "alert": self.alert.model_dump(), "now_min": self.now_min,
            "truth": {"category": self.truth.category.value, "aliases": self.truth.component_aliases,
                      "runbook": self.truth.runbook, "answerable": self.truth.answerable},
            "logs": [(l.t, l.service, l.level, l.message, l.host, l.key) for l in self.logs],
            "deploys": [(d.t_min, d.service, d.version, d.summary, d.key) for d in self.deploys],
            "metric_sample": sample,
        }

    def key_log_ids(self) -> set[str]:
        return {l.id for l in self.logs if l.key and l.t <= self.now_min * 60}

    def key_deploy_ids(self) -> set[str]:
        return {d.id for d in self.deploys if d.key}


def assign_deploy_ids(deploys: list[Deploy]) -> list[Deploy]:
    ordered = sorted(deploys, key=lambda d: d.t_min)
    for n, d in enumerate(ordered, start=1):
        d.id = f"D{n}"
    return ordered
