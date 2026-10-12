# API

Base path `/api/v1`. The OpenAPI document (`/openapi.json`, also committed at
`frontend/src/api/openapi.json`) is the detailed contract. Interactive docs: `/docs`.

## Endpoints

| Method | Path | Returns | Errors |
|---|---|---|---|
| GET | `/health` | `{"status": "ok"}` (liveness, touches nothing) | — |
| GET | `/system` | `SystemStatus` (mode, environment, region, LLM status, last sync, `data_as_of` = end of the last successful sync) | — |
| POST | `/sync` | `SyncRun` with `incidents_opened`, `incidents_updated`, `incidents_resolved`. 200 even if the sync failed: read `status`. | 409 `SYNC_IN_PROGRESS` |
| GET | `/incidents?status=open\|resolved\|all` | `{items: IncidentSummary[], total}`, severity then recency | 422 `VALIDATION_ERROR` |
| GET | `/incidents/{id}` | `Incident`: everything stored for it (facts, timeline, evidence series, rule ids, evidence hash), verbatim | 404 `NOT_FOUND` |
| POST | `/incidents/{id}/investigation` | `InvestigationResult`. **The only endpoint that calls an LLM provider.** 200 even when the run failed (provider error, or the reply was rejected twice): read `investigation.status` and `investigation.error` | 404 `NOT_FOUND`, 409 `INVESTIGATION_IN_PROGRESS`, 503 `LLM_NOT_CONFIGURED` |
| GET | `/incidents/{id}/investigation` | `InvestigationResult` for the latest saved run, with `outdated` (incident evidence hash differs) and `runs`. Never calls a provider | 404 `NOT_FOUND` (unknown incident, or never investigated) |
| GET | `/overview` | `Overview`: open counts by severity, top 5 open incidents, last sync, `data_as_of`, data origin, health of every resource in the latest snapshot (failing, degraded, no data, healthy) | — |

## Planned

`GET /resources` and `GET /resources/{id}` (Day 5).

All GET endpoints read the store through a service (`services/incidents.py`,
`services/system.py`); routes never touch the store (enforced by
`tests/test_architecture.py`).

## Error envelope

```json
{ "error": { "code": "SYNC_IN_PROGRESS", "message": "A sync is already running.", "hint": "Wait for it to finish, then retry." } }
```

Codes: `NOT_FOUND`, `VALIDATION_ERROR`, `SYNC_IN_PROGRESS`, `INVESTIGATION_IN_PROGRESS`,
`LLM_NOT_CONFIGURED`, `INTERNAL`. Errors from data sources
(e.g. AWS `ExpiredToken`) are reported inside `CollectorStatus`, not as HTTP errors.

## Investigation contract notes (Day 3)

- `IncidentSummary.investigation_status`: `not_run` | `completed` | `failed` | `outdated`
  (completed, but the incident's evidence hash has changed since) | `unavailable` (reserved).
- `SystemStatus.llm`: `{provider, model, configured}`. Default: `mock`, `mock-rules-v1`,
  configured. A selected but incomplete real provider reports `configured: false`.
- Failed runs are saved and returned like completed ones; `error.code` is a provider code
  (`timeout`, `unreachable`, `auth`, `rate_limited`, `provider_error`, `bad_response`) or a
  validator reason (`not_json`, `forbidden_field`, `remediation_not_human`,
  `schema_invalid`, `no_hypotheses`, `missing_citation`, `unknown_fact`, `duplicate_id`,
  `text_too_long`, `command_in_text`).
