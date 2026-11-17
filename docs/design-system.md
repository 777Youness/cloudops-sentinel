# Design system

Tokens are implemented in `frontend/src/styles/tokens.css`. Components use tokens only.

Visual language since ADR 0020: a light, card-based dashboard inspired by the MIT-licensed
Minimal UI kit (no code, components or assets copied; no UI library). Sentinel keeps its
own identity: IBM Plex, "Sentinel blue" accent, the shield mark.

## Principles

1. White cards on a light page group content; one level only (no card inside a card).
2. Color means state, never decoration. The accent is never a status.
3. Solid means observed; dashed means inferred (from Day 3).
4. Every number carries a unit and, where useful, a comparison.
5. Every view designs its loading, empty, error and stale states.
6. Every text color meets WCAG AA (4.5:1) on its background.

## Tokens

| Group | Values |
|---|---|
| Backgrounds | `--bg #F6F7F9` (page), `--surface #FFFFFF` (cards, sidebar), `--raised #F2F4F7` (table heads, hover, fills) |
| Borders | `--border` / `--border-strong`: grey 145 158 171 at 20 % / 36 %; dashed rules separate rows inside cards |
| Text | `--text-1 #1C252E` (15.5:1), `--text-2 #454F5B` (8.5:1), `--text-3 #637381` (4.9:1) |
| Accent | `--accent #0C68E9` "Sentinel blue" (5.0:1), `--accent-strong #0351AB`, 8 % / 16 % tints: selection, links, focus, deployment markers. Never a status. |
| State | Marks: `--ok #22C55E`, `--warn #FFAB00`, `--crit #FF5630`, `--info #00B8D9`, `--unknown #919EAB`. Words: `--ok-text #065E49`, `--warn-text #7A4100`, `--crit-text #B71D18`, `--info-text #006C9C`. 16 % tints for soft labels |
| Primary action | `--action #1C252E` with white text (one per view: Sync now) |
| Type | IBM Plex Sans (UI), IBM Plex Mono with tabular figures (numbers, IDs, timestamps). Sizes 11/12/13/14 (body)/16/18 (card titles)/20/24 (page titles)/32 (metric values); weights 400/500/600/700 |
| Spacing | 4, 8, 12, 16, 20, 24, 32, 40, 48. Page padding 40 (16 on phones). Table rows 52 px |
| Radius | 6 px labels, 8 px buttons and nav items, 16 px cards |
| Elevation | `--shadow-card` under cards; `--shadow-overlay` for the drawer and tooltips. No other shadows |
| Icons | lucide-react, only in navigation, metric cards and buttons, always next to text (`aria-hidden`) |
| Motion | 150 ms color/background transitions; respects `prefers-reduced-motion` |

## Amendments (Day 1)

Checked against common generic-UI tells and changed from the first spec:
- Labels use **sentence case**, not all caps.
- Metadata is shown as **key–value pairs**, not strings joined with "·".
- Buttons carry **no appended arrows**.
- The simulated-data strip spans the **full window width**, above sidebar and top bar.

## Severity and health

| Value | Encoding |
|---|---|
| Critical | Filled dark red label, white text "Critical" |
| High | Soft red label, text "High" |
| Medium | Soft amber label, text "Medium" |
| Low | Soft grey label, text "Low" |
| Row edge | 4 px bar in the severity color on the first cell (Incidents table) |

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

## Investigation panel (Day 3)

The investigation is inferred, never observed, and the page must make that impossible to
miss. It sits in the workspace's right panel after Evidence and before Details.

| Element | Encoding |
|---|---|
| Section title | "Investigation" + an "Inferred" label (outline tag, `--text-2`) + provider and model in `--text-3` |
| Mock output | A notice above the findings: "Mock provider: generated by fixed rules, not a language model." |
| Summary | Body text, `--text-1` |
| Hypothesis | **Dashed** 2 px left rule `--border-strong` (inferred), id in mono (`H1`), statement, "Confidence: medium" as text (never color), citation links |
| Citation | Fact id in mono as a link to `#fact-F3` (accent), so every claim leads to its evidence |
| Next check | Same layout as a hypothesis, id `C1` |
| Remediation | Id `R1`, description, a "Human decision" tag; plain text only, never a command or a button that acts |
| Limitations | Short list, `--text-2` |
| Metadata | Key–value pairs: provider, model, ran (UTC + relative), duration, attempts, runs, evidence hash |

States and copy:

| State | Copy |
|---|---|
| Not run | "No investigation yet." + "Sends this incident's 7 facts to the mock provider and checks that every hypothesis cites them. The incident itself is not changed." + Run investigation |
| Provider not configured | "Investigation unavailable." + "The openai_compatible provider is not configured. Set SENTINEL_LLM_BASE_URL and SENTINEL_LLM_MODEL, or use the mock." (no button) |
| Loading the saved run | Skeleton lines shaped like the summary |
| Running | Button "Investigating… 4 s" (disabled); a previous result stays visible |
| Failed run | "Investigation failed." + the error message + code in mono + hint + Run again |
| Outdated | Notice: "This investigation used older evidence. The incident has changed since it ran." + Run again |
| Request refused | Inline error under the button (409 already running, 503 not configured, unreachable) |

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
