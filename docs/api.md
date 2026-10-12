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
| GET | `/overview` | `Overview`: open counts by severity, top 5 open incidents, last sync, `data_as_of`, data origin, health of every resource in the latest snapshot | — |

## Planned

`POST /incidents/{id}/investigation` (Day 3), `GET /resources` and `GET /resources/{id}`
(Day 5).

All GET endpoints read the store through a service (`services/incidents.py`,
`services/system.py`); routes never touch the store (enforced by
`tests/test_architecture.py`).

## Error envelope

```json
{ "error": { "code": "SYNC_IN_PROGRESS", "message": "A sync is already running.", "hint": "Wait for it to finish, then retry." } }
```

Codes: `NOT_FOUND`, `VALIDATION_ERROR`, `SYNC_IN_PROGRESS`, `INTERNAL`
(later: `INVESTIGATION_IN_PROGRESS`, `LLM_NOT_CONFIGURED`). Errors from data sources
(e.g. AWS `ExpiredToken`) are reported inside `CollectorStatus`, not as HTTP errors.
