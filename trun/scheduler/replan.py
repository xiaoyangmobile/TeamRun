"""
Replan engine for dynamic workflow adjustment.

Implements controlled, local, traceable replanning when steps fail.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import ReplanConfig, ReplanPolicy
from ..llm.service_llm import ServiceLLM
from ..todo.models import (
    ReplanRecord,
    Step,
    StepStatus,
    StepType,
    TodoFile,
    ValidatorConfig,
)
from ..utils.logger import get_logger


class ReplanEngine:
    """
    Engine for handling step failures with controlled replanning.

    Design principles:
    1. Local scope - Only replan failed step and its dependents
    2. Traceable - All replans are recorded in history
    3. Limited - Maximum replan attempts per step
    4. Confirmable - Can require human confirmation before replan
    """

    REPLAN_PROMPT = """作为一个工作流规划专家，请为失败的步骤生成替代方案。

## 原始失败步骤
- ID: {step_id}
- 类型: {step_type}
- 描述: {step_description}
- 角色: {step_role}
- 失败原因: {error}

## 之前的执行上下文
已完成的步骤:
{completed_steps}

## 可用角色
{available_roles}

## 要求
1. 分析失败原因
2. 生成1-3个替代步骤来完成原任务
3. 新步骤应该解决导致失败的问题
4. 保持与原工作流的兼容性

## 输出格式
请以 JSON 格式输出新步骤列表：
```json
{{
  "analysis": "失败原因分析",
  "strategy": "修复策略说明",
  "steps": [
    {{
      "id": "step{step_id}.1",
      "type": "task",
      "role": "角色ID",
      "description": "步骤描述",
      "instruction": "详细指令",
      "output": "输出文件名",
      "depends": []
    }}
  ]
}}
```

