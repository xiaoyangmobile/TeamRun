"""
Configuration management for TeamRun.
"""

import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ============== Project Registry ==============

class ProjectInfo(BaseModel):
    """Information about a registered project."""

    work_path: str = Field(..., description="Working directory path for the project")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Project creation time")
    description: str = Field(default="", description="Optional project description")


class ProjectRegistry:
    """Manages project registration in ~/.team_run/projects.json."""

    GLOBAL_DIR = Path.home() / ".team_run"
    PROJECTS_FILE = "projects.json"

    def __init__(self):
        """Initialize project registry."""
        self._projects: dict[str, ProjectInfo] | None = None

    @property
    def projects_file_path(self) -> Path:
        """Path to the projects.json file."""
        return self.GLOBAL_DIR / self.PROJECTS_FILE

    def _ensure_global_dir(self) -> None:
        """Ensure the global .team_run directory exists."""
        self.GLOBAL_DIR.mkdir(parents=True, exist_ok=True)

    def _load_projects(self) -> dict[str, ProjectInfo]:
        """Load projects from projects.json."""
        if self._projects is not None:
            return self._projects

        if not self.projects_file_path.exists():
            self._projects = {}
            return self._projects

        with open(self.projects_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._projects = {
            name: ProjectInfo.model_validate(info)
            for name, info in data.items()
        }
        return self._projects

    def _save_projects(self) -> None:
        """Save projects to projects.json."""
        self._ensure_global_dir()

        projects = self._load_projects()
        data = {
            name: info.model_dump()
            for name, info in projects.items()
        }

        with open(self.projects_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def register_project(
        self,
        name: str,
        work_path: Path | str | None = None,
        description: str = ""
    ) -> ProjectInfo:
        """
        Register a new project.

        :param name: Project name (used as key)
        :param work_path: Working directory path (defaults to current directory)
        :param description: Optional project description
        :return: The created ProjectInfo
        """
        projects = self._load_projects()

        # Default to current directory if not specified
        if work_path is None:
            work_path = Path.cwd()
        else:
            work_path = Path(work_path).resolve()

        project_info = ProjectInfo(
            work_path=str(work_path),
            description=description
        )

        projects[name] = project_info
        self._save_projects()

        return project_info

    def get_project(self, name: str) -> ProjectInfo | None:
        """
        Get project info by name.

        :param name: Project name
        :return: ProjectInfo or None if not found
        """
        projects = self._load_projects()
        return projects.get(name)

    def get_work_path(self, name: str) -> Path | None:
        """
        Get work path for a project.

        :param name: Project name
        :return: Path to working directory or None if not found
        """
        project = self.get_project(name)
        if project:
            return Path(project.work_path)
        return None

    def list_projects(self) -> dict[str, ProjectInfo]:
        """
        List all registered projects.

        :return: Dictionary of project name to ProjectInfo
        """
        return self._load_projects().copy()

    def remove_project(self, name: str) -> bool:
        """
        Remove a project from the registry.

        :param name: Project name
        :return: True if removed, False if not found
        """
        projects = self._load_projects()
        if name in projects:
            del projects[name]
            self._save_projects()
            return True
        return False

    def project_exists(self, name: str) -> bool:
        """
        Check if a project exists.

        :param name: Project name
        :return: True if exists
        """
        return name in self._load_projects()


# ============== Replan Configuration ==============

class ReplanPolicy(str, Enum):
    """Policy for handling step failures."""

    DISABLED = "disabled"   # No replan, fail immediately
    AUTO = "auto"           # Automatically replan (local)
    CONFIRM = "confirm"     # Ask for confirmation before replan


class ReplanConfig(BaseModel):
    """Configuration for replan behavior."""

    policy: ReplanPolicy = Field(
        default=ReplanPolicy.AUTO,
        description="Replan policy: disabled, auto, or confirm"
    )
    max_attempts: int = Field(
        default=3,
        description="Maximum replan attempts per step"
    )
    scope: str = Field(
        default="local",
        description="Replan scope: 'local' (single step + dependents) or 'global' (full replan)"
    )


# ============== Validator Configuration ==============

class DefaultValidatorConfig(BaseModel):
    """Default validator settings."""

    auto_file_check: bool = Field(
        default=True,
        description="Automatically check output file existence"
    )
    auto_completion_marker: bool = Field(
        default=True,
        description="Check for <!-- TASK_COMPLETED --> marker"
    )
    test_command: str = Field(
        default="pytest",
        description="Default test command"
    )
    test_timeout: int = Field(
        default=300,
        description="Test timeout in seconds"
    )


class RoleConfig(BaseModel):
    """Configuration for a single role."""

    name: str = Field(..., description="Display name of the role")
    description: str = Field(..., description="Description of the role's responsibilities")
    agent: str = Field(..., description="Agent type: claude-code, codex, etc.")


class TeamConfig(BaseModel):
    """Main configuration for TeamRun."""

    roles: dict[str, RoleConfig] = Field(default_factory=dict, description="Role configurations")
    replan: ReplanConfig = Field(default_factory=ReplanConfig, description="Replan configuration")
    validators: DefaultValidatorConfig = Field(default_factory=DefaultValidatorConfig, description="Default validator config")

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
    PROJECT_FILE = "project.json"  # Stores project name

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

    @property
    def project_file_path(self) -> Path:
        """Path to project.json in .team_run directory."""
        return self.project_dir / self.PROJECT_DIR / self.PROJECT_FILE

    def save_project_name(self, project_name: str) -> None:
        """
        Save project name to .team_run/project.json.

        :param project_name: Project name to save
        """
        project_file = self.project_file_path
        project_file.parent.mkdir(parents=True, exist_ok=True)

        with open(project_file, "w", encoding="utf-8") as f:
            json.dump({"project_name": project_name}, f, indent=2, ensure_ascii=False)

    def load_project_name(self) -> str | None:
        """
        Load project name from .team_run/project.json.

        :return: Project name or None if not found
        """
        project_file = self.project_file_path
        if not project_file.exists():
            return None

        try:
            with open(project_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("project_name")
        except (json.JSONDecodeError, KeyError):
            return None

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
