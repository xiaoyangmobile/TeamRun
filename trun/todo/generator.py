"""
TODO file generator using Service LLM.
"""

from datetime import datetime
from typing import Any

from ..config import RoleConfig, TeamConfig
from ..llm.service_llm import ServiceLLM
from ..utils.logger import get_logger
from .models import Step, StepStatus, StepType, TodoFile, TodoMeta
from .parser import TodoWriter


class TodoGenerator:
    """
    Generator for TODO files using Service LLM.

    Analyzes user tasks and role configurations to generate
    structured TODO workflows.
    """

    SYSTEM_PROMPT = """你是一个项目工作流规划专家。你的任务是根据用户的任务描述和可用的角色配置，生成一个结构化的工作流程。

## 可用的步骤类型

1. @task(role) - 由指定角色执行的任务
2. @discuss(role1, role2, ...) - 多个角色之间的讨论
3. @parallel - 并行执行的子任务
4. @gate(condition) - 条件判断，决定流程走向
5. @human - 需要人工审核/确认的节点
6. @goto(step_id) - 跳转到指定步骤

## 输出格式

请以 JSON 格式输出工作流程，包含以下结构：

```json
{
  "title": "任务标题",
  "steps": [
    {
      "id": "step1",
      "type": "task",
      "role": "角色ID",
      "description": "步骤描述",
      "instruction": "详细的任务指令",
      "output": "输出文件名",
      "depends": []
    },
    {
      "id": "step2",
      "type": "human",
      "description": "审核xxx",
      "depends": ["step1"],
      "pass_step": "step3",
      "reject_step": "step1"
    },
    {
      "id": "step3",
      "type": "discuss",
      "participants": ["role1", "role2"],
      "rounds": 2,
      "description": "讨论xxx",
      "output": "discussion.md",
      "depends": ["step2"]
    },
    {
      "id": "step4",
      "type": "parallel",
      "description": "并行开发",
      "depends": ["step3"],
      "subtasks": [
        {
          "id": "step4.1",
          "type": "task",
          "role": "role1",
          "description": "子任务1"
        },
        {
          "id": "step4.2",
          "type": "task",
          "role": "role2",
          "description": "子任务2"
        }
      ]
    },
    {
      "id": "step5",
      "type": "gate",
      "condition": "review.md:passed",
      "depends": ["step4"],
      "pass_step": "step6",
      "reject_step": "step4"
    }
  ]
}
```

## 注意事项

1. 确保步骤之间的依赖关系正确
2. 为每个任务提供清晰的指令
3. 合理安排人工审核节点
4. 使用并行执行提高效率
5. 只使用提供的角色配置中的角色
"""

    def __init__(self, config: TeamConfig, service_llm: ServiceLLM | None = None):
        """
        Initialize TODO generator.

        :param config: Team configuration
        :param service_llm: Service LLM instance (creates one from env if not provided)
        """
        self.config = config
        # Use ServiceLLM.from_env() to read config from environment variables
        self.service_llm = service_llm or ServiceLLM.from_env()
        self.logger = get_logger()

    def _format_roles_info(self) -> str:
        """Format roles configuration for the prompt."""
        lines = ["## 可用角色\n"]
        for role_id, role in self.config.roles.items():
            lines.append(f"- **{role_id}** ({role.name}): {role.description}")
        return "\n".join(lines)

    async def generate(
        self,
        task_description: str,
        output_path: str | None = None
    ) -> TodoFile:
        """
        Generate a TODO file from task description.

        :param task_description: User's task description
        :param output_path: Optional path to save the TODO file
        :return: Generated TodoFile
        """
        self.logger.info(f"Generating TODO for task: {task_description[:50]}...")

        roles_info = self._format_roles_info()

        prompt = f"""请为以下任务生成工作流程：

## 任务描述
{task_description}

{roles_info}

请生成完整的工作流程 JSON。"""

        try:
            response = await self.service_llm.complete(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.7
            )

            # Parse JSON response
            todo_file = self._parse_response(response, task_description)

            # Save if path provided
            if output_path:
                writer = TodoWriter()
                writer.write_file(todo_file, output_path)
                self.logger.info(f"TODO file saved to: {output_path}")

            return todo_file

        except Exception as e:
            self.logger.error(f"Failed to generate TODO: {str(e)}")
            raise

    def _parse_response(self, response: str, task_description: str) -> TodoFile:
        """
        Parse LLM response into TodoFile.

        :param response: LLM response string
        :param task_description: Original task description
        :return: Parsed TodoFile
        """
        import json
        import re

        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            raise ValueError("No JSON found in response")

        data = json.loads(json_match.group())

        # Create TodoFile
        title = data.get("title", task_description[:50])
        steps = []

        for step_data in data.get("steps", []):
            step = self._parse_step(step_data)
            steps.append(step)

        return TodoFile(
            file_path="",
            meta=TodoMeta(
                title=title,
                created_at=datetime.now(),
                status=StepStatus.PENDING
            ),
            steps=steps
        )

    def _parse_step(self, data: dict[str, Any]) -> Step:
        """Parse step data into Step object."""
        step_type = StepType(data.get("type", "task"))

        step = Step(
            id=data.get("id", ""),
            type=step_type,
            status=StepStatus.PENDING,
            description=data.get("description", ""),
            role=data.get("role"),
            instruction=data.get("instruction"),
            participants=data.get("participants", []),
            rounds=data.get("rounds", 1),
            condition=data.get("condition"),
            pass_step=data.get("pass_step"),
            reject_step=data.get("reject_step"),
            target_step=data.get("target_step"),
            depends=data.get("depends", []),
            inputs=data.get("inputs", []),
            output=data.get("output"),
        )

        # Parse subtasks for parallel
        if step_type == StepType.PARALLEL and "subtasks" in data:
            step.subtasks = [
                self._parse_step(sub) for sub in data["subtasks"]
            ]

        return step
