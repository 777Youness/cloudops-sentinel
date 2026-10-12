import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

import type { Overview } from '../../api/types';
import { createQueryClient } from '../../app/queryClient';
import { OverviewPage } from './OverviewPage';

const NOW = new Date().toISOString();

const SYNC = {
  id: 'SYNC-0001',
  started_at: NOW,
  finished_at: NOW,
  status: 'success' as const,
  collectors: [{ name: 'simulator' as const, state: 'ok' as const, last_success_at: NOW }],
  resources_evaluated: 3,
  rules_evaluated: 7,
  incidents_opened: 1,
  incidents_updated: 0,
  incidents_resolved: 0,
};

const ALL_SIGNALS = [
  'cpu_utilization',
  'cpu_credit_balance',
  'memory_used',
  'status_check_failed',
  'request_rate',
  'error_rate_5xx',
  'latency_p95',
] as const;

function resource(id: string, health: Overview['resources'][number]['health'], extra = {}) {
  return {
    resource_id: id,
    resource_name: `${id}-name`,
    instance_type: 't3.micro',
    state: 'running' as const,
    data_origin: 'simulated' as const,
    health,
    open_incident_id: null,
    open_incident_severity: null,
    signals_expected: [...ALL_SIGNALS],
    signals_missing: [],
    last_datapoint_at: NOW,
    ...extra,
  };
}

const OVERVIEW: Overview = {
  mode: 'local',
  data_origin: 'simulated',
  last_sync: SYNC,
  data_as_of: NOW,
  open_total: 1,
  open_by_severity: { critical: 1, high: 0, medium: 0, low: 0 },
  top_open_incidents: [
    {
      id: 'INC-0007',
      title: 'Status check failing on sim-batch-01',
      severity: 'critical',
      status: 'open',
      resource_id: 'sim-batch',
      resource_name: 'sim-batch-01',
      data_origin: 'simulated',
      first_detected_at: NOW,
      resolved_at: null,
      key_signals: [{ signal: 'status_check_failed', value: 1, unit: 'count' }],
      investigation_status: 'not_run',
    },
  ],
  resources: [
    resource('sim-batch', 'crit', {
      open_incident_id: 'INC-0007',
      open_incident_severity: 'critical',
    }),
    resource('sim-api', 'ok', { signals_missing: ['memory_used'] }),
    resource('sim-empty', 'unknown', {
      signals_missing: [...ALL_SIGNALS],
      last_datapoint_at: null,
    }),
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function mockFetch(handler: () => Response | Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(handler));
}

function renderPage() {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('OverviewPage', () => {
  it('counts open incidents by severity, with text labels', async () => {
    mockFetch(() => json(OVERVIEW));
    renderPage();
    const summary = await screen.findByLabelText('Open incidents by severity');
    expect(within(summary).getByText('Critical').closest('div')).toHaveTextContent('Critical1');
    expect(within(summary).getByText('High').closest('div')).toHaveTextContent('High0');
  });

  it('links the most important open incidents to their workspace', async () => {
    mockFetch(() => json(OVERVIEW));
    renderPage();
    const link = await screen.findByRole('link', { name: 'Status check failing on sim-batch-01' });
    expect(link).toHaveAttribute('href', '/incidents/INC-0007');
  });

  it('shows health as text, never by color alone, and names missing signals', async () => {
    mockFetch(() => json(OVERVIEW));
    renderPage();
    const rows = (await screen.findAllByRole('row')).map((r) => r.textContent ?? '');
    expect(rows.find((r) => r.includes('sim-batch-name'))).toContain('Failing');
    const api = rows.find((r) => r.includes('sim-api-name'));
    expect(api).toContain('Healthy');
    expect(api).toContain('6 of 7');
    expect(api).toContain('Missing: Memory utilization');
    const empty = rows.find((r) => r.includes('sim-empty-name'));
    expect(empty).toContain('No data');
    expect(empty).toContain('0 of 7');
    expect(screen.getByText('2 resources with missing signals')).toBeInTheDocument();
  });

  it('shows where the data comes from and when it was collected', async () => {
    mockFetch(() => json(OVERVIEW));
    renderPage();
    const trust = await screen.findByRole('region', { name: 'Data trust' });
    expect(within(trust).getByText('Simulated')).toBeInTheDocument();
    expect(within(trust).getByText('simulator')).toBeInTheDocument();
    expect(within(trust).getByText('1 opened, 0 updated, 0 resolved')).toBeInTheDocument();
    expect(within(trust).queryByText('Stale')).toBeNull();
  });

  it('marks data from an old successful sync as stale', async () => {
    const old = new Date(Date.now() - 60 * 60_000).toISOString();
    mockFetch(() => json({ ...OVERVIEW, data_as_of: old }));
    renderPage();
    const trust = await screen.findByRole('region', { name: 'Data trust' });
    expect(within(trust).getByText('Stale')).toBeInTheDocument();
  });

  it('says plainly when nothing is open', async () => {
    mockFetch(() =>
      json({
        ...OVERVIEW,
        open_total: 0,
        open_by_severity: { critical: 0, high: 0, medium: 0, low: 0 },
        top_open_incidents: [],
      }),
    );
    renderPage();
    expect(await screen.findByText('No open incidents.')).toBeInTheDocument();
    expect(
      screen.getByText('3 resources and 7 rules evaluated in the last sync.'),
    ).toBeInTheDocument();
  });

  it('invites a first sync before any data exists', async () => {
    mockFetch(() =>
      json({
        ...OVERVIEW,
        data_origin: null,
        last_sync: null,
        data_as_of: null,
        open_total: 0,
        open_by_severity: { critical: 0, high: 0, medium: 0, low: 0 },
        top_open_incidents: [],
        resources: [],
      }),
    );
    renderPage();
    expect(await screen.findByText('No data yet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeInTheDocument();
  });

  it('explains an unreachable backend', async () => {
    mockFetch(() => Promise.reject(new TypeError('Failed to fetch')));
    renderPage();
    expect(await screen.findByText(/Sentinel API unreachable/)).toBeInTheDocument();
  });
});
