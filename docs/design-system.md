# Design system

Tokens are implemented in `frontend/src/styles/tokens.css`. Components use tokens only.

## Principles

1. Borders and typography structure the page; boxes are rare.
2. Color means state, never decoration.
3. Solid means observed; dashed means inferred (from Day 3).
4. Every number carries a unit and, where useful, a comparison.
5. Every view designs its loading, empty, error and stale states.

## Tokens

| Group | Values |
|---|---|
| Backgrounds | `--bg #0F1113`, `--surface #15181B`, `--raised #1B1F23` |
| Borders | `--border #262B30`, `--border-strong #343A41` |
| Text | `--text-1 #E4E6E8`, `--text-2 #A2A9B1`, `--text-3 #7D858E` |
| Accent | `--accent #6FA3D9`: selection, links, focus, deployment markers. Never a status. |
| State | `--ok #3FAE7A`, `--warn #D9A13B`, `--crit #E0584F`, `--unknown #7A828B`, 12% tints |
| Type | IBM Plex Sans (UI), IBM Plex Mono with tabular figures (numbers, IDs, timestamps). Sizes 11/12/13 (body)/14/16/20/24; weights 400/500/600 |
| Spacing | 4, 8, 12, 16, 24, 32, 48. Page padding 24. Table rows 36 px |
| Radius | 2 px; 4 px maximum |
| Elevation | None on content; one overlay shadow |
| Motion | 120 ms color/opacity transitions; respects `prefers-reduced-motion` |

## Amendments (Day 1)

Checked against common generic-UI tells and changed from the first spec:
- Labels use **sentence case**, not all caps.
- Metadata is shown as **key–value pairs**, not strings joined with "·".
- Buttons carry **no appended arrows**.
- The simulated-data strip spans the **full window width**, above sidebar and top bar.

## Severity and health

| Value | Encoding |
|---|---|
| Critical | Filled red tag, text "Critical" |
| High | Red outline tag, text "High" |
| Medium | Amber outline tag, text "Medium" |
| Low | Neutral outline tag, text "Low" |
| Row edge | 3 px bar in the severity color on the first cell |

Severity is always text plus color, never color alone.

## Resource health (Day 2c)

Health answers "is this resource fine right now?" It is computed by the backend
(`detection/health.py`), never in the UI.

| State | Rule | Encoding |
|---|---|---|
| `crit` | Open incident of severity high or critical | Filled dot `--crit`, text "Failing" |
| `warn` | Open incident of severity medium or low | Filled dot `--warn`, text "Degraded" |
| `ok` | Datapoints present, no open incident | Filled dot `--ok`, text "Healthy" |
| `unknown` | No datapoints at all for the resource | Hollow ring `--unknown`, text "No data" |

Missing signals are always listed next to the state ("2 of 7 signals missing:
memory utilization, p95 latency"), in `--text-2`. A resource is never shown as healthy
without that note when signals are missing. The dot is 8 px; shape and text carry the
meaning, color only reinforces it.

## Charts (Day 2c)

A chart earns its place by answering an investigation question: *when did this signal
cross its threshold, relative to the other signals, to deployments and to detection?*

**Layout.** Small multiples: one chart per signal, stacked, all on the same time domain
(the incident's evidence window), with a synchronized crosshair. Chart plot height 112 px.
The x-axis tick labels appear under the last chart only. Primary charts are the incident's
rule signals, plus request rate when R-5XX or R-LAT is involved; the remaining evidence
signals sit in a collapsed "Other signals" section.

**Encoding.**

| Element | Encoding |
|---|---|
| Series | 1.5 px line, `--text-1`; status check as a step line (Passed / Failed ticks) |
| Missing data | The line **breaks**. Never interpolated, never drawn as 0. The chart header states "N missing datapoints" in `--text-2` |
| Threshold | 1 px dashed line `--text-2`, labelled "Threshold 90%" (value from the breach fact) |
| Baseline (R-LAT) | 1 px dotted line `--text-3`; its value is in the chart header (an in-plot label collides with the threshold's) |
| Breach window | Band in the incident severity's 12% tint, from the breach fact's window |
| Deployment | 1 px vertical line `--accent`, labelled "Deploy" |
| Incident opened / resolved | 1 px vertical dotted line `--text-3`, labelled "Opened" / "Resolved"; the time axis extends to include them. Labels near the right edge sit left of their line |
| Y axis | 3 ticks, unit on every tick label, Plex Mono 11 px. CPU and memory percent are fixed 0–100%; everything else (including the 5xx rate) starts at 0 and always includes the threshold |
| X axis | UTC `HH:MM`, round 5/10/15/30/60-minute steps |
| Tooltip | The one overlay: absolute time `HH:MM UTC`, value with unit, or "No data" at a gap |

No animation, no area gradients, no legends (each chart has one series; labels sit on the
lines). Each chart is a `<figure>` with a caption and an `aria-label` summary (signal,
datapoints, range, threshold, peak) for screen readers.

Charts are drawn only from the evidence stored with the incident. The UI does not decide
whether a value breaches: thresholds, peaks and windows come from facts.

## Workspace evidence panel (Day 2c)

Facts are grouped as **Observed** (breaches, baseline deviations, deployments),
**Checked and normal**, and **Data gaps**. Every fact has the solid left rule (observed),
its id in mono (`F3`), the stored statement verbatim, and when it was observed. Data-gap
facts use a `--unknown` rule. Timeline entries that cite a fact link to it (`#fact-F3`);
the linked fact is outlined in `--accent` while targeted.

## States and copy

Copy is factual and specific. No exclamation marks, no apologies, no emoji.

| State | Copy |
|---|---|
| First load | Skeleton rows shaped like the table |
| Syncing | "Syncing… 4 s" in the top bar; existing data stays visible |
| Never synced | "No data yet." + "Run a sync to collect telemetry and evaluate the detection rules." + Sync now |
| No open incidents | "No open incidents. All monitored signals are within thresholds as of 14:02 UTC." + "1 resource and 1 rule evaluated in the last sync." |
| API unreachable | "Sentinel API unreachable at 127.0.0.1:8000." + start hint + Retry |
| Concurrent sync | "A sync is already running" |
| Last sync failed | "Last sync failed 3 min ago", linking to System |
| Stale data (Day 2c) | When the last **successful** sync finished more than 15 min ago, a notice above every page: "Data last synced 42 min ago." + "Values, health and incidents may have changed since. Sync now to refresh." A failed sync does not refresh data, so it does not clear the notice |
| Refetch failed with data on screen (Day 2c) | Data stays visible; an inline error above it: "Could not refresh. Showing data from 14:02 UTC." + Retry |
| Incident not found (Day 2c) | "Incident INC-0042 not found." + "There is no incident with this ID in the local history." + link "Back to incidents" |
| Overview, never synced (Day 2c) | "No data yet." + "Run a sync to collect telemetry, evaluate the detection rules and see the health of each monitored resource." + Sync now |
| Overview, no open incidents (Day 2c) | "No open incidents." + "7 resources and 7 rules evaluated in the last sync." |

## Review checklist

Reject: gradients, glass, glow, blobs, cards inside cards, radius > 4 px, decorative icons,
hero-sized headings, color without a state meaning, charts that answer no question, copy
that could belong to any SaaS product.
