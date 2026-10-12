/**
 * The only module that calls fetch. Every failure becomes an ApiError with one of two kinds:
 *
 *  - "unreachable": the backend could not be reached (not running, proxy error, network).
 *  - "http": the backend answered with the standard error envelope
 *            {"error": {"code", "message", "hint"}}.
 */
import type {
  ErrorResponse,
  Incident,
  IncidentList,
  IncidentStatusFilter,
  InvestigationResult,
  Overview,
  SyncRun,
  SystemStatus,
} from './types';

export const API_BASE = '/api/v1';
export const BACKEND_ADDRESS = '127.0.0.1:8000';

export class ApiError extends Error {
  readonly kind: 'unreachable' | 'http';
  readonly status: number | null;
  readonly code: string | null;
  readonly hint: string | null;

  constructor(
    kind: 'unreachable' | 'http',
    message: string,
    opts: { status?: number; code?: string; hint?: string | null } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = opts.status ?? null;
    this.code = opts.code ?? null;
    this.hint = opts.hint ?? null;
  }
}

function unreachable(): ApiError {
  return new ApiError('unreachable', `Sentinel API unreachable at ${BACKEND_ADDRESS}.`, {
    hint: 'Is the backend running? Start it with: uv run uvicorn sentinel.main:app --reload',
  });
}

async function request<T>(method: 'GET' | 'POST', path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { Accept: 'application/json' },
    });
  } catch {
    throw unreachable();
  }

  const isJson = response.headers.get('content-type')?.includes('application/json') ?? false;
  if (response.ok && isJson) {
    return (await response.json()) as T;
  }
  if (!isJson) {
    // A non-JSON 5xx comes from the dev proxy or a gateway, not from Sentinel itself.
    if (response.status >= 500) throw unreachable();
    throw new ApiError('http', `Unexpected response (HTTP ${response.status}).`, {
      status: response.status,
    });
  }
  const body = (await response.json()) as Partial<ErrorResponse>;
  const error = body.error;
  throw new ApiError('http', error?.message ?? `HTTP ${response.status}`, {
    status: response.status,
    code: error?.code ?? 'UNKNOWN',
    hint: error?.hint ?? null,
  });
}

export const api = {
  system: () => request<SystemStatus>('GET', '/system'),
  sync: () => request<SyncRun>('POST', '/sync'),
  incidents: (status: IncidentStatusFilter) =>
    request<IncidentList>('GET', `/incidents?status=${encodeURIComponent(status)}`),
  incident: (id: string) => request<Incident>('GET', `/incidents/${encodeURIComponent(id)}`),
  overview: () => request<Overview>('GET', '/overview'),
  // GET never calls a provider; POST is the only call that does (and may take a while).
  investigation: (id: string) =>
    request<InvestigationResult>('GET', `/incidents/${encodeURIComponent(id)}/investigation`),
  runInvestigation: (id: string) =>
    request<InvestigationResult>('POST', `/incidents/${encodeURIComponent(id)}/investigation`),
};
