"""
Claude Code adapter using Claude Agent SDK.
"""

import asyncio
from typing import Any

from ..utils.logger import get_logger
from .base import AgentAdapter, AgentResult


class ClaudeCodeAdapter(AgentAdapter):
    """
    Adapter for Claude Code using the official Claude Agent SDK.

    Requires: pip install claude-agent-sdk
    """

    def __init__(
        self,
        allowed_tools: list[str] | None = None,
        permission_mode: str = "acceptEdits"
    ):
        """
        Initialize Claude Code adapter.

        :param allowed_tools: List of allowed tools
        :param permission_mode: Permission mode for tool execution
        """
        self.allowed_tools = allowed_tools or [
            "Read", "Write", "Edit", "Bash", "Glob", "Grep"
        ]
        self.permission_mode = permission_mode
        self.logger = get_logger()
        self._running = False
        self._current_session_id: str | None = None

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def is_running(self) -> bool:
        return self._running

    async def execute(
        self,
        context_file: str,
        working_dir: str | None = None
    ) -> AgentResult:
        """
        Execute a task using Claude Code.

        :param context_file: Path to the task context file
        :param working_dir: Working directory for the agent
        :return: AgentResult with execution results
        """
        try:
            from claude_agent_sdk import query, ClaudeAgentOptions
        except ImportError:
            return AgentResult(
                success=False,
                error="claude-agent-sdk is not installed. Install with: pip install claude-agent-sdk"
            )

        self._running = True
        self.logger.info(f"Starting Claude Code execution with context: {context_file}")

        try:
            # Read context file
            with open(context_file, 'r', encoding='utf-8') as f:
                context = f.read()

            result_text = ""
            session_id = None
            output_files: list[str] = []

            # Track file changes via hook
            async def log_file_change(input_data: dict, tool_use_id: str, ctx: Any) -> dict:
                file_path = input_data.get("tool_input", {}).get("file_path")
                if file_path:
                    output_files.append(file_path)
                    self.logger.debug(f"File modified: {file_path}")
                return {}

            options = ClaudeAgentOptions(
                allowed_tools=self.allowed_tools,
                permission_mode=self.permission_mode,
                working_directory=working_dir,
            )

            prompt = f"请阅读以下任务上下文并执行任务：\n\n{context}"

            async for message in query(prompt=prompt, options=options):
                # Capture session ID
                if hasattr(message, "subtype") and message.subtype == "init":
                    session_id = getattr(message, "session_id", None)
                    self._current_session_id = session_id

                # Capture result
                if hasattr(message, "result"):
                    result_text = message.result

                # Log progress
                if hasattr(message, "type"):
                    self.logger.debug(f"Claude Code message: {message.type}")

            self._running = False
            self.logger.info(f"Claude Code execution completed. Session: {session_id}")

            return AgentResult(
                success=True,
                output=result_text,
                session_id=session_id,
                output_files=output_files
            )

        except Exception as e:
            self._running = False
            self.logger.error(f"Claude Code execution failed: {str(e)}")
            return AgentResult(
                success=False,
                error=str(e)
            )

    async def stop(self) -> None:
        """Stop the current execution."""
        self._running = False
        self.logger.info("Claude Code execution stop requested")
        # Note: The actual cancellation would depend on the SDK's capabilities
