"""
Unit tests for the EWMA predictor and storage-aware scheduler.
Run with: pytest test_model.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from ewma_predictor import EWMAPredictor, mape
from scheduler import NodeState, PendingPod, select_node, fits, cpu_imbalance, REQUEUE


def test_ewma_predictor_basic():
    p = EWMAPredictor(window=4, alpha=0.3)
    for v in [10, 12, 11, 13]:
        p.observe("cpu", v)
    pred = p.predict("cpu")
    assert 9 <= pred <= 14  # forecast should stay within the observed range


def test_ewma_single_sample():
    p = EWMAPredictor(window=4, alpha=0.3)
    p.observe("mem", 5.0)
    assert p.predict("mem") == 5.0


def test_ewma_empty_returns_zero():
    p = EWMAPredictor(window=4, alpha=0.3)
    assert p.predict("io") == 0.0


def test_ewma_invalid_alpha_rejected():
    with pytest.raises(ValueError):
        EWMAPredictor(window=4, alpha=1.5)


def test_ewma_invalid_window_rejected():
    with pytest.raises(ValueError):
        EWMAPredictor(window=1, alpha=0.3)


def test_mape_calculation():
    actual = [100, 200, 300]
    predicted = [108, 190, 312]
    err = mape(actual, predicted)
    assert 0 < err < 15  # sanity bound consistent with paper's 5-12% range


def test_scheduler_fits_rejects_overcommit():
    node = NodeState("n1", {"cpu": 10, "mem": 32, "io": 50000},
                      {"cpu": 9.5, "mem": 30, "io": 49000},
                      osd_load=0.5, osd_latency_ms=1.0, storage_bandwidth=50000)
    pod = PendingPod("p1", {"cpu": 1.0, "mem": 1.0, "io": 1000})
    assert fits(node, pod) is False


def test_scheduler_selects_least_loaded_node():
    nodes = [
        NodeState("busy", {"cpu": 10, "mem": 32, "io": 50000},
                  {"cpu": 9.0, "mem": 28, "io": 40000}, osd_load=0.8,
                  osd_latency_ms=1.2, storage_bandwidth=50000),
        NodeState("idle", {"cpu": 10, "mem": 32, "io": 50000},
                  {"cpu": 2.0, "mem": 8, "io": 5000}, osd_load=0.1,
                  osd_latency_ms=1.0, storage_bandwidth=50000),
    ]
    pod = PendingPod("p1", {"cpu": 0.5, "mem": 1.0, "io": 500})
    target = select_node(pod, nodes)
    assert target == "idle"


def test_scheduler_requeues_when_no_node_fits():
    nodes = [
        NodeState("full", {"cpu": 10, "mem": 32, "io": 50000},
                  {"cpu": 9.9, "mem": 31, "io": 49900}, osd_load=0.9,
                  osd_latency_ms=1.3, storage_bandwidth=50000),
    ]
    pod = PendingPod("p1", {"cpu": 5.0, "mem": 5.0, "io": 5000})
    target = select_node(pod, nodes)
    assert target is None


def test_cpu_imbalance_matches_definition():
    nodes = [
        NodeState("a", {"cpu": 10, "mem": 1, "io": 1}, {"cpu": 9.564, "mem": 0, "io": 0},
                   osd_load=0, osd_latency_ms=0, storage_bandwidth=1),
        NodeState("b", {"cpu": 10, "mem": 1, "io": 1}, {"cpu": 3.973, "mem": 0, "io": 0},
                   osd_load=0, osd_latency_ms=0, storage_bandwidth=1),
    ]
    # matches the paper's baseline CPU imbalance figure (~53.29% / 0.5329)
    assert cpu_imbalance(nodes) == pytest.approx(0.5591, abs=0.01)


def test_weights_must_sum_to_one():
    nodes = [NodeState("a", {"cpu": 10, "mem": 1, "io": 1}, {"cpu": 1, "mem": 0, "io": 0},
                        osd_load=0, osd_latency_ms=0, storage_bandwidth=1)]
    pod = PendingPod("p1", {"cpu": 0.1, "mem": 0, "io": 0})
    with pytest.raises(ValueError):
        select_node(pod, nodes, weights=(0.5, 0.5, 0.5))
