"""
Workflow scheduler for TODO execution.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..adapters.base import AgentResult
from ..adapters.factory import AdapterFactory
from ..config import ConfigManager, TeamConfig
from ..todo.generator import TodoGenerator
from ..todo.models import Step, StepStatus, StepType, TodoFile
from ..tools.git_ops import GitOpsTool
from ..utils.logger import get_logger
from .state_manager import StateManager


class HumanInteractionHandler:
    """Handler for human interaction points."""

    def __init__(self):
        self.auto_approve = False

    async def handle_review(
        self,
        step: Step,
        output_file: Path | None
    ) -> tuple[str, str | None]:
        """
        Handle human review interaction.

        :param step: The @human step
        :param output_file: File to review (if any)
        :return: Tuple of (action, feedback)
                 action: "pass", "reject", "quit"
                 feedback: Optional feedback text
        """
        if self.auto_approve:
            return ("pass", None)

        # This is a placeholder - actual implementation would use
        # rich/click for CLI interaction
        print(f"\n[TeamRun] 等待人工审核...")
        if output_file and output_file.exists():
            print(f"[TeamRun] 请查看文件：{output_file}")

        print("\n选项：")
        print("  [p] 通过 (pass)")
        print("  [r] 驳回 (reject)")
        print("  [m] 添加修改意见")
        print("  [q] 退出")

        while True:
            choice = input("\n> ").strip().lower()

            if choice == 'p':
                return ("pass", None)
            elif choice == 'r':
                return ("reject", None)
            elif choice == 'm':
                print("请输入修改意见（输入空行结束）：")
                lines = []
                while True:
                    line = input("> ")
                    if not line:
                        break
                    lines.append(line)
                feedback = "\n".join(lines)
                return ("reject", feedback)
            elif choice == 'q':
                return ("quit", None)
            else:
                print("无效选项，请重新输入")


class Scheduler:
    """
    Workflow scheduler for executing TODO files.

    Handles:
    - Step execution based on type
    - Dependency resolution
    - Parallel execution
    - Gate conditions
    - Human interaction
    """

    def __init__(
        self,
        config: TeamConfig,
        team_run_dir: str | Path = ".team_run",
        auto_approve: bool = False
    ):
        """
        Initialize scheduler.

        :param config: Team configuration
        :param team_run_dir: Path to .team_run directory
        :param auto_approve: Auto-approve human review steps
        """
        self.config = config
        self.team_run_dir = Path(team_run_dir)
        self.state_manager = StateManager(team_run_dir)
        self.git = GitOpsTool()
        self.logger = get_logger()

        self.human_handler = HumanInteractionHandler()
        self.human_handler.auto_approve = auto_approve

        self._running = False
        self._should_stop = False

    async def start(self, task_description: str) -> None:
        """
        Start a new task from description.

        :param task_description: User's task description
        """
        self.logger.info(f"Starting new task: {task_description[:50]}...")

        # Generate TODO
        generator = TodoGenerator(self.config)
        todo = await generator.generate(
            task_description,
            output_path=str(self.state_manager.main_todo_path)
        )

        # Save user request
        request_path = self.team_run_dir / "inputs" / "user_request.md"
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(
            f"# 用户需求\n\n{task_description}\n\n创建时间：{datetime.now()}",
            encoding="utf-8"
        )

        # Start execution
        await self.run(todo)

    async def resume(self) -> None:
        """Resume execution from the current state."""
        todo = self.state_manager.load_main_todo()
        if not todo:
            self.logger.error("No task to resume")
            raise ValueError("No active task found")

        self.logger.info(f"Resuming task: {todo.meta.title}")
        await self.run(todo)

    async def run(self, todo: TodoFile) -> None:
        """
        Run the TODO workflow.

        :param todo: TodoFile to execute
        """
        self._running = True
        self._should_stop = False

        self.logger.info(f"Running workflow: {todo.meta.title}")

        # Update overall status to running
        todo.meta.status = StepStatus.RUNNING
        self.state_manager.save_todo(todo)

        try:
            while not self._should_stop:
                # Get next step
                next_step = todo.get_next_step()

                if not next_step:
                    if todo.is_completed():
                        self.logger.info("Workflow completed successfully")
                        todo.meta.status = StepStatus.DONE
                    else:
                        self.logger.warning("Workflow blocked - no executable steps")
                    break

                # Execute step
                result = await self._execute_step(todo, next_step)

                if not result:
                    # Step failed or user quit
                    break

                # Reload TODO in case it was modified
                todo = self.state_manager.load_main_todo() or todo

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {str(e)}")
            todo.meta.status = StepStatus.FAILED
            raise

        finally:
            self._running = False
            self.state_manager.save_todo(todo)

    async def _execute_step(self, todo: TodoFile, step: Step) -> bool:
        """
        Execute a single step.

        :param todo: Parent TodoFile
        :param step: Step to execute
        :return: True if should continue, False to stop
        """
        self.logger.step(step.id, "starting", f"Executing {step.type.value}: {step.description}")
        self.state_manager.update_step_status(todo, step.id, StepStatus.RUNNING)

        try:
            if step.type == StepType.TASK:
                success = await self._execute_task(step)
            elif step.type == StepType.DISCUSS:
                success = await self._execute_discussion(todo, step)
            elif step.type == StepType.PARALLEL:
                success = await self._execute_parallel(todo, step)
            elif step.type == StepType.GATE:
                success = await self._execute_gate(todo, step)
            elif step.type == StepType.HUMAN:
                result = await self._execute_human(todo, step)
                if result == "quit":
                    return False
                success = result == "pass"
            elif step.type == StepType.GOTO:
                # GOTO doesn't really "execute", just marks as done
                success = True
            else:
                self.logger.error(f"Unknown step type: {step.type}")
                success = False

            if success:
                self.state_manager.update_step_status(todo, step.id, StepStatus.DONE)
                self.logger.step(step.id, "completed", f"Step completed")
            else:
                self.state_manager.update_step_status(todo, step.id, StepStatus.FAILED)
                self.logger.step(step.id, "failed", f"Step failed")
                return False

            return True

        except Exception as e:
            self.state_manager.update_step_status(todo, step.id, StepStatus.FAILED)
            self.logger.error(f"Step {step.id} failed with error: {str(e)}")
            return False

    async def _execute_task(self, step: Step) -> bool:
        """Execute a TASK step."""
        if not step.role:
            self.logger.error(f"Task step {step.id} has no role assigned")
            return False

        role_config = self.config.get_role(step.role)
        if not role_config:
            self.logger.error(f"Role not found: {step.role}")
            return False

        # Create context file
        context_path = self.state_manager.create_context_file(
            step,
            role_config.get_prompt(self.team_run_dir)
        )

        # Get adapter
        try:
            adapter = AdapterFactory.create(role_config.agent)
        except ValueError as e:
            self.logger.error(str(e))
            return False

        # Execute
        result = await adapter.execute(str(context_path))

        if not result.success:
            self.logger.error(f"Agent execution failed: {result.error}")
            return False

        return True

    async def _execute_discussion(self, todo: TodoFile, step: Step) -> bool:
        """Execute a DISCUSS step."""
        # TODO: Implement discussion logic
        # For now, just mark as done
        self.logger.info(f"Discussion step {step.id} - implementation pending")
        return True

    async def _execute_parallel(self, todo: TodoFile, step: Step) -> bool:
        """Execute a PARALLEL step with Git branch isolation."""
        if not step.subtasks:
            return True

        original_branch = self.git.current_branch()
        branches = []

        try:
            # Create branches for each subtask
            for subtask in step.subtasks:
                branch_name = f"trun/{step.id}/{subtask.id}"
                self.git.create_branch(branch_name, original_branch)
                branches.append((subtask, branch_name))

            # Execute subtasks in parallel
            tasks = []
            for subtask, branch in branches:
                self.git.switch_branch(branch)
                tasks.append(self._execute_task(subtask))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Switch back to original branch
            self.git.switch_branch(original_branch)

            # Check results and merge
            all_success = True
            for (subtask, branch), result in zip(branches, results):
                if isinstance(result, Exception):
                    self.logger.error(f"Subtask {subtask.id} failed: {str(result)}")
                    all_success = False
                elif not result:
                    all_success = False

            if not all_success:
                return False

            # Merge branches
            for subtask, branch in branches:
                merge_result = self.git.merge_branch(branch)
                if not merge_result["success"]:
                    conflicts = self.git.check_conflicts()
                    if conflicts["has_conflicts"]:
                        self.logger.error(
                            f"Merge conflict in branch {branch}. "
                            f"Conflicted files: {conflicts['conflicted_files']}"
                        )
                        return False

                # Delete merged branch
                self.git.delete_branch(branch)

            return True

        except Exception as e:
            # Cleanup: switch back to original branch
            if original_branch:
                self.git.switch_branch(original_branch)
            raise

    async def _execute_gate(self, todo: TodoFile, step: Step) -> bool:
        """Execute a GATE step."""
        # TODO: Implement condition evaluation using Service LLM
        # For now, always pass
        self.logger.info(f"Gate step {step.id} - condition: {step.condition}")
        return True

    async def _execute_human(self, todo: TodoFile, step: Step) -> str:
        """
        Execute a HUMAN step.

        :return: "pass", "reject", or "quit"
        """
        # Find the output file from the previous step
        output_file = None
        if step.depends:
            for dep_id in step.depends:
                dep_step = todo.get_step(dep_id)
                if dep_step and dep_step.output:
                    output_file = self.state_manager.get_output_path(dep_step.output)
                    break

        action, feedback = await self.human_handler.handle_review(step, output_file)

        if feedback:
            # Save feedback for the step to reject to
            reject_step_id = step.reject_step or (step.depends[0] if step.depends else None)
            if reject_step_id:
                self.state_manager.save_feedback(reject_step_id, feedback)

        return action

    def stop(self) -> None:
        """Stop the current execution."""
        self._should_stop = True
        self.logger.info("Stop requested")
