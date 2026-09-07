#!/usr/bin/env python3

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency
    yaml = None


FRONTMATTER_DELIM = "---"
DEFAULT_POLICY_PATH = Path(__file__).with_name("discovery_cleanup_policy.json")
SCRIPT_REF_RE = re.compile(r"(?:^|[\s`(\[])(scripts/[A-Za-z0-9_./-]+)", re.M)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]{1,}")


DEFAULT_POLICY = {
    "root_priority": [
        "~/.codex/skills",
        "~/.agents/skills",
        "~/.claude/skills",
        "~/.claude/plugins/marketplaces",
    ],
    "canonical_overrides": {
        "docx": "~/.codex/skills/docx",
        "pdf": "~/.codex/skills/pdf",
        "pptx": "~/.agents/skills/pptx",
        "scientific-writing": "~/.codex/skills/scientific-writing",
        "skill-creator": "~/.codex/skills/.system/skill-creator",
        "swun-thesis-docx-banshi1": "~/.codex/skills/swun-thesis-docx-banshi1",
    },
}


@dataclass(frozen=True)
class SkillInfo:
    folder_name: str
    path: str
    skill_md_path: str | None
    scan_root: str
    relative_path: str
    name: str | None
    description: str | None
    headings: list[str]
    token_set: list[str]
    frontmatter_status: str
    discoverable: bool
    quarantine_reasons: list[str]
    validation_issues: list[str]
    canonical_name: str | None
    canonical_path: str | None
    collision_count: int
    source_kind: str


def _default_skills_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser().resolve() / "skills"

    agents_skills = Path("~/.agents/skills").expanduser().resolve()
    if agents_skills.exists():
        return agents_skills

    return Path("~/.codex/skills").expanduser().resolve()


def _default_scan_roots() -> list[Path]:
    candidates = [
        Path("~/.agents/skills").expanduser().resolve(),
        Path("~/.codex/skills").expanduser().resolve(),
        Path("~/.claude/skills").expanduser().resolve(),
        Path("~/.claude/plugins/marketplaces").expanduser().resolve(),
    ]
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.exists():
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        roots.append(candidate)
    return roots


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_frontmatter(text: str) -> tuple[dict[str, str], str]:
    fm, body, _status = _extract_frontmatter_with_status(text)
    return fm, body


