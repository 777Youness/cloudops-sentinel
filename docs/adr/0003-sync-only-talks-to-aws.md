# ADR 0003 — Only the sync collects data; read endpoints serve stored data

- Status: accepted
- Date: 2026-09-23

## Context
Some AWS read APIs are billed per request (e.g. CloudWatch GetMetricData, Logs Insights,
Cost Explorer later). Calling AWS on every page view makes cost, latency and failures
unpredictable.

## Decision
`POST /api/v1/sync` is the only path that collects telemetry. GET endpoints read the store.
A sync is manual in V1 and protected by a lock (409 when already running).

## Alternatives considered
- Live AWS calls per request: fresher data, uncountable cost, many failure surfaces.
- Background auto-sync: deferred; adds concurrency and unseen errors.

## Consequences
Every billable call happens in one place. Data is only as fresh as the last sync, so the UI
always shows when that was.
