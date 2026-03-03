"""
File-based validators.
"""

from pathlib import Path
from typing import Any

from ..todo.models import ValidatorType
from .base import ValidationResult, Validator


class FileExistsValidator(Validator):
    """Validates that an output file exists."""

    @property
    def validator_type(self) -> ValidatorType:
        return ValidatorType.FILE_EXISTS

    async def validate(
        self,
        target: str,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None
    ) -> ValidationResult:
        """
        Check if the target file exists.

        :param target: File path to check
        :param options: Optional settings:
            - min_size: Minimum file size in bytes
            - not_empty: Require file to be non-empty
        :param context: Execution context (may contain working_dir)
        """
        options = options or {}
        context = context or {}

        # Resolve path
        file_path = Path(target)
        if not file_path.is_absolute() and "working_dir" in context:
            file_path = Path(context["working_dir"]) / file_path

        # Check existence
        if not file_path.exists():
            return self._make_result(
                success=False,
                message=f"File not found: {file_path}",
                details={"path": str(file_path)}
            )

        # Check if it's a file (not directory)
        if not file_path.is_file():
            return self._make_result(
                success=False,
                message=f"Path is not a file: {file_path}",
                details={"path": str(file_path)}
            )

        # Check minimum size
        file_size = file_path.stat().st_size
        min_size = options.get("min_size", 0)
        if file_size < min_size:
            return self._make_result(
                success=False,
                message=f"File too small: {file_size} bytes (min: {min_size})",
                details={"path": str(file_path), "size": file_size, "min_size": min_size}
            )

        # Check not empty
        if options.get("not_empty", False) and file_size == 0:
            return self._make_result(
                success=False,
                message=f"File is empty: {file_path}",
                details={"path": str(file_path)}
            )

        return self._make_result(
            success=True,
            message=f"File exists: {file_path}",
            details={"path": str(file_path), "size": file_size}
        )


class CompletionMarkerValidator(Validator):
    """Validates that a file contains the completion marker."""

    DEFAULT_MARKER = "<!-- TASK_COMPLETED -->"

    @property
    def validator_type(self) -> ValidatorType:
        return ValidatorType.FILE_EXISTS  # Reuse type, or could create a new one

    async def validate(
        self,
        target: str,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None
    ) -> ValidationResult:
        """
        Check if the target file contains the completion marker.

        :param target: File path to check
        :param options: Optional settings:
            - marker: Custom completion marker (default: <!-- TASK_COMPLETED -->)
        :param context: Execution context
        """
        options = options or {}
        context = context or {}

        marker = options.get("marker", self.DEFAULT_MARKER)

        # Resolve path
        file_path = Path(target)
        if not file_path.is_absolute() and "working_dir" in context:
            file_path = Path(context["working_dir"]) / file_path

        # Check existence first
        if not file_path.exists():
            return self._make_result(
                success=False,
                message=f"File not found: {file_path}",
                details={"path": str(file_path)}
            )

        # Read and check for marker
        try:
            content = file_path.read_text(encoding="utf-8")
            if marker in content:
                return self._make_result(
                    success=True,
                    message=f"Completion marker found in: {file_path}",
                    details={"path": str(file_path), "marker": marker}
                )
            else:
                return self._make_result(
                    success=False,
                    message=f"Completion marker not found in: {file_path}",
                    details={"path": str(file_path), "marker": marker}
                )
        except Exception as e:
            return self._make_result(
                success=False,
                message=f"Error reading file: {str(e)}",
                details={"path": str(file_path), "error": str(e)}
            )
