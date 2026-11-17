# ADR 0020 — A light, card-based dashboard look, without a UI library

- Status: accepted (2026-11-17). Amends the visual values of ADR 0011 and CLAUDE.md section 9.
- Date: 2026-11-17

## Context
The owner wants CloudOps Sentinel to look like a polished cloud observability SaaS
dashboard, using the free Minimal UI kit (`minimal-ui-kit/material-kit-react`, MIT, © 2021
Minimal UI) as the visual reference. That kit is built on MUI 7, Emotion, iconify,
ApexCharts, simplebar and more. CLAUDE.md section 5 forbids UI component libraries, and
ADR 0011 chose CSS Modules and tokens. Section 9 also forbade shadows on content and any
radius above 4 px, which is exactly what defines that look.

## Decision
Keep the architecture, change the visual language.
- **No MUI and no template code.** The look is rebuilt with the existing CSS Modules and
  tokens. Nothing is copied from the kit (no source files, components, theme files, fonts or
  images), so there is no license notice to carry. The kit is only a visual reference.
- **One new dependency, already approved:** `lucide-react` (CLAUDE.md section 5, "a few
  meaningful icons"). Fonts stay IBM Plex (the 700 weight file of the installed package).
- **Light theme, card surfaces**: page `#F6F7F9`, white cards with 16 px radius and one soft
  shadow token, grey table heads, dashed row separators, soft tinted status labels, a dark
  primary button, 24 px bold page titles, 32 px metric values.
- **Sentinel identity**: the shield mark and the "Sentinel blue" accent `#0C68E9`. The kit's
  green primary was not used because green already means "ok": the accent must never look
  like a status.
- **Accessibility**: every text color is at least 4.5:1 (computed); status words use dark
  "text" shades on 16 % tints, never the bright marks.
- **Kept rules**: no gradients, glassmorphism, glow, blobs, nested cards, emoji, decorative
  icons, marketing copy or chart animations; color encodes state only; solid = observed,
  dashed = inferred; severity is always a word.
- **New shared components**: `Card`, `PageHeader`, `Label`, `Table.module.css`; `Button`
  gains `primary`, `outlined` and `soft` variants. Below 1024 px the sidebar is a drawer.

## Alternatives considered
- **Adopt MUI from the kit**: closest to the reference, but three or more new runtime
  packages, a second styling system next to CSS Modules, a heavier bundle and a rewrite of
  most components and tests. Rejected: the look does not require the library.
- **Polish within the old rules** (dark, 4 px radius, no shadows): least change, but not the
  requested dashboard look.

## Consequences
- API clients, generated types, Query hooks, routing, and every test assertion are
  unchanged; the redesign is styles, layout and a few presentational components.
- The dark theme is gone; a dark mode would be a token set under a media query (not built).
- Icons appear only next to text, in navigation, metric cards and buttons.
