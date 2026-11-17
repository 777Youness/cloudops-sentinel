import type { ButtonHTMLAttributes, ReactNode } from 'react';

import styles from './Button.module.css';

type Variant = 'primary' | 'outlined' | 'soft';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary: the one main action of a view (Sync now). outlined: everything else. */
  variant?: Variant;
  /** A small leading icon (aria-hidden): the label always carries the meaning. */
  icon?: ReactNode;
}

export function Button({ className, variant = 'outlined', icon, children, ...props }: ButtonProps) {
  return (
    <button
      type="button"
      className={[styles.button, styles[variant], className].filter(Boolean).join(' ')}
      {...props}
    >
      {icon && (
        <span className={styles.icon} aria-hidden="true">
          {icon}
        </span>
      )}
      {children}
    </button>
  );
}
