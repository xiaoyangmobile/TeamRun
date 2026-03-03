"""
Data models for TODO files.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============== Validator Models ==============

class ValidatorType(str, Enum):
    """Validator type enumeration."""

    FILE_EXISTS = "file_exists"      # Check if output file exists
    TEST_PASS = "test_pass"          # Run tests and check pass
    SCHEMA = "schema"                # Validate against schema
    LLM = "llm"                      # LLM semantic validation
    CUSTOM = "custom"                # Custom validation command


class ValidatorConfig(BaseModel):
    """Configuration for a single validator."""

    type: ValidatorType = Field(..., description="Validator type")
    target: str = Field(..., description="Target to validate (file, test path, schema, etc.)")
    options: dict[str, Any] = Field(default_factory=dict, description="Additional options")
    required: bool = Field(default=True, description="Whether validation failure should fail the step")


class ValidationResult(BaseModel):
    """Result of a validation check."""

    success: bool = Field(..., description="Whether validation passed")
    validator_type: ValidatorType = Field(..., description="Type of validator")
    message: str = Field(default="", description="Result message")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional details")


# ============== Replan Models ==============

class ReplanRecord(BaseModel):
    """Record of a replan event."""

    timestamp: datetime = Field(default_factory=datetime.now, description="When replan occurred")
    original_step_id: str = Field(..., description="ID of the failed step")
    reason: str = Field(..., description="Reason for replan (error message)")
    new_steps: list[str] = Field(default_factory=list, description="IDs of newly created steps")
    context: str = Field(default="", description="Additional context")


class StepType(str, Enum):
    """Step type enumeration."""

    TASK = "task"
    DISCUSS = "discuss"
    PARALLEL = "parallel"
    GATE = "gate"
    HUMAN = "human"
    GOTO = "goto"


class StepStatus(str, Enum):
    """Step status enumeration."""

    PENDING = "pending"      # - [ ]
    RUNNING = "running"      # - [~]
    DONE = "done"            # - [x]
    FAILED = "failed"        # - [!]
    SKIPPED = "skipped"      # - [-]

    @classmethod
    def from_markdown(cls, marker: str) -> "StepStatus":
        """Convert markdown checkbox to status."""
        mapping = {
            "[ ]": cls.PENDING,
            "[~]": cls.RUNNING,
            "[x]": cls.DONE,
            "[!]": cls.FAILED,
            "[-]": cls.SKIPPED,
        }
        return mapping.get(marker, cls.PENDING)

    def to_markdown(self) -> str:
        """Convert status to markdown checkbox."""
        mapping = {
            self.PENDING: "[ ]",
            self.RUNNING: "[~]",
            self.DONE: "[x]",
            self.FAILED: "[!]",
            self.SKIPPED: "[-]",
        }
        return mapping.get(self, "[ ]")


class Step(BaseModel):
    """A single step in the TODO workflow."""

    id: str = Field(..., description="Step ID, e.g., 'step1', 'step6.1'")
    type: StepType = Field(..., description="Step type")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Current status")
    description: str = Field(default="", description="Step description")

    # For TASK type
    role: str | None = Field(None, description="Role ID for task execution")
    instruction: str | None = Field(None, description="Task instruction")

    # For DISCUSS type
    participants: list[str] = Field(default_factory=list, description="Discussion participants")
    rounds: int = Field(default=1, description="Number of discussion rounds")

    # For GATE type
    condition: str | None = Field(None, description="Gate condition expression")
    pass_step: str | None = Field(None, description="Step ID if condition passes")
    reject_step: str | None = Field(None, description="Step ID if condition fails")

    # For GOTO type
    target_step: str | None = Field(None, description="Target step ID")

    # Common fields
    depends: list[str] = Field(default_factory=list, description="Dependent step IDs")
    inputs: list[str] = Field(default_factory=list, description="Input file paths")
    output: str | None = Field(None, description="Output file path")

    # For PARALLEL type
    subtasks: list["Step"] = Field(default_factory=list, description="Subtasks for parallel execution")

    # Validators - NEW
    validators: list[ValidatorConfig] = Field(default_factory=list, description="Validators for step output")

    # Replan tracking - NEW
    replan_count: int = Field(default=0, description="Number of times this step has been replanned")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")

    def is_ready(self, completed_steps: set[str]) -> bool:
        """Check if this step is ready to execute (all dependencies completed)."""
        if self.status != StepStatus.PENDING:
            return False
        return all(dep in completed_steps for dep in self.depends)


class TodoMeta(BaseModel):
    """Metadata for a TODO file."""

    title: str = Field(..., description="Task title")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation time")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Overall status")

    # For discussion TODOs
    participants: list[str] = Field(default_factory=list, description="Discussion participants")
    total_rounds: int = Field(default=0, description="Total discussion rounds")


class TodoFile(BaseModel):
    """Represents a complete TODO file."""

    file_path: str = Field(..., description="Path to the TODO file")
    meta: TodoMeta = Field(..., description="TODO metadata")
    steps: list[Step] = Field(default_factory=list, description="Steps in the workflow")

    # Replan history - NEW
    replan_history: list[ReplanRecord] = Field(default_factory=list, description="History of replan events")

    def get_step(self, step_id: str) -> Step | None:
        """Get step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
            # Check subtasks for parallel steps
            for subtask in step.subtasks:
                if subtask.id == step_id:
                    return subtask
        return None

    def get_next_step(self) -> Step | None:
        """Get the next step to execute."""
        completed = {s.id for s in self.steps if s.status == StepStatus.DONE}

        for step in self.steps:
            if step.is_ready(completed):
                return step
        return None

    def get_completed_steps(self) -> list[Step]:
        """Get all completed steps."""
        return [s for s in self.steps if s.status == StepStatus.DONE]

    def get_failed_steps(self) -> list[Step]:
        """Get all failed steps."""
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    def is_completed(self) -> bool:
        """Check if all steps are completed."""
        return all(
            s.status in (StepStatus.DONE, StepStatus.SKIPPED)
            for s in self.steps
        )

    def update_step_status(self, step_id: str, status: StepStatus) -> bool:
        """Update a step's status. Returns True if found and updated."""
        step = self.get_step(step_id)
        if step:
            step.status = status
            return True
        return False

    # ============== Replan Support Methods ==============

    def get_step_index(self, step_id: str) -> int | None:
        """Get index of a step in the steps list."""
        for i, step in enumerate(self.steps):
            if step.id == step_id:
                return i
        return None

    def replace_steps_from(
        self,
        failed_step_id: str,
        new_steps: list[Step],
        reason: str = ""
    ) -> bool:
        """
        Replace a failed step and its dependents with new steps.
        This is the core method for local replan.

        :param failed_step_id: ID of the failed step to replace
        :param new_steps: New steps to insert
        :param reason: Reason for replan
        :return: True if successful
        """
        failed_idx = self.get_step_index(failed_step_id)
        if failed_idx is None:
            return False

        # Find all steps that depend on the failed step (transitively)
        steps_to_remove = self._find_dependent_steps(failed_step_id)
        steps_to_remove.add(failed_step_id)

        # Remove the failed step and dependents
        self.steps = [s for s in self.steps if s.id not in steps_to_remove]

        # Insert new steps at the position of failed step
        for i, new_step in enumerate(new_steps):
            self.steps.insert(failed_idx + i, new_step)

        # Record the replan event
        self.replan_history.append(ReplanRecord(
            original_step_id=failed_step_id,
            reason=reason,
            new_steps=[s.id for s in new_steps],
            context=f"Replaced {len(steps_to_remove)} step(s)"
        ))

        return True

    def _find_dependent_steps(self, step_id: str) -> set[str]:
        """Find all steps that depend on a given step (transitively)."""
        dependents: set[str] = set()
        to_check = [step_id]

        while to_check:
            current_id = to_check.pop(0)
            for step in self.steps:
                if current_id in step.depends and step.id not in dependents:
                    dependents.add(step.id)
                    to_check.append(step.id)

        return dependents

    def increment_replan_count(self, step_id: str) -> int:
        """Increment replan count for a step. Returns new count."""
        step = self.get_step(step_id)
        if step:
            step.replan_count += 1
            return step.replan_count
        return 0

    def add_replan_record(self, record: ReplanRecord) -> None:
        """Add a replan record to history."""
        self.replan_history.append(record)
