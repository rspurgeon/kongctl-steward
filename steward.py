#!/usr/bin/env python
"""kongctl-steward: Main entry point for the GitHub issue management agent."""

import os

# Suppress tokenizers parallelism warning (occurs when using ChromaDB embeddings)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.agent import StewardAgent
from src.config import load_config

console = Console()


def setup_logging(log_level: str, log_file: Path) -> None:
    """Configure logging with rich output and file handler."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(rich_tracebacks=True, console=console),
            logging.FileHandler(log_file),
        ],
    )


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    default=None,
    help="Run in dry-run mode (no actual actions, only logging)",
)
@click.option(
    "--repo",
    default=None,
    help="Override GitHub repository (owner/repo)",
)
@click.option(
    "--max-issues",
    default=None,
    type=int,
    help="Override max issues to process",
)
def main(dry_run: bool | None, repo: str | None, max_issues: int | None) -> None:
    """Run the kongctl-steward GitHub issue management agent."""
    try:
        # Load configuration
        config = load_config()

        # Override with CLI arguments
        if dry_run is not None:
            config.dry_run = dry_run
        if repo is not None:
            config.github_repo = repo
        if max_issues is not None:
            config.max_issues_per_run = max_issues

        # Setup logging
        setup_logging(config.log_level, config.log_file_path)
        logger = logging.getLogger(__name__)

        # Display configuration
        console.print("\n[bold cyan]kongctl-steward Agent[/bold cyan]")
        console.print(f"[dim]Version: 0.1.0[/dim]\n")
        console.print(f"Repository: [bold]{config.github_repo}[/bold]")
        console.print(f"LLM Provider: [bold]{config.llm_provider}[/bold]")
        console.print(
            f"Mode: [bold]{'DRY-RUN' if config.dry_run else 'LIVE'}[/bold]"
        )
        console.print(f"Max Issues: [bold]{config.max_issues_per_run}[/bold]\n")

        if config.dry_run:
            console.print(
                "[yellow]⚠ Running in DRY-RUN mode - no actions will be taken[/yellow]\n"
            )

        logger.info("Starting kongctl-steward agent")
        logger.info(f"Target repository: {config.github_repo}")
        logger.info(f"Dry-run mode: {config.dry_run}")

        # Initialize and run agent
        agent = StewardAgent(config)
        agent.run()

        console.print("\n[green]✓[/green] Agent execution complete\n")

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        logging.exception("Agent execution failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
