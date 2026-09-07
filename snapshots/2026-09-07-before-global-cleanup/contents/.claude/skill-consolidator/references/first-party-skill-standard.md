# First-party skill standard (required)

This is the checklist for what must exist in a first-party skill created via consolidation.

## 1) Required folder shape

```
skills/<skill-name>/
├── SKILL.md
└── references/ (required when content is non-trivial)
    └── ...
```

Add `scripts/` only when it prevents repeated manual work and can be tested.

## 2) SKILL.md frontmatter rules (strict)

- Frontmatter must contain **only**:
  - `name: ...`
  - `description: ...`
- No other frontmatter keys.

## 3) Description rules (this is the router)

The `description` must:

- Say what the skill does in one line
- Include trigger phrases people actually type (“use when asked to …”)
- Define what it does **not** cover if it could collide with other skills
- Prefer specificity over breadth (avoid stealing unrelated tasks)

## 4) Required SKILL.md sections (minimum)

Every first-party skill must include:

1. **When to Use This Skill** (must be the first section after the `#` title)
2. **Purpose** (1–3 bullets)
3. **Quick routing** (a decision list that links to reference files)
4. **Non‑negotiables** (guardrails that prevent common failures)
5. **Verification** (what to run/check before calling it “done”)
6. **Provenance** (which upstream skills it consolidated)

### “When to Use” structure (recommended)

Inside `## When to Use This Skill`, prefer two subsections:

1. **Mentions / keywords** (explicit words the user says: product names, file types, frameworks)
2. **Context** (what the user is trying to do, regardless of exact keywords)

## 5) Progressive disclosure rules

- Keep `SKILL.md` short (procedural + routing).
- Move long guidance into `references/`.
- Avoid copy/paste duplication across skills; prefer linking to shared references.

## 6) Scripts + tests (SRE/TDD expectations)

If you add any `scripts/`:

- Add a test file (or extend an existing one) so changes are safe.
- Prefer deterministic, offline behavior unless the script’s purpose is networked.
- Don’t write artifacts into `/tmp`; write into `./tmp/` in the repo.

## 7) Verification expectations (before installing globally)

At minimum:

- The skill reads cleanly and links resolve within the repo.
- Any script tests pass.
- The consolidation didn’t introduce trigger collisions (review the `description` carefully).

Recommended:

- Run the overlap scanner on the relevant upstream root (by default: globally installed skills) and confirm the cluster is addressed.
- Second-agent review + human check (per `review-and-decommission.md`).

## 8) Template (copy/paste)

Use this as a starting point when creating a new first-party skill:

```md
---
name: <skill-name>
description: <One-line what it does>. Use when asked to "<trigger phrase 1>", "<trigger phrase 2>", ... Also use when <context>. Avoid using for <common collision case>.
---

# <Title>

## When to Use This Skill

Use this skill when the user:

### Mentions / keywords

- Mentions “<keyword 1>”, “<keyword 2>”, or “<keyword 3>”
- References `<file.ext>` or `<library-name>`

### Context

- Is trying to <achieve outcome A>
- Is trying to <achieve outcome B>

## Purpose

- ...

## Quick routing

- **If X** → See `references/x.md`
- **If Y** → See `references/y.md`

## Non-negotiables

- ...

## Verification

- ...

## Provenance

- Consolidated from: `<upstream-skill-1>`, `<upstream-skill-2>`
```
