"""
State manager for TODO execution.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from ..todo.models import Step, StepStatus, TodoFile
from ..todo.parser import TodoParser, TodoWriter
from ..utils.logger import get_logger


class StateManager:
    """
    Manages the state of TODO execution.

    Handles:
    - Loading and saving TODO state
    - Updating step status
    - Managing context files
    - Tracking execution history
    """

    def __init__(self, team_run_dir: str | Path = ".team_run"):
        """
        Initialize state manager.

        :param team_run_dir: Path to .team_run directory
        """
        self.team_run_dir = Path(team_run_dir)
        self.todos_dir = self.team_run_dir / "todos"
        self.context_dir = self.team_run_dir / "context"
        self.outputs_dir = self.team_run_dir / "outputs"
        self.feedback_dir = self.team_run_dir / "feedback"

        self.logger = get_logger()
        self.parser = TodoParser()
        self.writer = TodoWriter()

        # Ensure directories exist
        for dir_path in [self.todos_dir, self.context_dir, self.outputs_dir, self.feedback_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    @property
    def main_todo_path(self) -> Path:
        """Path to the main TODO file."""
        return self.todos_dir / "main.todo.md"

    def load_main_todo(self) -> TodoFile | None:
        """
        Load the main TODO file.

        :return: TodoFile or None if not found
        """
        if not self.main_todo_path.exists():
            return None
        return self.parser.parse_file(self.main_todo_path)

    def save_todo(self, todo: TodoFile, path: Path | None = None) -> None:
        """
        Save a TODO file.

        :param todo: TodoFile to save
        :param path: Optional path (uses todo.file_path if not provided)
        """
        save_path = path or Path(todo.file_path) or self.main_todo_path
        self.writer.write_file(todo, save_path)
        self.logger.debug(f"Saved TODO to: {save_path}")

    def update_step_status(
        self,
        todo: TodoFile,
        step_id: str,
        status: StepStatus
    ) -> None:
        """
        Update a step's status and save.

        :param todo: TodoFile containing the step
        :param step_id: Step ID to update
        :param status: New status
        """
        if todo.update_step_status(step_id, status):
            self.save_todo(todo)
            self.logger.step(step_id, status.value, f"Status updated to {status.value}")

    def create_context_file(
        self,
        step: Step,
        role_prompt: str,
        input_files: list[str] | None = None
    ) -> Path:
        """
        Create a context file for a step.

        :param step: Step to create context for
        :param role_prompt: Role's system prompt
        :param input_files: List of input file paths
        :return: Path to the created context file
        """
        context_path = self.context_dir / f"{step.id}_context.md"

        content_lines = [
            "# 任务上下文",
            "",
            "## 角色",
            role_prompt,
            "",
            "## 任务",
            step.description or step.instruction or "执行任务",
            "",
        ]

        if step.instruction:
            content_lines.extend([
                "## 详细指令",
                step.instruction,
                "",
            ])

        if input_files or step.inputs:
            content_lines.append("## 输入文件")
            for f in (input_files or step.inputs):
                content_lines.append(f"- {f}")
            content_lines.append("")

        if step.output:
            content_lines.extend([
                "## 输出要求",
                f"- 输出文件：{self.outputs_dir / step.output}",
                "- 完成后在文件末尾添加标记：<!-- TASK_COMPLETED -->",
                "",
            ])

        # Check for feedback
        feedback_file = self.feedback_dir / f"{step.id}_feedback.md"
        if feedback_file.exists():
            feedback_content = feedback_file.read_text(encoding="utf-8")
            content_lines.extend([
                "## 修改意见（请特别注意）",
                feedback_content,
                "",
            ])

        content = "\n".join(content_lines)
        context_path.write_text(content, encoding="utf-8")

        self.logger.debug(f"Created context file: {context_path}")
        return context_path

    def save_feedback(self, step_id: str, feedback: str) -> Path:
        """
        Save feedback for a step.

        :param step_id: Step ID
        :param feedback: Feedback content
        :return: Path to feedback file
        """
        feedback_path = self.feedback_dir / f"{step_id}_feedback.md"
        feedback_path.write_text(feedback, encoding="utf-8")
        self.logger.info(f"Saved feedback to: {feedback_path}")
        return feedback_path

    def get_output_path(self, filename: str) -> Path:
        """
        Get full path for an output file.

        :param filename: Output filename
        :return: Full path in outputs directory
        """
        return self.outputs_dir / filename

    def check_output_completed(self, output_path: Path | str) -> bool:
        """
        Check if an output file has the completion marker.

        :param output_path: Path to output file
        :return: True if completed marker found
        """
        path = Path(output_path)
        if not path.exists():
            return False

        content = path.read_text(encoding="utf-8")
        return "<!-- TASK_COMPLETED -->" in content

    def get_current_state(self) -> dict[str, Any]:
        """
        Get current execution state summary.

        :return: State summary dict
        """
        todo = self.load_main_todo()
        if not todo:
            return {"status": "no_task", "message": "No active task found"}

        completed = todo.get_completed_steps()
        failed = todo.get_failed_steps()
        next_step = todo.get_next_step()

        return {
            "status": "running" if next_step else ("completed" if todo.is_completed() else "blocked"),
            "title": todo.meta.title,
            "total_steps": len(todo.steps),
            "completed_steps": len(completed),
            "failed_steps": len(failed),
            "next_step": next_step.id if next_step else None,
            "is_completed": todo.is_completed(),
        }
