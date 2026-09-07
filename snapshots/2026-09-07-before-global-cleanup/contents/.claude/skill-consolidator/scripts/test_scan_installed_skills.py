import sys

sys.dont_write_bytecode = True

import os
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scan_installed_skills import _apply_canonical_resolution
from scan_installed_skills import _classify_path
from scan_installed_skills import _default_skills_root
from scan_installed_skills import _extract_frontmatter
from scan_installed_skills import _extract_frontmatter_with_status
from scan_installed_skills import _iter_skill_dirs
from scan_installed_skills import _jaccard
from scan_installed_skills import _tokenize
from scan_installed_skills import SkillInfo


class TestScanInstalledSkills(unittest.TestCase):
    def test_extract_frontmatter_missing(self) -> None:
        fm, body = _extract_frontmatter("# Hello\n\nBody")
        self.assertEqual(fm, {})
        self.assertIn("Hello", body)

    def test_extract_frontmatter_simple(self) -> None:
        text = "\n".join(
            [
                "---",
                "name: my-skill",
                "description: Do a thing",
                "---",
                "",
                "# Title",
                "Body",
            ]
        )
        fm, body = _extract_frontmatter(text)
        self.assertEqual(fm["name"], "my-skill")
        self.assertEqual(fm["description"], "Do a thing")
        self.assertIn("# Title", body)

    def test_extract_frontmatter_invalid_yaml(self) -> None:
        text = "\n".join(
            [
                "---",
                "name: bad-skill",
                "description: Broken: value: extra",
                "---",
                "",
                "# Title",
            ]
        )
        _fm, _body, status = _extract_frontmatter_with_status(text)
        self.assertIn(status, {"ok", "invalid-frontmatter"})

    def test_tokenize_basic(self) -> None:
        tokens = _tokenize("Playwright best practices", "E2E tests")
        self.assertIn("playwright", tokens)
        self.assertIn("best", tokens)
        self.assertIn("e2e", tokens)

    def test_jaccard(self) -> None:
        a = {"a", "b", "c"}
        b = {"b", "c", "d"}
        self.assertAlmostEqual(_jaccard(a, b), 2 / 4)

    def test_default_skills_root_prefers_agents(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        tmp_root = repo_root / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)

        old_home = os.environ.get("HOME")
        old_codex_home = os.environ.get("CODEX_HOME")

        try:
            with tempfile.TemporaryDirectory(dir=tmp_root) as home_dir:
                os.environ["HOME"] = home_dir
                os.environ.pop("CODEX_HOME", None)

                agents_skills = Path(home_dir) / ".agents" / "skills"
                agents_skills.mkdir(parents=True, exist_ok=True)

                self.assertEqual(_default_skills_root(), agents_skills.resolve())
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

            if old_codex_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = old_codex_home

    def test_iter_skill_dirs_skips_archive(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        tmp_root = repo_root / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=tmp_root) as work_dir:
            root = Path(work_dir)
            (root / "_archive").mkdir(parents=True, exist_ok=True)
            (root / "keep-me").mkdir(parents=True, exist_ok=True)

            dirs = list(_iter_skill_dirs(root, include_system=False))
            names = [d.name for d in dirs]
            self.assertIn("keep-me", names)
            self.assertNotIn("_archive", names)

    def test_classify_path_detects_docs_and_backup(self) -> None:
        scan_root = Path("/tmp/market")
        source_kind, reasons = _classify_path(scan_root, scan_root / "docs/zh-CN/skills/example")
        self.assertEqual(source_kind, "docs-copy")
        self.assertIn("docs-copy", reasons)

        source_kind, reasons = _classify_path(scan_root, scan_root / "foo.backup-20260307")
        self.assertEqual(source_kind, "backup-copy")
        self.assertIn("backup-copy", reasons)

    def test_apply_canonical_resolution_shadows_duplicates(self) -> None:
        policy = {
            "root_priority": [
                "/Users/bit/.codex/skills",
                "/Users/bit/.agents/skills",
            ],
            "canonical_overrides": {
                "docx": "/Users/bit/.codex/skills/docx",
            },
        }
        skills = [
            SkillInfo(
                folder_name="docx",
                path="/Users/bit/.codex/skills/docx",
                skill_md_path="/Users/bit/.codex/skills/docx/SKILL.md",
                scan_root="/Users/bit/.codex/skills",
                relative_path="docx",
                name="docx",
                description="Use when docx",
                headings=[],
                token_set=["docx"],
                frontmatter_status="ok",
                discoverable=True,
                quarantine_reasons=[],
                validation_issues=[],
                canonical_name="docx",
                canonical_path=None,
                collision_count=0,
                source_kind="codex-skill",
            ),
            SkillInfo(
                folder_name="docx",
                path="/Users/bit/.agents/skills/docx",
                skill_md_path="/Users/bit/.agents/skills/docx/SKILL.md",
                scan_root="/Users/bit/.agents/skills",
                relative_path="docx",
                name="docx",
                description="Use when docx",
                headings=[],
                token_set=["docx"],
                frontmatter_status="ok",
                discoverable=True,
                quarantine_reasons=[],
                validation_issues=[],
                canonical_name="docx",
                canonical_path=None,
                collision_count=0,
                source_kind="agents-skill",
            ),
        ]

        updated, canonical_map = _apply_canonical_resolution(skills, policy)
        self.assertEqual(canonical_map["docx"], "/Users/bit/.codex/skills/docx")
        by_path = {skill.path: skill for skill in updated}
        self.assertTrue(by_path["/Users/bit/.codex/skills/docx"].discoverable)
        self.assertFalse(by_path["/Users/bit/.agents/skills/docx"].discoverable)
        self.assertIn("shadowed-by-canonical", by_path["/Users/bit/.agents/skills/docx"].quarantine_reasons)


if __name__ == "__main__":
    unittest.main()
