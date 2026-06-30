"""
Closed-loop adaptive controller (Monitoring -> Prediction -> Decision-Making
-> Adaptation), as described in the "Closed-Loop Adaptive Control" section
of the paper and illustrated in Figure 3.

This is a REFERENCE implementation showing how the EWMAPredictor
(ewma_predictor.py) and the storage-aware scheduler (scheduler.py) are
wired together against live Kubernetes / Prometheus / Ceph endpoints. It
requires cluster credentials and the `kubernetes` and
`prometheus-api-client` Python packages to run against a real cluster
(`pip install kubernetes prometheus-api-client`):

    python controller.py --kubeconfig ~/.kube/config \
        --prometheus-url http://prometheus.monitoring.svc:9090 \
        --interval 30

It is intentionally dependency-light and uses the official client
libraries' standard query/list/bind primitives so it can be adapted to a
specific cluster's metric names and label schema. Replace the
`fetch_demand_for_pod` and `fetch_node_state` stub implementations with
the Prometheus queries (PromQL) appropriate to your `kube-state-metrics`,
`node-exporter` and `ceph-exporter` setup before deploying.
"""

from __future__ import annotations
import argparse
import logging
import time
from typing import Dict, List

from ewma_predictor import EWMAPredictor, RESOURCE_TYPES
from scheduler import NodeState, PendingPod, select_node, REQUEUE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("controller")


def fetch_node_state(node_id: str, prometheus_url: str) -> NodeState:
    """Monitoring stage: pull current capacity/usage/Ceph OSD metrics for a
    node from Prometheus. Replace the PromQL queries below with the ones
    matching your exporters."""
    raise NotImplementedError(
        "Wire this up to your Prometheus instance, e.g.:\n"
        "  cpu_capacity = query(prometheus_url, 'kube_node_status_capacity{resource=\"cpu\",node=\"%s\"}' % node_id)\n"
        "  cpu_usage    = query(prometheus_url, 'node_namespace_pod:container_cpu_usage_seconds_total:sum_rate{node=\"%s\"}' % node_id)\n"
        "  osd_load     = query(prometheus_url, 'ceph_osd_op_r{instance=\"%s\"}' % node_id)\n"
        "  osd_latency  = query(prometheus_url, 'ceph_osd_apply_latency_ms{instance=\"%s\"}' % node_id)\n"
    )


def fetch_recent_demand(pod_id: str, resource_type: str, prometheus_url: str) -> float:
    """Monitoring stage: pull the most recent observed demand sample for a
    pending/running pod's resource type."""
    raise NotImplementedError("Wire this up to your Prometheus instance.")


class ClosedLoopController:
    """Ties together the four stages of Figure 3:
    Monitoring -> Prediction -> Decision-Making -> Adaptation.
    """

    def __init__(self, node_ids: List[str], prometheus_url: str,
                 window: int = 6, alpha: float = 0.3,
                 weights=(0.5, 0.3, 0.2), alpha_l: float = 1.0):
        self.node_ids = node_ids
        self.prometheus_url = prometheus_url
        self.predictors: Dict[str, EWMAPredictor] = {}
        self.weights = weights
        self.alpha_l = alpha_l
        self.window = window
        self.alpha = alpha

    def _predictor_for(self, pod_id: str) -> EWMAPredictor:
        if pod_id not in self.predictors:
            self.predictors[pod_id] = EWMAPredictor(window=self.window, alpha=self.alpha)
        return self.predictors[pod_id]

    def monitor_and_predict(self, pod_id: str) -> Dict[str, float]:
        """Monitoring + Prediction stages for a single pending pod."""
        predictor = self._predictor_for(pod_id)
        for resource_type in RESOURCE_TYPES:
            sample = fetch_recent_demand(pod_id, resource_type, self.prometheus_url)
            predictor.observe(resource_type, sample)
        return predictor.predict_all()

    def decide(self, pod_id: str, predicted_demand: Dict[str, float]) -> str:
        """Decision-Making stage: select target node via Algorithm 2."""
        nodes = [fetch_node_state(n, self.prometheus_url) for n in self.node_ids]
        pod = PendingPod(pod_id, predicted_demand)
        target = select_node(pod, nodes, alpha_l=self.alpha_l, weights=self.weights)
        return target or REQUEUE

    def adapt(self, pod_id: str, target_node: str) -> None:
        """Adaptation stage: bind the pod via the Kubernetes Bind API, or
        requeue. Requires the `kubernetes` client package and an
        authenticated client; left as an integration point."""
        if target_node == REQUEUE:
            log.info("pod=%s requeued (no feasible node)", pod_id)
            return
        log.info("pod=%s -> binding to node=%s", pod_id, target_node)
        # kubernetes.client.CoreV1Api().create_namespaced_binding(...)

    def run_once(self, pending_pod_ids: List[str]) -> None:
        for pod_id in pending_pod_ids:
            predicted = self.monitor_and_predict(pod_id)
            target = self.decide(pod_id, predicted)
            self.adapt(pod_id, target)

    def run_forever(self, interval_s: int, pending_pod_provider) -> None:
        """pending_pod_provider: callable returning the current list of
        pending pod IDs (e.g. via a Kubernetes watch on Pending pods)."""
        while True:
            self.run_once(pending_pod_provider())
            time.sleep(interval_s)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", required=False, default="~/.kube/config")
    parser.add_argument("--prometheus-url", required=True)
    parser.add_argument("--nodes", nargs="+", required=True, help="node IDs in the cluster")
    parser.add_argument("--interval", type=int, default=30, help="scrape interval in seconds")
    args = parser.parse_args()

    controller = ClosedLoopController(node_ids=args.nodes, prometheus_url=args.prometheus_url)
    log.info("Starting closed-loop controller on nodes=%s interval=%ss", args.nodes, args.interval)
    # controller.run_forever(args.interval, pending_pod_provider=<watch implementation>)
    log.info("This is a reference scaffold — wire pending_pod_provider and Prometheus queries before deploying.")


if __name__ == "__main__":
    main()
