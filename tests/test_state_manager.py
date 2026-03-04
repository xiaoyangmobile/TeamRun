"""
Tests for state manager behavior.
"""

from trun.scheduler.state_manager import StateManager
from trun.todo.models import StepStatus, TodoFile, TodoMeta


def test_save_todo_falls_back_to_main_todo_when_file_path_empty(tmp_path):
    """Saving a TodoFile with empty file_path should use main.todo.md."""
    manager = StateManager(tmp_path / ".team_run")
    todo = TodoFile(
        file_path="",
        meta=TodoMeta(title="test", status=StepStatus.PENDING),
        steps=[],
    )

    manager.save_todo(todo)

    assert manager.main_todo_path.exists()

