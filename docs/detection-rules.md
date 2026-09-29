# Detection rules

Thresholds live in `backend/sentinel/detection/thresholds.py` and must match this page.
Severity comes only from `detection/severity.py`.

## General behaviour

- A rule evaluates the **trailing** run of breaching datapoints: the breach still ongoing
  at the latest datapoint. A breach that already ended is not active.
- A datapoint covers one whole period, so N datapoints cover N × period.
  Duration = (last − first) + period.
- A gap longer than one period breaks the run. Missing data is never treated as a breach
  and never as zero.
- Every rule reports why it did **not** trigger: `insufficient_data`, `below_threshold`
  or `too_short`.

## Implemented

| Rule | Condition | Min. duration | Severity |
|---|---|---|---|
| R-CPU-SAT | `cpu_utilization` ≥ 90% (exactly 90 counts) | 10 min | medium |

## Planned for V1 (Day 2)

| Rule | Condition | Min. duration | Guard | Severity |
|---|---|---|---|---|
| R-CPU-CREDIT | Credit balance ≤ 5 on a standard-mode T instance | 2 datapoints | T-family | medium |
| R-MEM | Memory ≥ 90% | 10 min | Metric present | medium |
| R-5XX | 5xx rate ≥ 5% (2–5% → medium) | 5 min | ≥ 50 requests | high |
| R-LAT | p95 ≥ 3× baseline and ≥ 500 ms | 5 min | ≥ 50 requests; ≥ 30 min baseline | medium |
| R-STATUS | Status check failed | 2 datapoints | — | critical |
| C-USER-IMPACT | R-LAT and R-5XX active on the same resource | — | — | at least high |

Baseline: median over [first breach − 70 min, first breach − 10 min].
