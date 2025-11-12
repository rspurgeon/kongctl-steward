"""State manager for tracking agent runs and processed issues."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IssueProcessingState(BaseModel):
    """State for tracking processing of a single issue."""

    issue_number: int

    # Content tracking for change detection
    content_hash: str
    last_analyzed_at: datetime

    # Action tracking
    our_last_action: str | None = None  # Type of last action taken
    our_last_action_at: datetime | None = None
    labels_added: list[str] = Field(default_factory=list)  # Labels we added
    last_comment_count: int = 0  # Comment count when we last processed

    # Conversation tracking
    awaiting_user_response: bool = False
    clarification_attempts: int = 0
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
    last_cleanup: datetime | None = None  # Last time we cleaned up closed issues
    issue_states: dict[int, IssueProcessingState] = Field(default_factory=dict)
    run_history: list[RunMetrics] = Field(default_factory=list)
    total_actions: int = 0
    version: str = "0.2.0"  # Bumped for new state format

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
        logger.info(
            f"Initialized state manager with {len(self.state.issue_states)} tracked issues"
        )

    def _load_state(self) -> AgentState:
        """Load state from file or create new state."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)

                # Convert datetime strings back to datetime objects
                if data.get("last_run"):
                    data["last_run"] = datetime.fromisoformat(data["last_run"])

                if data.get("last_cleanup"):
                    data["last_cleanup"] = datetime.fromisoformat(data["last_cleanup"])

                # Convert issue states
                if data.get("issue_states"):
                    issue_states = {}
                    for issue_id, state_data in data["issue_states"].items():
                        # Convert datetime fields
                        if state_data.get("last_analyzed_at"):
                            state_data["last_analyzed_at"] = datetime.fromisoformat(
                                state_data["last_analyzed_at"]
                            )
                        if state_data.get("our_last_action_at"):
                            state_data["our_last_action_at"] = datetime.fromisoformat(
                                state_data["our_last_action_at"]
                            )
                        issue_states[int(issue_id)] = IssueProcessingState(**state_data)
                    data["issue_states"] = issue_states

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

            # Convert to dict with proper serialization (pydantic v1 uses dict())
            state_dict = self.state.dict()

            # Manually convert datetimes to ISO format
            if state_dict.get("last_run"):
                state_dict["last_run"] = self.state.last_run.isoformat()

            if state_dict.get("last_cleanup"):
                state_dict["last_cleanup"] = self.state.last_cleanup.isoformat()

            # Convert issue states
            if state_dict.get("issue_states"):
                for issue_id, issue_state in state_dict["issue_states"].items():
                    original = self.state.issue_states[int(issue_id)]
                    if issue_state.get("last_analyzed_at"):
                        issue_state["last_analyzed_at"] = (
                            original.last_analyzed_at.isoformat()
                        )
                    if issue_state.get("our_last_action_at") and original.our_last_action_at:
                        issue_state["our_last_action_at"] = (
                            original.our_last_action_at.isoformat()
                        )

            # Convert run history
            if state_dict.get("run_history"):
                for i, run in enumerate(state_dict["run_history"]):
                    if run.get("timestamp"):
                        run["timestamp"] = self.state.run_history[
                            i
                        ].timestamp.isoformat()

            with open(self.state_file, "w") as f:
                json.dump(state_dict, f, indent=2)

            logger.debug(f"Saved state to {self.state_file}")

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            raise

    def get_issue_state(self, issue_number: int) -> IssueProcessingState | None:
        """Get processing state for an issue."""
        return self.state.issue_states.get(issue_number)

    def get_or_create_issue_state(
        self, issue_number: int, content_hash: str
    ) -> IssueProcessingState:
        """Get or create processing state for an issue."""
        if issue_number not in self.state.issue_states:
            self.state.issue_states[issue_number] = IssueProcessingState(
                issue_number=issue_number,
                content_hash=content_hash,
                last_analyzed_at=datetime.now(),
            )
        return self.state.issue_states[issue_number]

    def update_issue_state(
        self,
        issue_number: int,
        content_hash: str | None = None,
        action_type: str | None = None,
        labels_added: list[str] | None = None,
        comment_count: int | None = None,
        awaiting_response: bool | None = None,
        requested_info: list[str] | None = None,
    ) -> None:
        """Update issue processing state."""
        state = self.state.issue_states.get(issue_number)
        if not state:
            logger.warning(f"Attempted to update non-existent state for issue #{issue_number}")
            return

        if content_hash:
            state.content_hash = content_hash

        if action_type:
            state.our_last_action = action_type
            state.our_last_action_at = datetime.now()

        if labels_added:
            state.labels_added.extend(labels_added)
            state.labels_added = list(set(state.labels_added))  # Deduplicate

        if comment_count is not None:
            state.last_comment_count = comment_count

        if awaiting_response is not None:
            state.awaiting_user_response = awaiting_response
            if awaiting_response:
                state.clarification_attempts += 1

        if requested_info:
            state.requested_info = requested_info

        state.last_analyzed_at = datetime.now()

    def should_cleanup_closed_issues(
        self, cleanup_interval_hours: float
    ) -> bool:
        """Check if we should run cleanup of closed issues."""
        if not self.state.last_cleanup:
            return True

        hours_since = (
            datetime.now() - self.state.last_cleanup
        ).total_seconds() / 3600
        return hours_since >= cleanup_interval_hours

    def cleanup_closed_issues(self, open_issue_numbers: set[int]) -> int:
        """
        Remove closed issues from state.

        Args:
            open_issue_numbers: Set of currently open issue numbers

        Returns:
            Number of closed issues removed
        """
        original_count = len(self.state.issue_states)

        # Keep only issues that are still open
        self.state.issue_states = {
            issue_id: state
            for issue_id, state in self.state.issue_states.items()
            if issue_id in open_issue_numbers
        }

        removed = original_count - len(self.state.issue_states)
        self.state.last_cleanup = datetime.now()

        if removed > 0:
            logger.info(f"Cleaned up {removed} closed issues from state")

        return removed

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
