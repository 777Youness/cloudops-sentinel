"""Detection thresholds. Must match docs/detection-rules.md."""

from datetime import timedelta

# R-CPU-SAT: sustained CPU saturation
CPU_SAT_THRESHOLD_PERCENT = 90.0  # a datapoint at exactly 90.0 counts as a breach (>=)
CPU_SAT_MIN_DURATION = timedelta(minutes=10)

# How much history before the breach is kept as evidence with the incident.
EVIDENCE_LOOKBACK = timedelta(minutes=60)
