import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';

import type { Incident, InvestigationResult } from '../../api/types';
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

const SYSTEM = {
  version: 'test',
  contract_version: '1',
  mode: 'local',
  environment: 'dev',
  region: 'eu-west-3',
  llm: { provider: 'mock', model: 'mock-rules-v1', configured: true },
  last_sync: null,
  data_as_of: null,
};

const NOT_FOUND = () =>
  json({ error: { code: 'NOT_FOUND', message: 'No investigation.', hint: null } }, 404);

type Handler = (init?: RequestInit) => Response | Promise<Response>;

/** `handler` answers the incident; /system and /investigation have their own answers. */
function mockFetch(
  handler: Handler,
  {
    investigation = NOT_FOUND,
    system = () => json(SYSTEM),
  }: { investigation?: Handler; system?: Handler } = {},
) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/investigation')) return investigation(init);
    if (url.endsWith('/system')) return system(init);
    return handler(init);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
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

const COMPLETED: InvestigationResult = {
  investigation: {
    id: 'INV-0001',
    incident_id: 'INC-0004',
    status: 'completed',
    provider: 'mock',
    model: 'mock-rules-v1',
    prompt_version: 'investigation-v1',
    started_at: iso(61),
    finished_at: iso(61),
    attempts: 1,
    evidence_hash: INCIDENT.evidence_hash,
    fact_ids: ['F1', 'F2', 'F3', 'F4'],
    findings: {
      summary: '1 breach fact(s) from R-CPU-SAT; 1 recorded change(s) in the evidence window.',
      hypotheses: [
        {
          id: 'H1',
          statement: 'A change deployed before the breach may have caused it.',
          confidence: 'medium',
          cites: ['F2', 'F1'],
        },
      ],
      next_checks: [
        { id: 'C1', description: 'Identify which processes consume the CPU.', cites: ['F1'] },
      ],
      remediation: [
        {
          id: 'R1',
          description: 'Consider reducing the load after review.',
          requires_human: true,
          cites: ['F1'],
        },
      ],
      limitations: ['Generated by the mock provider from fixed rules, not by a language model.'],
    },
    error: null,
  },
  outdated: false,
  incident_evidence_hash: INCIDENT.evidence_hash,
  runs: 1,
};

function investigationSection() {
  return screen.findByRole('region', { name: /^Investigation/ });
}

