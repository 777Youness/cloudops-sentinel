import type { Fact, MetricSeries } from '../../api/types';
import { annotationsFor, prepareSeries, timeDomain, timeTicks, valueDomain } from './chartData';

const T0 = Date.UTC(2026, 9, 12, 13, 0);
const iso = (minutes: number) => new Date(T0 + minutes * 60_000).toISOString();

function series(minutes: number[], values?: number[]): MetricSeries {
  return {
    resource_id: 'r-1',
    signal: 'cpu_utilization',
    unit: 'percent',
    statistic: 'Average',
    period_seconds: 60,
    source: 'test',
    points: minutes.map((m, i) => ({ t: iso(m), v: values?.[i] ?? 40 })),
  };
}

describe('prepareSeries', () => {
  it('keeps every datapoint and reports no gap when the series is complete', () => {
    const s = series([0, 1, 2, 3]);
    const { points, missing } = prepareSeries(s, timeDomain([s])!);
    expect(points.map((p) => p.v)).toEqual([40, 40, 40, 40]);
    expect(missing).toBe(0);
  });

  it('breaks the line at a gap with null, never 0 and never an interpolated value', () => {
    const s = series([0, 1, 4, 5], [10, 20, 80, 90]);
    const { points, missing } = prepareSeries(s, timeDomain([s])!);
    expect(points.map((p) => p.v)).toEqual([10, 20, null, 80, 90]);
    expect(points.some((p) => p.v === 0)).toBe(false);
    expect(missing).toBe(2); // minutes 2 and 3
  });

  it('counts missing periods before and after the series within the shared domain', () => {
    const domain: [number, number] = [T0, T0 + 10 * 60_000];
    expect(prepareSeries(series([3, 4, 5]), domain).missing).toBe(3 + 5);
  });

  it('treats an empty series as entirely missing', () => {
    const domain: [number, number] = [T0, T0 + 4 * 60_000];
    expect(prepareSeries(series([]), domain)).toEqual({ points: [], missing: 5 });
  });
});

describe('axes', () => {
  it('uses round UTC ticks', () => {
    const ticks = timeTicks([T0 + 7 * 60_000, T0 + 97 * 60_000]);
    expect(ticks.length).toBeLessThanOrEqual(7);
    expect(ticks.every((t) => (t / 60_000) % 15 === 0)).toBe(true);
  });

  it('fixes percent at 0-100 and keeps the threshold inside other ranges', () => {
    expect(valueDomain('percent', 'cpu_utilization', [97], [90]).domain).toEqual([0, 100]);
    // a 0-100 scale would flatten a 5% threshold into the axis
    const errors = valueDomain('percent', 'error_rate_5xx', [8.1], [5]);
    expect(errors.domain).toEqual([0, 10]);
    const latency = valueDomain('ms', 'latency_p95', [400], [540]);
    expect(latency.domain[0]).toBe(0);
    expect(latency.domain[1]).toBeGreaterThanOrEqual(540);
  });
});

describe('annotationsFor', () => {
  it('reads threshold, baseline, peak and window from the breach fact', () => {
    const fact: Fact = {
      id: 'F2',
      kind: 'baseline_deviation',
      statement: 'p95 latency at or above 532 ms',
      source: 'simulator',
      resource_id: 'r-1',
      observed_at: iso(20),
      window: { start: iso(5), end: iso(20) },
      rule_id: 'R-LAT',
      signal: 'latency_p95',
      value: 1412,
      baseline: 177,
      threshold: 532,
      unit: 'ms',
      event_id: null,
    };
    expect(annotationsFor('latency_p95', [fact])).toEqual({
      threshold: 532,
      baseline: 177,
      peak: 1412,
      breaches: [{ start: T0 + 5 * 60_000, end: T0 + 20 * 60_000 }],
    });
    expect(annotationsFor('cpu_utilization', [fact]).threshold).toBeNull();
  });
});
