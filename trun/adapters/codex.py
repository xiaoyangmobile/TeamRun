"""
Codex adapter using codex-local-sdk-python.
"""

import asyncio
from typing import Any

from ..utils.logger import get_logger
from .base import AgentAdapter, AgentResult


class CodexAdapter(AgentAdapter):
    """
    Adapter for Codex using the community codex-local-sdk-python.

    Requires: pip install codex-local-sdk-python
    """

    def __init__(
        self,
        max_retries: int = 3,
        sandbox_mode: str = "full_auto"
    ):
        """
        Initialize Codex adapter.

        :param max_retries: Maximum retry attempts
        :param sandbox_mode: Sandbox mode for execution
        """
        self.max_retries = max_retries
        self.sandbox_mode = sandbox_mode
        self.logger = get_logger()
        self._running = False
        self._client = None

    @property
    def name(self) -> str:
        return "codex"

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_client(self) -> Any:
        """Get or create Codex client."""
        if self._client is None:
            try:
                from codex_local_sdk import CodexLocalClient, RetryPolicy

                retry_policy = RetryPolicy(max_retries=self.max_retries)
                self._client = CodexLocalClient(
                    retry_policy=retry_policy,
                    event_hook=self._on_event
                )
            except ImportError:
                raise ImportError(
                    "codex-local-sdk-python is not installed. "
                    "Install with: pip install codex-local-sdk-python"
                )
        return self._client

    def _on_event(self, event: Any) -> None:
        """Handle Codex events."""
        event_type = getattr(event, "type", "unknown")
        self.logger.debug(f"Codex event: {event_type}")

    async def execute(
        self,
        context_file: str,
        working_dir: str | None = None
    ) -> AgentResult:
        """
        Execute a task using Codex.

        :param context_file: Path to the task context file
        :param working_dir: Working directory for the agent
        :return: AgentResult with execution results
        """
        try:
            from codex_local_sdk import CodexExecRequest, SandboxMode
        except ImportError:
            return AgentResult(
                success=False,
                error="codex-local-sdk-python is not installed. Install with: pip install codex-local-sdk-python"
            )

        self._running = True
        self.logger.info(f"Starting Codex execution with context: {context_file}")

        try:
            # Read context file
            with open(context_file, 'r', encoding='utf-8') as f:
                context = f.read()

            client = self._get_client()

            # Map sandbox mode
            sandbox_mapping = {
                "full_auto": SandboxMode.FULL_AUTO,
                "read_only": SandboxMode.READ_ONLY,
                "none": SandboxMode.NONE,
            }
            sandbox = sandbox_mapping.get(self.sandbox_mode, SandboxMode.FULL_AUTO)

            request = CodexExecRequest(
                prompt=f"请阅读以下任务上下文并执行任务：\n\n{context}",
                sandbox=sandbox,
            )

            result = await client.run_async(request, timeout_seconds=300)

            self._running = False
            self.logger.info(f"Codex execution completed. Session: {result.session_id}")

            return AgentResult(
                success=result.success,
                output=result.final_message or "",
                session_id=result.session_id,
                metadata={"raw_result": result}
            )

        except Exception as e:
            self._running = False
            self.logger.error(f"Codex execution failed: {str(e)}")
            return AgentResult(
                success=False,
                error=str(e)
            )

    async def stop(self) -> None:
        """Stop the current execution."""
        self._running = False
        self.logger.info("Codex execution stop requested")
