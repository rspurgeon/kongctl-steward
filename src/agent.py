"""Main agent orchestration logic."""

import logging
from datetime import datetime
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
        self.analyzer = IssueAnalyzer(
            self.llm, self.vector_store, config.confidence_threshold
        )
        self.state = StateManager(config.state_file_path)

        logger.info("Agent initialization complete")

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

    def _fetch_issues_to_process(self) -> list[Issue]:
        """Fetch issues that need processing."""
        # Fetch recent issues
        since = self.state.state.last_run if self.state.state.last_run else None

        issues = self.github.get_issues(
            state="open",
            since=since,
            max_issues=self.config.max_issues_per_run,
        )

        # Filter out already processed issues (unless they were updated)
        unprocessed = []
        for issue in issues:
            if not self.state.is_issue_processed(issue.number):
                unprocessed.append(issue)
            elif since and issue.updated_at > since:
                # Re-process if updated since last run
                logger.info(f"Re-processing updated issue #{issue.number}")
                unprocessed.append(issue)

        return unprocessed

    def _process_issue(self, issue: Issue, metrics: Any) -> None:
        """Process a single issue."""
        # Add to vector store for future similarity search
        self.vector_store.add_issue(issue)

        # Analyze the issue
        analysis = self.analyzer.analyze_issue(issue)

        # Track LLM token usage
        # Note: Would need to track this from analyzer in production
        # metrics.llm_tokens_used += tokens

        # Determine actions
        actions = self._determine_actions(issue, analysis)

        # Execute or log actions
        if actions:
            self._handle_actions(issue, actions, analysis, metrics)
        else:
            console.print("[dim]No actions needed[/dim]")

        # Mark as processed
        self.state.mark_issue_processed(issue.number)

    def _determine_actions(
        self, issue: Issue, analysis: AnalysisResult
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
            # Filter out labels that already exist
            new_labels = [
                label for label in analysis.suggested_labels if label not in issue.labels
            ]
            if new_labels:
                actions.append(
                    {
                        "type": "add_labels",
                        "labels": new_labels,
                        "confidence": analysis.label_confidence,
                    }
                )

        # Action: Comment about duplicates
        if (
            analysis.potential_duplicates
            and analysis.duplicate_confidence >= 0.85
        ):
            actions.append(
                {
                    "type": "comment_duplicate",
                    "duplicates": analysis.potential_duplicates,
                    "confidence": analysis.duplicate_confidence,
                }
            )
            actions.append(
                {
                    "type": "add_labels",
                    "labels": ["potential-duplicate"],
                    "confidence": analysis.duplicate_confidence,
                }
            )

        # Action: Request clarification
        if (
            analysis.needs_clarification
            and analysis.clarification_message
            and self.state.should_request_info(issue.number)
        ):
            actions.append(
                {
                    "type": "request_clarification",
                    "message": analysis.clarification_message,
                    "missing_info": analysis.missing_info,
                }
            )
            actions.append(
                {
                    "type": "add_labels",
                    "labels": ["needs-information"],
                    "confidence": 0.95,
                }
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
            action_type = action["type"]

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
            console.print(
                f"  [yellow]DRY-RUN:[/yellow] Would comment about duplicates:"
            )
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

            elif action_type == "comment_duplicate":
                comment = self._format_duplicate_comment(action["duplicates"])
                self.github.add_comment(issue.number, comment)
                console.print(f"  [green]✓[/green] Added duplicate comment")

            elif action_type == "request_clarification":
                comment = self._format_clarification_comment(
                    action["message"], action["missing_info"]
                )
                self.github.add_comment(issue.number, comment)
                self.state.update_conversation(
                    issue.number,
                    awaiting_response=True,
                    requested_info=action["missing_info"],
                )
                console.print(f"  [green]✓[/green] Requested clarification")

            elif action_type == "add_context":
                comment = self._format_context_comment(
                    action["hints"], action.get("related_issues", [])
                )
                self.github.add_comment(issue.number, comment)
                console.print(f"  [green]✓[/green] Added implementation context")

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
            lines.append(
                f"- #{dup['issue_number']}: {dup['title']} ({dup['state']})"
            )

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
