import styles from './SkeletonRows.module.css';

/** Placeholder rows shaped like the table that will replace them. */
export function SkeletonRows({ columns, rows = 4 }: { columns: number; rows?: number }) {
  return (
    <tbody aria-hidden="true">
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} className={styles.row}>
          {Array.from({ length: columns }, (_, c) => (
            <td key={c} className={styles.cell}>
              <span className={styles.bar} style={{ width: `${40 + ((r * 7 + c * 13) % 45)}%` }} />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}
