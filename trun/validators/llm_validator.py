"""
LLM-based semantic validator.
"""

from typing import Any

from ..llm.service_llm import ServiceLLM
from ..todo.models import ValidatorType
from .base import ValidationResult, Validator


class LLMValidator(Validator):
    """Validates output using LLM for semantic correctness."""

    VALIDATION_PROMPT = """请验证以下内容是否满足要求。

## 验证要求
{requirement}

## 待验证内容
{content}

## 验证规则
请检查：
1. 内容是否完整回应了要求
2. 是否有明显的错误或遗漏
3. 质量是否达到可接受的标准

## 输出格式
请只回答 "PASS" 或 "FAIL"，然后换行说明原因。

示例：
PASS
内容完整满足要求，逻辑清晰，没有发现错误。

或：
FAIL
内容缺少xxx部分，存在xxx错误。
"""

    def __init__(self, service_llm: ServiceLLM | None = None):
        """
        Initialize LLM validator.

        :param service_llm: ServiceLLM instance (creates from env if not provided)
        """
        self._service_llm = service_llm

    @property
    def service_llm(self) -> ServiceLLM:
        """Get or create ServiceLLM instance."""
        if self._service_llm is None:
            self._service_llm = ServiceLLM.from_env()
        return self._service_llm

    @property
    def validator_type(self) -> ValidatorType:
        return ValidatorType.LLM

    async def validate(
        self,
        target: str,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None
    ) -> ValidationResult:
        """
        Use LLM to validate content semantically.

        :param target: The requirement/criteria to validate against
        :param options: Optional settings:
            - content: Direct content to validate
            - content_file: Path to file containing content to validate
            - max_content_length: Maximum content length (default: 4000)
            - temperature: LLM temperature (default: 0.1)
        :param context: Execution context (may contain working_dir, step info)
        """
        options = options or {}
        context = context or {}

        max_length = options.get("max_content_length", 4000)
        temperature = options.get("temperature", 0.1)

        # Get content to validate
        content = options.get("content")
        if content is None and "content_file" in options:
            from pathlib import Path
            working_dir = Path(context.get("working_dir", "."))
            content_path = working_dir / options["content_file"]

            if not content_path.exists():
                return self._make_result(
                    success=False,
                    message=f"Content file not found: {content_path}",
                    details={"content_file": str(content_path)}
                )

            try:
                content = content_path.read_text(encoding="utf-8")
            except Exception as e:
                return self._make_result(
                    success=False,
                    message=f"Error reading content file: {str(e)}",
                    details={"content_file": str(content_path), "error": str(e)}
                )

        if content is None:
            return self._make_result(
                success=False,
                message="No content provided for LLM validation",
                details={"requirement": target}
            )

        # Truncate content if too long
        if len(content) > max_length:
            content = content[:max_length] + f"\n... (truncated, {len(content) - max_length} chars omitted)"

        # Build prompt
        prompt = self.VALIDATION_PROMPT.format(
            requirement=target,
            content=content
        )

        try:
            response = await self.service_llm.complete(
                prompt=prompt,
                system_prompt="你是一个严格的内容审核专家。请客观评估内容是否满足要求。",
                temperature=temperature,
                max_tokens=500
            )

            # Parse response
            response = response.strip()
            lines = response.split("\n", 1)
            verdict = lines[0].strip().upper()
            reason = lines[1].strip() if len(lines) > 1 else ""

            if verdict == "PASS":
                return self._make_result(
                    success=True,
                    message=f"LLM validation passed: {reason[:100]}",
                    details={
                        "requirement": target,
                        "reason": reason
                    }
                )
            else:
                return self._make_result(
                    success=False,
                    message=f"LLM validation failed: {reason[:100]}",
                    details={
                        "requirement": target,
                        "reason": reason,
                        "full_response": response
                    }
                )

        except Exception as e:
            return self._make_result(
                success=False,
                message=f"LLM validation error: {str(e)}",
                details={"requirement": target, "error": str(e)}
            )
