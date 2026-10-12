import { Outlet } from 'react-router';

import { StaleNotice } from '../components/StaleNotice';
import styles from './AppShell.module.css';
import { ModeStrip } from './ModeStrip';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function AppShell() {
  return (
    <div className={styles.frame}>
      {/* Spans the full width so it can't be missed and doesn't misalign the header rows. */}
      <ModeStrip />
      <div className={styles.shell}>
        <Sidebar />
        <div className={styles.main}>
          <TopBar />
          <main className={styles.content}>
            <StaleNotice />
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
