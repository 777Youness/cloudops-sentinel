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
export type Incident = Schemas['Incident'];
export type Fact = Schemas['Fact'];
export type TimelineEntry = Schemas['TimelineEntry'];
export type MetricSeries = Schemas['MetricSeries'];
export type MetricPoint = Schemas['MetricPoint'];
export type SignalName = MetricSeries['signal'];
export type Unit = MetricSeries['unit'];
export type Overview = Schemas['Overview'];
export type ResourceHealth = Schemas['ResourceHealth'];
export type HealthState = ResourceHealth['health'];
