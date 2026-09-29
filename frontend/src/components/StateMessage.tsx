/**
 * Designed states for "nothing to show" and "something went wrong".
 * Left-aligned inside the content area: a console states facts, it doesn't stage a hero.
 */
import type { ReactNode } from 'react';

import { ApiError } from '../api/client';
import styles from './StateMessage.module.css';

interface EmptyStateProps {
  title: string;
  detail?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ title, detail, action }: EmptyStateProps) {
  return (
    <div className={styles.state} role="status">
      <p className={styles.title}>{title}</p>
      {detail && <p className={styles.detail}>{detail}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}

interface ErrorStateProps {
  error: unknown;
  action?: ReactNode;
}

export function ErrorState({ error, action }: ErrorStateProps) {
  const apiError = error instanceof ApiError ? error : null;
  const message = apiError?.message ?? (error instanceof Error ? error.message : 'Unknown error.');
  return (
    <div className={`${styles.state} ${styles.error}`} role="alert">
      <p className={styles.title}>{message}</p>
      {apiError?.hint && <p className={styles.detail}>{apiError.hint}</p>}
      {apiError?.code && (
        <p className={styles.code}>
          <span className="mono">{apiError.code}</span>
          {apiError.status !== null && <span className="mono"> HTTP {apiError.status}</span>}
        </p>
      )}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