describe('InvestigationPanel', () => {
  it('offers to run an investigation and explains what it does', async () => {
    mockFetch(() => json(INCIDENT));
    renderAt('/incidents/INC-0004');
    const section = await investigationSection();
    expect(await within(section).findByText('No investigation yet.')).toBeInTheDocument();
    expect(
      within(section).getByText(/Sends this incident's 4 facts to the mock provider/),
    ).toBeInTheDocument();
    expect(within(section).getByRole('button', { name: 'Run investigation' })).toBeEnabled();
  });

  it('runs on demand and shows inferred findings that cite facts', async () => {
    let posted = false;
    const fetchMock = mockFetch(() => json(INCIDENT), {
      investigation: (init) => {
        if (init?.method === 'POST') {
          posted = true;
          return json(COMPLETED);
        }
        return posted ? json(COMPLETED) : NOT_FOUND();
      },
    });
    renderAt('/incidents/INC-0004');
    const section = await investigationSection();
    fireEvent.click(await within(section).findByRole('button', { name: 'Run investigation' }));

    expect(
      await within(section).findByText(/A change deployed before the breach/),
    ).toBeInTheDocument();
    expect(within(section).getByText('Inferred')).toBeInTheDocument();
    expect(within(section).getByRole('note')).toHaveTextContent(
      'Mock provider: generated by fixed rules',
    );
    expect(within(section).getByText('Confidence: medium')).toBeInTheDocument();
    const hypotheses = within(section).getByRole('region', { name: 'Hypotheses' });
    expect(within(hypotheses).getByRole('link', { name: 'F2' })).toHaveAttribute(
      'href',
      '#fact-F2',
    );
    expect(within(section).getByText('Human decision')).toBeInTheDocument();
    // remediation is text: the only button on the panel is "Run again"
    expect(
      within(section)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Run again']);
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST');
    expect(posts).toHaveLength(1);
  });

  it('shows a failed run with its reason', async () => {
    const failed: InvestigationResult = {
      ...COMPLETED,
      investigation: {
        ...COMPLETED.investigation,
        status: 'failed',
        attempts: 2,
        findings: null,
        error: {
          code: 'unknown_fact',
          message: 'H1 cites F9, which is not in the evidence.',
          hint: null,
        },
      },
    };
    mockFetch(() => json(INCIDENT), { investigation: () => json(failed) });
    renderAt('/incidents/INC-0004');
    const section = await investigationSection();
    expect(await within(section).findByText('Investigation failed.')).toBeInTheDocument();
    expect(within(section).getByText('unknown_fact')).toBeInTheDocument();
    expect(within(section).getByRole('button', { name: 'Run again' })).toBeInTheDocument();
  });

  it('says when the investigation used older evidence', async () => {
    mockFetch(() => json(INCIDENT), {
      investigation: () =>
        json({ ...COMPLETED, outdated: true, incident_evidence_hash: 'sha256:new' }),
    });
    renderAt('/incidents/INC-0004');
    const section = await investigationSection();
    expect(
      await within(section).findByText(/This investigation used older evidence/),
    ).toBeInTheDocument();
  });

  it('is unavailable, without a button, when the provider is not configured', async () => {
    mockFetch(() => json(INCIDENT), {
      system: () =>
        json({ ...SYSTEM, llm: { provider: 'openai_compatible', model: null, configured: false } }),
    });
    renderAt('/incidents/INC-0004');
    const section = await investigationSection();
    expect(await within(section).findByText('Investigation unavailable.')).toBeInTheDocument();
    expect(within(section).queryByRole('button')).toBeNull();
  });

  it('renders model text as plain text and keeps citations on the page', async () => {
    // The server validates citations; this checks the UI is safe even if it did not.
    const hostile: InvestigationResult = {
      ...COMPLETED,
      investigation: {
        ...COMPLETED.investigation,
        findings: {
          ...COMPLETED.investigation.findings!,
          summary: '<img src=x onerror="alert(1)"><a href="https://evil.test">click</a>',
          hypotheses: [
            {
              id: 'H1',
              statement: '<script>alert(1)</script>',
              confidence: 'low',
              cites: ['javascript:alert(1)'],
            },
          ],
        },
      },
    };
    mockFetch(() => json(INCIDENT), { investigation: () => json(hostile) });
    renderAt('/incidents/INC-0004');
    const section = await investigationSection();
    expect(await within(section).findByText(/<img src=x onerror/)).toBeInTheDocument();
    expect(within(section).getByText('<script>alert(1)</script>')).toBeInTheDocument();
    expect(
      section.querySelector('img, script, a[href^="https:"], a[href^="javascript:"]'),
    ).toBeNull();
    for (const link of within(section).getAllByRole('link')) {
      expect(link.getAttribute('href')).toMatch(/^#fact-/);
    }
  });

  it('reports a refused request inline', async () => {
    mockFetch(() => json(INCIDENT), {
      investigation: (init) =>
        init?.method === 'POST'
          ? json(
              {
                error: {
                  code: 'INVESTIGATION_IN_PROGRESS',
                  message: 'An investigation of INC-0004 is already running.',
                  hint: null,
                },
              },
              409,
            )
          : NOT_FOUND(),
    });
    renderAt('/incidents/INC-0004');
    const section = await investigationSection();
    fireEvent.click(await within(section).findByRole('button', { name: 'Run investigation' }));
    expect(await within(section).findByText(/already running/)).toBeInTheDocument();
  });
});
