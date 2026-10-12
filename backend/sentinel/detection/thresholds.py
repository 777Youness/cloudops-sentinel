"""Detection thresholds. Must match docs/detection-rules.md."""

from datetime import timedelta

# R-CPU-SAT: sustained CPU saturation
CPU_SAT_THRESHOLD_PERCENT = 90.0  # a datapoint at exactly 90.0 counts as a breach (>=)
CPU_SAT_MIN_DURATION = timedelta(minutes=10)

# R-CPU-CREDIT: CPU credits exhausted on a standard-mode burstable (T-family) instance
CPU_CREDIT_THRESHOLD = 5.0  # a datapoint at exactly 5.0 credits counts as a breach (<=)
CPU_CREDIT_MIN_DATAPOINTS = 2

# R-MEM: sustained memory pressure (CloudWatch agent metric mem_used_percent)
MEM_THRESHOLD_PERCENT = 90.0
MEM_MIN_DURATION = timedelta(minutes=10)

# R-STATUS: EC2 status check failing
STATUS_FAILED_THRESHOLD = 1.0  # StatusCheckFailed is 0 or 1 per period
STATUS_MIN_DATAPOINTS = 2

# R-5XX: elevated server error rate. Two tiers: >= 5% is high, 2-5% is medium.
ERR_5XX_HIGH_PERCENT = 5.0
ERR_5XX_MEDIUM_PERCENT = 2.0
ERR_5XX_MIN_DURATION = timedelta(minutes=5)

# R-LAT: p95 latency far above its own recent baseline
LAT_MIN_MS = 500.0
LAT_BASELINE_MULTIPLIER = 3.0
LAT_MIN_DURATION = timedelta(minutes=5)
# Baseline window, relative to the first breaching datapoint: [start - 70 min, start - 10 min)
LAT_BASELINE_FROM = timedelta(minutes=70)
LAT_BASELINE_TO = timedelta(minutes=10)
LAT_MIN_BASELINE_DATA = timedelta(minutes=30)

# R-5XX and R-LAT: below this many requests during the breach, a percentage means little.
MIN_REQUESTS = 50

# Resolution: every condition of an open incident must be clean (data present, not
# breaching, no gap) for at least this long.
RESOLVE_CLEAN_DURATION = timedelta(minutes=10)

# How much history before the breach is kept as evidence with the incident.
EVIDENCE_LOOKBACK = timedelta(minutes=60)
