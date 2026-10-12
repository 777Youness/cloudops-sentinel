/**
 * A refetch failed while data is already on screen: keep the data, say it may be old.
 * (docs/design-system.md, "Refetch failed with data on screen")
 */
import { formatUtc } from '../lib/format';
import { Button } from './Button';
import styles from './RefreshError.module.css';

export function RefreshError({ shownAt, onRetry }: { shownAt: number; onRetry: () => void }) {
  return (
    <div className={styles.banner} role="alert">
      <span>
        Could not refresh. Showing data from{' '}
        <span className="mono">{formatUtc(new Date(shownAt).toISOString())}</span>.
      </span>
      <Button onClick={onRetry}>Retry</Button>
    </div>
  );
}
