/**
 * Investigation workspace (docs/screens.md): everything stored for one incident.
 * Day 2c shows evidence only; the investigation sections arrive with Day 3.
 */
import { Link, useParams } from 'react-router';

import { ApiError } from '../../api/client';
import type { Incident } from '../../api/types';
import { Button } from '../../components/Button';
import { RefreshError } from '../../components/RefreshError';
import { SeverityTag } from '../../components/SeverityTag';
import { EmptyState, ErrorState } from '../../components/StateMessage';
import { formatRelative, formatUtc, formatUtcFull } from '../../lib/format';
import { useNow } from '../../lib/useNow';
import { useIncident } from './api';
import {
  annotationsFor,
  chartSignals,
  markersFor,
  type TimeDomain,
  timeDomain,
  timeTicks,
} from './chartData';
import { EvidencePanel, IncidentDetails } from './EvidencePanel';
import { InvestigationPanel } from './InvestigationPanel';
import { SignalChart } from './SignalChart';
import { Timeline } from './Timeline';
import styles from './WorkspacePage.module.css';

function When({ iso, now }: { iso: string; now: number }) {
  return (
    <span title={formatUtcFull(iso)}>
      <span className="mono">{formatUtc(iso)}</span>{' '}
      <span className={styles.relative}>{formatRelative(iso, now)}</span>
    </span>
  );
}

function Header({ incident, now }: { incident: Incident; now: number }) {
  return (
    <header className={styles.header}>
      <Link to="/incidents" className={styles.back}>
        Incidents
      </Link>
      <div className={styles.titleRow}>
        <h1 id="workspace-title" className={styles.h1}>
          {incident.title}
        </h1>
        <SeverityTag severity={incident.severity} />
        <span className={incident.status === 'open' ? styles.statusOpen : styles.statusResolved}>
          {incident.status === 'open' ? 'Open' : 'Resolved'}
        </span>
      </div>
      <dl className={styles.meta}>
        <div>
          <dt>Incident</dt>
          <dd className="mono">{incident.id}</dd>
        </div>
        <div>
          <dt>Resource</dt>
          <dd>
            {incident.resource_name} <span className="mono">{incident.resource_id}</span>
          </dd>
        </div>
        <div>
          <dt>Region</dt>
          <dd className="mono">{incident.region}</dd>
        </div>
        <div>
          <dt>First detected</dt>
          <dd>
            <When iso={incident.first_detected_at} now={now} />
          </dd>
        </div>
        <div>
          <dt>Last updated</dt>
          <dd>
            <When iso={incident.last_updated_at} now={now} />
          </dd>
        </div>
        {incident.resolved_at && (
          <div>
            <dt>Resolved</dt>
            <dd>
              <When iso={incident.resolved_at} now={now} />
            </dd>
          </div>
        )}
        <div>
          <dt>Data</dt>
          <dd>{incident.data_origin === 'simulated' ? 'Simulated' : 'AWS'}</dd>
        </div>
      </dl>
    </header>
  );
}

function Charts({ incident }: { incident: Incident }) {
  const series = incident.evidence.series;
  const dataDomain = timeDomain(series);
  if (!dataDomain) {
    return <p className={styles.muted}>No telemetry was stored with this incident.</p>;
  }
  const markers = markersFor(incident);
  // Detection runs just after the latest datapoint: widen the axis so its marker shows.
  const domain: TimeDomain = [
    Math.min(dataDomain[0], ...markers.map((m) => m.t)),
    Math.max(dataDomain[1], ...markers.map((m) => m.t)),
  ];
  const ticks = timeTicks(domain);
  const { primary, other } = chartSignals(incident);
  const bySignal = new Map(series.map((s) => [s.signal, s]));

  const chart = (signal: (typeof primary)[number], showTimeAxis: boolean) => (
    <SignalChart
      key={signal}
      series={bySignal.get(signal)!}
      domain={domain}
      dataDomain={dataDomain}
      ticks={ticks}
      annotations={annotationsFor(signal, incident.facts)}
      markers={markers}
      severity={incident.severity}
      showTimeAxis={showTimeAxis}
    />
  );

  return (
    <>
      <div className={styles.charts}>
        {primary.map((s, i) => chart(s, i === primary.length - 1))}
      </div>
      {other.length > 0 && (
        <details className={styles.other}>
          <summary>Other signals ({other.length})</summary>
          <div className={styles.charts}>
            {other.map((s, i) => chart(s, i === other.length - 1))}
          </div>
        </details>
      )}
    </>
  );
}

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="Loading incident">
      <div className={styles.skeletonTitle} />
      <div className={styles.skeletonMeta} />
      <div className={styles.layout}>
        <div>
          {[0, 1, 2].map((i) => (
            <div key={i} className={styles.skeletonChart} />
          ))}
        </div>
        <div className={styles.skeletonPanel} />
      </div>
    </div>
  );
}

export function WorkspacePage() {
  const { id = '' } = useParams();
  const incident = useIncident(id);
  const now = useNow();

  if (incident.isPending) return <Skeleton />;

  if (incident.isError && !incident.data) {
    if (incident.error instanceof ApiError && incident.error.status === 404) {
      return (
        <EmptyState
          title={`Incident ${id} not found.`}
          detail="There is no incident with this ID in the local history."
          action={<Link to="/incidents">Back to incidents</Link>}
        />
      );
    }
    return (
      <ErrorState
        error={incident.error}
        action={<Button onClick={() => incident.refetch()}>Retry</Button>}
      />
    );
  }

  const data = incident.data;
  return (
    <article aria-labelledby="workspace-title" className={styles.page}>
      {incident.isError && (
        <RefreshError shownAt={incident.dataUpdatedAt} onRetry={() => incident.refetch()} />
      )}
      <Header incident={data} now={now} />
      <div className={styles.layout}>
        <div className={styles.main}>
          <section aria-labelledby="signals-title">
            <h2 id="signals-title" className={styles.h2}>
              Signals
            </h2>
            <Charts incident={data} />
          </section>
          <section aria-labelledby="timeline-title">
            <h2 id="timeline-title" className={styles.h2}>
              Timeline
            </h2>
            <Timeline entries={data.timeline} now={now} />
          </section>
        </div>
        <aside className={styles.aside} aria-label="Evidence">
          <EvidencePanel incident={data} />
          <InvestigationPanel incident={data} />
          <IncidentDetails incident={data} />
        </aside>
      </div>
    </article>
  );
}
