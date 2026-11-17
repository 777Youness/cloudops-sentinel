import { Link, NavLink, useSearchParams } from 'react-router';

import type { IncidentStatusFilter, IncidentSummary } from '../../api/types';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Label, type LabelTone } from '../../components/Label';
import { PageHeader } from '../../components/PageHeader';
import { RefreshError } from '../../components/RefreshError';
import { SeverityTag } from '../../components/SeverityTag';
import { SkeletonRows } from '../../components/SkeletonRows';
import { EmptyState, ErrorState } from '../../components/StateMessage';
import table from '../../components/Table.module.css';
import {
  formatRelative,
  formatSignalValue,
  formatUtc,
  formatUtcFull,
  plural,
  SIGNAL_LABELS,
} from '../../lib/format';
import { useNow } from '../../lib/useNow';
import { useSync, useSyncActivity } from '../sync/api';
import { useSystem } from '../system/api';
import { useIncidents } from './api';
import styles from './IncidentsPage.module.css';

const FILTERS: { value: IncidentStatusFilter; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'all', label: 'All' },
];
const COLUMNS = 7;

const INVESTIGATION_LABELS: Record<IncidentSummary['investigation_status'], string> = {
  not_run: 'Not run',
  completed: 'Completed',
  failed: 'Failed',
  outdated: 'Outdated',
  unavailable: 'Unavailable',
};

const INVESTIGATION_TONE: Record<IncidentSummary['investigation_status'], LabelTone> = {
  not_run: 'neutral',
  completed: 'info',
  failed: 'crit',
  outdated: 'warn',
  unavailable: 'neutral',
};

function parseFilter(raw: string | null): IncidentStatusFilter {
  return raw === 'resolved' || raw === 'all' ? raw : 'open';
}

function IncidentRow({ incident, now }: { incident: IncidentSummary; now: number }) {
  return (
    <tr className={`${table.row} ${styles.row} ${styles[`sev_${incident.severity}`]}`}>
      <td>
        <SeverityTag severity={incident.severity} />
      </td>
      <td className={styles.title}>
        <Link to={`/incidents/${incident.id}`} className={table.primaryText}>
          {incident.title}
        </Link>
        <span className={`mono ${table.sub}`}>{incident.id}</span>
      </td>
      <td>
        <span className={styles.resourceName}>{incident.resource_name}</span>
        <span className={`mono ${table.sub}`}>{incident.resource_id}</span>
      </td>
      <td>
        {incident.key_signals.map((s) => (
          <span key={s.signal} className={table.signal}>
            <span className={table.signalLabel}>{SIGNAL_LABELS[s.signal]}</span>
            <span className="mono">{formatSignalValue(s)}</span>
          </span>
        ))}
      </td>
      <td title={formatUtcFull(incident.first_detected_at)}>
        <span className="mono">{formatUtc(incident.first_detected_at)}</span>
        <span className={table.sub}>{formatRelative(incident.first_detected_at, now)}</span>
      </td>
      <td>
        <Label tone={incident.status === 'open' ? 'neutral' : 'ok'}>
          {incident.status === 'open' ? 'Open' : 'Resolved'}
        </Label>
      </td>
      <td>
        <Label tone={INVESTIGATION_TONE[incident.investigation_status]}>
          {INVESTIGATION_LABELS[incident.investigation_status]}
        </Label>
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
          <Button variant="primary" onClick={() => sync.mutate()} disabled={pending}>
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
    <section aria-labelledby="incidents-title" className={styles.page}>
      <PageHeader
        title="Incidents"
        titleId="incidents-title"
        description="Detected by deterministic rules; severity comes from the rule matrix."
      />

      {incidents.isError && incidents.data && (
        <RefreshError shownAt={incidents.dataUpdatedAt} onRetry={() => incidents.refetch()} />
      )}
      <Card flush>
        <nav aria-label="Incident status" className={styles.tabs}>
          {FILTERS.map((f) => (
            <NavLink
              key={f.value}
              to={`?status=${f.value}`}
              onClick={(e) => {
                e.preventDefault();
                setParams({ status: f.value });
              }}
              className={f.value === filter ? `${styles.tab} ${styles.tabActive}` : styles.tab}
              aria-current={f.value === filter ? 'page' : undefined}
            >
              {f.label}
              {f.value === filter && incidents.isSuccess && (
                <span className={`mono ${styles.tabCount}`}>{incidents.data.total}</span>
              )}
            </NavLink>
          ))}
        </nav>
        {incidents.isError && !incidents.data ? (
          <ErrorState
            error={incidents.error}
            action={<Button onClick={() => incidents.refetch()}>Retry</Button>}
          />
        ) : (
          <>
            <div className={table.wrap}>
              <table className={`${table.table} ${styles.table}`}>
                <colgroup>
                  <col className={styles.colSeverity} />
                  <col />
                  <col />
                  <col />
                  <col />
                  <col className={styles.colStatus} />
                  <col className={styles.colInvestigation} />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">Severity</th>
                    <th scope="col">Incident</th>
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
            </div>
            {incidents.isSuccess && incidents.data.total === 0 && <EmptyBody filter={filter} />}
          </>
        )}
      </Card>
    </section>
  );
}
