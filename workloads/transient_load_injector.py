#!/usr/bin/env python3
"""
Transient load injector used for the "Transient" workload class in the
paper: random CPU bursts simulating unpredictable web-traffic spikes,
with a mean inter-arrival time of 90 seconds.

Inter-arrival times are drawn from an exponential distribution (Poisson
arrival process), and each burst runs a short CPU-bound computation for a
random duration.
"""
import argparse
import multiprocessing
import random
import time


def cpu_burn(duration_s: float) -> None:
    end = time.time() + duration_s
    x = 0.0001
    while time.time() < end:
        x = (x * 1.0000001) % 1e6


def run(mean_interarrival_s: float, burst_duration_range=(2, 10),
        total_runtime_s: float = 1800) -> None:
    start = time.time()
    while time.time() - start < total_runtime_s:
        wait = random.expovariate(1.0 / mean_interarrival_s)
        time.sleep(wait)
        duration = random.uniform(*burst_duration_range)
        p = multiprocessing.Process(target=cpu_burn, args=(duration,))
        p.start()
        print(f"[transient-load] burst started, duration={duration:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mean-interarrival", type=float, default=90.0)
    parser.add_argument("--runtime", type=float, default=1800.0,
                         help="total injector runtime in seconds")
    args = parser.parse_args()
    run(args.mean_interarrival, total_runtime_s=args.runtime)
