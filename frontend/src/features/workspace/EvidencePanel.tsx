/**
 * The facts stored with the incident, verbatim, grouped by what they tell the reader.
 * Every fact is observed (solid rule); nothing here is inferred.
 */
import type { Fact, Incident } from '../../api/types';
import { formatUtc, formatUtcFull } from '../../lib/format';
import styles from './EvidencePanel.module.css';

const GROUPS: { title: string; kinds: Fact['kind'][]; empty: string }[] = [
  {
    title: 'Observed',
    kinds: ['threshold_breach', 'baseline_deviation', 'event', 'alarm_state', 'log_pattern'],
    empty: 'No observed facts.',
  },
  { title: 'Checked and normal', kinds: ['within_normal'], empty: 'No other signal checked.' },
  {
    title: 'Data gaps',
    kinds: ['data_gap'],
    empty: 'No data gaps: every rule could be evaluated.',
  },
];

const BREACH_KINDS: Fact['kind'][] = ['threshold_breach', 'baseline_deviation'];

/**
 * Facts are append-only, so a "checked and normal" fact can be followed by a breach of the
 * same rule merged later. Say so, from the stored facts only, instead of letting the two
 * read as a contradiction.
 */
function laterBreach(fact: Fact, facts: Fact[]): Fact | undefined {
  if (fact.kind !== 'within_normal' || !fact.rule_id) return undefined;
  return facts.find(
    (f) =>
      BREACH_KINDS.includes(f.kind) &&
      f.rule_id === fact.rule_id &&
      new Date(f.observed_at) > new Date(fact.observed_at),
  );
}

function FactItem({ fact, supersededBy }: { fact: Fact; supersededBy?: Fact }) {
  return (
    <li
      id={`fact-${fact.id}`}
      className={fact.kind === 'data_gap' ? `${styles.fact} ${styles.gap}` : styles.fact}
    >
      <span className={`mono ${styles.id}`}>{fact.id}</span>
      <p className={styles.statement}>{fact.statement}</p>
      <p className={styles.meta}>
        <span className="mono" title={formatUtcFull(fact.observed_at)}>
          {formatUtc(fact.observed_at)}
        </span>
        {fact.rule_id && <span className="mono">{fact.rule_id}</span>}
        <span>{fact.source}</span>
        {supersededBy && (
          <span className={styles.superseded}>
            Later breached: <a href={`#fact-${supersededBy.id}`}>{supersededBy.id}</a>
          </span>
        )}
      </p>
    </li>
  );
}

export function EvidencePanel({ incident }: { incident: Incident }) {
  return (
    <div className={styles.panel}>
      <h2 className={styles.h2}>Evidence</h2>
      {GROUPS.map((group) => {
        const facts = incident.facts.filter((f) => group.kinds.includes(f.kind));
        return (
          <section key={group.title} aria-label={group.title} className={styles.group}>
            <h3 className={styles.h3}>
              <span>{group.title}</span>
              <span className="mono">{facts.length}</span>
            </h3>
            {facts.length === 0 ? (
              <p className={styles.empty}>{group.empty}</p>
            ) : (
              <ol className={styles.list}>
                {facts.map((f) => (
                  <FactItem key={f.id} fact={f} supersededBy={laterBreach(f, incident.facts)} />
                ))}
              </ol>
            )}
          </section>
        );
      })}
      <h2 className={styles.h2}>Details</h2>
      <dl className={styles.details}>
        <div>
          <dt>Rules</dt>
          <dd className="mono">{incident.rule_ids.join(', ')}</dd>
        </div>
        <div>
          <dt>Evidence hash</dt>
          <dd className="mono">{incident.evidence_hash}</dd>
        </div>
        <div>
          <dt>Last updated</dt>
          <dd className="mono">{formatUtcFull(incident.last_updated_at)}</dd>
        </div>
        <div>
          <dt>Investigation</dt>
          <dd>Not run</dd>
        </div>
      </dl>
    </div>
  );
}
