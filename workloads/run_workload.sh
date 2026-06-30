#!/usr/bin/env bash
# Workload generation scripts for the four workload classes described in
# "Workload Scenarios" section of the paper. Run each as a Kubernetes Job
# or directly inside a pod, matching the exact tool versions/parameters
# reported in the paper.
set -euo pipefail

run_compute_intensive() {
  # stress-ng v0.16.04
  stress-ng --cpu 8 --cpu-method matrixprod --timeout 30m
}

run_io_intensive() {
  # fio v3.36
  fio --name=hci-io-test \
      --rw=randread \
      --bs=4k \
      --iodepth=32 \
      --numjobs=4 \
      --size=4G \
      --runtime=1800 \
      --time_based
}

run_mixed_transactional() {
  # YCSB v0.17.0, workload A, against a Postgres pod, 1M records, 1000 ops/s
  ycsb load jdbc -P workloads/workloada \
       -p db.driver=org.postgresql.Driver \
       -p recordcount=1000000

  ycsb run jdbc -P workloads/workloada \
       -p db.driver=org.postgresql.Driver \
       -p operationcount=1000000 \
       -target 1000
}

run_transient() {
  # Python load injector: random CPU bursts, mean inter-arrival 90s.
  python3 "$(dirname "$0")/transient_load_injector.py" --mean-interarrival 90
}

case "${1:-}" in
  compute) run_compute_intensive ;;
  io) run_io_intensive ;;
  mixed) run_mixed_transactional ;;
  transient) run_transient ;;
  *)
    echo "Usage: $0 {compute|io|mixed|transient}" >&2
    exit 1
    ;;
esac
