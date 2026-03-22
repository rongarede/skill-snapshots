"""File operation utilities."""
from pathlib import Path
import subprocess


def run_command(cmd: list[str], cwd: Path) -> None:
    """Run shell command and raise on failure.

    Args:
        cmd: Command and arguments as list
        cwd: Working directory for command execution

    Raises:
        subprocess.CalledProcessError: If command fails
    """
    subprocess.run(cmd, cwd=str(cwd), check=True)


def ensure_dir(path: Path) -> None:
    """Ensure directory exists, creating if necessary.

    Args:
        path: Directory path to ensure exists
    """
    path.mkdir(parents=True, exist_ok=True)
