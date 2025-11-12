"""Factory for creating LLM providers."""

import logging

from ..config import Config
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


def create_llm_provider(config: Config) -> LLMProvider:
    """
    Create an LLM provider based on configuration.

    Args:
        config: Application configuration

    Returns:
        Configured LLM provider instance

    Raises:
        ValueError: If provider is invalid or credentials missing
    """
    provider = config.llm_provider.lower()

    if provider == "anthropic":
        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY required for anthropic provider")
        logger.info(f"Creating Anthropic provider with model: {config.anthropic_model}")
        return AnthropicProvider(
            api_key=config.anthropic_api_key,
            model=config.anthropic_model,
        )

    elif provider == "openai":
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY required for openai provider")
        logger.info(f"Creating OpenAI provider with model: {config.openai_model}")
        return OpenAIProvider(
            api_key=config.openai_api_key,
            model=config.openai_model,
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Supported providers: anthropic, openai"
        )
