"""
Environment variable management.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env(project_dir: str | Path | None = None) -> None:
    """
    Load environment variables from .env file.

    Priority:
    1. Project-level .env (if project_dir provided)
    2. Current working directory .env
    3. System environment variables

    :param project_dir: Project directory path
    """
    # Load from project directory if provided
    if project_dir:
        project_env = Path(project_dir) / ".env"
        if project_env.exists():
            load_dotenv(project_env)
            return

    # Load from current working directory
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        load_dotenv(cwd_env)


def get_env(key: str, default: str | None = None, required: bool = False) -> str | None:
    """
    Get environment variable value.

    :param key: Environment variable name
    :param default: Default value if not found
    :param required: Raise error if not found and no default
    :return: Environment variable value
    :raises ValueError: If required and not found
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' is not set")
    return value


def get_tavily_api_key() -> str:
    """Get Tavily API key from environment."""
    return get_env("TAVILY_API_KEY", required=True)


def get_openai_api_key() -> str | None:
    """Get OpenAI API key from environment."""
    return get_env("OPENAI_API_KEY")


def get_anthropic_api_key() -> str | None:
    """Get Anthropic API key from environment."""
    return get_env("ANTHROPIC_API_KEY")
