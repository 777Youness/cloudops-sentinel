import { useSystem } from '../features/system/api';
import styles from './ModeStrip.module.css';

/** Persistent in local mode: simulated data must never be mistaken for AWS data. */
export function ModeStrip() {
  const { data } = useSystem();
  if (data?.mode !== 'local') return null;
  return (
    <div className={styles.strip} role="note">
      Simulated data. Scenarios are replayed locally; nothing on this screen comes from AWS.
    </div>
  );
}
