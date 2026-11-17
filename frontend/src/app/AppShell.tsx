import { useState } from 'react';
import { Outlet, useLocation } from 'react-router';

import { StaleNotice } from '../components/StaleNotice';
import styles from './AppShell.module.css';
import { ModeStrip } from './ModeStrip';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function AppShell() {
  // Below 1024 px the sidebar is a drawer, opened from the top bar's menu button. It is
  // open only on the path it was opened from, so following a link closes it.
  const location = useLocation();
  const [openedOn, setOpenedOn] = useState<string | null>(null);
  const navOpen = openedOn === location.pathname;
  const setNavOpen = (open: boolean) => setOpenedOn(open ? location.pathname : null);

  return (
    <div className={styles.frame}>
      {/* Spans the full width so it can't be missed and doesn't misalign the header rows. */}
      <ModeStrip />
      <div className={styles.shell}>
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
        <div className={styles.main}>
          <TopBar onOpenNav={() => setNavOpen(true)} />
          <main className={styles.content}>
            <StaleNotice />
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
