import { Link, NavLink, useSearchParams } from 'react-router';

import type { IncidentStatusFilter, IncidentSummary } from '../../api/types';
import { Button } from '../../components/Button';
import { SkeletonRows } from '../../components/SkeletonRows';
import { RefreshError } from '../../components/RefreshError';
import { EmptyState, ErrorState } from '../../components/StateMessage';
import {
  plural,
  formatRelative,
  formatSignalValue,
  formatUtc,
  formatUtcFull,
  SIGNAL_LABELS,
} from '../../lib/format';
import { useNow } from '../../lib/useNow';
import { useSync, useSyncActivity } from '../sync/api';
import { useSystem } from '../system/api';
import { useIncidents } from './api';
import styles from './IncidentsPage.module.css';
import { SeverityTag } from '../../components/SeverityTag';

const FILTERS: { value: IncidentStatusFilter; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'all', label: 'All' },
];
const COLUMNS = 8;

const INVESTIGATION_LABELS: Record<IncidentSummary['investigation_status'], string> = {
  not_run: 'Not run',
  completed: 'Completed',
  failed: 'Failed',
  outdated: 'Outdated',
  unavailable: 'Unavailable',
};

function parseFilter(raw: string | null): IncidentStatusFilter {
  return raw === 'resolved' || raw === 'all' ? raw : 'open';
}

function IncidentRow({ incident, now }: { incident: IncidentSummary; now: number }) {
  return (
    <tr className={`${styles.row} ${styles[`sev_${incident.severity}`]}`}>
      <td>
        <SeverityTag severity={incident.severity} />
      </td>
      <td className="mono">
        <Link to={`/incidents/${incident.id}`} tabIndex={-1} aria-hidden="true">
          {incident.id}
        </Link>
      </td>
      <td className={styles.title}>
        <Link to={`/incidents/${incident.id}`} className={styles.titleLink}>
          {incident.title}
        </Link>
      </td>
      <td>
        <span className={styles.resourceName}>{incident.resource_name}</span>
        <span className={`mono ${styles.resourceId}`}>{incident.resource_id}</span>
      </td>
      <td>
        {incident.key_signals.map((s) => (
          <span key={s.signal} className={styles.signal}>
            <span className={styles.signalLabel}>{SIGNAL_LABELS[s.signal]}</span>
            <span className="mono">{formatSignalValue(s)}</span>
          </span>
        ))}
      </td>
      <td title={formatUtcFull(incident.first_detected_at)}>
        <span className="mono">{formatUtc(incident.first_detected_at)}</span>
        <span className={styles.relative}>{formatRelative(incident.first_detected_at, now)}</span>
      </td>
      <td>{incident.status === 'open' ? 'Open' : 'Resolved'}</td>
      <td className={incident.investigation_status === 'outdated' ? styles.outdated : styles.muted}>
        {INVESTIGATION_LABELS[incident.investigation_status]}
      </td>
    </tr>
  );
}

function EmptyBody({ filter }: { filter: IncidentStatusFilter }) {
  const system = useSystem();
  const sync = useSync();
  const { pending } = useSyncActivity();
  const last = system.data?.last_sync;

  if (!last) {
    return (
      <EmptyState
        title="No data yet."
        detail="Run a sync to collect telemetry and evaluate the detection rules."
        action={
          <Button onClick={() => sync.mutate()} disabled={pending}>
            {pending ? 'Syncing' : 'Sync now'}
          </Button>
        }
      />
    );
  }
  if (filter === 'open') {
    return (
      <EmptyState
        title={`No open incidents. All monitored signals are within thresholds as of ${formatUtc(last.finished_at)}.`}
        detail={`${plural(last.resources_evaluated, 'resource')} and ${plural(last.rules_evaluated, 'rule')} evaluated in the last sync.`}
      />
    );
  }
  return <EmptyState title={filter === 'resolved' ? 'No resolved incidents.' : 'No incidents.'} />;
}

export function IncidentsPage() {
  const [params, setParams] = useSearchParams();
  const filter = parseFilter(params.get('status'));
  const incidents = useIncidents(filter);
  const now = useNow();

  return (
    <section aria-labelledby="incidents-title">
      <header className={styles.header}>
        <h1 id="incidents-title" className={styles.h1}>
          Incidents
        </h1>
        <nav aria-label="Incident status" className={styles.filters}>
          {FILTERS.map((f) => (
            <NavLink
              key={f.value}
              to={`?status=${f.value}`}
              onClick={(e) => {
                e.preventDefault();
                setParams({ status: f.value });
              }}
              className={
                f.value === filter ? `${styles.filter} ${styles.filterActive}` : styles.filter
              }
              aria-current={f.value === filter ? 'page' : undefined}
            >
              {f.label}
            </NavLink>
          ))}
        </nav>
      </header>

      {incidents.isError && incidents.data && (
        <RefreshError shownAt={incidents.dataUpdatedAt} onRetry={() => incidents.refetch()} />
      )}
      {incidents.isError && !incidents.data ? (
        <ErrorState
          error={incidents.error}
          action={<Button onClick={() => incidents.refetch()}>Retry</Button>}
        />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <colgroup>
              <col className={styles.colSeverity} />
              <col className={styles.colId} />
              <col />
              <col className={styles.colResource} />
              <col className={styles.colSignal} />
              <col className={styles.colDetected} />
              <col className={styles.colStatus} />
              <col className={styles.colInvestigation} />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">Severity</th>
                <th scope="col">ID</th>
                <th scope="col">Title</th>
                <th scope="col">Resource</th>
                <th scope="col">Key signal</th>
                <th scope="col">Detected</th>
                <th scope="col">Status</th>
                <th scope="col">Investigation</th>
              </tr>
            </thead>
            {incidents.isPending ? (
              <SkeletonRows columns={COLUMNS} />
            ) : (
              <tbody>
                {incidents.data.items.map((i) => (
                  <IncidentRow key={i.id} incident={i} now={now} />
                ))}
              </tbody>
            )}
          </table>
          {incidents.isSuccess && incidents.data.total === 0 && <EmptyBody filter={filter} />}
        </div>
      )}
    </section>
  );
}
