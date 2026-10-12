/** The incident's timeline, oldest first. Entries that cite a fact link to it. */
import type { TimelineEntry } from '../../api/types';
import { formatRelative, formatUtc, formatUtcFull } from '../../lib/format';
import styles from './Timeline.module.css';

const KIND_LABEL: Record<TimelineEntry['kind'], string> = {
  event: 'Deployment',
  breach_start: 'Breach',
  alarm: 'Alarm',
  incident_opened: 'Opened',
  incident_updated: 'Updated',
  incident_resolved: 'Resolved',
  investigation: 'Investigation',
};

export function Timeline({ entries, now }: { entries: TimelineEntry[]; now: number }) {
  const ordered = [...entries].sort((a, b) => a.at.localeCompare(b.at));
  return (
    <ol className={styles.timeline}>
      {ordered.map((e, i) => (
        <li
          key={`${e.at}-${i}`}
          className={e.kind === 'event' ? `${styles.entry} ${styles.deploy}` : styles.entry}
        >
          <span className={`mono ${styles.time}`} title={formatUtcFull(e.at)}>
            {formatUtc(e.at)}
          </span>
          <span className={styles.kind}>{KIND_LABEL[e.kind]}</span>
          <span className={styles.label}>
            {e.label}
            {e.fact_id && (
              <a href={`#fact-${e.fact_id}`} className={`mono ${styles.factLink}`}>
                {e.fact_id}
              </a>
            )}
          </span>
          <span className={styles.relative}>{formatRelative(e.at, now)}</span>
        </li>
      ))}
    </ol>
  );
}
