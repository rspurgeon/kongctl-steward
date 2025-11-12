"""Vector store implementation using ChromaDB."""

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from ..github_client import Issue

logger = logging.getLogger(__name__)


class VectorStore:
    """Vector database for storing and searching issue knowledge."""

    def __init__(self, persist_directory: str | Path):
        """
        Initialize vector store.

        Args:
            persist_directory: Directory to persist the database
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB with persistence
        self.client = chromadb.Client(
            Settings(
                persist_directory=str(self.persist_directory),
                anonymized_telemetry=False,
            )
        )

        # Get or create collection for issues
        self.collection = self.client.get_or_create_collection(
            name="issues",
            metadata={"description": "GitHub issues for kongctl-steward"},
        )

        logger.info(
            f"Initialized vector store at {self.persist_directory} "
            f"with {self.collection.count()} existing documents"
        )

    def add_issue(self, issue: Issue) -> None:
        """
        Add an issue to the vector store.

        Args:
            issue: Issue to add
        """
        # Create a rich text representation for embedding
        text = self._issue_to_text(issue)

        # Metadata for filtering and retrieval
        metadata = {
            "issue_number": issue.number,
            "title": issue.title,
            "state": issue.state,
            "labels": ",".join(issue.labels),
            "created_at": issue.created_at.isoformat(),
            "updated_at": issue.updated_at.isoformat(),
            "user": issue.user,
        }

        # Use issue number as ID (convert to string)
        doc_id = f"issue_{issue.number}"

        self.collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata],
        )

        logger.debug(f"Added issue #{issue.number} to vector store")

    def add_issues(self, issues: list[Issue]) -> None:
        """
        Add multiple issues to the vector store in batch.

        Args:
            issues: List of issues to add
        """
        if not issues:
            return

        ids = [f"issue_{issue.number}" for issue in issues]
        documents = [self._issue_to_text(issue) for issue in issues]
        metadatas = [
            {
                "issue_number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "labels": ",".join(issue.labels),
                "created_at": issue.created_at.isoformat(),
                "updated_at": issue.updated_at.isoformat(),
                "user": issue.user,
            }
            for issue in issues
        ]

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(f"Added {len(issues)} issues to vector store")

    def find_similar_issues(
        self,
        issue: Issue,
        n_results: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        Find similar issues using semantic search.

        Args:
            issue: Issue to find similar issues for
            n_results: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of similar issues with metadata and similarity scores
        """
        text = self._issue_to_text(issue)

        results = self.collection.query(
            query_texts=[text],
            n_results=n_results,
            include=["metadatas", "distances"],
        )

        similar_issues = []
        if results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                # Convert distance to similarity (ChromaDB uses cosine distance)
                # Distance of 0 = identical, distance of 2 = opposite
                distance = results["distances"][0][i] if results["distances"] else 2.0
                similarity = 1 - (distance / 2)  # Normalize to 0-1 range

                if similarity >= min_similarity:
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    similar_issues.append(
                        {
                            "issue_number": metadata.get("issue_number"),
                            "title": metadata.get("title"),
                            "state": metadata.get("state"),
                            "labels": metadata.get("labels", "").split(",")
                            if metadata.get("labels")
                            else [],
                            "similarity": similarity,
                            "metadata": metadata,
                        }
                    )

        logger.debug(
            f"Found {len(similar_issues)} similar issues for #{issue.number} "
            f"(min_similarity={min_similarity})"
        )
        return similar_issues

    def search_by_text(
        self,
        query: str,
        n_results: int = 5,
        filter_labels: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search issues by text query.

        Args:
            query: Search query
            n_results: Maximum number of results
            filter_labels: Filter by labels

        Returns:
            List of matching issues with metadata
        """
        where = None
        if filter_labels:
            # Note: This is a simple contains check, may need refinement
            where = {"labels": {"$contains": filter_labels[0]}}

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["metadatas", "distances"],
        )

        issues = []
        if results["ids"]:
            for i in range(len(results["ids"][0])):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 2.0
                similarity = 1 - (distance / 2)

                issues.append(
                    {
                        "issue_number": metadata.get("issue_number"),
                        "title": metadata.get("title"),
                        "state": metadata.get("state"),
                        "labels": metadata.get("labels", "").split(",")
                        if metadata.get("labels")
                        else [],
                        "similarity": similarity,
                        "metadata": metadata,
                    }
                )

        return issues

    def get_count(self) -> int:
        """Get total number of issues in the store."""
        return self.collection.count()

    def clear(self) -> None:
        """Clear all issues from the store (use with caution!)."""
        self.client.delete_collection("issues")
        self.collection = self.client.create_collection(
            name="issues",
            metadata={"description": "GitHub issues for kongctl-steward"},
        )
        logger.warning("Cleared all issues from vector store")

    @staticmethod
    def _issue_to_text(issue: Issue) -> str:
        """
        Convert issue to text representation for embedding.

        Creates a rich representation including title, body, and labels.
        """
        parts = [
            f"Title: {issue.title}",
            f"Labels: {', '.join(issue.labels) if issue.labels else 'none'}",
            f"State: {issue.state}",
            f"Body: {issue.body}",
        ]
        return "\n\n".join(parts)
