import type { ButtonHTMLAttributes } from 'react';

import styles from './Button.module.css';

export function Button({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={[styles.button, className].filter(Boolean).join(' ')}
      {...props}
    />
  );
}
