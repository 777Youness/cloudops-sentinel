import type { ReactNode } from 'react';

import type { CollectorStatus, SyncRun } from '../../api/types';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Label, type LabelTone } from '../../components/Label';
import { PageHeader } from '../../components/PageHeader';
import { EmptyState, ErrorState } from '../../components/StateMessage';
import table from '../../components/Table.module.css';
import { capitalize, formatDurationMs, formatUtcFull, plural } from '../../lib/format';
import { useSystem } from './api';
import styles from './SystemPage.module.css';

const STATE_LABEL: Record<CollectorStatus['state'], string> = {
  ok: 'OK',
  degraded: 'Degraded',
  failed: 'Failed',
  disabled: 'Disabled',
};

const STATE_TONE: Record<CollectorStatus['state'], LabelTone> = {
  ok: 'ok',
  degraded: 'warn',
  failed: 'crit',
  disabled: 'neutral',
};

const OUTCOME_TONE: Record<SyncRun['status'], LabelTone> = {
  success: 'ok',
  partial: 'warn',
  failed: 'crit',
};

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.kv}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function LastSync({ run }: { run: SyncRun }) {
  const duration = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  return (
    <dl className={styles.list}>
      <Row label="Run">
        <span className="mono">{run.id}</span>
      </Row>
      <Row label="Outcome">
        <Label tone={OUTCOME_TONE[run.status]}>{capitalize(run.status)}</Label>
      </Row>
      <Row label="Started">
        <span className="mono">{formatUtcFull(run.started_at)}</span>
      </Row>
      <Row label="Duration">
        <span className="mono">{formatDurationMs(duration)}</span>
      </Row>
      <Row label="Evaluated">
        {plural(run.resources_evaluated, 'resource')}, {plural(run.rules_evaluated, 'rule')}
      </Row>
      <Row label="Incidents opened">
        <span className="mono">{run.incidents_opened}</span>
      </Row>
      <Row label="Updated, resolved">
        <span className="mono">
          {run.incidents_updated}, {run.incidents_resolved}
        </span>
      </Row>
    </dl>
  );
}

function DataSources({ run }: { run: SyncRun }) {
  return (
    <div className={table.wrap}>
      <table className={table.table}>
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">State</th>
            <th scope="col">Last success</th>
            <th scope="col">Error</th>
          </tr>
        </thead>
        <tbody>
          {run.collectors.map((c) => (
            <tr key={c.name} className={table.row}>
              <td className={`mono ${styles.source}`}>{c.name}</td>
              <td>
                <Label tone={STATE_TONE[c.state]}>{STATE_LABEL[c.state]}</Label>
              </td>
              <td className="mono">
                {c.last_success_at ? formatUtcFull(c.last_success_at) : 'Never'}
              </td>
              <td>
                {c.error ? (
                  <>
                    <span className={`mono ${styles.code}`}>{c.error.code}</span> {c.error.message}
                    {c.error.hint && <span className={styles.hint}>{c.error.hint}</span>}
                  </>
                ) : (
                  <span className={table.muted}>None</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SystemPage() {
  const system = useSystem();

  return (
    <section aria-labelledby="system-title" className={styles.page}>
      <PageHeader
        title="System"
        titleId="system-title"
        description="Where the data comes from, and whether each source is working."
      />
      {system.isError && (
        <Card>
          <ErrorState
            error={system.error}
            action={<Button onClick={() => system.refetch()}>Retry</Button>}
          />
        </Card>
      )}
      {system.isPending && (
        <Card>
          <p className={styles.muted}>Loading system status…</p>
        </Card>
      )}
      {system.isSuccess && (
        <>
          <div className={styles.columns}>
            <Card title="Runtime" titleId="runtime-title">
              <dl className={styles.list}>
                <Row label="Data mode">
                  <Label tone={system.data.mode === 'local' ? 'warn' : 'accent'}>
                    {system.data.mode === 'local' ? 'Simulated (local)' : 'AWS'}
                  </Label>
                </Row>
                <Row label="Environment">{system.data.environment}</Row>
                <Row label="Region">
                  <span className="mono">{system.data.region}</span>
                </Row>
                <Row label="Investigation provider">
                  <span className="mono">{system.data.llm.provider ?? 'none'}</span>
                  {system.data.llm.model && <span className="mono"> {system.data.llm.model}</span>}
                  {!system.data.llm.configured && (
                    <span className={styles.muted}> (not configured)</span>
                  )}
                </Row>
                <Row label="Version">
                  <span className="mono">{system.data.version}</span>
                </Row>
                <Row label="API contract">
                  <span className="mono">v{system.data.contract_version}</span>
                </Row>
              </dl>
            </Card>
            <Card title="Last sync" titleId="last-sync-title">
              {system.data.last_sync ? (
                <LastSync run={system.data.last_sync} />
              ) : (
                <EmptyState title="No sync has run since the backend started." />
              )}
            </Card>
          </div>
          {system.data.last_sync && (
            <Card
              title="Data sources"
              titleId="sources-title"
              subheader="One row per collector in the last sync; a failed source means its signals are missing, never healthy"
              flush
            >
              <DataSources run={system.data.last_sync} />
            </Card>
          )}
        </>
      )}
    </section>
  );
}
