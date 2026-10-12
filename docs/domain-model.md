# Domain model

Pydantic models in `backend/sentinel/domain/` are the source of truth. The frontend's
TypeScript types are generated from them (`npm run gen:api`). This page explains intent.

Conventions: all timestamps are timezone-aware UTC, serialized ISO 8601 with `Z`. Every
numeric value that has a unit carries a `unit` field. Missing data stays missing; it is
never represented as 0.

## Implemented (Day 1, milestones 2a, 2b, 2c)

**Observations** (`observations.py`)
- `Resource`: id, kind (`ec2_instance`), name, region, state, instance_type, credit_mode,
  tags, `data_origin` (`simulated` | `aws`).
- `MetricSeries`: resource_id, signal, unit, statistic, period_seconds, source, points
  (oldest → newest, complete periods only).
- `OpsEvent`: id (stable across syncs), resource_id, kind (`deployment`), at, label,
  source, data_origin. An observation: code never claims an event caused an incident.
- `ObservationSnapshot`: collected_at, window, data_origin, resources, series, events.

**Incidents** (`incidents.py`)
- `Fact`: id (`F1`…, unique within its incident), kind (`threshold_breach`,
  `baseline_deviation`, `within_normal`, `data_gap` are produced since milestone 2a; `event`,
  `event` since 2b; `alarm_state`, `log_pattern` are reserved), statement (template-generated),
  source, resource_id, observed_at, window, rule_id, signal, value, baseline, threshold, unit,
  event_id (for `event` facts). Facts are append-only: once stored, a fact never changes.
- `TimelineEntry`: at, kind, label, fact_id.
- `Incident`: id (`INC-0001`), fingerprint (resource id), title, severity (rule-based),
  status, resource, region, data_origin, rule_ids, detection times, key_signals, facts,
  timeline, evidence (series snapshot), evidence_hash.
- `IncidentSummary`: the list view of an incident, plus `investigation_status`.

**System** (`system.py`)
- `CollectorStatus`, `SyncRun`, `SystemStatus` (with `data_as_of`), `Health`.

**Overview** (`overview.py`, since 2c)
- `ResourceHealth`: resource id, name, instance type, state, data_origin, health
  (`ok` | `warn` | `crit` | `unknown`, decided in `detection/health.py`), open incident id
  and severity, expected signals, **missing signals** (listed, never zero), last datapoint.
- `SeverityCounts`, `Overview` (mode, data_origin, last_sync, data_as_of, open counts,
  top open incidents, resources).

**Errors** (`errors.py`)
- `SentinelError` subclasses with stable codes; `ErrorResponse` envelope.

## Planned (not implemented)

- Day 5: `LogSample` and `ResourceSummary` with AWS mode.
- Day 3: `Investigation`, `Hypothesis` (must cite ≥ 1 existing fact ID), `NextCheck`,
  `RemediationOption` (`requires_human` always true), investigation metadata.
