"""
EWMA-based workload demand prediction.

Implements Algorithm 1 ("EWMA-based workload demand prediction") from:
"Predictive and Adaptive Resource Scheduling for Kubernetes-Ceph
Hyperconverged Infrastructure on Proxmox VE".

Given a historical window of observed demand values for a resource type
(cpu, mem, io), produces a one-step-ahead forecast d_hat(t+1) using an
exponentially weighted moving average warm-started with the window mean.

The optimal smoothing factor alpha = 0.3 was identified in the paper via a
grid search over alpha in {0.1, 0.2, ..., 0.7}, minimising aggregate MAPE
on CPU (8.4%), memory (5.1%) and I/O (12.3%) demand.
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List


DEFAULT_ALPHA = 0.3
RESOURCE_TYPES = ("cpu", "mem", "io")


@dataclass
class EWMAPredictor:
    """Per-workload EWMA demand predictor for cpu/mem/io resource types.

    Parameters
    ----------
    window: int
        Historical window length W (W >= 2), as in Algorithm 1.
    alpha: float
        Smoothing factor in (0, 1]. Defaults to the empirically optimal
        value (alpha = 0.3) reported in the paper.
    """

    window: int = 6
    alpha: float = DEFAULT_ALPHA
    _history: Dict[str, Deque[float]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.window < 2:
            raise ValueError("window length W must be >= 2")
        if not (0 < self.alpha <= 1):
            raise ValueError("alpha must be in (0, 1]")
        self._history = {k: deque(maxlen=self.window) for k in RESOURCE_TYPES}

    def observe(self, resource_type: str, value: float) -> None:
        """Record a new observed demand sample d_j^k(t)."""
        if resource_type not in RESOURCE_TYPES:
            raise ValueError(f"unknown resource type: {resource_type}")
        self._history[resource_type].append(value)

    def predict(self, resource_type: str) -> float:
        """Return the one-step-ahead forecast d_hat_j^k(t+1).

        Implements Algorithm 1: warm-start with the window mean, then
        recursively apply EWMA smoothing across the window.
        """
        hist: List[float] = list(self._history[resource_type])
        if not hist:
            return 0.0
        if len(hist) == 1:
            return hist[0]

        # warm-start with window mean
        d_hat = sum(hist) / len(hist)

        # recursive EWMA update across the window (excludes last sample,
        # which is folded in as the final one-step-ahead update below)
        for sample in hist[1:-1]:
            d_hat = self.alpha * sample + (1 - self.alpha) * d_hat

        # one-step-ahead prediction using the most recent observation
        d_hat = self.alpha * hist[-1] + (1 - self.alpha) * d_hat
        return d_hat

    def predict_all(self) -> Dict[str, float]:
        """Return the predicted demand vector d_hat_j(t+1) for all resource types."""
        return {k: self.predict(k) for k in RESOURCE_TYPES}


def mape(actual: List[float], predicted: List[float]) -> float:
    """Mean Absolute Percentage Error, used to validate predictor accuracy."""
    if len(actual) != len(predicted) or not actual:
        raise ValueError("actual and predicted must be same non-zero length")
    errors = [
        abs((a - p) / a) for a, p in zip(actual, predicted) if a != 0
    ]
    return 100.0 * sum(errors) / len(errors) if errors else 0.0


if __name__ == "__main__":
    # Minimal smoke test / usage example
    predictor = EWMAPredictor(window=6, alpha=0.3)
    sample_cpu_series = [0.42, 0.45, 0.41, 0.50, 0.48, 0.53]
    for v in sample_cpu_series:
        predictor.observe("cpu", v)
    print("Predicted next-interval CPU demand:", predictor.predict("cpu"))
