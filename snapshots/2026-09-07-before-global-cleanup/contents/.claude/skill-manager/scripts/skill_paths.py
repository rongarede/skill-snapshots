import os
from typing import Iterable, Optional


def _unique_paths(paths: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        normalized = os.path.abspath(os.path.expanduser(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def candidate_skills_roots() -> list[str]:
    home = os.path.expanduser("~")
    codex_home = os.environ.get("CODEX_HOME")

    paths = [
        os.environ.get("SKILLS_ROOT"),
        os.environ.get("AGENTS_SKILLS_ROOT"),
        os.environ.get("CLAUDE_SKILLS_ROOT"),
        os.path.join(home, ".agents", "skills"),
    ]

    if codex_home:
        paths.append(os.path.join(codex_home, "skills"))

    paths.extend(
        [
            os.path.join(home, ".codex", "skills"),
            os.path.join(home, ".claude", "skills"),
        ]
    )

    return _unique_paths(path for path in paths if path)


def resolve_skills_root(explicit_root: Optional[str] = None) -> str:
    if explicit_root:
        return os.path.abspath(os.path.expanduser(explicit_root))

    candidates = candidate_skills_roots()
    for path in candidates:
        if os.path.isdir(path):
            return path

    return candidates[0]
