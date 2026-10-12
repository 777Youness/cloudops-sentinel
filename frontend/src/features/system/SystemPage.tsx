import type { ReactNode } from 'react';

import type { CollectorStatus, SyncRun } from '../../api/types';
import { Button } from '../../components/Button';
import { EmptyState, ErrorState } from '../../components/StateMessage';
import { capitalize, formatDurationMs, formatUtcFull, plural } from '../../lib/format';
import { useSystem } from './api';
import styles from './SystemPage.module.css';

const STATE_LABEL: Record<CollectorStatus['state'], string> = {
  ok: 'OK',
  degraded: 'Degraded',
  failed: 'Failed',
  disabled: 'Disabled',
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
    <>
      <dl className={styles.list}>
        <Row label="Run">
          <span className="mono">{run.id}</span>
        </Row>
        <Row label="Outcome">
          <span className={styles[`outcome_${run.status}`]}>{capitalize(run.status)}</span>
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
      </dl>
      <h2 className={styles.h2}>Data sources</h2>
      <table className={styles.table}>
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
            <tr key={c.name}>
              <td className="mono">{c.name}</td>
              <td className={styles[`state_${c.state}`]}>{STATE_LABEL[c.state]}</td>
              <td className="mono">
                {c.last_success_at ? formatUtcFull(c.last_success_at) : 'Never'}
              </td>
              <td>
                {c.error ? (
                  <>
                    <span className="mono">{c.error.code}</span> {c.error.message}
                    {c.error.hint && <span className={styles.hint}>{c.error.hint}</span>}
                  </>
                ) : (
                  <span className={styles.muted}>None</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function SystemPage() {
  const system = useSystem();

  return (
    <section aria-labelledby="system-title" className={styles.page}>
      <h1 id="system-title" className={styles.h1}>
        System
      </h1>
      {system.isError && (
        <ErrorState
          error={system.error}
          action={<Button onClick={() => system.refetch()}>Retry</Button>}
        />
      )}
      {system.isPending && <p className={styles.muted}>Loading system status…</p>}
      {system.isSuccess && (
        <>
          <h2 className={styles.h2}>Runtime</h2>
          <dl className={styles.list}>
            <Row label="Data mode">
              {system.data.mode === 'local' ? 'Simulated (local)' : 'AWS'}
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
          <h2 className={styles.h2}>Last sync</h2>
          {system.data.last_sync ? (
            <LastSync run={system.data.last_sync} />
          ) : (
            <EmptyState title="No sync has run since the backend started." />
          )}
        </>
      )}
    </section>
  );
}
