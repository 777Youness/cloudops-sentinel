# ADR 0012 — Simulated data is a first-class, always-labelled mode

- Status: accepted
- Date: 2026-09-23

## Context
Most development and many scenarios cannot use live AWS (cost, or failures that can't be
triggered safely). Simulated data must never be confused with real data.

## Decision
`SimulatedSource` replays YAML scenarios relative to "now" and implements the same
interface as the AWS collector. Every entity carries `data_origin`. Local mode shows a
persistent full-width strip. Modes are exclusive; origins never mix in one incident.
Each scenario declares its expected outcome, which a test enforces.

## Alternatives considered
- Mock data inside UI components: hides the data path, easy to confuse with real data.

## Consequences
Detection tests exercise the same code path AWS mode will use.
