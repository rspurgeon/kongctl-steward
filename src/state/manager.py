"""State manager for tracking agent runs and processed issues."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ConversationState(BaseModel):
    """State for tracking multi-turn conversations with users."""

    awaiting_response: bool = False
    attempts: int = 0
    last_comment_at: datetime | None = None
    requested_info: list[str] = Field(default_factory=list)


class RunMetrics(BaseModel):
    """Metrics for a single agent run."""

    run_id: str
    timestamp: datetime
    issues_processed: int = 0
    actions_taken: int = 0
    llm_tokens_used: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """Overall agent state."""

    last_run: datetime | None = None
    processed_issues: list[int] = Field(default_factory=list)
    conversation_state: dict[int, ConversationState] = Field(default_factory=dict)
    run_history: list[RunMetrics] = Field(default_factory=list)
    total_actions: int = 0
    version: str = "0.1.0"

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


class StateManager:
    """Manages persistent state across agent runs."""

    def __init__(self, state_file: Path):
        """
        Initialize state manager.

        Args:
            state_file: Path to state JSON file
        """
        self.state_file = state_file
        self.state = self._load_state()
        logger.info(f"Initialized state manager with {len(self.state.processed_issues)} processed issues")

    def _load_state(self) -> AgentState:
        """Load state from file or create new state."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)

                # Convert datetime strings back to datetime objects
                if data.get("last_run"):
                    data["last_run"] = datetime.fromisoformat(data["last_run"])

                # Convert conversation state timestamps
                if data.get("conversation_state"):
                    for issue_id, conv_state in data["conversation_state"].items():
                        if conv_state.get("last_comment_at"):
                            conv_state["last_comment_at"] = datetime.fromisoformat(
                                conv_state["last_comment_at"]
                            )
                        data["conversation_state"][int(issue_id)] = ConversationState(
                            **conv_state
                        )

                # Convert run history timestamps
                if data.get("run_history"):
                    data["run_history"] = [
                        RunMetrics(
                            **{
                                **run,
                                "timestamp": datetime.fromisoformat(run["timestamp"]),
                            }
                        )
                        for run in data["run_history"]
                    ]

                state = AgentState(**data)
                logger.info(f"Loaded state from {self.state_file}")
                return state

            except Exception as e:
                logger.warning(f"Failed to load state from {self.state_file}: {e}")
                logger.info("Creating new state")
                return AgentState()
        else:
            logger.info("No existing state file, creating new state")
            return AgentState()

    def save_state(self) -> None:
        """Save current state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict with proper serialization
            state_dict = self.state.model_dump(mode="json")

            # Manually convert datetimes to ISO format
            if state_dict.get("last_run"):
                state_dict["last_run"] = self.state.last_run.isoformat()

            # Convert conversation state
            if state_dict.get("conversation_state"):
                for issue_id, conv_state in state_dict["conversation_state"].items():
                    if conv_state.get("last_comment_at"):
                        conv_state["last_comment_at"] = self.state.conversation_state[
                            int(issue_id)
                        ].last_comment_at.isoformat()

            # Convert run history
            if state_dict.get("run_history"):
                for i, run in enumerate(state_dict["run_history"]):
                    if run.get("timestamp"):
                        run["timestamp"] = self.state.run_history[i].timestamp.isoformat()

            with open(self.state_file, "w") as f:
                json.dump(state_dict, f, indent=2)

            logger.debug(f"Saved state to {self.state_file}")

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            raise

    def mark_issue_processed(self, issue_number: int) -> None:
        """Mark an issue as processed."""
        if issue_number not in self.state.processed_issues:
            self.state.processed_issues.append(issue_number)

    def is_issue_processed(self, issue_number: int) -> bool:
        """Check if issue has been processed."""
        return issue_number in self.state.processed_issues

    def update_conversation(
        self,
        issue_number: int,
        awaiting_response: bool = False,
        requested_info: list[str] | None = None,
    ) -> None:
        """Update conversation state for an issue."""
        if issue_number not in self.state.conversation_state:
            self.state.conversation_state[issue_number] = ConversationState()

        conv = self.state.conversation_state[issue_number]
        conv.awaiting_response = awaiting_response
        conv.last_comment_at = datetime.now()

        if awaiting_response:
            conv.attempts += 1

        if requested_info:
            conv.requested_info = requested_info

    def get_conversation_state(self, issue_number: int) -> ConversationState | None:
        """Get conversation state for an issue."""
        return self.state.conversation_state.get(issue_number)

    def should_request_info(self, issue_number: int, max_attempts: int = 2) -> bool:
        """Check if we should request more information from user."""
        conv = self.get_conversation_state(issue_number)
        if not conv:
            return True
        return conv.attempts < max_attempts

    def start_run(self, run_id: str) -> RunMetrics:
        """Start a new run and return metrics object."""
        metrics = RunMetrics(
            run_id=run_id,
            timestamp=datetime.now(),
        )
        return metrics

    def finish_run(self, metrics: RunMetrics) -> None:
        """Finish a run and save metrics."""
        self.state.last_run = metrics.timestamp
        self.state.total_actions += metrics.actions_taken

        # Keep only last 100 runs to prevent unbounded growth
        self.state.run_history.append(metrics)
        if len(self.state.run_history) > 100:
            self.state.run_history = self.state.run_history[-100:]

        self.save_state()

    def get_recent_metrics(self, n: int = 10) -> list[RunMetrics]:
        """Get metrics for recent runs."""
        return self.state.run_history[-n:]
