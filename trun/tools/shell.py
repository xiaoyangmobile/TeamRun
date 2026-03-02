"""
Shell command execution tool.
"""

import subprocess
from typing import Any


class ShellTool:
    """Tool for executing shell commands."""

    def run_command(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int = 300,
        shell: bool = True,
        env: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        Execute a shell command.

        :param command: Command string
        :param cwd: Working directory
        :param timeout: Timeout in seconds
        :param shell: Use shell execution
        :param env: Additional environment variables
        :return: {"success": bool, "stdout": str, "stderr": str, "code": int}
        """
        try:
            import os
            full_env = os.environ.copy()
            if env:
                full_env.update(env)

            result = subprocess.run(
                command,
                shell=shell,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=full_env
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "code": -1
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "code": -1
            }

    def run_tests(
        self,
        test_command: str = "pytest",
        cwd: str | None = None,
        timeout: int = 600
    ) -> dict[str, Any]:
        """
        Run tests with common test frameworks.

        :param test_command: Test command (pytest, npm test, etc.)
        :param cwd: Working directory
        :param timeout: Timeout in seconds
        :return: Test execution result
        """
        return self.run_command(test_command, cwd=cwd, timeout=timeout)

    def run_build(
        self,
        build_command: str,
        cwd: str | None = None,
        timeout: int = 600
    ) -> dict[str, Any]:
        """
        Run build command.

        :param build_command: Build command
        :param cwd: Working directory
        :param timeout: Timeout in seconds
        :return: Build execution result
        """
        return self.run_command(build_command, cwd=cwd, timeout=timeout)
