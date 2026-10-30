import importlib.util
from pathlib import Path

from triage.scenarios import all_scenarios

spec = importlib.util.spec_from_file_location("build_data", Path(__file__).resolve().parents[1] / "site" / "build_data.py")
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)


def test_every_scenario_has_diagram_truth_on_known_boxes():
    ids = {n[0] for n in bd.NODES}
    assert set(bd.TRUTH_NODES) == {s.id[:3] for s in all_scenarios()}
    for truth in bd.TRUTH_NODES.values():
        assert all(n in ids for nodes in truth.values() for n in nodes)
    # the three unanswerable incidents have no single broken box
    assert all(not bd.TRUTH_NODES[s]["cause"] for s in ("s11", "s12", "s18"))
    assert all(a in ids and b in ids for a, b in bd.EDGES)


def test_blamed_component_maps_to_boxes():
    assert bd.blamed_nodes("game-server wildcard TLS certificate", "expired_credential") == ["edge"]
    assert bd.blamed_nodes("chess-db‑replica", "dependency_saturation") == ["chess-db"]
    assert bd.blamed_nodes("unknown", "insufficient_evidence") == []
    assert bd.service_node("kubelet") == "k8s" and bd.service_node("gs-04") == "game-server" and bd.service_node("") is None
