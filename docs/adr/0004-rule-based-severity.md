# ADR 0004 — Severity and risk are rule-based; the LLM never sets them

- Status: accepted
- Date: 2026-09-23

## Context
Severity decides urgency. It must be reproducible, explainable and testable.

## Decision
Severity comes from a documented matrix in `detection/severity.py`. The LLM (Day 3) may
explain impact but cannot create facts or change severity. The same principle applies to
drift risk in V3.

## Alternatives considered
- LLM-assigned severity (as in TerraGuard-AI's risk classification): flexible, but not
  reproducible and not testable.

## Consequences
Severity has unit tests. The investigation stays useful but optional.
