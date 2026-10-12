# ADR 0014 — Workspace charts are drawn only from stored evidence; gaps stay gaps

- Status: accepted
- Date: 2026-10-12

## Context
The incident workspace needs charts that are dense enough to investigate with: several
signals on one time axis, thresholds, breach windows, deployments. Charts are also the
easiest place to lie by accident: a library that connects points across a gap, a missing
value shown as 0, or a UI that recomputes "is this breaching?" with its own logic.

## Decision
- Charts render `Incident.evidence.series`, the series stored with the incident (ADR 0013),
  never a fresh query. What the chart shows is what detection saw.
- Thresholds, baselines, peaks and breach windows come from the incident's breach facts;
  deployment markers from its `event` facts. The UI never decides whether a value breaches.
- A missing period becomes a `null` point and the line breaks (`connectNulls={false}`);
  every chart states how many datapoints are missing. Tested in `chartData.test.ts`.
- Small multiples on one shared time domain with a synchronized crosshair
  (`syncMethod="value"`), no animation, colors from tokens via CSS (design-system "Charts").
- Library: Recharts 3.10 (approved dependency; supports React 19). Its `react-is` peer
  resolves to 17.x, which only affects Recharts' deprecated child scan used by Bar, Pie,
  Scatter, Funnel and RadialBar with fragment-wrapped children. The workspace uses
  `LineChart`, `ReferenceLine` and `ReferenceArea` only.

## Alternatives considered
- One chart with several y-axes: compact, but unit-mixing makes thresholds unreadable.
- Hand-written SVG: full control, but tooltips, synchronized cursors and accessibility would
  be re-implemented; Recharts is already on the approved list for this purpose.
- Fetching live series for the chart: would show data the incident was not decided on.

## Consequences
- An incident's charts are reproducible: same stored evidence, same picture.
- If Bar or Pie charts with `<Cell>` children inside fragments are ever added, install a
  `react-is` matching React first (needs approval under the dependency policy).
