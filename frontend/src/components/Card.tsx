import type { ReactNode } from 'react';

import styles from './Card.module.css';

interface CardProps {
  /** Section title, rendered as an h2 that labels the card's region. */
  title?: ReactNode;
  titleId?: string;
  subheader?: ReactNode;
  action?: ReactNode;
  /** Content that runs edge to edge (tables): no inner padding. */
  flush?: boolean;
  className?: string;
  children: ReactNode;
  'aria-label'?: string;
}

/**
 * A white surface on the page (ADR 0020). One level only: a card never contains a card,
 * so grouping inside a card uses rules and spacing, not nested boxes.
 */
export function Card({
  title,
  titleId,
  subheader,
  action,
  flush,
  className,
  children,
  'aria-label': ariaLabel,
}: CardProps) {
  return (
    <section
      className={[styles.card, className].filter(Boolean).join(' ')}
      aria-labelledby={title && titleId ? titleId : undefined}
      aria-label={ariaLabel}
    >
      {(title || action) && (
        <header className={styles.header}>
          <div className={styles.heading}>
            {title && (
              <h2 id={titleId} className={styles.title}>
                {title}
              </h2>
            )}
            {subheader && <p className={styles.subheader}>{subheader}</p>}
          </div>
          {action && <div className={styles.action}>{action}</div>}
        </header>
      )}
      <div className={flush ? styles.flush : styles.body}>{children}</div>
    </section>
  );
}
