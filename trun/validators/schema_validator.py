"""
Schema-based validator.
"""

import json
from pathlib import Path
from typing import Any

from ..todo.models import ValidatorType
from .base import ValidationResult, Validator


class SchemaValidator(Validator):
    """Validates output against a JSON schema or OpenAPI spec."""

    @property
    def validator_type(self) -> ValidatorType:
        return ValidatorType.SCHEMA

    async def validate(
        self,
        target: str,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None
    ) -> ValidationResult:
        """
        Validate a file against a schema.

        :param target: Path to the schema file (JSON Schema or OpenAPI spec)
        :param options: Optional settings:
            - data_file: Path to the file to validate
            - data: Direct data to validate (JSON string or dict)
            - schema_type: "jsonschema" or "openapi" (default: auto-detect)
        :param context: Execution context (may contain working_dir)
        """
        options = options or {}
        context = context or {}
        working_dir = Path(context.get("working_dir", "."))

        # Load schema
        schema_path = Path(target)
        if not schema_path.is_absolute():
            schema_path = working_dir / schema_path

        if not schema_path.exists():
            return self._make_result(
                success=False,
                message=f"Schema file not found: {schema_path}",
                details={"schema_path": str(schema_path)}
            )

        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return self._make_result(
                success=False,
                message=f"Invalid schema JSON: {str(e)}",
                details={"schema_path": str(schema_path), "error": str(e)}
            )

        # Load data to validate
        data = options.get("data")
        if data is None and "data_file" in options:
            data_path = Path(options["data_file"])
            if not data_path.is_absolute():
                data_path = working_dir / data_path

            if not data_path.exists():
                return self._make_result(
                    success=False,
                    message=f"Data file not found: {data_path}",
                    details={"data_path": str(data_path)}
                )

            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                return self._make_result(
                    success=False,
                    message=f"Invalid data JSON: {str(e)}",
                    details={"data_path": str(data_path), "error": str(e)}
                )

        if data is None:
            return self._make_result(
                success=False,
                message="No data provided for schema validation",
                details={"schema_path": str(schema_path)}
            )

        # If data is a string, try to parse it
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                return self._make_result(
                    success=False,
                    message=f"Invalid data JSON string: {str(e)}",
                    details={"error": str(e)}
                )

        # Perform validation
        return await self._validate_against_schema(data, schema, str(schema_path))

    async def _validate_against_schema(
        self,
        data: Any,
        schema: dict,
        schema_path: str
    ) -> ValidationResult:
        """Validate data against JSON schema."""
        try:
            import jsonschema
            from jsonschema import Draft7Validator, ValidationError
        except ImportError:
            return self._make_result(
                success=False,
                message="jsonschema package not installed. Install with: pip install jsonschema",
                details={}
            )

        try:
            # Create validator
            validator = Draft7Validator(schema)

            # Collect all errors
            errors = list(validator.iter_errors(data))

            if not errors:
                return self._make_result(
                    success=True,
                    message="Data validates against schema",
                    details={"schema_path": schema_path}
                )
            else:
                # Format errors
                error_messages = []
                for error in errors[:5]:  # Limit to first 5 errors
                    path = ".".join(str(p) for p in error.absolute_path)
                    error_messages.append(f"{path}: {error.message}" if path else error.message)

                return self._make_result(
                    success=False,
                    message=f"Schema validation failed: {len(errors)} error(s)",
                    details={
                        "schema_path": schema_path,
                        "error_count": len(errors),
                        "errors": error_messages
                    }
                )

        except Exception as e:
            return self._make_result(
                success=False,
                message=f"Schema validation error: {str(e)}",
                details={"schema_path": schema_path, "error": str(e)}
            )
