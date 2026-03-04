"""
Workflow scheduler for TODO execution.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..adapters.base import AgentResult
from ..adapters.factory import AdapterFactory
from ..config import ConfigManager, ReplanPolicy, TeamConfig
from ..todo.generator import TodoGenerator
from ..todo.models import Step, StepStatus, StepType, TodoFile, ValidationResult
from ..tools.git_ops import GitOpsTool
from ..utils.logger import get_logger
from ..validators.factory import StepValidator, ValidatorFactory
from .replan import ReplanEngine
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

    async def confirm_replan(
        self,
        step: Step,
        error: str
    ) -> bool:
        """
        Ask user to confirm replan.

        :param step: The failed step
        :param error: Error message
        :return: True if user confirms
        """
        print(f"\n[TeamRun] 步骤 {step.id} 执行失败")
        print(f"[TeamRun] 原因: {error[:200]}")
        print("\n是否进行重规划？")
        print("  [y] 是，重新规划")
        print("  [n] 否，停止执行")

        while True:
            choice = input("\n> ").strip().lower()
            if choice in ['y', 'yes', '是']:
                return True
            elif choice in ['n', 'no', '否']:
                return False
            else:
                print("请输入 y 或 n")


class Scheduler:
    """
    Workflow scheduler for executing TODO files.

    Handles:
    - Step execution based on type
    - Dependency resolution
    - Parallel execution
    - Gate conditions
    - Human interaction
    - Output validation (NEW)
    - Controlled replan on failure (NEW)
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

        # NEW: Initialize validator
        self.step_validator = StepValidator(working_dir=str(self.team_run_dir / "outputs"))

        # NEW: Initialize replan engine
        available_roles = {
            role_id: role.description
            for role_id, role in config.roles.items()
        }
        self.replan_engine = ReplanEngine(
            config=config.replan,
            available_roles=available_roles
        )

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
                # Reload TODO to get latest state (may have been modified by jumps)
                todo = self.state_manager.load_main_todo() or todo

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
                should_continue, jump_to = await self._execute_step(todo, next_step)

                if not should_continue:
                    # Step failed or user quit
                    break

                # If there's a jump, the target step has been reset to PENDING
                # The next iteration will pick it up via get_next_step()
                if jump_to:
                    self.logger.info(f"Jump triggered, will execute {jump_to} next")

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {str(e)}")
            todo.meta.status = StepStatus.FAILED
            raise

        finally:
            self._running = False
            self.state_manager.save_todo(todo)

    async def _execute_step(self, todo: TodoFile, step: Step) -> tuple[bool, str | None]:
        """
        Execute a single step with validation and replan support.

        :param todo: Parent TodoFile
        :param step: Step to execute
        :return: Tuple of (should_continue, jump_to_step_id)
                 - should_continue: True if should continue workflow
                 - jump_to_step_id: If set, jump to this step (reset it to PENDING)
        """
        self.logger.step(step.id, "starting", f"Executing {step.type.value}: {step.description}")
        self.state_manager.update_step_status(todo, step.id, StepStatus.RUNNING)

        try:
            jump_to: str | None = None
            success = False
            error_message = ""

            if step.type == StepType.TASK:
                success, error_message = await self._execute_task_with_validation(step)
            elif step.type == StepType.DISCUSS:
                success = await self._execute_discussion(todo, step)
                if not success:
                    error_message = "Discussion failed"
            elif step.type == StepType.PARALLEL:
                success = await self._execute_parallel(todo, step)
                if not success:
                    error_message = "Parallel execution failed"
            elif step.type == StepType.GATE:
                gate_passed = await self._execute_gate(todo, step)
                if gate_passed:
                    success = True
                    if step.pass_step:
                        jump_to = step.pass_step
                        self.logger.info(f"Gate {step.id} passed, jumping to {step.pass_step}")
                else:
                    if step.reject_step:
                        jump_to = step.reject_step
                        success = True  # Gate itself succeeded, just taking reject path
                        self.logger.info(f"Gate {step.id} failed, jumping to {step.reject_step}")
                    else:
                        success = False
                        error_message = "Gate condition failed"
            elif step.type == StepType.HUMAN:
                result = await self._execute_human(todo, step)
                if result == "quit":
                    return (False, None)
                if result == "pass":
                    success = True
                    if step.pass_step:
                        jump_to = step.pass_step
                        self.logger.info(f"Human review passed, jumping to {step.pass_step}")
                else:
                    success = False
                    error_message = "Human review rejected"
                    if step.reject_step:
                        jump_to = step.reject_step
                        success = True  # Human step itself succeeded
                        self.logger.info(f"Human review rejected, jumping to {step.reject_step}")
            elif step.type == StepType.GOTO:
                # GOTO: jump to target step
                if step.target_step:
                    jump_to = step.target_step
                    self.logger.info(f"GOTO: jumping to {step.target_step}")
                success = True
            else:
                self.logger.error(f"Unknown step type: {step.type}")
                success = False
                error_message = f"Unknown step type: {step.type}"

            if success:
                self.state_manager.update_step_status(todo, step.id, StepStatus.DONE)
                self.logger.step(step.id, "completed", f"Step completed")

                # Handle jump: reset target step and its dependents
                if jump_to:
                    self._reset_step_for_retry(todo, jump_to)

                return (True, jump_to)
            else:
                # Step failed - try replan
                return await self._handle_step_failure(todo, step, error_message)

        except Exception as e:
            error_message = str(e)
            self.logger.error(f"Step {step.id} failed with error: {error_message}")
            return await self._handle_step_failure(todo, step, error_message)

    async def _handle_step_failure(
        self,
        todo: TodoFile,
        step: Step,
        error: str
    ) -> tuple[bool, str | None]:
        """
        Handle a step failure with potential replan.

        :param todo: TodoFile containing the failed step
        :param step: The failed step
        :param error: Error message
        :return: Tuple of (should_continue, jump_to)
        """
        self.logger.step(step.id, "failed", f"Step failed: {error}")

        # Check if we can replan
        can_replan, reason = self.replan_engine.can_replan(step)

        if not can_replan:
            self.logger.info(f"Cannot replan: {reason}")
            self.state_manager.update_step_status(todo, step.id, StepStatus.FAILED)
            return (False, None)

        # Get confirmation if needed
        confirm_callback = None
        if self.config.replan.policy == ReplanPolicy.CONFIRM:
            confirm_callback = self.human_handler.confirm_replan

        # Try to replan
        should_continue, new_steps = await self.replan_engine.handle_failure(
            todo=todo,
            failed_step=step,
            error=error,
            confirm_callback=confirm_callback
        )

        if should_continue and new_steps:
            # Replan succeeded - save the updated TODO
            self.state_manager.save_todo(todo)
            self.logger.info(
                f"Replan applied: {step.id} replaced with {[s.id for s in new_steps]}"
            )
            # Continue execution - the new steps are now in the TODO
            return (True, None)
        else:
            # Replan failed or was rejected
            self.state_manager.update_step_status(todo, step.id, StepStatus.FAILED)
            return (False, None)

    async def _execute_task_with_validation(self, step: Step) -> tuple[bool, str]:
        """
        Execute a TASK step with output validation.

        :param step: The task step
        :return: Tuple of (success, error_message)
        """
        # First, execute the task
        if not step.role:
            return (False, f"Task step {step.id} has no role assigned")

        role_config = self.config.get_role(step.role)
        if not role_config:
            return (False, f"Role not found: {step.role}")

        # Create context file
        context_path = self.state_manager.create_context_file(
            step,
            role_config.description
        )

        # Get adapter
        try:
            adapter = AdapterFactory.create(role_config.agent)
        except ValueError as e:
            return (False, str(e))

        # Execute
        result = await adapter.execute(
            str(context_path),
            working_dir=str(self.state_manager.outputs_dir)
        )

        if not result.success:
            return (False, f"Agent execution failed: {result.error}")

        # Fallback: materialize agent text output into expected file when file is missing.
        if step.output:
            output_path = self.state_manager.get_output_path(step.output)
            if (not output_path.exists()) and (result.output or "").strip():
                content = result.output
                if "<!-- TASK_COMPLETED -->" not in content:
                    content = content.rstrip() + "\n\n<!-- TASK_COMPLETED -->\n"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(content, encoding="utf-8")
                self.logger.info(f"Materialized agent output to file: {output_path}")

        # Run validators
        validation_errors = []

        # 1. Default output file validation (if output is specified)
        if step.output:
            output_path = self.state_manager.get_output_path(step.output)

            # Check file exists
            if self.config.validators.auto_file_check:
                if not output_path.exists():
                    validation_errors.append(f"Output file not found: {output_path}")

            # Check completion marker
            if self.config.validators.auto_completion_marker:
                if not self.state_manager.check_output_completed(output_path):
                    validation_errors.append(f"Completion marker not found in: {output_path}")

        # 2. Run custom validators defined on the step
        if step.validators:
            context = {
                "working_dir": str(self.team_run_dir / "outputs"),
                "step_id": step.id,
                "step_output": step.output
            }

            all_passed, results = await self.step_validator.validate_step(
                validators=step.validators,
                context=context
            )

            if not all_passed:
                for vr in results:
                    if not vr.success:
                        validation_errors.append(f"[{vr.validator_type.value}] {vr.message}")

        # Check validation results
        if validation_errors:
            error_msg = "Validation failed:\n" + "\n".join(f"  - {e}" for e in validation_errors)
            self.logger.warning(error_msg)
            return (False, error_msg)

        return (True, "")

    def _reset_step_for_retry(self, todo: TodoFile, step_id: str) -> None:
        """
        Reset a step and all steps that depend on it for retry.

        :param todo: TodoFile containing the steps
        :param step_id: Step ID to reset
        """
        step = todo.get_step(step_id)
        if not step:
            self.logger.warning(f"Cannot reset step {step_id}: not found")
            return

        # Reset this step
        self.logger.info(f"Resetting step {step_id} for retry")
        self.state_manager.update_step_status(todo, step_id, StepStatus.PENDING)

        # Find and reset all steps that depend on this step (transitively)
        steps_to_check = [step_id]
        reset_steps = {step_id}

        while steps_to_check:
            current_id = steps_to_check.pop(0)
            for s in todo.steps:
                if current_id in s.depends and s.id not in reset_steps:
                    reset_steps.add(s.id)
                    steps_to_check.append(s.id)
                    if s.status in (StepStatus.DONE, StepStatus.FAILED):
                        self.logger.info(f"Resetting dependent step {s.id}")
                        self.state_manager.update_step_status(todo, s.id, StepStatus.PENDING)

    async def _execute_discussion(self, todo: TodoFile, step: Step) -> bool:
        """
        Execute a DISCUSS step.

        Multi-role discussion with rounds of turn-taking.
        Each participant speaks in turn, can see previous messages.
        Finally extracts a conclusion.
        """
        if not step.participants:
            self.logger.error(f"Discussion step {step.id} has no participants")
            return False

        self.logger.info(
            f"Starting discussion: {step.description} "
            f"with {step.participants}, {step.rounds} round(s)"
        )

        # Create discussion directory
        discussion_dir = self.team_run_dir / "discussions" / step.id
        discussion_dir.mkdir(parents=True, exist_ok=True)

        # Collect input context (from previous steps)
        input_context = ""
        for input_file in step.inputs:
            input_path = self.state_manager.get_output_path(input_file)
            if input_path.exists():
                input_context += f"\n\n## {input_file}\n\n"
                input_context += input_path.read_text(encoding="utf-8")

        # Discussion record
        discussion_record = f"# 讨论记录：{step.description}\n\n"
        discussion_record += f"参与者：{', '.join(step.participants)}\n"
        discussion_record += f"轮次：{step.rounds}\n\n"

        if input_context:
            discussion_record += f"## 讨论背景\n{input_context}\n\n"

        all_messages: list[dict[str, str]] = []

        # Execute rounds
        for round_num in range(1, step.rounds + 1):
            discussion_record += f"## 第 {round_num} 轮\n\n"

            for participant in step.participants:
                role_config = self.config.get_role(participant)
                if not role_config:
                    self.logger.warning(f"Role not found: {participant}, skipping")
                    continue

                # Build context for this participant
                participant_context = self._build_discussion_context(
                    step=step,
                    participant=participant,
                    role_config=role_config,
                    round_num=round_num,
                    total_rounds=step.rounds,
                    input_context=input_context,
                    previous_messages=all_messages
                )

                # Save context file
                context_file = discussion_dir / f"round{round_num}_{participant}_context.md"
                context_file.write_text(participant_context, encoding="utf-8")

                # Execute with agent
                try:
                    adapter = AdapterFactory.create(role_config.agent)
                    result = await adapter.execute(str(context_file))

                    if result.success:
                        message = result.output or "(无回复)"
                    else:
                        message = f"(执行失败: {result.error})"
                        self.logger.warning(f"Participant {participant} failed: {result.error}")

                except Exception as e:
                    message = f"(执行异常: {str(e)})"
                    self.logger.error(f"Participant {participant} exception: {str(e)}")

                # Record message
                all_messages.append({
                    "round": round_num,
                    "participant": participant,
                    "role_name": role_config.name,
                    "message": message
                })

                discussion_record += f"### {role_config.name} ({participant})\n\n"
                discussion_record += f"{message}\n\n"

                # Save individual response
                response_file = discussion_dir / f"round{round_num}_{participant}_response.md"
                response_file.write_text(message, encoding="utf-8")

        # Extract conclusion using Service LLM
        discussion_record += "## 讨论结论\n\n"

        conclusion = await self._extract_discussion_conclusion(step, all_messages)
        discussion_record += conclusion + "\n"

        # Save discussion record
        record_file = discussion_dir / "discussion_record.md"
        record_file.write_text(discussion_record, encoding="utf-8")

        # Save to output if specified
        if step.output:
            output_path = self.state_manager.get_output_path(step.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(discussion_record, encoding="utf-8")

        self.logger.info(f"Discussion {step.id} completed")
        return True

    def _build_discussion_context(
        self,
        step: Step,
        participant: str,
        role_config: Any,
        round_num: int,
        total_rounds: int,
        input_context: str,
        previous_messages: list[dict]
    ) -> str:
        """Build context for a discussion participant."""
        context = f"# 讨论任务\n\n"
        context += f"## 你的角色\n\n{role_config.name}: {role_config.description}\n\n"
        context += f"## 讨论主题\n\n{step.description}\n\n"
        context += f"## 当前轮次\n\n第 {round_num} 轮，共 {total_rounds} 轮\n\n"

        if input_context:
            context += f"## 讨论背景材料\n{input_context}\n\n"

        if previous_messages:
            context += "## 之前的发言\n\n"
            for msg in previous_messages:
                context += f"**{msg['role_name']}** (第{msg['round']}轮):\n"
                context += f"{msg['message']}\n\n"

        context += "## 你的任务\n\n"
        if round_num == 1:
            context += "请根据你的角色和专业知识，对讨论主题发表你的看法和建议。\n"
        else:
            context += "请根据之前的发言，补充你的观点或回应其他参与者的意见。\n"

        if round_num == total_rounds and participant == step.participants[-1]:
            context += "\n作为最后一位发言者，请尝试总结讨论要点。\n"

        context += "\n请直接输出你的发言内容，不要输出其他格式。"

        return context

    async def _extract_discussion_conclusion(
        self,
        step: Step,
        messages: list[dict]
    ) -> str:
        """Extract conclusion from discussion using Service LLM."""
        from ..llm.service_llm import ServiceLLM

        llm = ServiceLLM.from_env()

        # Build summary prompt
        discussion_text = ""
        for msg in messages:
            discussion_text += f"**{msg['role_name']}** (第{msg['round']}轮):\n"
            discussion_text += f"{msg['message']}\n\n"

        prompt = f"""请根据以下讨论记录，提取关键结论和达成的共识。

## 讨论主题
{step.description}

## 讨论记录
{discussion_text}

## 要求
请输出：
1. 达成的共识
2. 存在的分歧（如有）
3. 下一步行动建议

请直接输出结论内容。"""

        try:
            conclusion = await llm.complete(
                prompt=prompt,
                system_prompt="你是一个讨论总结专家，善于提取多人讨论中的关键信息和共识。",
                temperature=0.5
            )
            return conclusion
        except Exception as e:
            self.logger.error(f"Failed to extract conclusion: {str(e)}")
            return "(结论提取失败，请人工总结)"

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
                create_result = self.git.create_branch(
                    branch_name,
                    original_branch,
                    checkout=False
                )
                if not create_result["success"]:
                    self.logger.error(f"Failed to create branch {branch_name}: {create_result['stderr']}")
                    return False
                branches.append((subtask, branch_name))

            # Execute subtasks in isolated branches.
            # NOTE: this is branch-isolated execution, not concurrent worktree execution.
            all_success = True
            for subtask, branch in branches:
                switch_result = self.git.switch_branch(branch)
                if not switch_result["success"]:
                    self.logger.error(f"Failed to switch to branch {branch}: {switch_result['stderr']}")
                    all_success = False
                    continue

                self.state_manager.update_step_status(todo, subtask.id, StepStatus.RUNNING)
                try:
                    success, error = await self._execute_task_with_validation(subtask)
                    result = success
                except Exception as e:
                    self.logger.error(f"Subtask {subtask.id} failed: {str(e)}")
                    result = False

                if result:
                    self.state_manager.update_step_status(todo, subtask.id, StepStatus.DONE)
                else:
                    self.state_manager.update_step_status(todo, subtask.id, StepStatus.FAILED)
                    all_success = False

                if original_branch:
                    self.git.switch_branch(original_branch)

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
        """
        Execute a GATE step.

        Evaluates a condition and returns True (pass) or False (reject).
        The scheduler will handle jumping to pass_step or reject_step.

        Condition format examples:
        - "review.md:passed" - Check if file contains 'passed' indicator
        - "tests:all_pass" - Check if tests pass
        - Custom conditions evaluated by Service LLM
        """
        self.logger.info(f"Gate step {step.id} - evaluating condition: {step.condition}")

        if not step.condition:
            self.logger.warning(f"Gate step {step.id} has no condition, defaulting to pass")
            return True

        condition = step.condition.strip()

        # Handle file-based conditions (format: "filename:check")
        if ":" in condition:
            file_part, check_part = condition.split(":", 1)
            file_path = self.state_manager.get_output_path(file_part.strip())

            if not file_path.exists():
                self.logger.warning(f"Gate condition file not found: {file_path}")
                return False

            file_content = file_path.read_text(encoding="utf-8")

            # Simple keyword checks
            check_part = check_part.strip().lower()
            if check_part in ["passed", "pass", "approved", "ok", "success"]:
                # Check for positive indicators
                positive_keywords = ["通过", "passed", "approved", "✓", "成功", "ok", "lgtm"]
                negative_keywords = ["失败", "failed", "rejected", "✗", "不通过", "error"]

                has_positive = any(kw in file_content.lower() for kw in positive_keywords)
                has_negative = any(kw in file_content.lower() for kw in negative_keywords)

                if has_negative:
                    self.logger.info(f"Gate {step.id}: Found negative indicator, condition failed")
                    return False
                if has_positive:
                    self.logger.info(f"Gate {step.id}: Found positive indicator, condition passed")
                    return True

                # If no clear indicator, use LLM to evaluate
                return await self._evaluate_gate_with_llm(step, file_content)

            elif check_part in ["failed", "fail", "rejected", "error"]:
                # Inverse check
                result = not await self._execute_gate(
                    todo,
                    Step(
                        id=step.id,
                        type=step.type,
                        condition=f"{file_part}:passed"
                    )
                )
                return result

        # For complex conditions, use LLM evaluation
        return await self._evaluate_gate_with_llm(step, None)

    async def _evaluate_gate_with_llm(
        self,
        step: Step,
        context_content: str | None
    ) -> bool:
        """Use Service LLM to evaluate a gate condition."""
        from ..llm.service_llm import ServiceLLM

        llm = ServiceLLM.from_env()

        prompt = f"""请评估以下条件是否满足。

## 条件
{step.condition}

## 步骤描述
{step.description or "无"}

"""
        if context_content:
            prompt += f"""## 相关内容
{context_content[:3000]}  # Limit content length

"""

        prompt += """## 要求
请判断条件是否满足，只回答 "是" 或 "否"。"""

        try:
            response = await llm.complete(
                prompt=prompt,
                system_prompt="你是一个条件评估专家，根据给定的条件和上下文，判断条件是否满足。只回答'是'或'否'。",
                temperature=0.1
            )

            response = response.strip().lower()
            passed = response in ["是", "yes", "true", "通过", "满足", "passed"]

            self.logger.info(f"Gate {step.id} LLM evaluation: {response} -> {'passed' if passed else 'failed'}")
            return passed

        except Exception as e:
            self.logger.error(f"Gate LLM evaluation failed: {str(e)}")
            return False

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
