import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';

import type { Incident } from '../../api/types';
import { createQueryClient } from '../../app/queryClient';
import { WorkspacePage } from './WorkspacePage';

const T0 = Date.UTC(2026, 9, 12, 13, 0);
const iso = (minutes: number) => new Date(T0 + minutes * 60_000).toISOString();

function points(from: number, to: number, value: (m: number) => number, skip: number[] = []) {
  const out = [];
  for (let m = from; m <= to; m++) if (!skip.includes(m)) out.push({ t: iso(m), v: value(m) });
  return out;
}

const INCIDENT: Incident = {
  id: 'INC-0004',
  fingerprint: 'sim-escalation',
  title: 'Sustained CPU saturation on sim-api-01',
  severity: 'medium',
  status: 'open',
  resource_id: 'sim-cpu-saturation',
  resource_name: 'sim-api-01',
  region: 'eu-west-3',
  data_origin: 'simulated',
  rule_ids: ['R-CPU-SAT'],
  first_detected_at: iso(60),
  last_updated_at: iso(60),
  resolved_at: null,
  key_signals: [{ signal: 'cpu_utilization', value: 97, unit: 'percent' }],
  facts: [
    {
      id: 'F1',
      kind: 'threshold_breach',
      statement: 'CPU utilization at or above 90% for 21 min since 13:39 UTC (peak 100.0%)',
      source: 'simulator',
      resource_id: 'sim-cpu-saturation',
      observed_at: iso(60),
      window: { start: iso(39), end: iso(60) },
      rule_id: 'R-CPU-SAT',
      signal: 'cpu_utilization',
      value: 100,
      baseline: null,
      threshold: 90,
      unit: 'percent',
      event_id: null,
    },
    {
      id: 'F2',
      kind: 'event',
      statement: 'Deployment at 13:35 UTC: Deploy v1.4.2',
      source: 'simulator',
      resource_id: 'sim-cpu-saturation',
      observed_at: iso(35),
      window: null,
      rule_id: null,
      signal: null,
      value: null,
      baseline: null,
      threshold: null,
      unit: null,
      event_id: 'x:deploy',
    },
    {
      id: 'F3',
      kind: 'within_normal',
      statement: 'p95 latency below 500 ms (latest 175 ms)',
      source: 'simulator',
      resource_id: 'sim-cpu-saturation',
      observed_at: iso(59),
      window: null,
      rule_id: 'R-LAT',
      signal: 'latency_p95',
      value: 175,
      baseline: null,
      threshold: 500,
      unit: 'ms',
      event_id: null,
    },
    {
      id: 'F4',
      kind: 'data_gap',
      statement: 'Not enough memory utilization data to evaluate R-MEM',
      source: 'detection',
      resource_id: 'sim-cpu-saturation',
      observed_at: iso(60),
      window: { start: iso(-120), end: iso(60) },
      rule_id: 'R-MEM',
      signal: 'memory_used',
      value: null,
      baseline: null,
      threshold: null,
      unit: null,
      event_id: null,
    },
  ],
  timeline: [
    { at: iso(35), kind: 'event', label: 'Deployment: Deploy v1.4.2', fact_id: 'F2' },
    { at: iso(39), kind: 'breach_start', label: 'CPU utilization reached 90%', fact_id: 'F1' },
    {
      at: iso(60),
      kind: 'incident_opened',
      label: 'Incident opened by R-CPU-SAT, severity medium',
      fact_id: null,
    },
  ],
  evidence: {
    series: [
      {
        resource_id: 'sim-cpu-saturation',
        signal: 'cpu_utilization',
        unit: 'percent',
        statistic: 'Average',
        period_seconds: 60,
        source: 'simulator',
        // two datapoints missing at minutes 20 and 21
        points: points(0, 59, (m) => (m >= 39 ? 97 : 40), [20, 21]),
      },
      {
        resource_id: 'sim-cpu-saturation',
        signal: 'latency_p95',
        unit: 'ms',
        statistic: 'p95',
        period_seconds: 60,
        source: 'simulator',
        points: points(0, 59, () => 175),
      },
    ],
  },
  evidence_hash: 'sha256:0123456789abcdef',
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

function renderAt(path: string) {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/incidents/:id" element={<WorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('WorkspacePage', () => {
  it('shows the header with severity as text and the incident metadata', async () => {
    mockFetch(() => json(INCIDENT));
    renderAt('/incidents/INC-0004');
    expect(
      await screen.findByRole('heading', { level: 1, name: INCIDENT.title }),
    ).toBeInTheDocument();
    expect(screen.getByText('Medium')).toBeInTheDocument();
    expect(screen.getByText('Simulated')).toBeInTheDocument();
    expect(screen.getByText('eu-west-3')).toBeInTheDocument();
  });

  it('groups stored facts verbatim into observed, checked and normal, and data gaps', async () => {
    mockFetch(() => json(INCIDENT));
    renderAt('/incidents/INC-0004');
    const observed = await screen.findByRole('region', { name: 'Observed' });
    expect(within(observed).getByText(INCIDENT.facts[0]!.statement)).toBeInTheDocument();
    expect(within(observed).getByText(INCIDENT.facts[1]!.statement)).toBeInTheDocument();
    const normal = screen.getByRole('region', { name: 'Checked and normal' });
    expect(within(normal).getByText(INCIDENT.facts[2]!.statement)).toBeInTheDocument();
    const gaps = screen.getByRole('region', { name: 'Data gaps' });
    expect(within(gaps).getByText(INCIDENT.facts[3]!.statement)).toBeInTheDocument();
    expect(screen.getByText('sha256:0123456789abcdef')).toBeInTheDocument();
  });

  it('marks a normal check that a later merged breach contradicts', async () => {
    const latencyBreach = {
      ...INCIDENT.facts[0]!,
      id: 'F5',
      kind: 'baseline_deviation' as const,
      statement: 'p95 latency at or above 540 ms for 6 min since 14:00 UTC',
      observed_at: iso(70),
      rule_id: 'R-LAT',
      signal: 'latency_p95' as const,
    };
    mockFetch(() => json({ ...INCIDENT, facts: [...INCIDENT.facts, latencyBreach] }));
    renderAt('/incidents/INC-0004');
    const normal = await screen.findByRole('region', { name: 'Checked and normal' });
    expect(within(normal).getByText(/Later breached/)).toBeInTheDocument();
    expect(within(normal).getByRole('link', { name: 'F5' })).toHaveAttribute('href', '#fact-F5');
  });

  it('links timeline entries to the facts they cite', async () => {
    mockFetch(() => json(INCIDENT));
    renderAt('/incidents/INC-0004');
    const link = await screen.findByRole('link', { name: 'F1' });
    expect(link).toHaveAttribute('href', '#fact-F1');
    expect(document.getElementById('fact-F1')).not.toBeNull();
  });

  it('charts the breaching signal first and reports missing datapoints instead of hiding them', async () => {
    mockFetch(() => json(INCIDENT));
    renderAt('/incidents/INC-0004');
    const plot = await screen.findByRole('img', { name: /^CPU utilization/ });
    expect(plot).toHaveAccessibleName(/threshold 90%/);
    expect(plot).toHaveAccessibleName(/2 missing datapoints/);
    expect(screen.getByText('2 missing datapoints')).toBeInTheDocument();
    // latency has no breach fact: it is a secondary chart, behind "Other signals"
    expect(screen.getByText('Other signals (1)')).toBeInTheDocument();
  });

  it('shows a not-found state for an unknown incident', async () => {
    mockFetch(() =>
      json(
        { error: { code: 'NOT_FOUND', message: 'Incident INC-9999 not found.', hint: null } },
        404,
      ),
    );
    renderAt('/incidents/INC-9999');
    expect(await screen.findByText('Incident INC-9999 not found.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to incidents' })).toHaveAttribute(
      'href',
      '/incidents',
    );
  });

  it('explains an unreachable backend', async () => {
    mockFetch(() => Promise.reject(new TypeError('Failed to fetch')));
    renderAt('/incidents/INC-0004');
    expect(await screen.findByText(/Sentinel API unreachable/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows a skeleton while loading', () => {
    mockFetch(() => new Promise(() => {}));
    renderAt('/incidents/INC-0004');
    expect(screen.getByLabelText('Loading incident')).toHaveAttribute('aria-busy', 'true');
  });
});
