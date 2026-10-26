"""Scenario registry. `all_scenarios()` builds the 18 incidents deterministically."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from triage.scenarios.model import Scenario

# Prompts in triage/prompts.py are tuned on these only (one per tier: s01 medium bad_change, already seen in the
# first smoke traces; s08 easy infra_failure; s11 hard abstain). Their results are optimistic, so the report also
# gives accuracy on the other 15. Do not change this list once real results exist.
DEV_SCENARIOS = ("s01", "s08", "s11")


def is_dev(scenario_id: str) -> bool:
    return scenario_id[:3] in DEV_SCENARIOS


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
