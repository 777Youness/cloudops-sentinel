/**
 * One signal of an incident, drawn from its stored evidence (docs/design-system.md, "Charts").
 * Every chart of the workspace shares the same time domain and a synchronized crosshair.
 */
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { MetricSeries, Severity, Unit } from '../../api/types';
import {
  formatLimit,
  formatPeriod,
  formatUtc,
  formatValue,
  plural,
  SIGNAL_TITLES,
} from '../../lib/format';
import {
  type Annotations,
  type Marker,
  prepareSeries,
  type TimeDomain,
  valueDomain,
} from './chartData';
import styles from './SignalChart.module.css';

const PLOT_HEIGHT = 112;
const AXIS_HEIGHT = 24;
const STATISTIC_LABEL: Record<MetricSeries['statistic'], string> = {
  Average: 'Average',
  Maximum: 'Maximum',
  p95: 'p95',
  Sum: 'Sum',
};

function tickValue(value: number, unit: Unit, isStatus: boolean): string {
  if (isStatus) return value >= 1 ? 'Failed' : 'Passed';
  return formatLimit(value, unit);
}

interface ChartTooltipProps {
  active: boolean | undefined;
  value: unknown;
  label: string | number | undefined;
  unit: Unit;
  isStatus: boolean;
}

function ChartTooltip({ active, value, label, unit, isStatus }: ChartTooltipProps) {
  if (!active || label === undefined) return null;
  let text = 'No data';
  if (typeof value === 'number') {
    text = isStatus ? (value >= 1 ? 'Failed' : 'Passed') : formatValue(value, unit);
  }
  return (
    <div className={styles.tooltip}>
      <span className="mono">{formatUtc(new Date(Number(label)).toISOString())}</span>
      <span className={`mono ${typeof value === 'number' ? '' : styles.noData}`}>{text}</span>
    </div>
  );
}

interface SignalChartProps {
  series: MetricSeries;
  /** The drawn time axis (data plus lifecycle markers). */
  domain: TimeDomain;
  /** Earliest to latest datapoint of the evidence: missing periods are counted only here. */
  dataDomain: TimeDomain;
  ticks: number[];
  annotations: Annotations;
  markers: Marker[];
  severity: Severity;
  showTimeAxis: boolean;
}

