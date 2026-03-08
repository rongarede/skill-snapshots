"""Tests for file_utils module."""
import pytest
import subprocess
from pathlib import Path
from scripts.utils.file_utils import run_command, ensure_dir

def test_run_command_success():
    """Test successful command execution."""
    # Should not raise
    run_command(["echo", "test"], Path("/tmp"))

def test_run_command_failure():
    """Test command failure raises exception."""
    with pytest.raises(subprocess.CalledProcessError):
        run_command(["false"], Path("/tmp"))

def test_ensure_dir_creates_directory(tmp_path):
    """Test directory creation."""
    test_dir = tmp_path / "test_swun_skill"
    ensure_dir(test_dir)
    assert test_dir.exists()
    assert test_dir.is_dir()
