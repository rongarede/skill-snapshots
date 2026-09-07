# Opinionated defaults (from `serp-starter`)

Use these defaults to pick a “canonical” skill when consolidating overlaps (or to decide when to create a hub + leaf structure).

## Preferred product stack

- **Runtime/UI**: Next.js App Router + React + Tailwind CSS + shadcn/ui.
- **Hosting/runtime target (planned)**: Cloudflare via OpenNext adapter (Next.js on Workers).
- **Data (planned)**: Cloudflare D1 (SQLite) + Drizzle ORM + Drizzle Kit migrations.
- **Storage (planned)**: Cloudflare R2.
- **Auth (planned)**: Better Auth.
- **Payments (planned)**: Stripe.
- **Docs**: Fumadocs + MDX in `docs/`.

## Preferred testing + code health

- **Unit tests**: Vitest.
- **E2E/smoke**: Playwright.
- **SRE/code health tools**:
  - jscpd (duplicate code detection / refactor targeting)
  - dependency-cruiser (dependency graph rules: cycles/layering/forbidden imports)
  - react-scan (React render hotspots)

## Preferred developer workflow

- **Node**: >= 20.9
- **Package manager**: pnpm (>= 10)
- **Quality gates**: lint + typecheck + tests + secret scan via git hooks (lefthook in `serp-starter`)

## How to apply these in skill consolidation

- If multiple skills cover the same domain area, prefer the one that matches these defaults (or merge toward them).
- If a domain has multiple viable variants (e.g., auth), keep a small hub skill that routes to leaf skills; mark the preferred leaf as “default”.
- When extracting shared content, keep the canonical version aligned with these defaults so future work converges instead of diverging.

