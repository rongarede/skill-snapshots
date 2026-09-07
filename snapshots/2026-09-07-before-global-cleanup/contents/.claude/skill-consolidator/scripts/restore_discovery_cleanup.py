#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore skill files disabled by apply_discovery_cleanup.py.")
    parser.add_argument("--manifest", type=str, required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for op in manifest.get("operations", []):
        if op.get("status") != "renamed":
            continue
        source = Path(op["target"])
        target = Path(op["path"])
        if source.exists() and not target.exists():
            source.rename(target)

    print(f"Restored from: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
