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
| Health unknown | Hollow ring (shape means "no data") — Day 2 |

Severity is always text plus color, never color alone.

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

## Review checklist

Reject: gradients, glass, glow, blobs, cards inside cards, radius > 4 px, decorative icons,
hero-sized headings, color without a state meaning, charts that answer no question, copy
that could belong to any SaaS product.
