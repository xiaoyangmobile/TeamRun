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
    - TRUN_LLM_PROVIDER: LLM provider (openai, anthropic, minimax, etc.)
    - TRUN_LLM_MODEL: Model name (default: gpt-4)
    - OPENAI_API_KEY / ANTHROPIC_API_KEY: API keys
    - ANTHROPIC_BASE_URL / OPENAI_API_BASE: Optional API base URLs

    Supported providers:
    - openai: gpt-4, gpt-4-turbo, gpt-3.5-turbo
    - anthropic: claude-3-opus, claude-3-sonnet, claude-3-haiku, or Minimax models via Anthropic-compatible API
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None
    ):
        """
        Initialize Service LLM.

        All parameters can be overridden by environment variables.

        :param provider: LLM provider (openai, anthropic, etc.)
        :param model: Model name
        :param api_key: API key (uses environment variable if not provided)
        :param api_base: API base URL (uses environment variable if not provided)
        """
        # Environment variables take precedence
        self.provider = os.getenv("TRUN_LLM_PROVIDER", provider or "openai")
        self.model = os.getenv("TRUN_LLM_MODEL", model or "gpt-4")
        self.api_key = api_key
        self.api_base = api_base
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

    def _get_api_base(self) -> str | None:
        """Get API base URL from parameter or environment."""
        if self.api_base:
            return self.api_base

        env_var_mapping = {
            "openai": "OPENAI_API_BASE",
            "anthropic": "ANTHROPIC_BASE_URL",
        }
        env_var = env_var_mapping.get(self.provider)
        if env_var:
            return os.getenv(env_var)
        return None

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
        api_key = self._get_api_key()
        api_base = self._get_api_base()

        self.logger.debug(f"ServiceLLM chat: {len(messages)} messages, provider={self.provider}, model={self.model}, api_base={api_base}")

        try:
            if self.provider == "anthropic":
                content = await self._chat_anthropic(messages, api_key, api_base, temperature, max_tokens)
            else:
                content = await self._chat_litellm(messages, api_key, api_base, temperature, max_tokens)

            if save_history:
                self._history.extend(messages)
                self._history.append({"role": "assistant", "content": content})

            return content

        except Exception as e:
            self.logger.error(f"ServiceLLM chat failed: {str(e)}")
            raise

    async def _chat_anthropic(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        api_base: str | None,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Use Anthropic SDK directly for better base_url support."""
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic is not installed. Install with: pip install anthropic"
            )

        # Create client with optional base_url
        client_kwargs = {"api_key": api_key}
        if api_base:
            client_kwargs["base_url"] = api_base

        client = anthropic.AsyncAnthropic(**client_kwargs)

        # Extract system message if present
        system_content = None
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                chat_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        # Build request kwargs
        request_kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": chat_messages,
        }

        # Only add temperature if it's valid for Minimax (0.0, 1.0]
        # Minimax requires temperature > 0
        if temperature > 0:
            request_kwargs["temperature"] = min(temperature, 1.0)
        else:
            request_kwargs["temperature"] = 1.0

        if system_content:
            request_kwargs["system"] = system_content

        response = await client.messages.create(**request_kwargs)

        # Extract text content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return content

    async def _chat_litellm(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        api_base: str | None,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Use litellm for OpenAI and other providers."""
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "litellm is not installed. Install with: pip install litellm"
            )

        # Map provider to litellm model format
        if self.provider == "openai":
            if api_base:
                model = f"openai/{self.model}"
            else:
                model = self.model
        else:
            model = f"{self.provider}/{self.model}"

        # Build completion kwargs
        completion_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_key": api_key
        }
        if api_base:
            completion_kwargs["api_base"] = api_base

        response = await litellm.acompletion(**completion_kwargs)
        return response.choices[0].message.content

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
