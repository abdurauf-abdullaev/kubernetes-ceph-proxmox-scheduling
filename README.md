# Predictive and Adaptive Resource Scheduling for Kubernetes–Ceph Hyperconverged Infrastructure on Proxmox VE

Reference implementation and experimental data accompanying the manuscript
*"Predictive and Adaptive Resource Scheduling for Kubernetes–Ceph
Hyperconverged Infrastructure on Proxmox VE."*

## Repository structure

```
src/
  ewma_predictor.py     Algorithm 1 — EWMA-based workload demand prediction
  scheduler.py           Algorithm 2 — adaptive, storage-aware pod placement
  controller.py           Closed-loop controller wiring (Monitoring -> Prediction
                          -> Decision-Making -> Adaptation, Figure 3)
tests/
  test_model.py           Unit tests for the predictor and scheduler
configs/kubernetes/
  predictive-scheduler-deployment.yaml   Scheduler deployment manifest
  prometheus-scrape-config.yaml          Prometheus scrape config (30s interval)
  ceph-storageclass.yaml                 Ceph CSI StorageClass / pool (3x replication)
workloads/
  run_workload.sh                 Launches the four workload classes
  transient_load_injector.py      Poisson-arrival CPU burst injector
data/
  summary_results.csv             Table 2 — baseline vs. proposed comparison
  cpu_utilization_timeseries.csv  Figure 5 — per-node CPU utilization over time
  osd_latency_timeseries.csv      Figure 7 — Ceph OSD latency over time
  prediction_accuracy.csv         EWMA predictor MAPE by resource type
```

## Algorithms

- **`ewma_predictor.py`** implements Algorithm 1: an exponentially weighted
  moving average forecaster, warm-started with the window mean, smoothing
  factor α = 0.3 (selected via grid search over α ∈ {0.1, …, 0.7}).
- **`scheduler.py`** implements Algorithm 2: feasibility filtering followed
  by a weighted scoring function over CPU imbalance, predicted storage
  latency, and Ceph OSD load, selecting the minimum-score node.
- **`controller.py`** is a reference scaffold wiring the two algorithms into
  a closed-loop controller against live Kubernetes/Prometheus/Ceph
  endpoints. The Prometheus query stubs (`fetch_node_state`,
  `fetch_recent_demand`) must be adapted to your cluster's exporter label
  schema before deployment.

## Testbed

Three-node cluster, each node: Intel Core i7-13620H (10c/16t), 32 GB DDR5,
2× 100 GB NVMe (one for Proxmox VE, one for Ceph OSD), 1 Gbps interconnect.
Proxmox VE 9.1.4, Ceph 19.2.3 (3× replication, Ceph CSI), Kubernetes
1.29.15, Prometheus scraping every 30 s. See `configs/kubernetes/` for the
corresponding manifests.

## Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Reproducing workloads

```bash
./workloads/run_workload.sh compute    # stress-ng, CPU-intensive
./workloads/run_workload.sh io         # fio, I/O-intensive
./workloads/run_workload.sh mixed      # YCSB workload A vs Postgres
./workloads/run_workload.sh transient  # Poisson-arrival CPU bursts
```

## Data availability

The `data/` directory contains the processed experimental results reported
in the manuscript (Table 2, Figures 5 and 7, and EWMA prediction-accuracy
figures). Raw Prometheus/Ceph metric exports from the 30-minute evaluation
runs are available from the corresponding author on reasonable request.

## Authors

| Name | Affiliation | Email |
|---|---|---|
| Razvan Craciunescu (corresponding author) | National University of Science and Technology POLITEHNICA Bucharest, Romania | razvan.craciunescu@upb.ro |
| Doston Khasanov | Tashkent University of Information Technologies, Uzbekistan | dhasanov0992@gmail.com |
| Abdurauf Abdullaev | Tashkent University of Information Technologies, Uzbekistan | nashfizmat@gmail.com |
| Halimjon Khujamatov | Fergana State Technical University, Uzbekistan | kh.khujamatov@tuit.uz |
| Temirbek Toshtemirov | Tashkent University of Information Technologies, Uzbekistan | t.toshtemirov@tuit.uz |
| Alisher Mamatov | Republican Scientific and Methodological Center for the Development of Education of the Republic of Uzbekistan, Uzbekistan | a.mamatov1991@gmail.com |

## Citation

If you use this code, please cite the manuscript:

> Khasanov, D., Abdullaev, A., Khujamatov, H., Toshtemirov, T., Mamatov, A.,
> Craciunescu, R. "Predictive and Adaptive Resource Scheduling for
> Kubernetes–Ceph Hyperconverged Infrastructure on Proxmox VE" (full
> citation to be updated upon publication).
