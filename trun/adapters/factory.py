"""
Agent adapter factory.
"""

from typing import Type

from .base import AgentAdapter
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter


class AdapterFactory:
    """Factory for creating agent adapters."""

    _adapters: dict[str, Type[AgentAdapter]] = {
        "claude-code": ClaudeCodeAdapter,
        "codex": CodexAdapter,
    }

    @classmethod
    def create(cls, agent_type: str, **kwargs) -> AgentAdapter:
        """
        Create an agent adapter by type.

        :param agent_type: Agent type name
        :param kwargs: Additional arguments for the adapter
        :return: Agent adapter instance
        :raises ValueError: If agent type is unknown
        """
        if agent_type not in cls._adapters:
            available = ", ".join(cls._adapters.keys())
            raise ValueError(
                f"Unknown agent type: {agent_type}. Available: {available}"
            )
        return cls._adapters[agent_type](**kwargs)

    @classmethod
    def register(cls, name: str, adapter_class: Type[AgentAdapter]) -> None:
        """
        Register a custom agent adapter.

        :param name: Adapter name
        :param adapter_class: Adapter class
        """
        cls._adapters[name] = adapter_class

    @classmethod
    def available_adapters(cls) -> list[str]:
        """Get list of available adapter names."""
        return list(cls._adapters.keys())

    @classmethod
    def is_available(cls, agent_type: str) -> bool:
        """Check if an adapter type is available."""
        return agent_type in cls._adapters
