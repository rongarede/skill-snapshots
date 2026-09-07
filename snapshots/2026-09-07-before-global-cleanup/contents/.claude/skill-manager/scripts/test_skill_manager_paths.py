import json
import os
import pathlib
import subprocess
import tempfile
import unittest


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


def make_skill(root: pathlib.Path, name: str, frontmatter: str = "") -> pathlib.Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\n{frontmatter}description: test skill\n---\n",
        encoding="utf-8",
    )
    return skill_dir


class SkillManagerPathTests(unittest.TestCase):
    def run_script(self, script_name: str, *args: str, home: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = home
        env.pop("CODEX_HOME", None)
        return subprocess.run(
            ["python3", str(SCRIPT_DIR / script_name), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_list_skills_uses_default_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_root = pathlib.Path(tmpdir) / ".agents" / "skills"
            make_skill(skills_root, "demo-skill")

            result = self.run_script("list_skills.py", home=tmpdir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("demo-skill", result.stdout)

    def test_scan_and_check_uses_default_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_root = pathlib.Path(tmpdir) / ".agents" / "skills"
            make_skill(skills_root, "demo-skill")

            result = self.run_script("scan_and_check.py", home=tmpdir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), [])

    def test_list_skills_accepts_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_root = pathlib.Path(tmpdir) / "custom-skills"
            make_skill(skills_root, "demo-skill")

            result = self.run_script("list_skills.py", str(skills_root), home=tmpdir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("demo-skill", result.stdout)

    def test_scan_and_check_accepts_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_root = pathlib.Path(tmpdir) / "custom-skills"
            make_skill(skills_root, "demo-skill")

            result = self.run_script("scan_and_check.py", str(skills_root), home=tmpdir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), [])

    def test_delete_skill_uses_default_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_root = pathlib.Path(tmpdir) / ".agents" / "skills"
            skill_dir = make_skill(skills_root, "demo-skill")

            result = self.run_script("delete_skill.py", "demo-skill", home=tmpdir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(skill_dir.exists())

    def test_delete_skill_accepts_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_root = pathlib.Path(tmpdir) / "custom-skills"
            skill_dir = make_skill(skills_root, "demo-skill")

            result = self.run_script(
                "delete_skill.py", "demo-skill", str(skills_root), home=tmpdir
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(skill_dir.exists())


if __name__ == "__main__":
    unittest.main()
