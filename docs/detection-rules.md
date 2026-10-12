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
- Every rule reports why it did **not** trigger:

| Reason | Meaning | Becomes |
|---|---|---|
| `below_threshold` | The latest datapoint is not breaching | `within_normal` fact |
| `too_short` | Breaching now, not for long enough yet | nothing |
| `insufficient_data` | Signal missing, or too little history (e.g. no latency baseline) | `data_gap` fact |
| `insufficient_traffic` | Fewer than 50 requests during the breach | `data_gap` fact |
| `not_applicable` | Rule does not apply to this resource (e.g. not a T instance) | nothing |

Facts are only attached to an incident, so `within_normal` and `data_gap` facts appear only
on resources where at least one rule triggered. They tell the reader (and, from Day 3, the
LLM) what was checked and found normal, and what could not be checked.

## Rules

| Rule | Condition | Min. duration | Guard | Severity |
|---|---|---|---|---|
| R-CPU-SAT | `cpu_utilization` ≥ 90% | 10 min | — | medium |
| R-CPU-CREDIT | `cpu_credit_balance` ≤ 5 | 2 datapoints | T-family and `credit_mode = standard`, else `not_applicable` | medium |
| R-MEM | `memory_used` ≥ 90% | 10 min | Metric present (CloudWatch agent), else `insufficient_data` | medium |
| R-STATUS | `status_check_failed` ≥ 1 | 2 datapoints | — | critical |
| R-5XX | `error_rate_5xx` ≥ 2% | 5 min | ≥ 50 requests during the breach | high if ≥ 5% has itself lasted 5 min, else medium |
| R-LAT | `latency_p95` ≥ max(500 ms, 3 × baseline) | 5 min | ≥ 50 requests; ≥ 30 min of baseline data | medium |
| C-USER-IMPACT | R-LAT and R-5XX both active on the same resource | — | — | high |

Every threshold is inclusive ("exactly 90%" breaches; "exactly 5 credits" breaches).

### R-5XX tiers

The rule triggers on the ≥ 2% run. If the trailing ≥ 5% run has also lasted 5 minutes (and
passes the traffic guard on its own window), the result is the full tier and the fact
reports the ≥ 5% run; otherwise it is the lower tier. `RuleResult.lower_tier` carries this;
`severity.py` maps it to medium.

### R-LAT baseline

The baseline depends on when the breach started, and the breach depends on the baseline.
The rule breaks the circle in three steps:

1. Find the trailing run at the absolute floor (≥ 500 ms). If it is absent or shorter than
   5 minutes, stop (`below_threshold` / `too_short`).
2. Baseline = median of the datapoints in [run start − 70 min, run start − 10 min). The
   10-minute gap keeps the slow-down's ramp out of the baseline. Fewer than 30 minutes of
   data there → `insufficient_data`.
3. The breach is the trailing run at max(500 ms, 3 × baseline). It is a sub-run of step 1.

### Request count

Requests during a breach = sum of `request_rate` (per minute) × period minutes over the
breach window. If there is no request datapoint in that window the count is unknown, not
zero: the result is `insufficient_data` on `request_rate`.

## Incidents

One incident per resource. Every rule that triggers on the resource in the same evaluation
goes into it: `rule_ids` in the order above, severity = highest in the matrix, title from
the highest-severity rule (the derived rule wins ties). C-USER-IMPACT has no fact of its
own; the R-5XX and R-LAT facts are its evidence.

When an incident opens, its facts are ordered: breaches (`threshold_breach`, or
`baseline_deviation` for R-LAT), then `event` (deployments in the evidence window), then
`within_normal`, then `data_gap`. IDs are `F1`, `F2`, … in that order. Later facts (merged
rules, new events, resolution) are appended with the next ids.

## Resolution

An open incident resolves when no rule triggers on its resource and **every** signal-based
rule in its `rule_ids` has been clean for at least 10 minutes:

| Rule | Clean means |
|---|---|
| R-CPU-SAT, R-MEM | below 90% |
| R-CPU-CREDIT | above 5 credits |
| R-STATUS | below 1 (passing) |
| R-5XX | below 2% (the lower tier, not 5%) |
| R-LAT | below the threshold recorded in its fact (max(500 ms, 3 × baseline) at detection) |
| C-USER-IMPACT | derived: clears when R-5XX and R-LAT do |

Clean runs follow the same rules as breach runs: trailing, a gap breaks them, and missing
data is never clean. While open, severity never drops; it only rises when a more severe
rule triggers.
