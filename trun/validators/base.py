"""
Base validator classes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..todo.models import ValidatorType, ValidationResult as ModelValidationResult


@dataclass
class ValidationResult:
    """Result of a validation check."""

    success: bool
    validator_type: ValidatorType
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_model(self) -> ModelValidationResult:
        """Convert to Pydantic model."""
        return ModelValidationResult(
            success=self.success,
            validator_type=self.validator_type,
            message=self.message,
            details=self.details
        )


class Validator(ABC):
    """
    Abstract base class for validators.

    Validators check step outputs to ensure they meet requirements.
    """

    @property
    @abstractmethod
    def validator_type(self) -> ValidatorType:
        """Get the validator type."""
        pass

    @abstractmethod
    async def validate(
        self,
        target: str,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None
    ) -> ValidationResult:
        """
        Perform validation.

        :param target: Target to validate (file path, test path, etc.)
        :param options: Additional options for the validator
        :param context: Execution context (working_dir, step info, etc.)
        :return: ValidationResult
        """
        pass

    def _make_result(
        self,
        success: bool,
        message: str = "",
        details: dict[str, Any] | None = None
    ) -> ValidationResult:
        """Helper to create a ValidationResult."""
        return ValidationResult(
            success=success,
            validator_type=self.validator_type,
            message=message,
            details=details or {}
        )


class CompositeValidator:
    """
    Combines multiple validators and runs them in sequence.
    """

    def __init__(self, validators: list[Validator] | None = None):
        self.validators = validators or []

    def add(self, validator: Validator) -> None:
        """Add a validator."""
        self.validators.append(validator)

    async def validate_all(
        self,
        targets: dict[ValidatorType, str],
        options: dict[ValidatorType, dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
        stop_on_failure: bool = True
    ) -> list[ValidationResult]:
        """
        Run all validators.

        :param targets: Map of validator type to target
        :param options: Map of validator type to options
        :param context: Shared execution context
        :param stop_on_failure: Stop on first failure if True
        :return: List of validation results
        """
        results = []
        options = options or {}

        for validator in self.validators:
            vtype = validator.validator_type
            target = targets.get(vtype, "")

            if not target:
                continue

            result = await validator.validate(
                target=target,
                options=options.get(vtype),
                context=context
            )
            results.append(result)

            if not result.success and stop_on_failure:
                break

        return results

    @property
    def all_passed(self) -> bool:
        """Check if all validators in the last run passed."""
        # This is a placeholder - actual implementation would track last results
        return True
