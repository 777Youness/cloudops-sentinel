/** Formatting rules from docs/design-system.md. */
import type { KeySignal, SignalName, Unit } from '../api/types';

export function formatUtc(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${hh}:${mm} UTC`;
}

export function formatUtcFull(iso: string): string {
  return new Date(iso)
    .toISOString()
    .replace('T', ' ')
    .replace(/\.\d+Z$/, ' UTC');
}

export function formatRelative(iso: string, nowMs: number): string {
  const seconds = Math.max(0, Math.round((nowMs - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return 'less than a minute ago';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} days ago`;
}

export function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function formatValue(value: number, unit: Unit): string {
  switch (unit) {
    case 'percent':
      return `${value.toFixed(1)}%`;
    case 'ms':
      return `${Math.round(value).toLocaleString('en-US')} ms`;
    case 'per_minute':
      return `${Math.round(value)}/min`;
    case 'credits':
      return `${value.toFixed(1)} credits`;
    case 'count':
      return String(Math.round(value));
  }
}

export function formatSignalValue(signal: KeySignal): string {
  return formatValue(signal.value, signal.unit);
}

/** A threshold or axis value: no needless decimals (90%, 5 credits, 540 ms). */
export function formatLimit(value: number, unit: Unit): string {
  const n = Number.isInteger(value) ? String(value) : value.toFixed(1);
  switch (unit) {
    case 'percent':
      return `${n}%`;
    case 'ms':
      return `${Math.round(value).toLocaleString('en-US')} ms`;
    case 'per_minute':
      return `${n}/min`;
    case 'credits':
      return `${n} cr`;
    case 'count':
      return n;
  }
}

export const SIGNAL_LABELS: Record<KeySignal['signal'], string> = {
  cpu_utilization: 'CPU',
  cpu_credit_balance: 'CPU credits',
  memory_used: 'Memory',
  status_check_failed: 'Status check',
  latency_p95: 'p95 latency',
  error_rate_5xx: '5xx rate',
  request_rate: 'Requests',
};

/** Full signal names, for chart titles and table headers. */
export const SIGNAL_TITLES: Record<SignalName, string> = {
  cpu_utilization: 'CPU utilization',
  cpu_credit_balance: 'CPU credit balance',
  memory_used: 'Memory utilization',
  status_check_failed: 'EC2 status check',
  latency_p95: 'p95 latency',
  error_rate_5xx: '5xx error rate',
  request_rate: 'Request rate',
};

export function formatPeriod(seconds: number): string {
  return seconds % 60 === 0 ? `${seconds / 60} min` : `${seconds} s`;
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
