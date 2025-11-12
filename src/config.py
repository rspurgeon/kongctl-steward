"""Configuration management for kongctl-steward agent."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Agent configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # GitHub Configuration
    github_token: str = Field(..., description="GitHub API token")
    github_repo: str = Field(..., description="Target repository (owner/repo)")
    github_bot_username: str | None = Field(
        default=None, description="Bot username for comment detection (auto-detected if not set)"
    )

    # LLM Provider Configuration
    llm_provider: Literal["anthropic", "openai"] = Field(
        default="anthropic", description="LLM provider to use"
    )

    # Anthropic Configuration
    anthropic_api_key: str | None = Field(
        default=None, description="Anthropic API key"
    )
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022", description="Anthropic model to use"
    )

    # OpenAI Configuration
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(
        default="gpt-4-turbo-preview", description="OpenAI model to use"
    )

    # Agent Configuration
    dry_run: bool = Field(default=True, description="Run in dry-run mode (no actions)")
    confidence_threshold: float = Field(
        default=0.80, description="Minimum confidence for actions"
    )
    max_issues_per_run: int = Field(
        default=20, description="Maximum issues to process per run"
    )
    schedule_hours: int = Field(
        default=4, description="Hours between scheduled runs"
    )
    min_hours_between_actions: float = Field(
        default=1.0, description="Minimum hours between actions on same issue"
    )
    state_cleanup_interval_hours: float = Field(
        default=24.0, description="Hours between closed issue cleanup"
    )

    # Vector Database
    vector_db_path: str = Field(
        default="./chroma_db", description="Path to vector database"
    )

    # State Management
    state_file: str = Field(
        default="./state/agent_state.json", description="Path to state file"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: str = Field(
        default="./logs/steward.log", description="Path to log file"
    )

    def validate_llm_config(self) -> None:
        """Validate that the selected LLM provider has required credentials."""
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY required when using anthropic provider")
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY required when using openai provider")

    @property
    def state_file_path(self) -> Path:
        """Get state file path as Path object."""
        return Path(self.state_file)

    @property
    def vector_db_path_obj(self) -> Path:
        """Get vector DB path as Path object."""
        return Path(self.vector_db_path)

    @property
    def log_file_path(self) -> Path:
        """Get log file path as Path object."""
        return Path(self.log_file)


def load_config() -> Config:
    """Load and validate configuration."""
    config = Config()
    config.validate_llm_config()

    # Ensure directories exist
    config.state_file_path.parent.mkdir(parents=True, exist_ok=True)
    config.log_file_path.parent.mkdir(parents=True, exist_ok=True)
    config.vector_db_path_obj.mkdir(parents=True, exist_ok=True)

    return config
