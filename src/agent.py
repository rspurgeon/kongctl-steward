"""Main agent orchestration logic."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .analyzer import AnalysisResult, IssueAnalyzer
from .config import Config
from .github_client import GitHubClient, Issue
from .llm import create_llm_provider
from .state import StateManager
from .vector_store import VectorStore

logger = logging.getLogger(__name__)
console = Console()


class StewardAgent:
    """Main agent that orchestrates issue processing."""

    def __init__(self, config: Config):
        """
        Initialize the steward agent.

        Args:
            config: Application configuration
        """
        self.config = config

        # Initialize components
        logger.info("Initializing agent components...")

        self.github = GitHubClient(config.github_token, config.github_repo)
        self.vector_store = VectorStore(config.vector_db_path)
        self.llm = create_llm_provider(config)
        self.state = StateManager(config.state_file_path)

        # Detect bot username for comment filtering (needed by analyzer)
        self.bot_username = self._get_bot_username()

        # Initialize analyzer with github client and bot username
        self.analyzer = IssueAnalyzer(
            self.llm,
            self.vector_store,
            self.github,
            self.bot_username,
            config.confidence_threshold,
        )

        logger.info("Agent initialization complete")

    def _get_bot_username(self) -> str:
        """Get bot username for identifying our own comments."""
        if self.config.github_bot_username:
            return self.config.github_bot_username

        # Auto-detect from authenticated user
        try:
            user = self.github.client.get_user()
            username = user.login
            logger.info(f"Auto-detected bot username: {username}")
            return username
        except Exception as e:
            logger.warning(f"Failed to auto-detect bot username: {e}")
            return "steward-bot"  # Fallback

    def run(self) -> None:
        """Execute a single agent run."""
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics = self.state.start_run(run_id)
        start_time = datetime.now()

        try:
            console.print(
                Panel.fit(
                    f"[bold cyan]Agent Run: {run_id}[/bold cyan]",
                    border_style="cyan",
                )
            )

            # Cleanup closed issues if needed
            if self.state.should_cleanup_closed_issues(
                self.config.state_cleanup_interval_hours
            ):
                self._cleanup_closed_issues()

            # Fetch issues to process
            issues = self._fetch_issues_to_process()
            console.print(f"\n[bold]Found {len(issues)} issues to process[/bold]\n")

            if not issues:
                console.print("[yellow]No new issues to process[/yellow]")
                return

            # Process each issue
            for i, issue in enumerate(issues, 1):
                console.print(
                    f"[cyan]Processing {i}/{len(issues)}:[/cyan] "
                    f"Issue #{issue.number} - {issue.title}"
                )

                try:
                    self._process_issue(issue, metrics)
                    metrics.issues_processed += 1

                except Exception as e:
                    logger.exception(f"Error processing issue #{issue.number}")
                    metrics.errors.append(f"Issue #{issue.number}: {str(e)}")
                    console.print(f"[red]✗ Error: {e}[/red]")

                console.print("")  # Blank line between issues

            # Display summary
            self._display_summary(metrics)

        except Exception as e:
            logger.exception("Agent run failed")
            metrics.errors.append(f"Run failed: {str(e)}")
            raise

        finally:
            # Save metrics
            metrics.duration_seconds = (datetime.now() - start_time).total_seconds()
            self.state.finish_run(metrics)

    def _cleanup_closed_issues(self) -> None:
        """Remove closed issues from state."""
        console.print("[dim]Checking for closed issues to clean up...[/dim]")

        # Fetch all currently open issue numbers
        all_open = self.github.get_issues(state="open", max_issues=None)
        open_numbers = {issue.number for issue in all_open}

        # Cleanup state
        removed = self.state.cleanup_closed_issues(open_numbers)
        if removed > 0:
            console.print(f"[dim]Cleaned up {removed} closed issues from state[/dim]\n")

    def _fetch_issues_to_process(self) -> list[Issue]:
        """Fetch issues that need processing."""
        # Fetch recent issues
        since = self.state.state.last_run if self.state.state.last_run else None

        issues = self.github.get_issues(
            state="open",
            since=since,
            max_issues=self.config.max_issues_per_run,
        )

        # Filter issues based on reprocessing logic
        to_process = []
        for issue in issues:
            should_process, reason = self._should_reprocess_issue(issue)
            if should_process:
                logger.info(f"Will process issue #{issue.number}: {reason}")
                to_process.append(issue)
            else:
                logger.debug(f"Skipping issue #{issue.number}: {reason}")

        return to_process

    def _should_reprocess_issue(self, issue: Issue) -> tuple[bool, str]:
        """
        Determine if issue needs reprocessing.

        Returns:
            (should_reprocess, reason)
        """
        issue_state = self.state.get_issue_state(issue.number)

        # First time seeing this issue
        if not issue_state:
            return (True, "first_analysis")

        # Check if we acted too recently (cooldown period)
        if issue_state.our_last_action_at:
            hours_since_action = (
                datetime.now() - issue_state.our_last_action_at
            ).total_seconds() / 3600
            if hours_since_action < self.config.min_hours_between_actions:
                return (
                    False,
                    f"cooldown_active (last action {hours_since_action:.1f}h ago)",
                )

        # Check if issue content changed (user edited title/body)
        current_hash = self._hash_issue_content(issue)
        if current_hash != issue_state.content_hash:
            return (True, "content_changed")

        # Check if issue was updated AFTER our last action
        if issue_state.our_last_action_at:
            if issue.updated_at <= issue_state.our_last_action_at:
                # No changes since we acted
                return (False, "no_changes_since_our_action")

        # Check if there are new comments (potential new information)
        if self._has_new_user_comments(issue, issue_state):
            # User added info after we asked for clarification
            if issue_state.awaiting_user_response:
                return (True, "user_responded_to_clarification")
            # User added unsolicited info (might change analysis)
            return (True, "new_user_comments")

        # Check if comment count changed (simple heuristic)
        if issue.comments_count > issue_state.last_comment_count:
            return (True, "comment_count_increased")

        # Issue updated but not by meaningful user activity
        return (False, "no_meaningful_changes")

    def _hash_issue_content(self, issue: Issue) -> str:
        """
        Hash of issue title and body for change detection.

        Normalizes whitespace to avoid false positives.
        """
        content = f"{issue.title}|{issue.body or ''}"
        # Normalize whitespace
        content = " ".join(content.split())
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _has_new_user_comments(self, issue: Issue, issue_state: Any) -> bool:
        """Check if user (not agent) added comments since our last action."""
        if not issue_state.our_last_action_at:
            return False

        try:
            comments = self.github.get_issue_comments(issue.number)
            for comment in comments:
                # Skip agent's own comments
                if comment["user"] == self.bot_username:
                    continue

                # New user comment since our last action
                if comment["created_at"] > issue_state.our_last_action_at:
                    logger.debug(
                        f"Found new comment from {comment['user']} on issue #{issue.number}"
                    )
                    return True

            return False

        except Exception as e:
            logger.warning(f"Failed to check comments for issue #{issue.number}: {e}")
            return False  # Assume no new comments on error

    def _process_issue(self, issue: Issue, metrics: Any) -> None:
        """Process a single issue."""
        # Add to vector store for future similarity search
        self.vector_store.add_issue(issue)

        # Get or create issue state
        content_hash = self._hash_issue_content(issue)
        issue_state = self.state.get_or_create_issue_state(issue.number, content_hash)

        # Analyze the issue
        analysis = self.analyzer.analyze_issue(issue)

        # Determine actions
        actions = self._determine_actions(issue, analysis, issue_state)

        # Execute or log actions
        if actions:
            self._handle_actions(issue, actions, analysis, metrics)
        else:
            console.print("[dim]No actions needed[/dim]")

        # Update state with current content hash and comment count
        self.state.update_issue_state(
            issue.number,
            content_hash=content_hash,
            comment_count=issue.comments_count,
        )

    def _determine_actions(
        self, issue: Issue, analysis: AnalysisResult, issue_state: Any
    ) -> list[dict[str, Any]]:
        """Determine what actions to take based on analysis."""
        actions = []

        # Only take action if confidence is high enough
        if not self.analyzer.should_take_action(analysis):
            logger.info(
                f"Confidence {analysis.overall_confidence:.2f} below threshold "
                f"{self.config.confidence_threshold}"
            )
            return actions

        # Action: Add labels
        if analysis.suggested_labels and analysis.label_confidence >= 0.80:
            # Filter out labels that:
            # 1. Already exist on the issue
            # 2. We added before and were removed (respect maintainer decisions)
            new_labels = []
            for label in analysis.suggested_labels:
                if label in issue.labels:
                    continue  # Already applied

                # Check if we added this label before and it was removed
                if issue_state and label in issue_state.labels_added:
                    logger.info(
                        f"Skipping label '{label}' on #{issue.number} - "
                        "was previously removed by maintainer"
                    )
                    continue

                new_labels.append(label)

            if new_labels:
                actions.append(
                    {
                        "type": "add_labels",
                        "labels": new_labels,
                        "confidence": analysis.label_confidence,
                    }
                )

        # Action: Comment about duplicates
        if analysis.potential_duplicates and analysis.duplicate_confidence >= 0.85:
            actions.append(
                {
                    "type": "comment_duplicate",
                    "duplicates": analysis.potential_duplicates,
                    "confidence": analysis.duplicate_confidence,
                }
            )
            # Only add duplicate label if not already removed
            if not issue_state or "potential-duplicate" not in issue_state.labels_added:
                actions.append(
                    {
                        "type": "add_labels",
                        "labels": ["potential-duplicate"],
                        "confidence": analysis.duplicate_confidence,
                    }
                )

        # Action: Request clarification
        if analysis.needs_clarification and analysis.clarification_message:
            # Check if we've already asked too many times
            if not issue_state or issue_state.clarification_attempts < 2:
                actions.append(
                    {
                        "type": "request_clarification",
                        "message": analysis.clarification_message,
                        "missing_info": analysis.missing_info,
                    }
                )
                # Only add needs-information label if not already removed
                if (
                    not issue_state
                    or "needs-information" not in issue_state.labels_added
                ):
                    actions.append(
                        {
                            "type": "add_labels",
                            "labels": ["needs-information"],
                            "confidence": 0.95,
                        }
                    )
            else:
                logger.info(
                    f"Skipping clarification for #{issue.number} - "
                    f"already asked {issue_state.clarification_attempts} times"
                )

        # Action: Add context (implementation hints)
        if analysis.implementation_hints:
            actions.append(
                {
                    "type": "add_context",
                    "hints": analysis.implementation_hints,
                    "related_issues": analysis.related_issues,
                }
            )

        return actions

    def _handle_actions(
        self,
        issue: Issue,
        actions: list[dict[str, Any]],
        analysis: AnalysisResult,
        metrics: Any,
    ) -> None:
        """Execute or log actions based on dry-run mode."""
        for action in actions:
            if self.config.dry_run:
                self._log_action(issue, action)
            else:
                self._execute_action(issue, action)

            metrics.actions_taken += 1

    def _log_action(self, issue: Issue, action: dict[str, Any]) -> None:
        """Log an action in dry-run mode."""
        action_type = action["type"]

        if action_type == "add_labels":
            console.print(
                f"  [yellow]DRY-RUN:[/yellow] Would add labels: "
                f"{', '.join(action['labels'])} "
                f"(confidence: {action['confidence']:.2f})"
            )

        elif action_type == "comment_duplicate":
            console.print(f"  [yellow]DRY-RUN:[/yellow] Would comment about duplicates:")
            for dup in action["duplicates"][:2]:  # Show max 2
                console.print(
                    f"    - Issue #{dup['issue_number']}: {dup['title']} "
                    f"(similarity: {dup['similarity']:.2f})"
                )

        elif action_type == "request_clarification":
            console.print(
                f"  [yellow]DRY-RUN:[/yellow] Would request clarification:"
            )
            console.print(f"    Missing: {', '.join(action['missing_info'])}")

        elif action_type == "add_context":
            console.print(
                f"  [yellow]DRY-RUN:[/yellow] Would add implementation context:"
            )
            for hint in action["hints"][:2]:  # Show max 2
                console.print(f"    - {hint}")

    def _execute_action(self, issue: Issue, action: dict[str, Any]) -> None:
        """Execute an action (live mode)."""
        action_type = action["type"]

        try:
            if action_type == "add_labels":
                self.github.add_labels(issue.number, action["labels"])
                console.print(
                    f"  [green]✓[/green] Added labels: {', '.join(action['labels'])}"
                )
                # Update state to track labels we added
                self.state.update_issue_state(
                    issue.number,
                    action_type="add_labels",
                    labels_added=action["labels"],
                )

            elif action_type == "comment_duplicate":
                comment = self._format_duplicate_comment(action["duplicates"])
                self.github.add_comment(issue.number, comment)
                console.print(f"  [green]✓[/green] Added duplicate comment")
                self.state.update_issue_state(
                    issue.number, action_type="comment_duplicate"
                )

            elif action_type == "request_clarification":
                comment = self._format_clarification_comment(
                    action["message"], action["missing_info"]
                )
                self.github.add_comment(issue.number, comment)
                console.print(f"  [green]✓[/green] Requested clarification")
                self.state.update_issue_state(
                    issue.number,
                    action_type="request_clarification",
                    awaiting_response=True,
                    requested_info=action["missing_info"],
                )

            elif action_type == "add_context":
                comment = self._format_context_comment(
                    action["hints"], action.get("related_issues", [])
                )
                self.github.add_comment(issue.number, comment)
                console.print(f"  [green]✓[/green] Added implementation context")
                self.state.update_issue_state(
                    issue.number, action_type="add_context"
                )

        except Exception as e:
            logger.error(f"Failed to execute action {action_type}: {e}")
            console.print(f"  [red]✗ Failed: {e}[/red]")
            raise

    def _format_duplicate_comment(self, duplicates: list[dict[str, Any]]) -> str:
        """Format comment about duplicate issues."""
        lines = [
            "This issue appears to be related to existing issues:",
            "",
        ]

        for dup in duplicates:
            lines.append(f"- #{dup['issue_number']}: {dup['title']} ({dup['state']})")

        lines.extend(
            [
                "",
                "Please check if these issues address your concern. "
                "If this is indeed a duplicate, please reference the related issue. "
                "If there are differences, please clarify what makes this issue unique.",
            ]
        )

        return "\n".join(lines)

    def _format_clarification_comment(
        self, message: str, missing_info: list[str]
    ) -> str:
        """Format comment requesting clarification."""
        return message

    def _format_context_comment(
        self, hints: list[str], related_issues: list[int]
    ) -> str:
        """Format comment with implementation context."""
        lines = ["**Implementation Context:**", ""]

        for hint in hints:
            lines.append(f"- {hint}")

        if related_issues:
            lines.extend(["", "**Related Issues:**"])
            for issue_num in related_issues[:5]:  # Max 5
                lines.append(f"- #{issue_num}")

        return "\n".join(lines)

    def _display_summary(self, metrics: Any) -> None:
        """Display run summary."""
        table = Table(title="Run Summary", show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold")

        table.add_row("Issues Processed", str(metrics.issues_processed))
        table.add_row("Actions Taken", str(metrics.actions_taken))
        table.add_row("Errors", str(len(metrics.errors)))

        console.print("")
        console.print(table)

        if metrics.errors:
            console.print("\n[red]Errors:[/red]")
            for error in metrics.errors:
                console.print(f"  - {error}")
