"""Configuration management for kongctl-steward agent."""

import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Agent configuration loaded from environment variables."""

    class Config:
        """Pydantic v1 config."""
        case_sensitive = False
        extra = "ignore"

    # GitHub Configuration
    github_token: str = Field(..., description="GitHub API token")
    github_repo: str = Field(..., description="Target repository (owner/repo)")
    github_bot_username: Optional[str] = Field(
        default=None, description="Bot username for comment detection (auto-detected if not set)"
    )

    # LLM Provider Configuration
    llm_provider: Literal["anthropic", "openai"] = Field(
        default="anthropic", description="LLM provider to use"
    )

    # Anthropic Configuration
    anthropic_api_key: Optional[str] = Field(
        default=None, description="Anthropic API key"
    )
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022", description="Anthropic model to use"
    )

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
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
    # Load environment variables from .env file
    load_dotenv()

    # Create config from environment variables
    config = Config(
        github_token=os.getenv("GITHUB_TOKEN", ""),
        github_repo=os.getenv("GITHUB_REPO", ""),
        github_bot_username=os.getenv("GITHUB_BOT_USERNAME"),
        llm_provider=os.getenv("LLM_PROVIDER", "anthropic"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"),
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.80")),
        max_issues_per_run=int(os.getenv("MAX_ISSUES_PER_RUN", "20")),
        schedule_hours=int(os.getenv("SCHEDULE_HOURS", "4")),
        min_hours_between_actions=float(os.getenv("MIN_HOURS_BETWEEN_ACTIONS", "1.0")),
        state_cleanup_interval_hours=float(os.getenv("STATE_CLEANUP_INTERVAL_HOURS", "24.0")),
        vector_db_path=os.getenv("VECTOR_DB_PATH", "./chroma_db"),
        state_file=os.getenv("STATE_FILE", "./state/agent_state.json"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("LOG_FILE", "./logs/steward.log"),
    )

    config.validate_llm_config()

    # Ensure directories exist
    config.state_file_path.parent.mkdir(parents=True, exist_ok=True)
    config.log_file_path.parent.mkdir(parents=True, exist_ok=True)
    config.vector_db_path_obj.mkdir(parents=True, exist_ok=True)

    return config
