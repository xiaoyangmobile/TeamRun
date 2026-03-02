"""
Tests for built-in tools.
"""

import os
import pytest
from pathlib import Path

from trun.tools.file_ops import FileOpsTool
from trun.tools.shell import ShellTool
from trun.tools.git_ops import GitOpsTool


class TestFileOpsTool:
    """Tests for FileOpsTool."""

    def test_read_write_file(self, tmp_path):
        """Test reading and writing files."""
        tool = FileOpsTool()
        file_path = str(tmp_path / "test.txt")

        # Write
        result = tool.write_file(file_path, "Hello, World!")
        assert result["success"] is True

        # Read
        result = tool.read_file(file_path)
        assert result["success"] is True
        assert result["content"] == "Hello, World!"

    def test_append_file(self, tmp_path):
        """Test appending to files."""
        tool = FileOpsTool()
        file_path = str(tmp_path / "test.txt")

        tool.write_file(file_path, "Line 1\n")
        tool.append_file(file_path, "Line 2\n")

        result = tool.read_file(file_path)
        assert result["content"] == "Line 1\nLine 2\n"

    def test_file_exists(self, tmp_path):
        """Test file existence check."""
        tool = FileOpsTool()
        file_path = str(tmp_path / "test.txt")

        assert tool.file_exists(file_path) is False

        tool.write_file(file_path, "test")
        assert tool.file_exists(file_path) is True

    def test_list_files(self, tmp_path):
        """Test listing files."""
        tool = FileOpsTool()

        # Create some files
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "c.md").write_text("c")

        files = tool.list_files(str(tmp_path), "*.txt")
        assert len(files) == 2

    def test_read_nonexistent_file(self):
        """Test reading non-existent file."""
        tool = FileOpsTool()
        result = tool.read_file("/nonexistent/path/file.txt")
        assert result["success"] is False
        assert "error" in result


class TestShellTool:
    """Tests for ShellTool."""

    def test_run_command_success(self):
        """Test running successful command."""
        tool = ShellTool()
        result = tool.run_command("echo 'Hello'")

        assert result["success"] is True
        assert "Hello" in result["stdout"]
        assert result["code"] == 0

    def test_run_command_failure(self):
        """Test running failing command."""
        tool = ShellTool()
        result = tool.run_command("exit 1")

        assert result["success"] is False
        assert result["code"] == 1

    def test_run_command_timeout(self):
        """Test command timeout."""
        tool = ShellTool()
        result = tool.run_command("sleep 10", timeout=1)

        assert result["success"] is False
        assert "timed out" in result["stderr"].lower()

    def test_run_command_with_cwd(self, tmp_path):
        """Test running command in specific directory."""
        tool = ShellTool()
        result = tool.run_command("pwd", cwd=str(tmp_path))

        assert result["success"] is True
        assert str(tmp_path) in result["stdout"]


class TestGitOpsTool:
    """Tests for GitOpsTool."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository."""
        import subprocess

        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            capture_output=True
        )

        # Create initial commit
        (repo_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True
        )

        return repo_path

    def test_status(self, git_repo):
        """Test git status."""
        tool = GitOpsTool(str(git_repo))
        result = tool.status()

        assert result["success"] is True

    def test_current_branch(self, git_repo):
        """Test getting current branch."""
        tool = GitOpsTool(str(git_repo))
        branch = tool.current_branch()

        assert branch in ["main", "master"]

    def test_create_switch_branch(self, git_repo):
        """Test creating and switching branches."""
        tool = GitOpsTool(str(git_repo))

        # Create branch
        result = tool.create_branch("feature/test")
        assert result["success"] is True

        # Check current branch
        assert tool.current_branch() == "feature/test"

        # Switch back
        original = "main" if "main" in tool.list_branches() else "master"
        result = tool.switch_branch(original)
        assert result["success"] is True

    def test_list_branches(self, git_repo):
        """Test listing branches."""
        tool = GitOpsTool(str(git_repo))
        tool.create_branch("feature/a")
        tool.create_branch("feature/b")

        branches = tool.list_branches()
        assert len(branches) >= 2
