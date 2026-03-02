"""
Git operations tool.
"""

import subprocess
from typing import Any


class GitOpsTool:
    """Tool for Git operations."""

    def __init__(self, repo_path: str = "."):
        """
        Initialize Git tool.

        :param repo_path: Path to the Git repository
        """
        self.repo_path = repo_path

    def _run_git(self, args: list[str]) -> dict[str, Any]:
        """
        Execute a git command.

        :param args: Git command arguments
        :return: {"success": bool, "stdout": str, "stderr": str, "code": int}
        """
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "code": result.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "code": -1
            }

    def status(self) -> dict[str, Any]:
        """
        Get Git status.

        :return: Git status result
        """
        return self._run_git(["status", "--short"])

    def current_branch(self) -> str | None:
        """
        Get current branch name.

        :return: Branch name or None if not in a git repo
        """
        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if result["success"]:
            return result["stdout"].strip()
        return None

    def create_branch(self, branch_name: str, from_branch: str | None = None) -> dict[str, Any]:
        """
        Create a new branch.

        :param branch_name: New branch name
        :param from_branch: Base branch (uses current if None)
        :return: Operation result
        """
        if from_branch:
            return self._run_git(["checkout", "-b", branch_name, from_branch])
        return self._run_git(["checkout", "-b", branch_name])

    def switch_branch(self, branch_name: str) -> dict[str, Any]:
        """
        Switch to a branch.

        :param branch_name: Branch name
        :return: Operation result
        """
        return self._run_git(["checkout", branch_name])

    def merge_branch(
        self,
        branch_name: str,
        no_ff: bool = False,
        message: str | None = None
    ) -> dict[str, Any]:
        """
        Merge a branch into current branch.

        :param branch_name: Branch to merge
        :param no_ff: Use --no-ff flag
        :param message: Merge commit message
        :return: Operation result
        """
        args = ["merge", branch_name]
        if no_ff:
            args.append("--no-ff")
        if message:
            args.extend(["-m", message])
        return self._run_git(args)

    def delete_branch(self, branch_name: str, force: bool = False) -> dict[str, Any]:
        """
        Delete a branch.

        :param branch_name: Branch to delete
        :param force: Force delete
        :return: Operation result
        """
        flag = "-D" if force else "-d"
        return self._run_git(["branch", flag, branch_name])

    def check_conflicts(self) -> dict[str, Any]:
        """
        Check for merge conflicts.

        :return: {"has_conflicts": bool, "conflicted_files": list[str]}
        """
        result = self._run_git(["diff", "--name-only", "--diff-filter=U"])
        conflicted_files = []
        if result["stdout"].strip():
            conflicted_files = result["stdout"].strip().split('\n')

        return {
            "has_conflicts": len(conflicted_files) > 0,
            "conflicted_files": conflicted_files
        }

    def add(self, files: list[str] | str = ".") -> dict[str, Any]:
        """
        Stage files for commit.

        :param files: Files to stage (list or ".")
        :return: Operation result
        """
        if isinstance(files, str):
            files = [files]
        return self._run_git(["add"] + files)

    def commit(self, message: str) -> dict[str, Any]:
        """
        Create a commit.

        :param message: Commit message
        :return: Operation result
        """
        return self._run_git(["commit", "-m", message])

    def stash(self, message: str | None = None) -> dict[str, Any]:
        """
        Stash changes.

        :param message: Stash message
        :return: Operation result
        """
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        return self._run_git(args)

    def stash_pop(self) -> dict[str, Any]:
        """
        Pop the latest stash.

        :return: Operation result
        """
        return self._run_git(["stash", "pop"])

    def list_branches(self, all_branches: bool = False) -> list[str]:
        """
        List branches.

        :param all_branches: Include remote branches
        :return: List of branch names
        """
        args = ["branch"]
        if all_branches:
            args.append("-a")
        result = self._run_git(args)
        if result["success"]:
            branches = []
            for line in result["stdout"].strip().split('\n'):
                branch = line.strip().lstrip('* ')
                if branch:
                    branches.append(branch)
            return branches
        return []
