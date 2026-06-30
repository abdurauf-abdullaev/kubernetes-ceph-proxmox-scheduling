"""
Adaptive and storage-aware pod placement.

Implements Algorithm 2 from "Predictive and Adaptive Resource Scheduling
for Kubernetes-Ceph Hyperconverged Infrastructure on Proxmox VE".

This module computes the target node for a pending pod given predicted
resource demand, candidate node capacities, and Ceph OSD load/latency
signals, using a weighted scoring function that balances:
  - CPU imbalance contribution (w1)
  - storage I/O latency contribution (w2)
  - Ceph OSD load contribution (w3)

It is designed to run as a Kubernetes custom scheduler / scheduler
extender, consuming metrics from the Kubernetes API and Prometheus and
issuing Bind calls via the standard Kubernetes Bind API. The actual
cluster wiring (informers, leader election, watch loops) is intentionally
left out of this reference implementation; see configs/kubernetes for
the deployment manifests used to run this as a second scheduler in the
cluster.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

REQUEUE = "REQUEUE"


@dataclass
class NodeState:
    node_id: str
    capacity: Dict[str, float]       # C_i^{cpu, mem, io}
    current_usage: Dict[str, float]  # current allocated demand per resource
    osd_load: float                  # rho_i^osd  (0..1)
    osd_latency_ms: float            # L_i^osd, Ceph OSD apply latency
    storage_bandwidth: float         # B_i^sto


@dataclass
class PendingPod:
    pod_id: str
    predicted_demand: Dict[str, float]  # d_hat_j(t+1) for cpu, mem, io


def fits(node: NodeState, pod: PendingPod) -> bool:
    """Feasibility check: predicted demand must not exceed remaining capacity
    for any resource type k in {cpu, mem, io}."""
    for k in ("cpu", "mem", "io"):
        projected = node.current_usage.get(k, 0.0) + pod.predicted_demand.get(k, 0.0)
        if projected > node.capacity.get(k, 0.0):
            return False
    return True


def utilisation(node: NodeState, resource: str) -> float:
    cap = node.capacity.get(resource, 0.0)
    if cap <= 0:
        return 0.0
    return node.current_usage.get(resource, 0.0) / cap


def cpu_imbalance(nodes: List[NodeState]) -> float:
    """Delta_cpu = max_i U_i^cpu - min_i U_i^cpu across all nodes."""
    utils = [utilisation(n, "cpu") for n in nodes]
    return (max(utils) - min(utils)) if utils else 0.0


def score_node(
    node: NodeState,
    pod: PendingPod,
    all_nodes: List[NodeState],
    alpha_l: float,
    weights: Tuple[float, float, float],
) -> float:
    """score(i) = w1 * Delta_cpu(i) + w2 * L_bar_i + w3 * rho_i^osd"""
    w1, w2, w3 = weights
    delta_cpu = cpu_imbalance(all_nodes)
    io_demand = pod.predicted_demand.get("io", 0.0)
    l_bar = alpha_l * io_demand / node.storage_bandwidth if node.storage_bandwidth > 0 else float("inf")
    return w1 * delta_cpu + w2 * l_bar + w3 * node.osd_load


def select_node(
    pod: PendingPod,
    nodes: List[NodeState],
    alpha_l: float = 1.0,
    weights: Tuple[float, float, float] = (0.5, 0.3, 0.2),
) -> Optional[str]:
    """Select the target node i* for pod p_j, or return None (REQUEUE)
    if no node satisfies the feasibility constraint.

    weights = (w1, w2, w3) must sum to 1, matching the objective weights
    in Algorithm 2.
    """
    if abs(sum(weights) - 1.0) > 1e-6:
        raise ValueError("objective weights (w1, w2, w3) must sum to 1")

    feasible = [n for n in nodes if fits(n, pod)]
    if not feasible:
        return None  # caller should Requeue(pod)

    scored = [
        (n.node_id, score_node(n, pod, feasible, alpha_l, weights))
        for n in feasible
    ]
    scored.sort(key=lambda t: t[1])
    return scored[0][0]


if __name__ == "__main__":
    # Minimal usage example with three nodes resembling the testbed
    nodes = [
        NodeState("node-1", {"cpu": 10, "mem": 32, "io": 50000},
                  {"cpu": 6.4, "mem": 18, "io": 12000}, osd_load=0.4,
                  osd_latency_ms=1.0, storage_bandwidth=50000),
        NodeState("node-2", {"cpu": 10, "mem": 32, "io": 50000},
                  {"cpu": 5.8, "mem": 17, "io": 11000}, osd_load=0.35,
                  osd_latency_ms=1.0, storage_bandwidth=50000),
        NodeState("node-3", {"cpu": 10, "mem": 32, "io": 50000},
                  {"cpu": 5.5, "mem": 16, "io": 10500}, osd_load=0.3,
                  osd_latency_ms=1.0, storage_bandwidth=50000),
    ]
    pod = PendingPod("pod-demo", {"cpu": 0.8, "mem": 1.5, "io": 1500})
    target = select_node(pod, nodes)
    print("Selected node:", target or REQUEUE)
