"""Anthropic Claude LLM provider implementation."""

import logging
from typing import Any

from anthropic import Anthropic

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider implementation."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key
            model: Model to use (default: claude-3-5-sonnet-20241022)
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model
        logger.info(f"Initialized Anthropic provider with model: {model}")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> LLMResponse:
        """Generate a response using Claude."""
        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            # Extract text content from response
            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

            logger.debug(
                f"Generated response: {len(content)} chars, "
                f"tokens: {usage['input_tokens']} in / {usage['output_tokens']} out"
            )

            return LLMResponse(
                content=content,
                model=self.model,
                usage=usage,
                raw_response=response,
            )

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    def count_tokens(self, text: str) -> int:
        """
        Approximate token count for Anthropic models.

        Uses a simple heuristic: ~4 characters per token.
        For production, consider using the tokenizer library.
        """
        return len(text) // 4

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "anthropic"

    @property
    def model_name(self) -> str:
        """Return model name."""
        return self.model
