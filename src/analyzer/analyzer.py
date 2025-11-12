"""Issue analyzer using LLM for classification and enrichment."""

import json
import logging
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from ..github_client import Issue
from ..llm import LLMProvider
from ..vector_store import VectorStore
from .prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    CLASSIFICATION_PROMPT_TEMPLATE,
)

if TYPE_CHECKING:
    from ..github_client import GitHubClient

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of issue analysis."""

    issue_number: int

    # Classification
    suggested_labels: list[str]
    label_confidence: float

    # Duplicate detection
    potential_duplicates: list[dict[str, Any]]
    duplicate_confidence: float

    # Information quality
    needs_clarification: bool
    missing_info: list[str]
    clarification_message: str | None

    # Context enrichment
    related_issues: list[int]
    implementation_hints: list[str]

    # Overall confidence
    overall_confidence: float

    # Raw LLM response for debugging
    raw_analysis: dict[str, Any] | None = None


class IssueAnalyzer:
    """Analyzes issues using LLM and vector search."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        vector_store: VectorStore,
        github_client: "GitHubClient",
        bot_username: str,
        confidence_threshold: float = 0.80,
    ):
        """
        Initialize issue analyzer.

        Args:
            llm_provider: LLM provider for analysis
            vector_store: Vector store for semantic search
            github_client: GitHub client for fetching comments
            bot_username: Bot's username for identifying own comments
            confidence_threshold: Minimum confidence for actions
        """
        self.llm = llm_provider
        self.vector_store = vector_store
        self.github = github_client
        self.bot_username = bot_username
        self.confidence_threshold = confidence_threshold
        logger.info(
            f"Initialized IssueAnalyzer with {llm_provider.provider_name} "
            f"and confidence threshold {confidence_threshold}"
        )

    def analyze_issue(self, issue: Issue) -> AnalysisResult:
        """
        Perform comprehensive analysis of an issue.

        Args:
            issue: Issue to analyze

        Returns:
            AnalysisResult with classifications and suggestions
        """
        logger.info(f"Analyzing issue #{issue.number}: {issue.title}")

        # Find similar issues for duplicate detection and context
        similar_issues = self.vector_store.find_similar_issues(
            issue, n_results=5, min_similarity=0.75
        )

        # Build context for LLM
        similar_context = self._format_similar_issues(similar_issues)

        # Get agent's previous comments on this issue
        agent_comments = self._get_agent_comments(issue)

        # Get LLM analysis
        prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
            issue_number=issue.number,
            issue_title=issue.title,
            issue_body=issue.body or "(no description)",
            existing_labels=", ".join(issue.labels) if issue.labels else "none",
            agent_comments=agent_comments,
            similar_issues=similar_context,
        )

        response = self.llm.generate(
            prompt=prompt,
            system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
            temperature=0.3,  # Lower temperature for more consistent analysis
        )

        # Parse LLM response
        analysis = self._parse_llm_response(response.content)

        # Identify high-confidence duplicates
        potential_duplicates = []
        duplicate_confidence = 0.0

        for similar in similar_issues:
            # Exclude the issue itself
            if similar["issue_number"] == issue.number:
                continue

            # High similarity suggests potential duplicate
            if similar["similarity"] > 0.85:
                potential_duplicates.append(
                    {
                        "issue_number": similar["issue_number"],
                        "title": similar["title"],
                        "similarity": similar["similarity"],
                        "state": similar["state"],
                    }
                )
                duplicate_confidence = max(duplicate_confidence, similar["similarity"])

        # Extract related issues (similar but not duplicates)
        related_issues = [
            similar["issue_number"]
            for similar in similar_issues
            if similar["issue_number"] != issue.number
            and 0.70 <= similar["similarity"] < 0.85
        ]

        return AnalysisResult(
            issue_number=issue.number,
            suggested_labels=analysis.get("labels", []),
            label_confidence=analysis.get("label_confidence", 0.0),
            potential_duplicates=potential_duplicates,
            duplicate_confidence=duplicate_confidence,
            needs_clarification=analysis.get("needs_clarification", False),
            missing_info=analysis.get("missing_info", []),
            clarification_message=analysis.get("clarification_message"),
            related_issues=related_issues,
            implementation_hints=analysis.get("implementation_hints", []),
            overall_confidence=analysis.get("overall_confidence", 0.0),
            raw_analysis=analysis,
        )

    def _parse_llm_response(self, response: str) -> dict[str, Any]:
        """
        Parse LLM response into structured analysis.

        Expects JSON response from LLM.
        """
        try:
            # Try to extract JSON from response
            # LLM might wrap it in markdown code blocks
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            analysis = json.loads(response.strip())
            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response was: {response}")

            # Return minimal default structure
            return {
                "labels": [],
                "label_confidence": 0.0,
                "needs_clarification": False,
                "missing_info": [],
                "clarification_message": None,
                "implementation_hints": [],
                "overall_confidence": 0.0,
            }

    def _get_agent_comments(self, issue: Issue) -> str:
        """
        Get agent's previous comments on this issue for LLM context.

        Args:
            issue: Issue to get comments for

        Returns:
            Formatted string of agent's previous comments
        """
        try:
            all_comments = self.github.get_issue_comments(issue.number)

            # Filter to only agent's comments
            agent_comments = [
                c for c in all_comments
                if c["user"] == self.bot_username
            ]

            if not agent_comments:
                return "None - this is your first time analyzing this issue."

            # Format for LLM
            lines = []
            for i, comment in enumerate(agent_comments, 1):
                timestamp = comment["created_at"].strftime("%Y-%m-%d %H:%M")
                # Truncate long comments to save tokens
                body = comment["body"]
                if len(body) > 500:
                    body = body[:500] + "..."
                lines.append(f"{i}. [{timestamp}] {body}")

            return "\n\n".join(lines)

        except Exception as e:
            logger.warning(f"Failed to fetch agent comments for issue #{issue.number}: {e}")
            return "Unable to retrieve previous comments."

    def _format_similar_issues(self, similar_issues: list[dict[str, Any]]) -> str:
        """Format similar issues for LLM context."""
        if not similar_issues:
            return "No similar issues found."

        lines = []
        for issue in similar_issues[:3]:  # Limit to top 3 to save tokens
            lines.append(
                f"- Issue #{issue['issue_number']}: {issue['title']} "
                f"(similarity: {issue['similarity']:.2f}, state: {issue['state']})"
            )

        return "\n".join(lines)

    def should_take_action(self, result: AnalysisResult) -> bool:
        """
        Determine if we should take action based on analysis confidence.

        Args:
            result: Analysis result

        Returns:
            True if confidence exceeds threshold
        """
        return result.overall_confidence >= self.confidence_threshold
