"""
Base adapter for AI agents.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Result from agent execution."""

    success: bool
    output: str = ""
    error: str | None = None
    session_id: str | None = None
    output_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    """
    Abstract base class for AI agent adapters.

    All agent adapters must implement this interface to provide
    a unified way to execute tasks across different AI agents.
    """

    @abstractmethod
    async def execute(
        self,
        context_file: str,
        working_dir: str | None = None
    ) -> AgentResult:
        """
        Execute a task based on the context file.

        :param context_file: Path to the task context file
        :param working_dir: Working directory for the agent
        :return: AgentResult with execution results
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the current task execution."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the adapter name."""
        pass

    @property
    def is_running(self) -> bool:
        """Check if the agent is currently running a task."""
        return False
