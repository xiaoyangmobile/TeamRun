"""
Data models for TODO files.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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
