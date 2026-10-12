/**
 * Turns an incident's stored evidence into chart-ready data. Pure functions, no React.
 *
 * Integrity rules (docs/design-system.md, "Charts"):
 *  - a missing period becomes a `null` point, so the line breaks; it is never interpolated
 *    and never 0;
 *  - thresholds, baselines and breach windows come from the stored facts; the UI never
 *    decides on its own whether a value breaches.
 */
import type { Fact, Incident, MetricSeries, SignalName, Unit } from '../../api/types';

export interface ChartPoint {
  t: number; // epoch ms
  v: number | null; // null = no datapoint for this period
}

export interface PreparedSeries {
  points: ChartPoint[];
  missing: number; // periods without a datapoint inside the time domain
}

export type TimeDomain = [number, number];

const ms = (iso: string) => new Date(iso).getTime();

/** Earliest and latest datapoint across every evidence series: the shared time axis. */
export function timeDomain(series: MetricSeries[]): TimeDomain | null {
  let start = Infinity;
  let end = -Infinity;
  for (const s of series) {
    for (const p of s.points) {
      const t = ms(p.t);
      if (t < start) start = t;
      if (t > end) end = t;
    }
  }
  return Number.isFinite(start) ? [start, end] : null;
}

/**
 * Points in time order, with a null inserted after every datapoint that is followed by a
 * gap longer than one period. Missing periods are counted over the whole time domain,
 * including before the first and after the last datapoint.
 */
export function prepareSeries(series: MetricSeries, domain: TimeDomain): PreparedSeries {
  const period = series.period_seconds * 1000;
  const sorted = [...series.points].sort((a, b) => ms(a.t) - ms(b.t));
  const points: ChartPoint[] = [];
  let missing = 0;

  if (sorted.length === 0) {
    return { points, missing: Math.floor((domain[1] - domain[0]) / period) + 1 };
  }
  missing += Math.max(0, Math.round((ms(sorted[0]!.t) - domain[0]) / period));

  sorted.forEach((p, i) => {
    const t = ms(p.t);
    points.push({ t, v: p.v });
    const next = sorted[i + 1];
    if (next) {
      const skipped = Math.round((ms(next.t) - t) / period) - 1;
      if (skipped > 0) {
        missing += skipped;
        points.push({ t: t + period, v: null }); // one null is enough to break the line
      }
    }
  });

  missing += Math.max(0, Math.round((domain[1] - ms(sorted.at(-1)!.t)) / period));
  return { points, missing };
}

const TICK_STEPS_MIN = [5, 10, 15, 30, 60, 120];

/** Round UTC ticks (every 5, 10, 15, 30, 60 or 120 min), at most `maxTicks` of them. */
export function timeTicks(domain: TimeDomain, maxTicks = 7): number[] {
  const span = domain[1] - domain[0];
  const stepMin =
    TICK_STEPS_MIN.find((m) => span / (m * 60_000) <= maxTicks - 1) ?? TICK_STEPS_MIN.at(-1)!;
  const step = stepMin * 60_000;
  const ticks: number[] = [];
  for (let t = Math.ceil(domain[0] / step) * step; t <= domain[1]; t += step) ticks.push(t);
  return ticks;
}

/** A "nice" upper bound: 1, 2, 2.5 or 5 times a power of ten. */
function niceCeil(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const nice = [1, 2, 2.5, 5, 10].find((m) => m * power >= value)!;
  return nice * power;
}

/**
 * Y range. Utilization percentages (CPU, memory) are fixed at 0-100 so they compare at a
 * glance; the status check is 0-1; everything else, including the 5xx rate (whose 2-5%
 * thresholds would vanish on a 0-100 scale), starts at 0 and always includes the
 * reference lines.
 */
export function valueDomain(unit: Unit, signal: SignalName, values: number[], refs: number[]) {
  if (unit === 'percent' && signal !== 'error_rate_5xx') {
    return { domain: [0, 100] as [number, number], ticks: [0, 50, 100] };
  }
  if (signal === 'status_check_failed')
    return { domain: [0, 1] as [number, number], ticks: [0, 1] };
  const top = niceCeil(Math.max(0, ...values, ...refs) * 1.1);
  return { domain: [0, top] as [number, number], ticks: [0, top / 2, top] };
}

const BREACH_KINDS: Fact['kind'][] = ['threshold_breach', 'baseline_deviation'];

export interface Annotations {
  threshold: number | null;
  baseline: number | null;
  peak: number | null;
  breaches: { start: number; end: number }[];
}

/** Reference lines and breach windows for one signal, read from its breach facts. */
export function annotationsFor(signal: SignalName, facts: Fact[]): Annotations {
  const breaches = facts.filter((f) => f.signal === signal && BREACH_KINDS.includes(f.kind));
  const latest = breaches.at(-1);
  return {
    threshold: latest?.threshold ?? null,
    baseline: latest?.baseline ?? null,
    peak: latest?.value ?? null,
    breaches: breaches
      .filter((f) => f.window)
      .map((f) => ({ start: ms(f.window!.start), end: ms(f.window!.end) })),
  };
}

export interface Marker {
  t: number;
  kind: 'deployment' | 'opened' | 'resolved';
  label: string;
}

/** Vertical markers shared by every chart: deployments (event facts), opened, resolved. */
export function markersFor(incident: Incident): Marker[] {
  const markers: Marker[] = incident.facts
    .filter((f) => f.kind === 'event')
    .map((f) => ({ t: ms(f.observed_at), kind: 'deployment', label: f.statement }));
  markers.push({ t: ms(incident.first_detected_at), kind: 'opened', label: 'Incident opened' });
  if (incident.resolved_at) {
    markers.push({ t: ms(incident.resolved_at), kind: 'resolved', label: 'Incident resolved' });
  }
  return markers.sort((a, b) => a.t - b.t);
}

const SIGNAL_ORDER: SignalName[] = [
  'cpu_utilization',
  'cpu_credit_balance',
  'memory_used',
  'status_check_failed',
  'request_rate',
  'error_rate_5xx',
  'latency_p95',
];

/**
 * Primary charts: signals with a breach fact (in fact order), plus request rate when an
 * application rule is involved, because R-5XX and R-LAT depend on traffic.
 * Every other evidence series is secondary.
 */
export function chartSignals(incident: Incident): { primary: SignalName[]; other: SignalName[] } {
  const available = new Set(incident.evidence.series.map((s) => s.signal));
  const primary: SignalName[] = [];
  for (const f of incident.facts) {
    if (f.signal && BREACH_KINDS.includes(f.kind) && !primary.includes(f.signal)) {
      primary.push(f.signal);
    }
  }
  const appRules = incident.rule_ids.some((r) => r === 'R-5XX' || r === 'R-LAT');
  if (appRules && available.has('request_rate') && !primary.includes('request_rate')) {
    primary.push('request_rate');
  }
  const other = SIGNAL_ORDER.filter((s) => available.has(s) && !primary.includes(s));
  return { primary: primary.filter((s) => available.has(s)), other };
}