注意：
- 新步骤ID应该基于原步骤ID（如 step3.1, step3.2）
- 确保依赖关系正确
- 只生成必要的步骤，不要过度设计
"""

    def __init__(
        self,
        config: ReplanConfig,
        service_llm: ServiceLLM | None = None,
        available_roles: dict[str, str] | None = None
    ):
        """
        Initialize replan engine.

        :param config: Replan configuration
        :param service_llm: ServiceLLM instance (creates from env if not provided)
        :param available_roles: Available roles {role_id: description}
        """
        self.config = config
        self._service_llm = service_llm
        self.available_roles = available_roles or {}
        self.logger = get_logger()

    @property
    def service_llm(self) -> ServiceLLM:
        """Get or create ServiceLLM instance."""
        if self._service_llm is None:
            self._service_llm = ServiceLLM.from_env()
        return self._service_llm

    def can_replan(self, step: Step) -> tuple[bool, str]:
        """
        Check if a step can be replanned.

        :param step: The failed step
        :return: Tuple of (can_replan, reason)
        """
        # Check if replan is enabled
        if self.config.policy == ReplanPolicy.DISABLED:
            return False, "Replan is disabled"

        # Check replan count
        if step.replan_count >= self.config.max_attempts:
            return False, f"Max replan attempts ({self.config.max_attempts}) reached"

        # Only TASK and DISCUSS steps can be replanned
        if step.type not in (StepType.TASK, StepType.DISCUSS, StepType.PARALLEL):
            return False, f"Step type {step.type} cannot be replanned"

        return True, "OK"

    async def replan(
        self,
        todo: TodoFile,
        failed_step: Step,
        error: str,
        context: dict[str, Any] | None = None
    ) -> list[Step] | None:
        """
        Generate new steps to replace a failed step.

        :param todo: The TodoFile containing the failed step
        :param failed_step: The step that failed
        :param error: Error message or reason for failure
        :param context: Additional context
        :return: List of new steps, or None if replan failed
        """
        can_replan, reason = self.can_replan(failed_step)
        if not can_replan:
            self.logger.warning(f"Cannot replan step {failed_step.id}: {reason}")
            return None

        self.logger.info(f"Generating replan for step {failed_step.id}: {error}")

        # Build context for LLM
        completed_steps = self._format_completed_steps(todo)
        roles_info = self._format_roles()

        prompt = self.REPLAN_PROMPT.format(
            step_id=failed_step.id,
            step_type=failed_step.type.value,
            step_description=failed_step.description,
            step_role=failed_step.role or "N/A",
            error=error,
            completed_steps=completed_steps,
            available_roles=roles_info
        )

        try:
            response = await self.service_llm.complete(
                prompt=prompt,
                system_prompt="你是一个工作流规划专家，善于分析失败原因并生成替代方案。",
                temperature=0.5
            )

            new_steps = self._parse_replan_response(response, failed_step)

            if new_steps:
                self.logger.info(f"Generated {len(new_steps)} new steps for replan")
                return new_steps
            else:
                self.logger.warning("Failed to parse replan response")
                return None

        except Exception as e:
            self.logger.error(f"Replan generation failed: {str(e)}")
            return None

    def _format_completed_steps(self, todo: TodoFile) -> str:
        """Format completed steps for context."""
        completed = todo.get_completed_steps()
        if not completed:
            return "（无已完成步骤）"

        lines = []
        for step in completed:
            lines.append(f"- {step.id}: {step.description}")
        return "\n".join(lines)

    def _format_roles(self) -> str:
        """Format available roles for prompt."""
        if not self.available_roles:
            return "（未配置角色）"

        lines = []
        for role_id, desc in self.available_roles.items():
            lines.append(f"- {role_id}: {desc}")
        return "\n".join(lines)

    def _parse_replan_response(self, response: str, original_step: Step) -> list[Step] | None:
        """Parse LLM response into Step objects."""
        import json
        import re

        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return None

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return None

        steps_data = data.get("steps", [])
        if not steps_data:
            return None

        new_steps = []
        for i, step_data in enumerate(steps_data):
            # Generate step ID if not provided
            step_id = step_data.get("id", f"{original_step.id}.{i + 1}")

            step = Step(
                id=step_id,
                type=StepType(step_data.get("type", "task")),
                status=StepStatus.PENDING,
                description=step_data.get("description", ""),
                role=step_data.get("role"),
                instruction=step_data.get("instruction"),
                depends=step_data.get("depends", []),
                inputs=step_data.get("inputs", []),
                output=step_data.get("output"),
                # Mark as replanned
                metadata={
                    "replanned_from": original_step.id,
                    "replan_reason": data.get("analysis", "")
                }
            )
            new_steps.append(step)

        return new_steps

    def apply_replan(
        self,
        todo: TodoFile,
        failed_step: Step,
        new_steps: list[Step],
        error: str
    ) -> bool:
        """
        Apply a replan to the TodoFile.

        :param todo: TodoFile to modify
        :param failed_step: The original failed step
        :param new_steps: New steps to insert
        :param error: Original error message
        :return: True if successful
        """
        # Increment replan count on the original step concept
        # (the new steps will carry this in metadata)
        for new_step in new_steps:
            new_step.replan_count = failed_step.replan_count + 1

        # Use TodoFile's replace method
        success = todo.replace_steps_from(
            failed_step_id=failed_step.id,
            new_steps=new_steps,
            reason=error
        )

        if success:
            self.logger.info(
                f"Applied replan: replaced {failed_step.id} with "
                f"{[s.id for s in new_steps]}"
            )

        return success

    async def handle_failure(
        self,
        todo: TodoFile,
        failed_step: Step,
        error: str,
        confirm_callback: Any | None = None
    ) -> tuple[bool, list[Step] | None]:
        """
        Handle a step failure with potential replan.

        :param todo: TodoFile containing the failed step
        :param failed_step: The step that failed
        :param error: Error message
        :param confirm_callback: Optional async callback for confirmation
        :return: Tuple of (should_continue, new_steps)
        """
        can_replan, reason = self.can_replan(failed_step)
        if not can_replan:
            self.logger.info(f"Cannot replan: {reason}")
            return False, None

        # Check if confirmation is needed
        if self.config.policy == ReplanPolicy.CONFIRM:
            if confirm_callback:
                confirmed = await confirm_callback(failed_step, error)
                if not confirmed:
                    self.logger.info("Replan rejected by user")
                    return False, None
            else:
                # No callback provided, default to not replanning
                self.logger.warning("Replan requires confirmation but no callback provided")
                return False, None

        # Generate new steps
        new_steps = await self.replan(todo, failed_step, error)

        if new_steps:
            # Apply the replan
            success = self.apply_replan(todo, failed_step, new_steps, error)
            return success, new_steps
        else:
            return False, None
