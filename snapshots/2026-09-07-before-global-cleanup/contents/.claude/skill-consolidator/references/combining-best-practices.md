# Combining Skills: duplication, organization, and best practices

## Guiding principles

- **Prefer small, composable skills** over one “mega skill”.
- Consolidation is primarily about:
  - Removing duplicate prose
  - Standardizing naming and triggers
  - Creating a clear routing structure (hub -> leaf)
  - Making “the best version” easy to find

## Duplication (safe workflow)

1. Keep the installed directory read-only (treat it as the “upstream” source of truth).
2. Copy any skill you plan to change into this repo’s `skills/`.
3. Make changes only in this repo; later, decide what to package/install.

### Recommended folder split

- `skills/` (first-party) for the consolidated result you actually want to maintain and install
- Prefer reading upstream skills from `~/.agents/skills/` (read-only) instead of copying them into this repo.

## Organization patterns (recommended)

### Pattern A: Canonical skill + deprecated stubs

Use when 2+ skills do the same job.

- Pick one canonical skill name (prefer the one users already type).
- Keep old skill folders, but update their `description` to:
  - Clarify they are deprecated
  - Point to the canonical skill name
  - Narrow their triggers to avoid competing with the canonical skill

### Pattern B: Hub skill + leaf skills

Use when multiple skills share a domain but differ in execution.

- Create a hub skill with:
  - A tight decision tree (“if the task is X, use skill Y”)
  - Links to the leaf skills
- Keep leaf skills focused and reusable.

### Pattern C: Shared references (progressive disclosure)

Use when multiple skills have identical sections (best practices, setup steps, checklists).

- Move shared content into a single canonical `references/` file.
- Link to it from each relevant `SKILL.md`.

If you want cross-skill sharing within this repo, create:

- `skills/_shared/references/<topic>.md`

Then reference it from multiple skills with relative links.

## Best practices for combining overlapping content

- **Keep frontmatter minimal**: only `name` and `description`.
- **Don’t break triggers accidentally**:
  - A small change in `description` can change which skill triggers.
  - When deprecating, narrow triggers instead of leaving them broad.
- **Prefer our defaults when picking “canonical”**:
  - When the overlap is between two “equally good” skills, consolidate toward the version aligned with `skills/skill-consolidator/references/opinionated-defaults.md`.
- **Normalize vocabulary**:
  - Use the same words for the same concepts (“E2E”, “Playwright”, “browser automation”).
  - Add synonyms to `description` (that’s what the router uses).
- **Prefer links over copy/paste**:
  - If two skills need the same long section, pick one canonical location.
- **Avoid deep dependency chains**:
  - Keep links one hop deep so the agent doesn’t have to chase references endlessly.
- **Keep the user in the loop**:
  - Produce a short merge plan before applying large restructures.
  - Apply changes in small batches (one cluster at a time).

## Acceptance checklist for a consolidation PR

- A report exists that explains why skills were merged/deprecated.
- The canonical skill’s `description` includes the common trigger phrases.
- Deprecated skills point to the canonical skill and have narrowed triggers.
- Shared content is extracted into `references/` (no duplicated long sections).
- Links are relative and work in-repo.
