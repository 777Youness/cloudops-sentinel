/**
 * Overview (docs/screens.md): what is wrong right now, and can I trust this data?
 * Everything here is read from GET /overview; health is decided by the backend.
 */
import { Info, OctagonAlert, Siren, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';

import type {
  HealthState,
  IncidentSummary,
  Overview,
  ResourceHealth,
  Severity,
} from '../../api/types';
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
  capitalize,
  formatRelative,
  formatSignalValue,
  formatUtc,
  formatUtcFull,
  plural,
  SIGNAL_LABELS,
  SIGNAL_TITLES,
} from '../../lib/format';
import { isStale } from '../../lib/staleness';
import { useNow } from '../../lib/useNow';
import { useSync, useSyncActivity } from '../sync/api';
import { useOverview } from './api';
import styles from './OverviewPage.module.css';

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low'];

const SEVERITY_ICON: Record<Severity, ReactNode> = {
  critical: <OctagonAlert />,
  high: <Siren />,
  medium: <TriangleAlert />,
  low: <Info />,
};

const HEALTH_TONE: Record<HealthState, LabelTone> = {
  crit: 'crit',
  warn: 'warn',
  ok: 'ok',
  unknown: 'unknown',
};

const HEALTH_LABEL: Record<HealthState, string> = {
  crit: 'Failing',
  warn: 'Degraded',
  ok: 'Healthy',
  unknown: 'No data',
};

function SeveritySummary({ overview }: { overview: Overview }) {
  return (
    <dl className={styles.severities} aria-label="Open incidents by severity">
      {SEVERITIES.map((s) => {
        const count = overview.open_by_severity[s];
        const classes = [styles.metric, styles[`metric_${s}`], count === 0 ? styles.zero : '']
          .filter(Boolean)
          .join(' ');
        return (
          <div key={s} className={classes}>
            <dt className={styles.metricHead}>
              <SeverityTag severity={s} />
              <span className={styles.metricIcon} aria-hidden="true">
                {SEVERITY_ICON[s]}
              </span>
            </dt>
            <dd className={`mono ${styles.metricValue}`}>{count}</dd>
            <dd className={styles.metricCaption}>open {count === 1 ? 'incident' : 'incidents'}</dd>
          </div>
        );
      })}
    </dl>
  );
}

