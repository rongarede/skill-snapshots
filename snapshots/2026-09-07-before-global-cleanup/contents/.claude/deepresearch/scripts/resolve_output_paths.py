#!/usr/bin/env python3
"""Resolve deep-research deliverable and evidence locations.

Reader-facing reports belong in an Obsidian vault's PARA resources area.  The
source registry and run state are reproducible machine data, so they remain
outside the vault.  The script is intentionally side-effect free: callers
create directories only after showing or recording the resolved locations.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path


PARA_DIRECTORIES = {
    "100_Projects",
    "200_Areas",
    "300_Resources",
    "400_Archives",
    "500_Journal",
}


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", value, flags=re.UNICODE)
    return cleaned.strip("_") or "research"


def find_vault_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if all((candidate / directory).is_dir() for directory in PARA_DIRECTORIES):
            return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve deep-research output paths")
    parser.add_argument("--cwd", default=".", help="Workspace used to discover an Obsidian vault")
    parser.add_argument("--topic", required=True, help="Research topic used in the dated folder name")
    parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD format")
    args = parser.parse_args()

    start = Path(args.cwd).expanduser().resolve()
    folder_name = f"{slugify(args.topic)}_Research_{args.date.replace('-', '')}"
    vault_root = find_vault_root(start)

    if vault_root:
        deliverable_dir = vault_root / "300_Resources" / "Res_调研" / folder_name
        location_type = "obsidian_vault"
    else:
        deliverable_dir = Path.home() / "Documents" / folder_name
        location_type = "documents_fallback"

    evidence_dir = Path.home() / ".codex" / "research_output" / folder_name
    print(
        json.dumps(
            {
                "location_type": location_type,
                "vault_root": str(vault_root) if vault_root else None,
                "deliverable_dir": str(deliverable_dir),
                "evidence_dir": str(evidence_dir),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
