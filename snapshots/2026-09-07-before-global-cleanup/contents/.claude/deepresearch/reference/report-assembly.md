# Report Assembly: Progressive File Generation

## Length Requirements by Mode

| Mode | Target Words | Description |
|------|--------------|-------------|
| Quick | 2,000-4,000 | Baseline quality threshold |
| Standard | 4,000-8,000 | Comprehensive analysis |
| Deep | 8,000-15,000 | Thorough investigation |
| UltraDeep | 15,000-20,000+ | Maximum rigor (at output limit) |

---

## Output Token Safeguard

**Claude Code default limit:** 32,000 output tokens (~24,000 words total per execution)

**Practical limits:**
- Target <=20,000 words total output
- Leave safety margin for tool call overhead
- Reports >20,000 words require auto-continuation (see continuation.md)

---

## Progressive Section Generation

**Core Strategy:** Generate and write each section individually using Write/Edit tools. This allows unlimited report length while keeping each generation manageable.

### Phase 8.1: Setup

```bash
# Resolve the output destination first. The script walks upward from the current
# workspace to discover an Obsidian PARA vault and prints both paths as JSON.
python scripts/resolve_output_paths.py --cwd "$(pwd)" --topic "[TopicName]"

# Create the reader-facing destination returned as deliverable_dir.
mkdir -p [deliverable-folder]

# Initialize markdown file with frontmatter
# Path: [deliverable-folder]/research_report_[YYYYMMDD]_[slug].md
```

### Phase 8.2: Section Generation Loop

**Pattern:** Generate section -> Write/Edit to file -> Move to next section
Each Write/Edit call contains ONE section (<=2,000 words per call)

**Initialize research run (persist to disk):**
```bash
# Create run manifest and evidence files outside the Obsidian vault when one is in scope.
# Use [evidence-run-folder] for that location; otherwise it may be [deliverable-folder].
python scripts/citation_manager.py init-run --out-dir [evidence-run-folder] --query "[question]" --mode [mode]
# Creates: run_manifest.json, sources.jsonl, evidence.jsonl, claims.jsonl
```

**Register each source as you encounter it:**
```bash
python scripts/citation_manager.py register-source \
  --json '{"raw_url": "...", "title": "...", "source_type": "academic", "year": "2024"}' \
  --dir [folder]
# Returns stable source_id (sha256-based, survives renumbering and continuation)
```

**Assign display numbers after all sources registered:**
```bash
python scripts/citation_manager.py assign-display-numbers --dir [folder]
# Maps stable source_ids to [1], [2], [3]... for rendering
```

Source identity is stable across edits and continuation. Display numbers are derived at render time, never stored in state. This survives context compaction and enables continuation agents to pick up citation state via stable IDs.

**Section sequence:**

1. **Executive Summary** (200-400 words)
   - Tool: Write(file, frontmatter + Executive Summary)
   - Track citations
   - Progress: "Executive Summary complete"

2. **Introduction** (400-800 words)
   - Tool: Edit(file, append Introduction)
   - Track citations
   - Progress: "Introduction complete"

3. **Finding 1-N** (600-2,000 words each)
   - Tool: Edit(file, append Finding N)
   - Track citations
   - Progress: "Finding N complete"

4. **Synthesis & Insights**
   - Novel insights beyond source statements
   - Tool: Edit(append)

5. **Limitations & Caveats**
   - Counterevidence, gaps, uncertainties
   - Tool: Edit(append)

6. **Recommendations**
   - Immediate actions, next steps, research needs
   - Tool: Edit(append)

7. **Bibliography** (CRITICAL)
   - EVERY citation from citations_used list
   - NO ranges, NO placeholders, NO truncation
   - Tool: Edit(append)

8. **Methodology Appendix**
   - Research process, verification approach
   - Tool: Edit(append)

---

## File Organization

**1. Create dedicated reader-facing folder:**
- In an Obsidian vault: `[vault]/300_Resources/Res_调研/[TopicName]_Research_[YYYYMMDD]/`
- Outside an Obsidian vault: `~/Documents/[TopicName]_Research_[YYYYMMDD]/`
- Clean topic name (remove special chars, use underscores). Preserve all readable reports in this folder.

**2. File naming convention:**
All files use same base name:
- `research_report_20251104_topic_slug.md`
- `research_report_20251104_topic_slug.html`
- `research_report_20251104_topic_slug.pdf`

**3. Evidence and run state:** keep source registries, evidence, claims, manifests, temporary render files, and continuation state in an external run folder. Do not mirror them into the Vault merely for convenience.

---

## Word Count Per Section

**CRITICAL:** No single Edit call should exceed 2,000 words.

Example: 10 findings x 1,500 words = 15,000 words total
- Each Edit call: 1,500 words (under limit)
- File grows to 15,000 words
- No single tool call exceeds limits
