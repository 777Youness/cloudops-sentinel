import { NavLink } from 'react-router';

import { useIncidents } from '../features/incidents/api';
import styles from './Sidebar.module.css';

function linkClass({ isActive }: { isActive: boolean }) {
  return isActive ? `${styles.link} ${styles.active}` : styles.link;
}

export function Sidebar() {
  const open = useIncidents('open');
  const openCount = open.data?.total;

  return (
    <aside className={styles.sidebar}>
      <div className={styles.wordmark}>
        <span className={styles.product}>Sentinel</span>
        <span className={styles.family}>CloudOps</span>
      </div>
      <nav aria-label="Main" className={styles.nav}>
        <NavLink to="/" end className={linkClass}>
          Overview
        </NavLink>
        <NavLink to="/incidents" className={linkClass}>
          <span>Incidents</span>
          {openCount !== undefined && openCount > 0 && (
            <span className={`mono ${styles.count}`} aria-label={`${openCount} open`}>
              {openCount}
            </span>
          )}
        </NavLink>
      </nav>
      <nav aria-label="Sentinel" className={styles.bottom}>
        <NavLink to="/system" className={linkClass}>
          System
        </NavLink>
      </nav>
    </aside>
  );
}
