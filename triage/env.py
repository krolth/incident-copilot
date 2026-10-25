"""The simulated operations environment an agent queries.

An Environment wraps ONE scenario and exposes four tools, behind the interface a real
Elasticsearch / Grafana / deploy-history / vector-search client would offer:

    search_logs, get_metrics, get_recent_deploys, search_knowledge

Every tool returns plain text with evidence ids in square brackets, e.g. [L0231], [D2],
[M:svc:metric:1h], [K:RB-01#0]. Agents cite those ids. The Environment records which ids were
ever shown to the agent (`seen_ids`) so citation validity can be checked, and logs every call.
"""
from __future__ import annotations

import re
import threading
import time
from collections import Counter
from datetime import datetime

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from triage.scenarios.model import LEVELS, WINDOW_MINUTES, Scenario

ID_RE = re.compile(r"\[((?:L\d{4})|(?:D\d+)|(?:M:[^\]\s]+)|(?:K:[^\]\s]+))\]")
MAX_LOG_LINES = 20
MAX_CHARS = 6000
TOOL_NAMES = ("search_logs", "get_metrics", "get_recent_deploys", "search_knowledge")


class Trace:
    """Thread-safe, time-ordered list of events (LLM calls and tool calls) for one run."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._lock = threading.Lock()
        self._t0 = time.perf_counter()

    def add(self, **event) -> None:
        with self._lock:
            event["t"] = round(time.perf_counter() - self._t0, 3)
            self.events.append(event)


class SearchLogsArgs(BaseModel):
    service: str = Field("", description="Service name to search; empty string searches all services.")
    query: str = Field("", description="Words that must ALL appear in the message or host name (case-insensitive). Empty matches everything.")
    level: str = Field("", description="DEBUG, INFO, WARN or ERROR; empty for all levels.")
    window: str = Field("1h", description="Look-back window ending now: 15m, 1h, 6h, 24h or 7d.")


class GetMetricsArgs(BaseModel):
    service: str = Field(description="Service name, e.g. 'matchmaking-svc'.")
    metric: str = Field(description="Metric name, e.g. 'error_rate_pct', 'latency_p99_ms', 'cpu_pct', 'memory_pct', 'request_rate_rps'.")
    window: str = Field("1h", description="Look-back window ending now: 15m, 1h, 6h, 24h or 7d.")


class GetDeploysArgs(BaseModel):
    service: str = Field("", description="Service name; empty lists deploys of all services.")
    window: str = Field("24h", description="Look-back window ending now: 15m, 1h, 6h, 24h or 7d.")


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(description="What to look for in runbooks and past incident postmortems, in plain words.")
    k: int = Field(4, description="Number of passages to return (1-8).")


class Environment:
    def __init__(self, scenario: Scenario, retriever=None, trace: Trace | None = None) -> None:
        self.scenario = scenario
        self.retriever = retriever
        self.trace = trace or Trace()
        self.calls: list[dict] = []
        self.seen_ids: set[str] = set()
        self.evidence: dict[str, str] = {}  # id -> short text shown to the agent (used by the judge)
        self._lock = threading.Lock()

    # ---- helpers ------------------------------------------------------------------------------
    def _now_s(self) -> int:
        return self.scenario.now_min * 60

    def _window_minutes(self, window: str) -> int | None:
        return WINDOW_MINUTES.get(window)

    def _bad_window(self, window: str) -> str:
        return f"ERROR: unknown window '{window}'. Valid windows: {', '.join(WINDOW_MINUTES)}."

    def _record(self, agent: str, name: str, args: dict, output: str) -> str:
        output = output[:MAX_CHARS]
        ids = set(ID_RE.findall(output))
        lines = output.split("\n")
        snippets: dict[str, str] = {}
        for n, line in enumerate(lines):
            m = re.match(r"\[((?:L\d{4})|(?:D\d+)|(?:M:[^\]\s]+)|(?:K:[^\]\s]+))\]", line)
            if m and m.group(1) not in snippets:
                extra = " ".join(lines[n + 1:n + 3]) if m.group(1)[0] in "KM" else ""
                snippets[m.group(1)] = f"{line} {extra}".strip()[:400]
        with self._lock:
            for k, v in snippets.items():
                self.evidence.setdefault(k, v)
            self.calls.append({"agent": agent, "tool": name, "args": args, "output_chars": len(output)})
            self.seen_ids |= ids
        self.trace.add(type="tool", agent=agent, name=name, args=args, output_preview=output[:400])
        return output

    # ---- tools --------------------------------------------------------------------------------
    def search_logs(self, service: str = "", query: str = "", level: str = "", window: str = "1h", agent: str = "") -> str:
        args = {"service": service, "query": query, "level": level, "window": window}
        minutes = self._window_minutes(window)
        if minutes is None:
            return self._record(agent, "search_logs", args, self._bad_window(window))
        lvl = level.upper().strip()
        if lvl and lvl not in LEVELS:
            return self._record(agent, "search_logs", args, f"ERROR: unknown level '{level}'. Valid: {', '.join(LEVELS)}.")
        now_s, start_s = self._now_s(), self._now_s() - minutes * 60
        tokens = query.lower().split()
        sc = self.scenario
        hits = [l for l in sc.logs
                if start_s <= l.t <= now_s
                and (not service or l.service == service)
                and (not lvl or l.level == lvl)
                and all(tok in f"{l.message} {l.host}".lower() for tok in tokens)]
        label = f"search_logs(service={service or '*'}, query='{query}', level={lvl or '*'}, window={window})"
        if not hits:
            known = sorted({l.service for l in sc.logs})
            hint = "" if (not service or service in known) else f" Services with logs: {', '.join(known)}."
            return self._record(agent, "search_logs", args, f"{label}: 0 matching lines.{hint}")
        by_level = Counter(l.level for l in hits)
        by_host = Counter(l.host for l in hits if l.host).most_common(3)
        newest = max(l.t for l in hits)
        header = (f"{label}: {len(hits)} matching lines; by level: "
                  + " ".join(f"{k}={v}" for k, v in sorted(by_level.items()))
                  + ("; top hosts: " + ", ".join(f"{h}({n})" for h, n in by_host) if by_host else "")
                  + f"; newest match: {sc.abs_time(newest)} ({round((now_s - newest) / 60, 1)} min before now)")
        shown = hits if len(hits) <= MAX_LOG_LINES else hits[:6] + hits[-(MAX_LOG_LINES - 6):]
        lines = []
        for i, l in enumerate(shown):
            if len(hits) > MAX_LOG_LINES and i == 6:
                lines.append(f"... {len(hits) - MAX_LOG_LINES} matching lines omitted ...")
            host = f"[{l.host}]" if l.host else ""
            lines.append(f"[{l.id}] {sc.abs_time(l.t)} {l.level} {l.service}{host} {l.message}")
        return self._record(agent, "search_logs", args, header + "\n" + "\n".join(lines))

    def get_metrics(self, service: str, metric: str, window: str = "1h", agent: str = "") -> str:
        args = {"service": service, "metric": metric, "window": window}
        minutes = self._window_minutes(window)
        if minutes is None:
            return self._record(agent, "get_metrics", args, self._bad_window(window))
        svc = self.scenario.metrics.get(service)
        if svc is None:
            return self._record(agent, "get_metrics", args,
                                f"ERROR: unknown service '{service}'. Known services: {', '.join(sorted(self.scenario.metrics))}.")
        m = svc.get(metric)
        if m is None:
            return self._record(agent, "get_metrics", args,
                                f"ERROR: no metric '{metric}' for {service}. Available: {', '.join(sorted(svc))}.")
        now = self.scenario.now_min
        fine = [m.value(now - minutes + i * minutes / 59) for i in range(60)]
        n_points = 12
        fmt = "%H:%M" if minutes <= 1440 else "%m-%d %H:%M"
        points = []
        for i in range(n_points):
            t = now - minutes + i * minutes / (n_points - 1)
            stamp = self.scenario.abs_time(t * 60)
            label = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").strftime(fmt)
            points.append(f"{label}={m.value(t):.2f}")
        mid = f"M:{service}:{metric}:{window}"
        unit = f" unit={m.unit}" if m.unit else ""
        text = (f"[{mid}]{unit} window={window} ending {self.scenario.abs_time(now * 60)}: "
                f"min={min(fine):.2f} max={max(fine):.2f} mean={sum(fine) / len(fine):.2f} last={fine[-1]:.2f}\n"
                f"points (oldest to newest): " + ", ".join(points))
        return self._record(agent, "get_metrics", args, text)

    def get_recent_deploys(self, service: str = "", window: str = "24h", agent: str = "") -> str:
        args = {"service": service, "window": window}
        minutes = self._window_minutes(window)
        if minutes is None:
            return self._record(agent, "get_recent_deploys", args, self._bad_window(window))
        now = self.scenario.now_min
        found = [d for d in self.scenario.deploys
                 if now - minutes <= d.t_min <= now and (not service or d.service == service)]
        if not found:
            return self._record(agent, "get_recent_deploys", args,
                                f"get_recent_deploys(service={service or '*'}, window={window}): no code deploys in this window.")
        lines = [f"[{d.id}] {self.scenario.abs_time(d.t_min * 60)} {d.service} {d.version}: {d.summary}"
                 for d in sorted(found, key=lambda d: -d.t_min)]
        return self._record(agent, "get_recent_deploys", args,
                            f"get_recent_deploys(service={service or '*'}, window={window}): {len(found)} deploys\n" + "\n".join(lines))

    def search_knowledge(self, query: str, k: int = 4, agent: str = "") -> str:
        args = {"query": query, "k": k}
        if self.retriever is None:
            return self._record(agent, "search_knowledge", args, "ERROR: knowledge base is not available.")
        k = max(1, min(int(k), 8))
        hits = self.retriever.search(query, k)
        if not hits:
            return self._record(agent, "search_knowledge", args, f"search_knowledge('{query}'): no passages found.")
        blocks = [f"[{h.chunk_id}] ({h.kind}) {h.title}\n{h.text[:700]}" for h in hits]
        return self._record(agent, "search_knowledge", args, f"search_knowledge('{query}'): {len(hits)} passages\n\n" + "\n\n".join(blocks))

    # ---- tool objects for agents ------------------------------------------------------------------
    def tools(self, names: tuple[str, ...] | list[str] = TOOL_NAMES, agent: str = "") -> list[StructuredTool]:
        defs = {
            "search_logs": StructuredTool.from_function(
                func=lambda service="", query="", level="", window="1h": self.search_logs(service, query, level, window, agent),
                name="search_logs", args_schema=SearchLogsArgs,
                description="Search application logs (Elasticsearch-style). Returns counts, top hosts, newest match time, and matching lines with ids like [L0231]."),
            "get_metrics": StructuredTool.from_function(
                func=lambda service, metric, window="1h": self.get_metrics(service, metric, window, agent),
                name="get_metrics", args_schema=GetMetricsArgs,
                description="Read one metric of one service over a look-back window (Grafana-style). Returns summary stats and 12 points; id like [M:svc:metric:1h]. Use a longer window to see slow trends."),
            "get_recent_deploys": StructuredTool.from_function(
                func=lambda service="", window="24h": self.get_recent_deploys(service, window, agent),
                name="get_recent_deploys", args_schema=GetDeploysArgs,
                description="List recent CODE deploys (not configuration or feature-flag changes). Ids like [D2]."),
            "search_knowledge": StructuredTool.from_function(
                func=lambda query, k=4: self.search_knowledge(query, k, agent),
                name="search_knowledge", args_schema=SearchKnowledgeArgs,
                description="Search runbooks and past incident postmortems. Returns passages with ids like [K:RB-01#0]."),
        }
        return [defs[n] for n in names]