export function SignalChart({
  series,
  domain,
  dataDomain,
  ticks,
  annotations,
  markers,
  severity,
  showTimeAxis,
}: SignalChartProps) {
  const { points, missing } = prepareSeries(series, dataDomain);
  const isStatus = series.signal === 'status_check_failed';
  const values = points.flatMap((p) => (p.v === null ? [] : [p.v]));
  const refs = [annotations.threshold, annotations.baseline].filter((r) => r !== null);
  const y = valueDomain(series.unit, series.signal, values, refs);
  const latest = values.at(-1);
  const title = SIGNAL_TITLES[series.signal];
  const band = severity === 'high' || severity === 'critical' ? styles.bandCrit : styles.bandWarn;

  const summary = [
    `${title}, ${plural(values.length, 'datapoint')} from ${formatUtc(new Date(dataDomain[0]).toISOString())} to ${formatUtc(new Date(dataDomain[1]).toISOString())}`,
    annotations.threshold !== null &&
      `threshold ${formatLimit(annotations.threshold, series.unit)}`,
    annotations.peak !== null && `peak ${formatValue(annotations.peak, series.unit)}`,
    missing > 0 && plural(missing, 'missing datapoint'),
  ]
    .filter(Boolean)
    .join('; ');

  return (
    <figure className={styles.chart}>
      <figcaption className={styles.head}>
        <span className={styles.title}>{title}</span>
        <span className={styles.meta}>
          {STATISTIC_LABEL[series.statistic]}, {formatPeriod(series.period_seconds)}
        </span>
        <dl className={styles.stats}>
          {latest !== undefined && (
            <div>
              <dt>Latest</dt>
              <dd className="mono">{tickValue(latest, series.unit, isStatus)}</dd>
            </div>
          )}
          {annotations.peak !== null && (
            <div>
              <dt>{series.signal === 'cpu_credit_balance' ? 'Lowest' : 'Peak'}</dt>
              <dd className="mono">{formatValue(annotations.peak, series.unit)}</dd>
            </div>
          )}
          {annotations.threshold !== null && !isStatus && (
            <div>
              <dt>Threshold</dt>
              <dd className="mono">{formatLimit(annotations.threshold, series.unit)}</dd>
            </div>
          )}
          {annotations.baseline !== null && (
            <div>
              <dt>Baseline</dt>
              <dd className="mono">{formatValue(annotations.baseline, series.unit)}</dd>
            </div>
          )}
        </dl>
        {missing > 0 && (
          <span className={styles.missing}>{plural(missing, 'missing datapoint')}</span>
        )}
      </figcaption>
      <div
        className={styles.plot}
        role="img"
        aria-label={summary}
        style={{ height: PLOT_HEIGHT + (showTimeAxis ? AXIS_HEIGHT : 0) }}
      >
        <ResponsiveContainer
          width="100%"
          height="100%"
          initialDimension={{ width: 800, height: PLOT_HEIGHT }}
        >
          <LineChart
            data={points}
            syncId="incident-evidence"
            syncMethod="value"
            margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
            accessibilityLayer={false}
          >
            <CartesianGrid vertical={false} className={styles.grid} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={domain}
              ticks={ticks}
              tickFormatter={(t: number) =>
                formatUtc(new Date(t).toISOString()).replace(' UTC', '')
              }
              hide={!showTimeAxis}
              height={AXIS_HEIGHT}
              tickLine={false}
              axisLine={false}
              className={styles.axis}
              allowDataOverflow
            />
            <YAxis
              domain={y.domain}
              ticks={y.ticks}
              tickFormatter={(v: number) => tickValue(v, series.unit, isStatus)}
              width={64}
              tickLine={false}
              axisLine={false}
              className={styles.axis}
              allowDataOverflow
            />
            {annotations.breaches.map((b) => (
              <ReferenceArea
                key={`breach-${b.start}`}
                x1={b.start}
                x2={b.end}
                className={band}
                ifOverflow="hidden"
              />
            ))}
            {annotations.threshold !== null && !isStatus && (
              <ReferenceLine
                y={annotations.threshold}
                className={styles.threshold}
                label={{
                  value: `Threshold ${formatLimit(annotations.threshold, series.unit)}`,
                  position: 'insideTopRight',
                  className: styles.refLabel,
                }}
              />
            )}
            {annotations.baseline !== null && (
              // No in-plot label: the baseline value is in the chart header, and a second
              // label collides with the threshold's when both lines are close.
              <ReferenceLine y={annotations.baseline} className={styles.baseline} />
            )}
            {markers.map((m) => (
              <ReferenceLine
                key={`${m.kind}-${m.t}`}
                x={m.t}
                className={m.kind === 'deployment' ? styles.deploy : styles.lifecycle}
                ifOverflow="hidden"
                label={{
                  value:
                    m.kind === 'deployment'
                      ? 'Deploy'
                      : m.kind === 'opened'
                        ? 'Opened'
                        : 'Resolved',
                  // Near the right edge the label goes left of its line, so it is not clipped.
                  position:
                    m.t > domain[0] + (domain[1] - domain[0]) * 0.85
                      ? 'insideTopRight'
                      : 'insideTopLeft',
                  className: m.kind === 'deployment' ? styles.deployLabel : styles.refLabel,
                }}
              />
            ))}
            <Tooltip
              content={(props) => (
                <ChartTooltip
                  active={props.active}
                  value={props.payload?.[0]?.value}
                  label={props.label}
                  unit={series.unit}
                  isStatus={isStatus}
                />
              )}
              cursor={{ className: styles.cursor }}
              isAnimationActive={false}
            />
            <Line
              dataKey="v"
              type={isStatus ? 'stepAfter' : 'linear'}
              className={styles.line}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, className: styles.activeDot }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
