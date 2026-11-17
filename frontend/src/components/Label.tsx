import type { ReactNode } from 'react';

import styles from './Label.module.css';

export type LabelTone = 'ok' | 'warn' | 'crit' | 'info' | 'unknown' | 'accent' | 'neutral';

/**
 * A soft, rounded status label. Always text: the tone reinforces the word, it never
 * replaces it (CLAUDE.md section 9: color encodes state, never color alone).
 */
export function Label({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: LabelTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={[styles.label, styles[tone], className].filter(Boolean).join(' ')}>
      {children}
    </span>
  );
}
