/**
 * Friendly names for the generated API types. The shapes themselves come from
 * schema.d.ts, which is generated from the backend's OpenAPI document (npm run gen:api).
 * Never write API types by hand.
 */
import type { components } from './schema';

type Schemas = components['schemas'];

export type IncidentList = Schemas['IncidentList'];
export type IncidentSummary = Schemas['IncidentSummary'];
export type Severity = IncidentSummary['severity'];
export type KeySignal = Schemas['KeySignal'];
export type SystemStatus = Schemas['SystemStatus'];
export type SyncRun = Schemas['SyncRun'];
export type CollectorStatus = Schemas['CollectorStatus'];
export type ErrorResponse = Schemas['ErrorResponse'];
export type IncidentStatusFilter = 'open' | 'resolved' | 'all';
