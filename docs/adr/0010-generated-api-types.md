# ADR 0010 — API types are generated from OpenAPI

- Status: accepted
- Date: 2026-09-23

## Context
A Python backend and a TypeScript frontend describing the same data drift apart silently.

## Decision
Pydantic models are the source of truth. `npm run gen:api` exports the OpenAPI document
without starting a server (`python -m sentinel.openapi_export`) and generates
`src/api/schema.d.ts` with openapi-typescript. Both files are committed, so contract
changes are visible in diffs. CI regenerates them and fails if they differ.

## Alternatives considered
- Hand-written TypeScript types: duplicated, drift silently.
- Generating from a running server: requires the backend to be up in CI.

## Consequences
A renamed backend field becomes a TypeScript compile error at every use site.
Requires TypeScript 5.x for now (openapi-typescript's peer range).
