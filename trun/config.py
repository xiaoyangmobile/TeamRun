"""
Configuration management for TeamRun.
"""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RoleConfig(BaseModel):
    """Configuration for a single role."""

    name: str = Field(..., description="Display name of the role")
    description: str = Field(..., description="Description of the role's responsibilities")
    agent: str = Field(..., description="Agent type: claude-code, codex, etc.")
    prompt: str | None = Field(None, description="System prompt for the role")
    prompt_file: str | None = Field(None, description="Path to prompt file")

    def get_prompt(self, base_dir: Path | None = None) -> str:
        """Get the prompt content, either inline or from file."""
        if self.prompt:
            return self.prompt
        if self.prompt_file:
            prompt_path = Path(self.prompt_file)
            if base_dir and not prompt_path.is_absolute():
                prompt_path = base_dir / prompt_path
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8")
        return ""


class ServiceLLMConfig(BaseModel):
    """Configuration for the service LLM. All settings can be overridden by environment variables."""

    provider: str = Field(default="openai", description="LLM provider")
    model: str = Field(default="gpt-4", description="Model name")
    api_key_env: str = Field(default="OPENAI_API_KEY", description="Environment variable for API key")

    @classmethod
    def from_env(cls) -> "ServiceLLMConfig":
        """Create config from environment variables."""
        return cls(
            provider=os.getenv("TRUN_LLM_PROVIDER", "openai"),
            model=os.getenv("TRUN_LLM_MODEL", "gpt-4"),
            api_key_env=os.getenv("TRUN_LLM_API_KEY_ENV", "OPENAI_API_KEY"),
        )

    def get_provider(self) -> str:
        """Get provider, with env override."""
        return os.getenv("TRUN_LLM_PROVIDER", self.provider)

    def get_model(self) -> str:
        """Get model, with env override."""
        return os.getenv("TRUN_LLM_MODEL", self.model)

    def get_api_key(self) -> str | None:
        """Get API key from environment."""
        api_key_env = os.getenv("TRUN_LLM_API_KEY_ENV", self.api_key_env)
        return os.getenv(api_key_env)


class TeamConfig(BaseModel):
    """Main configuration for TeamRun."""

    roles: dict[str, RoleConfig] = Field(default_factory=dict, description="Role configurations")
    service_llm: ServiceLLMConfig = Field(default_factory=ServiceLLMConfig, description="Service LLM config")

    @classmethod
    def load(cls, config_path: Path | str) -> "TeamConfig":
        """Load configuration from a JSON file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls.model_validate(data)

    def save(self, config_path: Path | str) -> None:
        """Save configuration to a JSON file."""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)

    def get_role(self, role_id: str) -> RoleConfig | None:
        """Get role configuration by ID."""
        return self.roles.get(role_id)

    def add_role(self, role_id: str, role: RoleConfig) -> None:
        """Add or update a role."""
        self.roles[role_id] = role

    def remove_role(self, role_id: str) -> bool:
        """Remove a role. Returns True if removed, False if not found."""
        if role_id in self.roles:
            del self.roles[role_id]
            return True
        return False


class ConfigManager:
    """Manages configuration loading with global/project priority."""

    GLOBAL_DIR = Path.home() / ".team_run"
    PROJECT_DIR = ".team_run"
    CONFIG_FILE = "team.config.json"

    def __init__(self, project_dir: Path | str | None = None):
        """
        Initialize config manager.

        :param project_dir: Project directory (defaults to current working directory)
        """
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self._config: TeamConfig | None = None

    @property
    def global_config_path(self) -> Path:
        """Global configuration file path."""
        return self.GLOBAL_DIR / self.CONFIG_FILE

    @property
    def project_config_path(self) -> Path:
        """Project-level configuration file path."""
        return self.project_dir / self.PROJECT_DIR / self.CONFIG_FILE

    @property
    def active_config_path(self) -> Path:
        """Get the active configuration path (project > global)."""
        if self.project_config_path.exists():
            return self.project_config_path
        return self.global_config_path

    @property
    def team_run_dir(self) -> Path:
        """Get the active .team_run directory."""
        if (self.project_dir / self.PROJECT_DIR).exists():
            return self.project_dir / self.PROJECT_DIR
        return self.GLOBAL_DIR

    def load_config(self) -> TeamConfig:
        """
        Load configuration with priority: project > global.
        Creates default config if none exists.
        """
        if self._config is not None:
            return self._config

        # Try project config first
        if self.project_config_path.exists():
            self._config = TeamConfig.load(self.project_config_path)
            return self._config

        # Try global config
        if self.global_config_path.exists():
            self._config = TeamConfig.load(self.global_config_path)
            return self._config

        # Create default config
        self._config = TeamConfig()
        return self._config

    def save_config(self, config: TeamConfig | None = None, to_project: bool = True) -> Path:
        """
        Save configuration to file.

        :param config: Configuration to save (uses cached if None)
        :param to_project: Save to project config (True) or global (False)
        :return: Path where config was saved
        """
        config = config or self._config or TeamConfig()

        if to_project:
            path = self.project_config_path
        else:
            path = self.global_config_path

        config.save(path)
        self._config = config
        return path

    def ensure_directories(self, project_level: bool = True) -> Path:
        """
        Ensure .team_run directories exist.

        :param project_level: Create project-level directory (True) or global (False)
        :return: Path to the created directory
        """
        if project_level:
            base_dir = self.project_dir / self.PROJECT_DIR
        else:
            base_dir = self.GLOBAL_DIR

        # Create subdirectories
        subdirs = ["todos", "context", "outputs", "inputs", "feedback", "logs", "prompts"]
        for subdir in subdirs:
            (base_dir / subdir).mkdir(parents=True, exist_ok=True)

        return base_dir

    def init_project(self) -> Path:
        """
        Initialize a new project with default configuration.

        :return: Path to the created .team_run directory
        """
        base_dir = self.ensure_directories(project_level=True)

        # Create default config if not exists
        if not self.project_config_path.exists():
            default_config = TeamConfig()
            default_config.save(self.project_config_path)

        return base_dir
