"""
Tests for configuration management.
"""

import json
import pytest
from pathlib import Path

from trun.config import ConfigManager, RoleConfig, TeamConfig, ServiceLLMConfig


class TestRoleConfig:
    """Tests for RoleConfig."""

    def test_create_role(self):
        """Test creating a role configuration."""
        role = RoleConfig(
            name="项目经理",
            description="负责项目规划",
            agent="claude-code",
            prompt="你是项目经理"
        )

        assert role.name == "项目经理"
        assert role.agent == "claude-code"

    def test_get_prompt_inline(self):
        """Test getting inline prompt."""
        role = RoleConfig(
            name="Test",
            description="Test",
            agent="claude-code",
            prompt="Inline prompt"
        )

        assert role.get_prompt() == "Inline prompt"

    def test_get_prompt_from_file(self, tmp_path):
        """Test getting prompt from file."""
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("File prompt content", encoding="utf-8")

        role = RoleConfig(
            name="Test",
            description="Test",
            agent="claude-code",
            prompt_file=str(prompt_file)
        )

        assert role.get_prompt() == "File prompt content"


class TestTeamConfig:
    """Tests for TeamConfig."""

    def test_add_remove_role(self):
        """Test adding and removing roles."""
        config = TeamConfig()

        role = RoleConfig(
            name="PM",
            description="Project Manager",
            agent="claude-code"
        )

        config.add_role("pm", role)
        assert "pm" in config.roles
        assert config.get_role("pm") == role

        assert config.remove_role("pm") is True
        assert "pm" not in config.roles
        assert config.remove_role("pm") is False

    def test_save_load(self, tmp_path):
        """Test saving and loading configuration."""
        config = TeamConfig()
        config.add_role("pm", RoleConfig(
            name="PM",
            description="Project Manager",
            agent="claude-code",
            prompt="You are a PM"
        ))
        config.service_llm = ServiceLLMConfig(
            provider="openai",
            model="gpt-4"
        )

        config_path = tmp_path / "team.config.json"
        config.save(config_path)

        loaded = TeamConfig.load(config_path)
        assert "pm" in loaded.roles
        assert loaded.roles["pm"].name == "PM"
        assert loaded.service_llm.model == "gpt-4"


class TestConfigManager:
    """Tests for ConfigManager."""

    def test_ensure_directories(self, tmp_path):
        """Test directory creation."""
        manager = ConfigManager(project_dir=tmp_path)
        base_dir = manager.ensure_directories(project_level=True)

        assert base_dir.exists()
        assert (base_dir / "todos").exists()
        assert (base_dir / "context").exists()
        assert (base_dir / "outputs").exists()
        assert (base_dir / "logs").exists()

    def test_init_project(self, tmp_path):
        """Test project initialization."""
        manager = ConfigManager(project_dir=tmp_path)
        base_dir = manager.init_project()

        assert base_dir.exists()
        assert manager.project_config_path.exists()

    def test_config_priority(self, tmp_path):
        """Test project config takes priority over global."""
        manager = ConfigManager(project_dir=tmp_path)

        # Create project config
        manager.ensure_directories(project_level=True)
        project_config = TeamConfig()
        project_config.add_role("project_role", RoleConfig(
            name="Project",
            description="From project",
            agent="claude-code"
        ))
        project_config.save(manager.project_config_path)

        # Load should use project config
        loaded = manager.load_config()
        assert "project_role" in loaded.roles
