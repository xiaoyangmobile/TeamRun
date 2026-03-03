"""
Test-based validator.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from ..todo.models import ValidatorType
from .base import ValidationResult, Validator


class TestPassValidator(Validator):
    """Validates that tests pass."""

    @property
    def validator_type(self) -> ValidatorType:
        return ValidatorType.TEST_PASS

    async def validate(
        self,
        target: str,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None
    ) -> ValidationResult:
        """
        Run tests and check if they pass.

        :param target: Test path or pattern (e.g., "tests/test_auth.py")
        :param options: Optional settings:
            - command: Test command (default: pytest)
            - timeout: Timeout in seconds (default: 300)
            - args: Additional arguments for the test command
            - coverage: Enable coverage checking
            - min_coverage: Minimum coverage percentage
        :param context: Execution context (may contain working_dir)
        """
        options = options or {}
        context = context or {}

        command = options.get("command", "pytest")
        timeout = options.get("timeout", 300)
        extra_args = options.get("args", [])
        working_dir = context.get("working_dir", ".")

        # Build command
        cmd_parts = [command, target]
        if extra_args:
            cmd_parts.extend(extra_args)

        # Add verbose flag for better output
        if command == "pytest" and "-v" not in cmd_parts:
            cmd_parts.append("-v")

        try:
            # Run tests
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                cwd=working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return self._make_result(
                    success=False,
                    message=f"Test timed out after {timeout} seconds",
                    details={
                        "target": target,
                        "command": " ".join(cmd_parts),
                        "timeout": timeout
                    }
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if process.returncode == 0:
                # Parse test summary if pytest
                summary = self._parse_pytest_summary(stdout_str)
                return self._make_result(
                    success=True,
                    message=f"Tests passed: {target}",
                    details={
                        "target": target,
                        "command": " ".join(cmd_parts),
                        "summary": summary,
                        "stdout": stdout_str[-2000:] if len(stdout_str) > 2000 else stdout_str
                    }
                )
            else:
                return self._make_result(
                    success=False,
                    message=f"Tests failed: {target}",
                    details={
                        "target": target,
                        "command": " ".join(cmd_parts),
                        "return_code": process.returncode,
                        "stdout": stdout_str[-2000:] if len(stdout_str) > 2000 else stdout_str,
                        "stderr": stderr_str[-1000:] if len(stderr_str) > 1000 else stderr_str
                    }
                )

        except FileNotFoundError:
            return self._make_result(
                success=False,
                message=f"Test command not found: {command}",
                details={"command": command}
            )
        except Exception as e:
            return self._make_result(
                success=False,
                message=f"Error running tests: {str(e)}",
                details={"target": target, "error": str(e)}
            )

    def _parse_pytest_summary(self, output: str) -> dict[str, Any]:
        """Parse pytest output for summary statistics."""
        import re

        summary = {}

        # Look for summary line like "5 passed, 2 failed, 1 skipped"
        pattern = r"(\d+)\s+(passed|failed|skipped|error|warning)"
        matches = re.findall(pattern, output.lower())

        for count, status in matches:
            summary[status] = int(count)

        # Look for duration
        duration_match = re.search(r"in\s+([\d.]+)\s*s", output)
        if duration_match:
            summary["duration_seconds"] = float(duration_match.group(1))

        return summary
