/**
 * Shown above every page when the data is older than the staleness limit.
 * Based on the last *successful* sync: a failed sync refreshes nothing.
 */
import { useSystem } from '../features/system/api';
import { formatRelative, formatUtcFull } from '../lib/format';
import { isStale } from '../lib/staleness';
import { useNow } from '../lib/useNow';
import styles from './StaleNotice.module.css';

export function StaleNotice() {
  const { data } = useSystem();
  const now = useNow();
  const asOf = data?.data_as_of;
  if (!asOf || !isStale(asOf, now)) return null;
  return (
    <div className={styles.notice} role="status">
      <p className={styles.title}>
        Data last synced <span title={formatUtcFull(asOf)}>{formatRelative(asOf, now)}</span>.
      </p>
      <p className={styles.detail}>
        Values, health and incidents may have changed since. Sync now to refresh.
      </p>
    </div>
  );
}
