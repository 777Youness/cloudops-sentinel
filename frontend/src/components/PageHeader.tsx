import type { ReactNode } from 'react';

import styles from './PageHeader.module.css';

interface PageHeaderProps {
  title: ReactNode;
  titleId: string;
  /** One line under the title: what this page answers (docs/screens.md). */
  description?: ReactNode;
  /** Above the title, e.g. a link back to the list. */
  eyebrow?: ReactNode;
  /** Labels or actions on the right. */
  action?: ReactNode;
}

export function PageHeader({ title, titleId, description, eyebrow, action }: PageHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.text}>
        {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
        <h1 id={titleId} className={styles.title}>
          {title}
        </h1>
        {description && <p className={styles.description}>{description}</p>}
      </div>
      {action && <div className={styles.action}>{action}</div>}
    </header>
  );
}
