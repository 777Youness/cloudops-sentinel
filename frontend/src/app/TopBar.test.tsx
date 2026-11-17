import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

import { createQueryClient } from './queryClient';
import { TopBar } from './TopBar';

function systemWith(status: 'success' | 'partial' | 'failed') {
  const at = new Date().toISOString();
  return {
    version: 'test',
    contract_version: '1',
    mode: 'aws',
    environment: 'dev',
    region: 'eu-west-3',
    llm: { provider: 'mock', model: 'mock-rules-v1', configured: true },
    last_sync: {
      id: 'SYNC-0001',
      started_at: at,
      finished_at: at,
      status,
      collectors: [],
      resources_evaluated: 1,
      rules_evaluated: 7,
      incidents_opened: 0,
      incidents_updated: 0,
      incidents_resolved: 0,
    },
    data_as_of: at,
  };
}

function renderWith(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    ),
  );
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('TopBar sync status', () => {
  it('shows AWS data mode', async () => {
    renderWith(systemWith('success'));
    expect(await screen.findByText('AWS')).toBeInTheDocument();
  });

  it('never presents a partial sync as a clean one', async () => {
    renderWith(systemWith('partial'));
    const link = await screen.findByRole('link', { name: /Last sync partial/ });
    expect(link).toHaveAttribute('href', '/system');
    expect(screen.queryByText(/^Synced/)).not.toBeInTheDocument();
  });

  it('links a failed sync to the System page', async () => {
    renderWith(systemWith('failed'));
    expect(await screen.findByRole('link', { name: /Last sync failed/ })).toHaveAttribute(
      'href',
      '/system',
    );
  });
});
