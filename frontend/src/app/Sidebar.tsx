import { LayoutDashboard, Server, ShieldCheck, Siren, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { NavLink } from 'react-router';

import { useIncidents } from '../features/incidents/api';
import { useSystem } from '../features/system/api';
import styles from './Sidebar.module.css';

function linkClass({ isActive }: { isActive: boolean }) {
  return isActive ? `${styles.link} ${styles.active}` : styles.link;
}

function Item({
  to,
  end,
  icon,
  children,
}: {
  to: string;
  end?: boolean;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <NavLink to={to} end={end} className={linkClass}>
      <span className={styles.icon} aria-hidden="true">
        {icon}
      </span>
      {children}
    </NavLink>
  );
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const incidents = useIncidents('open');
  const openCount = incidents.data?.total;
  const { data: system } = useSystem();

  return (
    <>
      {open && <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />}
      <aside className={open ? `${styles.sidebar} ${styles.open}` : styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            <ShieldCheck />
          </span>
          <span className={styles.wordmark}>
            <span className={styles.product}>Sentinel</span>
            <span className={styles.family}>CloudOps</span>
          </span>
          {open && (
            <button type="button" className={styles.close} onClick={onClose}>
              <X aria-hidden="true" />
              <span className="visually-hidden">Close menu</span>
            </button>
          )}
        </div>
        <nav aria-label="Main" className={styles.nav}>
          <p className={styles.section}>Monitoring</p>
          <Item to="/" end icon={<LayoutDashboard />}>
            <span className={styles.text}>Overview</span>
          </Item>
          <Item to="/incidents" icon={<Siren />}>
            <span className={styles.text}>Incidents</span>
            {openCount !== undefined && openCount > 0 && (
              <span className={`mono ${styles.count}`} aria-label={`${openCount} open`}>
                {openCount}
              </span>
            )}
          </Item>
        </nav>
        <nav aria-label="Sentinel" className={styles.nav}>
          <p className={styles.section}>Platform</p>
          <Item to="/system" icon={<Server />}>
            <span className={styles.text}>System</span>
          </Item>
        </nav>
        {system && (
          <dl className={styles.context}>
            <div>
              <dt>Version</dt>
              <dd className="mono">{system.version}</dd>
            </div>
            <div>
              <dt>API contract</dt>
              <dd className="mono">v{system.contract_version}</dd>
            </div>
          </dl>
        )}
      </aside>
    </>
  );
}