function OpenIncidents({ overview, now }: { overview: Overview; now: number }) {
  const last = overview.last_sync;
  if (overview.open_total === 0) {
    return (
      <EmptyState
        title="No open incidents."
        detail={
          last
            ? `${plural(last.resources_evaluated, 'resource')} and ${plural(last.rules_evaluated, 'rule')} evaluated in the last sync.`
            : undefined
        }
      />
    );
  }
  return (
    <>
      <div className={table.wrap}>
        <table className={table.table}>
          <thead>
            <tr>
              <th scope="col">Severity</th>
              <th scope="col">Incident</th>
              <th scope="col">Key signal</th>
              <th scope="col">Detected</th>
            </tr>
          </thead>
          <tbody>
            {overview.top_open_incidents.map((i: IncidentSummary) => (
              <tr key={i.id} className={table.row}>
                <td>
                  <SeverityTag severity={i.severity} />
                </td>
                <td>
                  <Link to={`/incidents/${i.id}`} className={table.primaryText}>
                    {i.title}
                  </Link>
                  <span className={`mono ${table.sub}`}>{i.id}</span>
                </td>
                <td>
                  {i.key_signals.map((s) => (
                    <span key={s.signal} className={table.signal}>
                      <span className={table.signalLabel}>{SIGNAL_LABELS[s.signal]}</span>
                      <span className="mono">{formatSignalValue(s)}</span>
                    </span>
                  ))}
                </td>
                <td title={formatUtcFull(i.first_detected_at)}>
                  <span className="mono">{formatUtc(i.first_detected_at)}</span>
                  <span className={table.sub}>{formatRelative(i.first_detected_at, now)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={table.footer}>
        <Link to="/incidents?status=open">All open incidents ({overview.open_total})</Link>
      </p>
    </>
  );
}

function DataTrust({ overview, now }: { overview: Overview; now: number }) {
  const last = overview.last_sync;
  const asOf = overview.data_as_of;
  const stale = isStale(asOf, now);
  const withGaps = overview.resources.filter((r) => r.signals_missing.length > 0);

  return (
    <dl className={styles.trust}>
      <div>
        <dt>Data</dt>
        <dd>
          {overview.data_origin === 'aws' ? (
            <Label tone="accent">AWS</Label>
          ) : overview.data_origin === 'simulated' ? (
            <Label tone="warn">Simulated</Label>
          ) : (
            'None collected yet'
          )}
        </dd>
      </div>
      <div>
        <dt>Data as of</dt>
        <dd>
          {asOf ? (
            <>
              <span className="mono" title={formatUtcFull(asOf)}>
                {formatUtc(asOf)}
              </span>{' '}
              <span className={styles.sub}>{formatRelative(asOf, now)}</span>
              {stale && (
                <Label tone="warn" className={styles.stale}>
                  Stale
                </Label>
              )}
            </>
          ) : (
            'No sync has succeeded yet'
          )}
        </dd>
      </div>
      <div>
        <dt>Last sync</dt>
        <dd>
          {last ? (
            <>
              <Label
                tone={
                  last.status === 'success' ? 'ok' : last.status === 'partial' ? 'warn' : 'crit'
                }
              >
                {capitalize(last.status)}
              </Label>{' '}
              <span className={styles.sub} title={formatUtcFull(last.finished_at)}>
                {formatRelative(last.finished_at, now)}
              </span>
              {last.status !== 'success' && (
                <>
                  {' '}
                  <Link to="/system">Details in System</Link>
                </>
              )}
            </>
          ) : (
            'Never'
          )}
        </dd>
      </div>
      {last && (
        <>
          <div>
            <dt>Sources</dt>
            <dd>
              {last.collectors.map((c) => (
                <span key={c.name} className={styles.collector}>
                  <span className="mono">{c.name}</span>{' '}
                  <span className={c.state === 'ok' ? styles.collectorOk : styles.failed}>
                    {c.state === 'ok' ? 'OK' : capitalize(c.state)}
                  </span>
                </span>
              ))}
            </dd>
          </div>
          <div>
            <dt>Evaluated</dt>
            <dd>
              {plural(last.resources_evaluated, 'resource')}, {plural(last.rules_evaluated, 'rule')}
            </dd>
          </div>
          <div>
            <dt>Last sync changed</dt>
            <dd className="mono">
              {last.incidents_opened} opened, {last.incidents_updated} updated,{' '}
              {last.incidents_resolved} resolved
            </dd>
          </div>
        </>
      )}
      <div>
        <dt>Missing signals</dt>
        <dd>
          {overview.resources.length === 0
            ? 'Unknown until a sync succeeds'
            : withGaps.length === 0
              ? 'None: every resource reports every expected signal'
              : `${plural(withGaps.length, 'resource')} with missing signals`}
        </dd>
      </div>
    </dl>
  );
}

function Health({ health }: { health: HealthState }) {
  return (
    <Label tone={HEALTH_TONE[health]}>
      <span className={`${styles.dot} ${styles[`health_${health}`]}`} aria-hidden="true" />
      {HEALTH_LABEL[health]}
    </Label>
  );
}

function Signals({ resource }: { resource: ResourceHealth }) {
  const expected = resource.signals_expected.length;
  const present = expected - resource.signals_missing.length;
  return (
    <>
      <span className="mono">
        {present} of {expected}
      </span>
      {resource.signals_missing.length > 0 && (
        <span className={styles.missing}>
          Missing: {resource.signals_missing.map((s) => SIGNAL_TITLES[s]).join(', ')}
        </span>
      )}
    </>
  );
}

function Resources({ overview }: { overview: Overview }) {
  if (overview.resources.length === 0) {
    return (
      <EmptyState
        title="No resource data."
        detail="Resources appear after the first successful sync."
      />
    );
  }
  return (
    <div className={table.wrap}>
      <table className={table.table}>
        <thead>
          <tr>
            <th scope="col">Health</th>
            <th scope="col">Resource</th>
            <th scope="col">Type</th>
            <th scope="col">Open incident</th>
            <th scope="col">Signals</th>
          </tr>
        </thead>
        <tbody>
          {overview.resources.map((r) => (
            <tr key={r.resource_id} className={table.row}>
              <td>
                <Health health={r.health} />
              </td>
              <td>
                <span className={table.primaryText}>{r.resource_name}</span>
                <span className={`mono ${table.sub}`}>{r.resource_id}</span>
              </td>
              <td className="mono">{r.instance_type}</td>
              <td>
                {r.open_incident_id ? (
                  <>
                    <Link to={`/incidents/${r.open_incident_id}`} className="mono">
                      {r.open_incident_id}
                    </Link>
                    {r.open_incident_severity && (
                      <span className={table.sub}>{capitalize(r.open_incident_severity)}</span>
                    )}
                  </>
                ) : (
                  <span className={table.muted}>None</span>
                )}
              </td>
              <td>
                <Signals resource={r} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NeverSynced() {
  const sync = useSync();
  const { pending } = useSyncActivity();
  return (
    <EmptyState
      title="No data yet."
      detail="Run a sync to collect telemetry, evaluate the detection rules and see the health of each monitored resource."
      action={
        <Button variant="primary" onClick={() => sync.mutate()} disabled={pending}>
          {pending ? 'Syncing' : 'Sync now'}
        </Button>
      }
    />
  );
}

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="Loading overview" className={styles.skeleton}>
      <div className={styles.severities}>
        {SEVERITIES.map((s) => (
          <div key={s} className={`${styles.metric} ${styles.metricSkeleton}`} />
        ))}
      </div>
      <Card flush>
        <table className={table.table}>
          <SkeletonRows columns={5} rows={5} />
        </table>
      </Card>
    </div>
  );
}

export function OverviewPage() {
  const overview = useOverview();
  const now = useNow();

  let body;
  if (overview.isPending) {
    body = <Skeleton />;
  } else if (overview.isError && !overview.data) {
    body = (
      <Card>
        <ErrorState
          error={overview.error}
          action={<Button onClick={() => overview.refetch()}>Retry</Button>}
        />
      </Card>
    );
  } else if (!overview.data.last_sync) {
    body = (
      <Card>
        <NeverSynced />
      </Card>
    );
  } else {
    const data = overview.data;
    body = (
      <>
        {overview.isError && (
          <RefreshError shownAt={overview.dataUpdatedAt} onRetry={() => overview.refetch()} />
        )}
        <SeveritySummary overview={data} />
        <div className={styles.columns}>
          <Card
            title="Open incidents"
            titleId="open-title"
            subheader="Highest severity first"
            flush
          >
            <OpenIncidents overview={data} now={now} />
          </Card>
          <Card
            title="Data trust"
            titleId="trust-title"
            subheader="Where this data comes from and how fresh it is"
          >
            <DataTrust overview={data} now={now} />
          </Card>
        </div>
        <Card
          title="Monitored resources"
          titleId="resources-title"
          subheader="Health is decided by the backend; missing signals are named, never shown as 0"
          flush
        >
          <Resources overview={data} />
        </Card>
      </>
    );
  }

  return (
    <section aria-labelledby="overview-title" className={styles.page}>
      <PageHeader
        title="Overview"
        titleId="overview-title"
        description="What is wrong right now, and whether the data can be trusted."
      />
      {body}
    </section>
  );
}
