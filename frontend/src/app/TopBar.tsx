import { Link } from 'react-router';

import { ApiError } from '../api/client';
import { Button } from '../components/Button';
import { useElapsedSeconds, useSync, useSyncActivity } from '../features/sync/api';
import { useSystem } from '../features/system/api';
import { formatRelative, formatUtcFull } from '../lib/format';
import { useNow } from '../lib/useNow';
import styles from './TopBar.module.css';

function SyncStatus() {
  const system = useSystem();
  const { pending, lastError } = useSyncActivity();
  const elapsed = useElapsedSeconds(pending);
  const now = useNow();

  if (pending) {
    return <span className={styles.status}>Syncing… {elapsed} s</span>;
  }
  if (lastError instanceof ApiError && lastError.code === 'SYNC_IN_PROGRESS') {
    return <span className={styles.status}>A sync is already running</span>;
  }
  if (system.isError) {
    return <span className={`${styles.status} ${styles.crit}`}>API unreachable</span>;
  }
  const last = system.data?.last_sync;
  if (!last) {
    return <span className={styles.status}>Never synced</span>;
  }
  if (last.status === 'failed') {
    return (
      <Link to="/system" className={`${styles.status} ${styles.crit}`}>
        Last sync failed {formatRelative(last.finished_at, now)}
      </Link>
    );
  }
  return (
    <span className={styles.status} title={formatUtcFull(last.finished_at)}>
      Synced {formatRelative(last.finished_at, now)}
    </span>
  );
}

export function TopBar() {
  const { data } = useSystem();
  const sync = useSync();
  const { pending } = useSyncActivity();

  return (
    <header className={styles.bar}>
      <dl className={styles.context}>
        <div className={styles.item}>
          <dt>Environment</dt>
          <dd>{data?.environment ?? '–'}</dd>
        </div>
        <div className={styles.item}>
          <dt>Data</dt>
          <dd>{data ? (data.mode === 'local' ? 'Simulated' : 'AWS') : '–'}</dd>
        </div>
        <div className={styles.item}>
          <dt>Region</dt>
          <dd className="mono">{data?.region ?? '–'}</dd>
        </div>
      </dl>
      <div className={styles.actions}>
        <SyncStatus />
        <Button onClick={() => sync.mutate()} disabled={pending}>
          Sync now
        </Button>
      </div>
    </header>
  );
}
