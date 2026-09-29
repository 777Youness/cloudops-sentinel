import { formatRelative, formatSignalValue, formatUtc } from './format';

describe('format', () => {
  const now = Date.parse('2026-09-23T14:30:00Z');

  it('formats relative times', () => {
    expect(formatRelative('2026-09-23T14:29:40Z', now)).toBe('less than a minute ago');
    expect(formatRelative('2026-09-23T14:16:00Z', now)).toBe('14 min ago');
    expect(formatRelative('2026-09-23T11:30:00Z', now)).toBe('3 h ago');
  });

  it('formats UTC clock time', () => {
    expect(formatUtc('2026-09-23T09:05:00Z')).toBe('09:05 UTC');
  });

  it('always shows a unit', () => {
    expect(formatSignalValue({ signal: 'cpu_utilization', value: 97.26, unit: 'percent' })).toBe(
      '97.3%',
    );
    expect(formatSignalValue({ signal: 'latency_p95', value: 1240.4, unit: 'ms' })).toBe(
      '1,240 ms',
    );
  });
});
