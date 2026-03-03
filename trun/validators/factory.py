"""
Validator factory.
"""

from typing import Any, Type

from ..todo.models import ValidatorConfig, ValidatorType
from .base import Validator, ValidationResult
from .file_validator import FileExistsValidator, CompletionMarkerValidator
from .test_validator import TestPassValidator
from .schema_validator import SchemaValidator
from .llm_validator import LLMValidator


class ValidatorFactory:
    """Factory for creating validators."""

    _validators: dict[ValidatorType, Type[Validator]] = {
        ValidatorType.FILE_EXISTS: FileExistsValidator,
        ValidatorType.TEST_PASS: TestPassValidator,
        ValidatorType.SCHEMA: SchemaValidator,
        ValidatorType.LLM: LLMValidator,
    }

    @classmethod
    def create(cls, validator_type: ValidatorType, **kwargs) -> Validator:
        """
        Create a validator by type.

        :param validator_type: Type of validator to create
        :param kwargs: Additional arguments for the validator
        :return: Validator instance
        :raises ValueError: If validator type is unknown
        """
        if validator_type not in cls._validators:
            available = ", ".join(v.value for v in cls._validators.keys())
            raise ValueError(
                f"Unknown validator type: {validator_type}. Available: {available}"
            )
        return cls._validators[validator_type](**kwargs)

    @classmethod
    def create_from_config(cls, config: ValidatorConfig, **kwargs) -> Validator:
        """
        Create a validator from a ValidatorConfig.

        :param config: Validator configuration
        :param kwargs: Additional arguments for the validator
        :return: Validator instance
        """
        return cls.create(config.type, **kwargs)

    @classmethod
    def register(cls, validator_type: ValidatorType, validator_class: Type[Validator]) -> None:
        """
        Register a custom validator.

        :param validator_type: Validator type
        :param validator_class: Validator class
        """
        cls._validators[validator_type] = validator_class

    @classmethod
    def available_validators(cls) -> list[ValidatorType]:
        """Get list of available validator types."""
        return list(cls._validators.keys())


class StepValidator:
    """
    Validator runner for a step.

    Runs all configured validators for a step and aggregates results.
    """

    def __init__(self, working_dir: str = "."):
        """
        Initialize step validator.

        :param working_dir: Working directory for validation
        """
        self.working_dir = working_dir

    async def validate_step(
        self,
        validators: list[ValidatorConfig],
        context: dict[str, Any] | None = None
    ) -> tuple[bool, list[ValidationResult]]:
        """
        Run all validators for a step.

        :param validators: List of validator configurations
        :param context: Additional context (step info, output files, etc.)
        :return: Tuple of (all_passed, results)
        """
        context = context or {}
        context.setdefault("working_dir", self.working_dir)

        results: list[ValidationResult] = []
        all_passed = True

        for config in validators:
            try:
                validator = ValidatorFactory.create_from_config(config)
                result = await validator.validate(
                    target=config.target,
                    options=config.options,
                    context=context
                )
                results.append(result)

                if not result.success and config.required:
                    all_passed = False
                    # Don't break - run all validators to collect all issues

            except Exception as e:
                # Create a failed result for the exception
                results.append(ValidationResult(
                    success=False,
                    validator_type=config.type,
                    message=f"Validator error: {str(e)}",
                    details={"error": str(e), "config": config.model_dump()}
                ))
                if config.required:
                    all_passed = False

        return all_passed, results

    async def validate_output_file(
        self,
        output_path: str,
        check_completion_marker: bool = True
    ) -> tuple[bool, list[ValidationResult]]:
        """
        Quick validation for output file existence and completion marker.

        :param output_path: Path to output file
        :param check_completion_marker: Whether to check for completion marker
        :return: Tuple of (success, results)
        """
        results: list[ValidationResult] = []
        context = {"working_dir": self.working_dir}

        # Check file exists
        file_validator = FileExistsValidator()
        file_result = await file_validator.validate(
            target=output_path,
            options={"not_empty": True},
            context=context
        )
        results.append(file_result)

        if not file_result.success:
            return False, results

        # Check completion marker
        if check_completion_marker:
            marker_validator = CompletionMarkerValidator()
            marker_result = await marker_validator.validate(
                target=output_path,
                context=context
            )
            results.append(marker_result)

            if not marker_result.success:
                return False, results

        return True, results
