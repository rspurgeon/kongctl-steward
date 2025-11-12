#!/usr/bin/env python
"""Initialize knowledge base by fetching and indexing all historical issues."""

import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import track

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.github_client import GitHubClient
from src.vector_store import VectorStore

console = Console()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Initialize knowledge base with historical issues."""
    console.print("\n[bold cyan]Knowledge Base Initialization[/bold cyan]\n")

    try:
        # Load configuration
        config = load_config()

        console.print(f"Repository: [bold]{config.github_repo}[/bold]")
        console.print(f"Vector DB: [bold]{config.vector_db_path}[/bold]\n")

        # Initialize GitHub client and vector store
        github = GitHubClient(config.github_token, config.github_repo)
        vector_store = VectorStore(config.vector_db_path)

        # Get repository info
        repo_info = github.get_repo_info()
        console.print(f"Repository: {repo_info['full_name']}")
        console.print(f"Open Issues: {repo_info['open_issues']}")
        console.print(f"Language: {repo_info['language']}\n")

        # Check current knowledge base size
        current_count = vector_store.get_count()
        console.print(f"Current knowledge base: {current_count} issues\n")

        # Fetch all issues
        console.print("[cyan]Fetching all issues (this may take a moment)...[/cyan]")
        all_issues = github.get_all_issues_for_knowledge_base(max_issues=1000)

        console.print(f"[green]✓[/green] Fetched {len(all_issues)} issues\n")

        if not all_issues:
            console.print("[yellow]No issues found to index[/yellow]")
            return

        # Add issues to vector store
        console.print("[cyan]Indexing issues into vector database...[/cyan]")

        for issue in track(all_issues, description="Indexing"):
            vector_store.add_issue(issue)

        # Verify
        final_count = vector_store.get_count()
        console.print(
            f"\n[green]✓[/green] Knowledge base initialized with {final_count} issues"
        )
        console.print(
            f"[dim]Added {final_count - current_count} new issues[/dim]\n"
        )

    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}\n")
        logger.exception("Knowledge base initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
