"""Scenario registry. `all_scenarios()` builds the 12 incidents deterministically."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from triage.scenarios.model import Scenario


@lru_cache(maxsize=1)
def _built() -> tuple[Scenario, ...]:
    from triage.scenarios.defs import _BUILDERS
    return tuple(b() for b in _BUILDERS)


def all_scenarios() -> list[Scenario]:
    return list(_built())


def get_scenario(scenario_id: str) -> Scenario:
    for s in _built():
        if s.id == scenario_id or s.id.startswith(scenario_id):
            return s
    raise KeyError(f"unknown scenario {scenario_id!r}")


def fingerprint(scenarios: list[Scenario] | None = None) -> str:
    """Short hash of everything that defines the scenarios. Printed in every run summary."""
    payload = [s.fingerprint_payload() for s in (scenarios or all_scenarios())]
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]
