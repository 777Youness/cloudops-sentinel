# ADR 0011 — CSS Modules and design tokens

- Status: accepted
- Date: 2026-09-23

## Context
The console must look like deliberate engineering software, not a template.

## Decision
Styling uses CSS Modules plus CSS custom properties defined in `tokens.css`. Components
never use raw colors, ad-hoc font sizes or shadows.

## Alternatives considered
- Tailwind: fast, but encourages template-looking defaults and hides the design system.
- A component library: a strong visual identity that isn't ours.

## Consequences
More CSS to write; the design system is explicit and reviewable.
