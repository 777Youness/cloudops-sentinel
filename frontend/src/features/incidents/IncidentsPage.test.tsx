import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

import { createQueryClient } from '../../app/queryClient';
import { IncidentsPage } from './IncidentsPage';

const SYSTEM_NEVER_SYNCED = {
  version: 'test',
  contract_version: '1',
  mode: 'local',
  environment: 'dev',
  region: 'eu-west-3',
  llm: { provider: null, model: null, configured: false },
  last_sync: null,
};

const INCIDENTS_ONE = {
  total: 1,
  items: [
    {
      id: 'INC-0001',
      title: 'Sustained CPU saturation on sim-api-01',
      severity: 'medium',
      status: 'open',
      resource_id: 'sim-cpu-saturation',
      resource_name: 'sim-api-01',
      data_origin: 'simulated',
      first_detected_at: '2026-09-23T14:05:00Z',
      resolved_at: null,
      key_signals: [{ signal: 'cpu_utilization', value: 97.3, unit: 'percent' }],
      investigation_status: 'not_run',
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function mockFetch(routes: Record<string, () => Response | Promise<Response>>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const path = Object.keys(routes).find((p) => url.startsWith(p));
      if (!path) throw new Error(`unmocked ${url}`);
      return routes[path]!();
    }),
  );
}

function renderPage() {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/incidents']}>
        <IncidentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('IncidentsPage', () => {
  it('lists incidents with a text severity label', async () => {
    mockFetch({
      '/api/v1/incidents': () => json(INCIDENTS_ONE),
      '/api/v1/system': () => json(SYSTEM_NEVER_SYNCED),
    });
    renderPage();
    expect(await screen.findByText('Sustained CPU saturation on sim-api-01')).toBeInTheDocument();
    expect(screen.getByText('Medium')).toBeInTheDocument();
    expect(screen.getByText('97.3%')).toBeInTheDocument();
  });

  it('invites a first sync when nothing has been collected', async () => {
    mockFetch({
      '/api/v1/incidents': () => json({ items: [], total: 0 }),
      '/api/v1/system': () => json(SYSTEM_NEVER_SYNCED),
    });
    renderPage();
    expect(await screen.findByText('No data yet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeInTheDocument();
  });

  it('explains an unreachable backend instead of showing a blank page', async () => {
    mockFetch({
      '/api/v1/incidents': () => Promise.reject(new TypeError('Failed to fetch')),
      '/api/v1/system': () => Promise.reject(new TypeError('Failed to fetch')),
    });
    renderPage();
    expect(await screen.findByText(/Sentinel API unreachable/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
