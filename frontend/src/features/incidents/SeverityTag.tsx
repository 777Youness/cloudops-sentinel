import type { Severity } from '../../api/types';
import styles from './SeverityTag.module.css';

const LABELS: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

/**
 * Severity is always text + color, never color alone.
 * critical = filled red, high = red outline, medium = amber outline, low = neutral outline.
 */
export function SeverityTag({ severity }: { severity: Severity }) {
  return <span className={`${styles.tag} ${styles[severity]}`}>{LABELS[severity]}</span>;
}
