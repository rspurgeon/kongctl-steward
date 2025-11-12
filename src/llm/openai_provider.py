"""OpenAI GPT LLM provider implementation."""

import logging

from openai import OpenAI

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider implementation."""

    def __init__(self, api_key: str, model: str = "gpt-4-turbo-preview"):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4-turbo-preview)
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"Initialized OpenAI provider with model: {model}")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> LLMResponse:
        """Generate a response using GPT."""
        try:
            messages = []

            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = response.choices[0].message.content or ""

            usage = {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens
                if response.usage
                else 0,
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
            logger.error(f"OpenAI API error: {e}")
            raise

    def count_tokens(self, text: str) -> int:
        """
        Approximate token count for OpenAI models.

        Uses a simple heuristic: ~4 characters per token.
        For production, consider using tiktoken library.
        """
        return len(text) // 4

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "openai"

    @property
    def model_name(self) -> str:
        """Return model name."""
        return self.model
