# Screens

| Route | Screen | Question it answers | Status |
|---|---|---|---|
| `/incidents` | Incidents | What happened, how bad, what's still open? | Day 1 (rows link to the workspace since 2c) |
| `/system` | System | Where does the data come from, and is it working? | Day 1 (minimal) |
| `/` | Overview | What's wrong right now, and can I trust this data? | Day 2c |
| `/incidents/:id` | Investigation workspace | Why did this happen, what do I check next? | Day 2c (evidence); Day 3 (investigation panel) |
| `/resources`, `/resources/:id` | Resources | What am I monitoring, how is it behaving? | Day 5 |

Cost (V2) and Drift (V3) are not routed in V1.

## Global chrome

- Simulated-data strip (local mode only), full width.
- Sidebar (208 px): wordmark; Overview; Incidents with open count; System pinned at the bottom.
- Top bar (44 px): Environment, Data (Simulated/AWS), Region; sync status; Sync now.
- Filters live in the URL (`?status=open`).
- Stale-data notice above every page when the last successful sync is older than 15 min.

## Incidents (Day 1)

Table columns: Severity, ID, Title, Resource (name + id), Key signal, Detected (UTC time +
relative), Status, Investigation. Sorted by severity, then most recent. Filter: Open
(default), Resolved, All. The ID and title link to the incident's workspace (since 2c).

## System (Day 1)

Runtime: data mode, environment, region, investigation provider, version, API contract.
Last sync: run id, outcome, start, duration, evaluated counts, incidents opened.
Data sources: source, state, last success, error code + message + hint.

## Overview (Day 2c)

1. Header "Overview" and the open-incident count by severity as an inline list of severity
   tags with mono counts (no tiles).
2. Two columns from 1280 px (stacked below):
   - **Open incidents**: the five most important (severity, then most recent): severity,
     title (link to workspace), resource, key signal, detected. Link "All open incidents".
   - **Data trust**: data origin, last sync (outcome, relative and UTC), data age with the
     stale marker, collectors and their state, resources and rules evaluated, what the last
     sync changed (opened / updated / resolved), resources with missing signals.
3. **Monitored resources** table, needing attention first (failing, degraded, no data,
   healthy): health (dot/ring + text), name + id, instance type,
   open incident (link with severity), signals (`7 of 7` or the missing ones by name).
   Resource names are not links until the Resources pages exist (Day 5).

## Investigation workspace

Built in Day 2c (evidence only):

- Header: back link "Incidents"; title; severity tag; status (Open / Resolved); key–value
  metadata: resource (name + id), region, first detected, last updated, resolved (if any),
  data origin.
- Left: signal charts (see "Charts" in the design system), then the timeline: chronological,
  UTC time + relative, entries citing a fact link to it.
- Right (sticky, 400 px): Evidence (Observed, Checked and normal, Data gaps), then metadata:
  rules, evidence hash, last updated, investigation status ("Not run").

Day 3: the right panel is Evidence, then **Investigation** (see design-system
"Investigation panel": dashed rule and "Inferred", hypotheses, next checks, remediation
tagged "Human decision" and text only, limitations, run metadata, mock label, outdated
notice), then Details. The Run button is the only control that calls a provider.
