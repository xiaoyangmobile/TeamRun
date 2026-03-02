"""
Service LLM for system-level tasks.
"""

import os
from typing import Any

from ..utils.logger import get_logger


class ServiceLLM:
    """
    Service LLM for handling system-level tasks.

    Used for:
    - Generating initial TODO files
    - Extracting discussion conclusions
    - Evaluating gate conditions
    - Other system automation tasks

    Configuration is read from environment variables:
    - TRUN_LLM_PROVIDER: LLM provider (default: openai)
    - TRUN_LLM_MODEL: Model name (default: gpt-4)
    - OPENAI_API_KEY / ANTHROPIC_API_KEY: API keys
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None
    ):
        """
        Initialize Service LLM.

        All parameters can be overridden by environment variables.

        :param provider: LLM provider (openai, anthropic, etc.)
        :param model: Model name
        :param api_key: API key (uses environment variable if not provided)
        """
        # Environment variables take precedence
        self.provider = os.getenv("TRUN_LLM_PROVIDER", provider or "openai")
        self.model = os.getenv("TRUN_LLM_MODEL", model or "gpt-4")
        self.api_key = api_key
        self.logger = get_logger()
        self._history: list[dict[str, str]] = []

    @classmethod
    def from_env(cls) -> "ServiceLLM":
        """Create ServiceLLM instance from environment variables."""
        return cls()

    def _get_api_key(self) -> str:
        """Get API key from parameter or environment."""
        if self.api_key:
            return self.api_key

        env_var_mapping = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        env_var = env_var_mapping.get(self.provider, f"{self.provider.upper()}_API_KEY")
        key = os.getenv(env_var)

        if not key:
            raise ValueError(f"API key not found. Set {env_var} environment variable.")

        return key

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        save_history: bool = True
    ) -> str:
        """
        Send a chat completion request.

        :param messages: List of messages with role and content
        :param temperature: Sampling temperature
        :param max_tokens: Maximum tokens in response
        :param save_history: Whether to save to conversation history
        :return: Assistant response content
        """
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "litellm is not installed. Install with: pip install litellm"
            )

        api_key = self._get_api_key()

        # Map provider to litellm model format
        if self.provider == "openai":
            model = self.model
        elif self.provider == "anthropic":
            model = f"anthropic/{self.model}"
        else:
            model = f"{self.provider}/{self.model}"

        self.logger.debug(f"ServiceLLM chat: {len(messages)} messages, model={model}")

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key
            )

            content = response.choices[0].message.content

            if save_history:
                self._history.extend(messages)
                self._history.append({"role": "assistant", "content": content})

            return content

        except Exception as e:
            self.logger.error(f"ServiceLLM chat failed: {str(e)}")
            raise

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str:
        """
        Simple completion with a single prompt.

        :param prompt: User prompt
        :param system_prompt: Optional system prompt
        :param temperature: Sampling temperature
        :param max_tokens: Maximum tokens in response
        :return: Assistant response content
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            save_history=False
        )

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history.clear()

    @property
    def history(self) -> list[dict[str, str]]:
        """Get conversation history."""
        return self._history.copy()
