# Domain model

Pydantic models in `backend/sentinel/domain/` are the source of truth. The frontend's
TypeScript types are generated from them (`npm run gen:api`). This page explains intent.

Conventions: all timestamps are timezone-aware UTC, serialized ISO 8601 with `Z`. Every
numeric value that has a unit carries a `unit` field. Missing data stays missing; it is
never represented as 0.

## Implemented (Day 1, milestone 2a)

**Observations** (`observations.py`)
- `Resource`: id, kind (`ec2_instance`), name, region, state, instance_type, credit_mode,
  tags, `data_origin` (`simulated` | `aws`).
- `MetricSeries`: resource_id, signal, unit, statistic, period_seconds, source, points
  (oldest → newest, complete periods only).
- `ObservationSnapshot`: collected_at, window, data_origin, resources, series.

**Incidents** (`incidents.py`)
- `Fact`: id (`F1`…, unique within its incident), kind (`threshold_breach`,
  `baseline_deviation`, `within_normal`, `data_gap` are produced since milestone 2a; `event`,
  `alarm_state`, `log_pattern` are reserved), statement (template-generated),
  source, resource_id, observed_at, window, rule_id, signal, value, baseline, threshold, unit.
- `TimelineEntry`: at, kind, label, fact_id.
- `Incident`: id (`INC-0001`), fingerprint (resource id), title, severity (rule-based),
  status, resource, region, data_origin, rule_ids, detection times, key_signals, facts,
  timeline, evidence (series snapshot), evidence_hash.
- `IncidentSummary`: the list view of an incident, plus `investigation_status`.

**System** (`system.py`)
- `CollectorStatus`, `SyncRun`, `SystemStatus`, `Health`.

**Errors** (`errors.py`)
- `SentinelError` subclasses with stable codes; `ErrorResponse` envelope.

## Planned (not implemented)

- Day 2 (2b, 2c): `OpsEvent` (deployment events), incident lifecycle fields, `Overview`,
  incident detail. `LogSample` and `ResourceSummary` follow with AWS mode.
- Day 3: `Investigation`, `Hypothesis` (must cite ≥ 1 existing fact ID), `NextCheck`,
  `RemediationOption` (`requires_human` always true), investigation metadata.
