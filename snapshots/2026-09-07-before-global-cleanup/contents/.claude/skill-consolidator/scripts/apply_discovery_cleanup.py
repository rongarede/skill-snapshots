#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_REASONS = {
    "backup-copy",
    "docs-copy",
    "editor-mirror",
    "example",
    "invalid-frontmatter",
    "missing-frontmatter",
    "missing-name",
    "shadowed-by-canonical",
    "template",
}


def _read_inventory(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _default_manifest_path(inventory_path: Path) -> Path:
    return inventory_path.parent / "cleanup_manifest.json"


def _target_path(skill_md_path: Path) -> Path:
    return skill_md_path.with_name("SKILL.disabled.md")


def main() -> int:
    parser = argparse.ArgumentParser(description="Disable non-discoverable skill files based on inventory.json.")
    parser.add_argument("--inventory", type=str, required=True)
    parser.add_argument("--manifest", type=str, default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reason", action="append", default=None, dest="reasons")
    args = parser.parse_args()

    inventory_path = Path(args.inventory).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else _default_manifest_path(inventory_path)
    selected_reasons = set(args.reasons or DEFAULT_REASONS)
    inventory = _read_inventory(inventory_path)

    operations: list[dict] = []
    for skill in inventory.get("skills", []):
        reasons = set(skill.get("quarantine_reasons") or [])
        skill_md = skill.get("skill_md_path")
        if not skill_md or not reasons.intersection(selected_reasons):
            continue

        source = Path(skill_md)
        target = _target_path(source)
        operations.append(
            {
                "path": str(source),
                "target": str(target),
                "name": skill.get("name"),
                "reasons": sorted(reasons.intersection(selected_reasons)),
                "status": "pending",
            }
        )

    if not args.execute:
        print(json.dumps({"execute": False, "operations": operations}, indent=2, ensure_ascii=False))
        return 0

    for op in operations:
        source = Path(op["path"])
        target = Path(op["target"])
        if not source.exists():
            op["status"] = "missing-source"
            continue
        if target.exists():
            op["status"] = "target-exists"
            continue
        source.rename(target)
        op["status"] = "renamed"

    manifest = {
        "inventory": str(inventory_path),
        "operations": operations,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
