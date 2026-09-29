# ADR 0002 — Layered core with import rules enforced by a test

- Status: accepted
- Date: 2026-09-23

## Context
Detection and investigation logic must be testable without AWS or HTTP, and reusable later
(e.g. in a Lambda). AI-assisted development can quietly erode such boundaries.

## Decision
`domain/` and `detection/` (and later `investigation/`, except providers) contain no I/O.
External libraries are confined: boto3 to `collectors/aws/`, sqlite3 to `store/`, FastAPI
to `api/`, LLM HTTP calls to `investigation/providers/`. `tests/test_architecture.py`
parses every module's imports and fails on violations.

## Alternatives considered
- Convention and code review only: not verifiable, easy to break.
- A dedicated tool (import-linter): an extra dependency for ~60 lines of test code.

## Consequences
The "pure core" claim is checkable in CI. New packages must be added to the test's rules.
