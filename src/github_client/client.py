"""GitHub API client implementation."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from github import Github
from github.Issue import Issue as GHIssue
from github.Repository import Repository

logger = logging.getLogger(__name__)


@dataclass
class Issue:
    """Simplified issue representation."""

    number: int
    title: str
    body: str
    state: str
    labels: list[str]
    created_at: datetime
    updated_at: datetime
    comments_count: int
    user: str
    url: str
    raw: Any = None  # Store the original PyGithub Issue object

    @classmethod
    def from_github_issue(cls, issue: GHIssue) -> "Issue":
        """Create Issue from PyGithub Issue object."""
        return cls(
            number=issue.number,
            title=issue.title,
            body=issue.body or "",
            state=issue.state,
            labels=[label.name for label in issue.labels],
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            comments_count=issue.comments,
            user=issue.user.login if issue.user else "unknown",
            url=issue.html_url,
            raw=issue,
        )


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(self, token: str, repo_name: str):
        """
        Initialize GitHub client.

        Args:
            token: GitHub personal access token
            repo_name: Repository in format 'owner/repo'
        """
        self.client = Github(token)
        self.repo_name = repo_name
        self.repo: Repository = self.client.get_repo(repo_name)
        logger.info(f"Initialized GitHub client for repository: {repo_name}")

    def get_issues(
        self,
        state: str = "open",
        since: datetime | None = None,
        labels: list[str] | None = None,
        max_issues: int | None = None,
    ) -> list[Issue]:
        """
        Fetch issues from the repository.

        Args:
            state: Issue state ('open', 'closed', 'all')
            since: Only issues updated after this time
            labels: Filter by labels
            max_issues: Maximum number of issues to return

        Returns:
            List of Issue objects
        """
        logger.info(f"Fetching issues (state={state}, since={since})")

        kwargs: dict[str, Any] = {"state": state}
        if since:
            kwargs["since"] = since
        if labels:
            kwargs["labels"] = labels

        issues = []
        for gh_issue in self.repo.get_issues(**kwargs):
            # Skip pull requests (they appear as issues in GitHub API)
            if gh_issue.pull_request:
                continue

            issues.append(Issue.from_github_issue(gh_issue))

            if max_issues and len(issues) >= max_issues:
                break

        logger.info(f"Fetched {len(issues)} issues")
        return issues

    def get_all_issues_for_knowledge_base(
        self, max_issues: int = 1000
    ) -> list[Issue]:
        """
        Fetch all issues (open and closed) for knowledge base initialization.

        Args:
            max_issues: Maximum number of issues to fetch

        Returns:
            List of all issues
        """
        logger.info(f"Fetching all issues for knowledge base (max: {max_issues})")
        return self.get_issues(state="all", max_issues=max_issues)

    def add_labels(self, issue_number: int, labels: list[str]) -> None:
        """
        Add labels to an issue.

        Args:
            issue_number: Issue number
            labels: List of label names to add
        """
        issue = self.repo.get_issue(issue_number)
        issue.add_to_labels(*labels)
        logger.info(f"Added labels {labels} to issue #{issue_number}")

    def add_comment(self, issue_number: int, comment: str) -> None:
        """
        Add a comment to an issue.

        Args:
            issue_number: Issue number
            comment: Comment text
        """
        issue = self.repo.get_issue(issue_number)
        issue.create_comment(comment)
        logger.info(f"Added comment to issue #{issue_number}")

    def get_issue_comments(self, issue_number: int) -> list[dict[str, Any]]:
        """
        Get all comments for an issue.

        Args:
            issue_number: Issue number

        Returns:
            List of comment dictionaries
        """
        issue = self.repo.get_issue(issue_number)
        comments = []
        for comment in issue.get_comments():
            comments.append(
                {
                    "user": comment.user.login if comment.user else "unknown",
                    "body": comment.body,
                    "created_at": comment.created_at,
                }
            )
        return comments

    def get_repo_info(self) -> dict[str, Any]:
        """Get repository information."""
        return {
            "name": self.repo.name,
            "full_name": self.repo.full_name,
            "description": self.repo.description,
            "open_issues": self.repo.open_issues_count,
            "stars": self.repo.stargazers_count,
            "language": self.repo.language,
        }
