# Review + decommission (second-agent, then human)

## Goal

Make consolidation safe:

- Catch lost capability before it ships
- Avoid trigger collisions
- Keep the whole change reversible

## Second-agent review (required)

Run a second agent as a strict reviewer. They should not “help implement” — only review and flag risks.

### Inputs the reviewer must inspect

- The upstream source skills (typically in `~/.agents/skills/<...>/SKILL.md`)
- The new canonical skill (`skills/<canonical-skill>/SKILL.md`)
- Any extracted references (`skills/<canonical-skill>/references/*`)
- The overlap report: `tmp/skill-consolidator/overlap_report.md`

### Reviewer checklist (go/no-go)

- **Coverage:** canonical skill still covers the important use cases from upstream
- **Routing:** `description` includes the real-world trigger phrases and is not overly broad
- **Collisions:** no other skill in-repo will compete for the same triggers (or it’s intentional)
- **Links:** “See also” links are direct (no deep reference chains)
- **Progressive disclosure:** long content moved to `references/` instead of bloating `SKILL.md`
- **Reversibility:** upstream sources are still present (or archived), not deleted

### Copy/paste prompt for the second agent

```
Act as a strict reviewer of a skill consolidation.

Review:
- Upstream installed skills in `~/.agents/skills/` relevant to the consolidation
- The new canonical skill in `skills/<canonical-skill>/`
- `tmp/skill-consolidator/overlap_report.md`

Output:
1) Go/No-go
2) Top 5 risks or missing coverage items
3) Trigger-collision concerns (if any)
4) Specific recommended edits (file + section names, not full rewrites)
```

## Human check (recommended default)

After the second-agent review is “Go”:

- Read the canonical `description` and confirm it matches how you actually talk to the agent.
- Spot-check 2–3 example prompts you’d use and confirm the canonical skill would route correctly.
- Confirm old skills won’t compete (either archived, or their SKILL.md removed/renamed, or triggers narrowed).

## Decommission (safe + reversible)

Do **not** delete upstream skills immediately.

Preferred options (in order):

1. **Disable triggering in any local copies**
   - Remove/rename `SKILL.md` files in any copied skill folders so they can’t trigger.
3. **Deprecate in first-party copies (only if you must keep them)**
   - Narrow triggers in `description`
   - Add a short pointer to the canonical skill

## Acceptance criteria (before you “consider it done”)

- Second-agent review says **Go**
- Human check completed
- Canonical skill has a clear “See also” section or internal routing
- Local copies (if any) are archived/disabled, not deleted
- Scanner + tests still pass