def _extract_frontmatter_with_status(text: str) -> tuple[dict[str, str], str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return {}, text, "missing-frontmatter"

    try:
        end_index = lines[1:].index(FRONTMATTER_DELIM) + 1
    except ValueError:
        return {}, text, "missing-frontmatter"

    fm_text = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :])

    if yaml is not None:
        try:
            data = yaml.safe_load(fm_text) or {}
        except Exception:
            return {}, body, "invalid-frontmatter"
        if not isinstance(data, dict):
            return {}, body, "invalid-frontmatter"
        fm = {}
        for key in ("name", "description"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                fm[key] = value.strip()
        return fm, body, "ok"

    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in ("name", "description") and value:
            fm[key] = value.strip('"').strip("'")
    return fm, body, "ok"


def _extract_headings(markdown: str) -> list[str]:
    headings: list[str] = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line.startswith("#"):
            continue
        heading = line.lstrip("#").strip()
        if heading:
            headings.append(heading)
    return headings


def _tokenize(*parts: str) -> set[str]:
    joined = "\n".join([p for p in parts if p])
    return set(TOKEN_RE.findall(joined.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = a.intersection(b)
    union = a.union(b)
    return len(inter) / max(1, len(union))


def _iter_skill_dirs(skills_root: Path, include_system: bool) -> Iterable[Path]:
    if not skills_root.exists():
        return []
    for p in sorted(skills_root.iterdir()):
        if not p.is_dir():
            continue
        if p.name == "_archive":
            continue
        if p.name.startswith(".") and not include_system:
            continue
        yield p


def _iter_skill_md_files(scan_root: Path, include_system: bool) -> Iterable[Path]:
    if not scan_root.exists():
        return []

    blocked = {".git", "__pycache__", "node_modules", ".venv"}
    allowed_hidden_roots = {".agents", ".cursor"}
    if include_system:
        allowed_hidden_roots.add(".system")
    for path in sorted(scan_root.rglob("SKILL.md")):
        rel_parts = path.relative_to(scan_root).parts
        if any(part in blocked for part in rel_parts):
            continue
        if rel_parts and rel_parts[0].startswith(".") and rel_parts[0] not in allowed_hidden_roots:
            continue
        yield path


def _classify_path(scan_root: Path, skill_dir: Path) -> tuple[str, list[str]]:
    rel = skill_dir.relative_to(scan_root).as_posix()
    reasons: list[str] = []
    source_kind = "local-skill"

    if ".backup-" in skill_dir.name or ".backup-" in rel or "/backup" in f"/{rel}":
        reasons.append("backup-copy")
        source_kind = "backup-copy"
    if rel.startswith("docs/") or "/docs/" in f"/{rel}":
        reasons.append("docs-copy")
        source_kind = "docs-copy"
    if rel.startswith(".agents/") or rel.startswith(".cursor/") or "/.agents/" in f"/{rel}" or "/.cursor/" in f"/{rel}":
        reasons.append("editor-mirror")
        source_kind = "editor-mirror"
    if rel.startswith("template/") or "/template/" in f"/{rel}":
        reasons.append("template")
        source_kind = "template"
    if "example-plugin/" in rel:
        reasons.append("example")
        source_kind = "example"

    if "/marketplaces" in str(scan_root):
        if not reasons:
            source_kind = "marketplace-skill"
    elif "/.claude/skills" in str(scan_root):
        source_kind = "claude-skill"
    elif "/.codex/skills" in str(scan_root):
        source_kind = "codex-skill"
    elif "/.agents/skills" in str(scan_root):
        source_kind = "agents-skill"

    return source_kind, reasons


def _find_missing_script_refs(body: str, skill_dir: Path) -> list[str]:
    refs = sorted(set(SCRIPT_REF_RE.findall(body)))
    missing = [ref for ref in refs if not (skill_dir / ref).exists()]
    return missing


def _load_skill_info(skill_md_path: Path, scan_root: Path) -> SkillInfo:
    skill_dir = skill_md_path.parent
    folder_name = skill_dir.name
    rel = skill_dir.relative_to(scan_root).as_posix()
    text = _read_text(skill_md_path)
    fm, body, frontmatter_status = _extract_frontmatter_with_status(text)
    name = fm.get("name")
    description = fm.get("description")
    headings = _extract_headings(body)
    tokens = _tokenize(folder_name, rel, name or "", description or "", " ".join(headings))
    source_kind, reasons = _classify_path(scan_root, skill_dir)

    if frontmatter_status == "missing-frontmatter":
        reasons.append("missing-frontmatter")
    elif frontmatter_status == "invalid-frontmatter":
        reasons.append("invalid-frontmatter")
    if not name:
        reasons.append("missing-name")

    validation_issues: list[str] = []
    missing_refs = _find_missing_script_refs(body, skill_dir)
    if missing_refs:
        validation_issues.extend([f"broken-script-ref:{ref}" for ref in missing_refs])

    discoverable = not reasons

    return SkillInfo(
        folder_name=folder_name,
        path=str(skill_dir),
        skill_md_path=str(skill_md_path),
        scan_root=str(scan_root),
        relative_path=rel,
        name=name,
        description=description,
        headings=headings,
        token_set=sorted(tokens),
        frontmatter_status=frontmatter_status,
        discoverable=discoverable,
        quarantine_reasons=sorted(set(reasons)),
        validation_issues=validation_issues,
        canonical_name=name if name else None,
        canonical_path=None,
        collision_count=0,
        source_kind=source_kind,
    )


def _cluster_pairs(skills: list[SkillInfo], min_similarity: float) -> list[dict]:
    clusters: list[dict] = []
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            a = skills[i]
            b = skills[j]
            sim = _jaccard(set(a.token_set), set(b.token_set))
            if sim < min_similarity:
                continue
            clusters.append(
                {
                    "similarity": round(sim, 4),
                    "a": {"folder": a.folder_name, "name": a.name, "path": a.path},
                    "b": {"folder": b.folder_name, "name": b.name, "path": b.path},
                }
            )
    clusters.sort(key=lambda x: x["similarity"], reverse=True)
    return clusters


def _resolve_path(path_str: str) -> str:
    return str(Path(path_str).expanduser().resolve())


def _load_policy(policy_path: Path) -> dict:
    policy = {
        "root_priority": [_resolve_path(p) for p in DEFAULT_POLICY["root_priority"]],
        "canonical_overrides": {k: _resolve_path(v) for k, v in DEFAULT_POLICY["canonical_overrides"].items()},
        "policy_path": str(policy_path),
    }

    if not policy_path.exists():
        return policy

    raw = json.loads(_read_text(policy_path))
    root_priority = raw.get("root_priority", DEFAULT_POLICY["root_priority"])
    canonical_overrides = raw.get("canonical_overrides", DEFAULT_POLICY["canonical_overrides"])
    policy["root_priority"] = [_resolve_path(p) for p in root_priority]
    policy["canonical_overrides"] = {k: _resolve_path(v) for k, v in canonical_overrides.items()}
    return policy


def _rank_skill(skill: SkillInfo, policy: dict) -> tuple[int, int, int, str]:
    override = policy["canonical_overrides"].get(skill.name or "")
    if override and override == skill.path:
        return (0, 0, len(Path(skill.path).parts), skill.path)

    root_rank = len(policy["root_priority"])
    for idx, root in enumerate(policy["root_priority"]):
        try:
            Path(skill.path).relative_to(Path(root))
            root_rank = idx
            break
        except ValueError:
            continue

    return (1, root_rank, len(Path(skill.path).parts), skill.path)


def _apply_canonical_resolution(skills: list[SkillInfo], policy: dict) -> tuple[list[SkillInfo], dict[str, str]]:
    all_by_name: dict[str, list[SkillInfo]] = {}
    discoverable_by_name: dict[str, list[SkillInfo]] = {}

    for skill in skills:
        if not skill.name:
            continue
        all_by_name.setdefault(skill.name, []).append(skill)
        if skill.discoverable:
            discoverable_by_name.setdefault(skill.name, []).append(skill)

    canonical_map: dict[str, str] = {}
    for name, candidates in discoverable_by_name.items():
        winner = sorted(candidates, key=lambda s: _rank_skill(s, policy))[0]
        canonical_map[name] = winner.path

    updated: list[SkillInfo] = []
    for skill in skills:
        collision_count = len(all_by_name.get(skill.name or "", []))
        canonical_path = canonical_map.get(skill.name or "")
        reasons = list(skill.quarantine_reasons)
        discoverable = skill.discoverable
        if discoverable and canonical_path and skill.path != canonical_path:
            reasons.append("shadowed-by-canonical")
            discoverable = False

        updated.append(
            replace(
                skill,
                discoverable=discoverable,
                quarantine_reasons=sorted(set(reasons)),
                canonical_path=canonical_path,
                collision_count=collision_count,
            )
        )

    return updated, canonical_map


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_overlap_report(path: Path, skills: list[SkillInfo], pairs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_folder = {s.folder_name: s for s in skills}

    lines: list[str] = []
    lines.append("# Skill overlap report")
    lines.append("")
    lines.append(f"- Skills scanned: **{len(skills)}**")
    lines.append(f"- Similar pairs (>= threshold): **{len(pairs)}**")
    lines.append("")
    lines.append("## Top similar pairs")
    lines.append("")

    if not pairs:
        lines.append("_No similar pairs found at the chosen threshold._")
    else:
        for idx, pair in enumerate(pairs[:200], start=1):
            a = by_folder.get(pair["a"]["folder"])
            b = by_folder.get(pair["b"]["folder"])
            lines.append(f"{idx}. **{pair['similarity']}**: `{pair['a']['folder']}` ↔ `{pair['b']['folder']}`")
            if a and a.description:
                lines.append(f"   - A desc: {a.description}")
            if b and b.description:
                lines.append(f"   - B desc: {b.description}")
            lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_quarantine_report(path: Path, skills: list[SkillInfo]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [skill for skill in skills if not skill.discoverable]

    lines = [
        "# Skill quarantine report",
        "",
        f"- Skills quarantined: **{len(rows)}**",
        "",
    ]
    if not rows:
        lines.append("_No quarantined skills._")
    else:
        for skill in rows:
            reasons = ", ".join(skill.quarantine_reasons) or "n/a"
            lines.append(f"- `{skill.path}`")
            lines.append(f"  - name: `{skill.name}`")
            lines.append(f"  - reasons: {reasons}")
            if skill.canonical_path:
                lines.append(f"  - canonical: `{skill.canonical_path}`")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_collision_report(path: Path, skills: list[SkillInfo], canonical_map: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_name: dict[str, list[SkillInfo]] = {}
    for skill in skills:
        if not skill.name:
            continue
        by_name.setdefault(skill.name, []).append(skill)

    collisions = {name: rows for name, rows in by_name.items() if len(rows) > 1}
    lines = [
        "# Skill collision report",
        "",
        f"- Colliding names: **{len(collisions)}**",
        "",
    ]
    if not collisions:
        lines.append("_No name collisions found._")
    else:
        for name in sorted(collisions):
            lines.append(f"## `{name}`")
            lines.append("")
            if name in canonical_map:
                lines.append(f"- canonical: `{canonical_map[name]}`")
            for skill in sorted(collisions[name], key=lambda s: s.path):
                status = "discoverable" if skill.discoverable else "quarantined"
                reasons = ", ".join(skill.quarantine_reasons) or "n/a"
                lines.append(f"- `{status}` `{skill.path}`")
                lines.append(f"  - reasons: {reasons}")
            lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan installed skills, emit an inventory, and classify discovery cleanup actions."
    )
    parser.add_argument("--skills-root", type=str, action="append", default=None)
    parser.add_argument("--out-dir", type=str, required=True)
    parser.add_argument("--min-similarity", type=float, default=0.15)
    parser.add_argument("--include-system", action="store_true")
    parser.add_argument("--policy", type=str, default=str(DEFAULT_POLICY_PATH))
    args = parser.parse_args()

    scan_roots = [Path(p).expanduser().resolve() for p in args.skills_root] if args.skills_root else _default_scan_roots()
    out_dir = Path(args.out_dir).expanduser().resolve()
    policy = _load_policy(Path(args.policy).expanduser().resolve())

    skills: list[SkillInfo] = []
    for scan_root in scan_roots:
        for skill_md in _iter_skill_md_files(scan_root, include_system=args.include_system):
            skills.append(_load_skill_info(skill_md, scan_root))

    skills, canonical_map = _apply_canonical_resolution(skills, policy)
    pairs = _cluster_pairs(skills, min_similarity=float(args.min_similarity))

    inventory = {
        "scan_roots": [str(root) for root in scan_roots],
        "policy_path": policy["policy_path"],
        "count": len(skills),
        "discoverable_count": sum(1 for skill in skills if skill.discoverable),
        "quarantined_count": sum(1 for skill in skills if not skill.discoverable),
        "skills": [asdict(s) for s in skills],
    }

    _write_json(out_dir / "inventory.json", inventory)
    _write_json(out_dir / "similar_pairs.json", pairs)
    _write_json(out_dir / "canonical_map.json", canonical_map)
    _write_overlap_report(out_dir / "overlap_report.md", skills, pairs)
    _write_quarantine_report(out_dir / "quarantine_report.md", skills)
    _write_collision_report(out_dir / "collision_report.md", skills, canonical_map)

    print(f"Wrote: {out_dir / 'inventory.json'}")
    print(f"Wrote: {out_dir / 'similar_pairs.json'}")
    print(f"Wrote: {out_dir / 'canonical_map.json'}")
    print(f"Wrote: {out_dir / 'overlap_report.md'}")
    print(f"Wrote: {out_dir / 'quarantine_report.md'}")
    print(f"Wrote: {out_dir / 'collision_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
