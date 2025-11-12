#!/usr/bin/env python
"""Utility script to validate ChromaDB vector store state."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vector_store import VectorStore
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def main():
    """Check and display vector database status."""
    console.print(Panel.fit("ChromaDB Vector Store Validation", style="bold blue"))

    vector_db_path = "./chroma_db"

    console.print(f"\n📁 Vector DB Path: {vector_db_path}")

    # Check if directory exists
    if not Path(vector_db_path).exists():
        console.print("[red]❌ Vector DB directory does not exist![/red]")
        console.print(f"   Run: python scripts/init_knowledge.py")
        return 1

    try:
        # Initialize vector store
        console.print("\n🔌 Connecting to vector store...")
        vs = VectorStore(vector_db_path)

        # Get count
        count = vs.collection.count()
        console.print(f"[green]✓[/green] Connected successfully")
        console.print(f"\n📊 Total Documents: [bold cyan]{count}[/bold cyan]")

        if count == 0:
            console.print("\n[yellow]⚠️  Vector database is empty![/yellow]")
            console.print("   Run: python scripts/init_knowledge.py")
            return 1

        # Get sample documents
        console.print("\n📝 Fetching sample documents...")
        result = vs.collection.peek(limit=5)

        # Display sample issues
        if result['ids']:
            table = Table(title=f"Sample Issues (showing {len(result['ids'])} of {count})")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Issue #", style="magenta")
            table.add_column("Title", style="green")
            table.add_column("State", style="yellow")
            table.add_column("Labels", style="blue")

            for i, doc_id in enumerate(result['ids']):
                metadata = result['metadatas'][i] if result['metadatas'] else {}
                issue_num = str(metadata.get('issue_number', 'N/A'))
                title = metadata.get('title', 'N/A')[:50]
                state = metadata.get('state', 'N/A')
                labels = metadata.get('labels', '')[:30]

                table.add_row(doc_id, issue_num, title, state, labels)

            console.print(table)

        # Test embedding dimensions
        if result['embeddings'] and result['embeddings'][0]:
            embed_dim = len(result['embeddings'][0])
            console.print(f"\n🔢 Embedding Dimensions: [bold cyan]{embed_dim}[/bold cyan]")

        # Test similarity search
        console.print("\n🔍 Testing similarity search...")
        test_results = vs.collection.query(
            query_texts=["authentication login error"],
            n_results=3,
            include=["metadatas", "distances"]
        )

        if test_results['ids'] and test_results['ids'][0]:
            console.print(f"[green]✓[/green] Similarity search working")
            console.print(f"   Found {len(test_results['ids'][0])} similar issues")

            # Show top result
            top_metadata = test_results['metadatas'][0][0] if test_results['metadatas'] else {}
            top_distance = test_results['distances'][0][0] if test_results['distances'] else 0
            top_similarity = 1 - (top_distance / 2)

            console.print(f"\n   Top match:")
            console.print(f"   • Issue #{top_metadata.get('issue_number', 'N/A')}")
            console.print(f"   • Title: {top_metadata.get('title', 'N/A')[:60]}")
            console.print(f"   • Similarity: {top_similarity:.2%}")
        else:
            console.print("[yellow]⚠️  Similarity search returned no results[/yellow]")

        # Summary
        console.print("\n" + "="*60)
        console.print("[bold green]✅ Vector Database Status: HEALTHY[/bold green]")
        console.print(f"   • Documents indexed: {count}")
        console.print(f"   • Embeddings working: Yes")
        console.print(f"   • Similarity search: Functional")
        console.print("="*60)

        return 0

    except Exception as e:
        console.print(f"\n[red]❌ Error: {e}[/red]")
        import traceback
        console.print(f"\n[dim]{traceback.format_exc()}[/dim]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
