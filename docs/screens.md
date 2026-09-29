# Screens

| Route | Screen | Question it answers | Status |
|---|---|---|---|
| `/incidents` | Incidents | What happened, how bad, what's still open? | Day 1 |
| `/system` | System | Where does the data come from, and is it working? | Day 1 (minimal) |
| `/` | Overview | What's wrong right now, and can I trust this data? | Day 2 (redirects to Incidents until then) |
| `/incidents/:id` | Investigation workspace | Why did this happen, what do I check next? | Day 2–3 |
| `/resources`, `/resources/:id` | Resources | What am I monitoring, how is it behaving? | Day 5 |

Cost (V2) and Drift (V3) are not routed in V1.

## Global chrome

- Simulated-data strip (local mode only), full width.
- Sidebar (208 px): wordmark; Incidents with open count; System pinned at the bottom.
- Top bar (44 px): Environment, Data (Simulated/AWS), Region; sync status; Sync now.
- Filters live in the URL (`?status=open`).

## Incidents (Day 1)

Table columns: Severity, ID, Title, Resource (name + id), Key signal, Detected (UTC time +
relative), Status, Investigation. Sorted by severity, then most recent. Filter: Open
(default), Resolved, All. Rows are not clickable until the workspace exists (Day 2).

## System (Day 1)

Runtime: data mode, environment, region, investigation provider, version, API contract.
Last sync: run id, outcome, start, duration, evaluated counts, incidents opened.
Data sources: source, state, last success, error code + message + hint.

## Investigation workspace (Day 2–3)

Header (title, severity, status, resource, region, first detected). Left: signal charts on
one shared time axis with threshold lines and deployment markers, then the timeline.
Right (sticky, 400 px): Facts (solid rule), Investigation (dashed rule, "Inferred"),
Next checks, Remediation ("Human decision"), Limitations, metadata.
