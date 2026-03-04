#!/usr/bin/env python3
"""
Graphiti Knowledge Graph Cleanup Tool (SPEC-038 REQ-015)

Delete entities from Neo4j knowledge graph by document ID or全部.

Prerequisites:
- Must run inside txtai-mcp Docker container (required dependencies)
- Neo4j must be running and accessible

Usage:
    # Dry-run (default - shows what would be deleted)
    docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID>

    # Actually delete (requires --confirm)
    docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --document-id <UUID> --confirm

    # Delete all entities (requires --confirm)
    docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --all --confirm

    # List all documents with entities
    docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py --list

Environment Variables:
    NEO4J_URI: Neo4j connection URI (default: bolt://neo4j:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password (required)
"""

import argparse
import os
import sys
from typing import List, Tuple

from neo4j import GraphDatabase


def check_docker_environment():
    """REQ-013: Verify script runs inside Docker container."""
    if not os.path.exists('/.dockerenv'):
        print("ERROR: This script must run inside txtai-mcp Docker container")
        print("")
        print("Usage:")
        print("  docker exec txtai-mcp uv run python /app/scripts/graphiti-cleanup.py [options]")
        print("")
        print("Do NOT run this script directly on the host machine.")
        sys.exit(1)


def validate_environment() -> Tuple[str, str, str]:
    """
    Validate required environment variables.

    Returns:
        Tuple of (neo4j_uri, neo4j_user, neo4j_password)
    """
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://neo4j:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD')

    if not neo4j_password:
        print("ERROR: NEO4J_PASSWORD environment variable is required")
        print("")
        print("Action required:")
        print("  1. Add NEO4J_PASSWORD to .env file")
        print("  2. Restart containers: docker compose restart txtai-mcp")
        sys.exit(1)

    return neo4j_uri, neo4j_user, neo4j_password


def list_documents_with_entities(driver) -> List[Tuple[str, int]]:
    """
    List all document IDs with entity counts.

    Args:
        driver: Neo4j driver instance

    Returns:
        List of (document_id, entity_count) tuples, sorted by count descending
    """
    with driver.session() as session:
        query = """
        MATCH (e:Entity)
        WHERE e.group_id IS NOT NULL
        RETURN e.group_id as doc_id, count(e) as cnt
        ORDER BY cnt DESC
        """
        result = session.run(query)
        documents = [(record["doc_id"], record["cnt"]) for record in result]
        return documents


def count_entities_for_document(driver, doc_id: str) -> int:
    """
    Count entities for a specific document.

    Args:
        driver: Neo4j driver instance
        doc_id: Document UUID

    Returns:
        Number of entities with this group_id
    """
    with driver.session() as session:
        query = "MATCH (e:Entity {group_id: $doc_id}) RETURN count(e) as cnt"
        result = session.run(query, doc_id=doc_id)
        record = result.single()
        return record["cnt"] if record else 0


def count_all_entities(driver) -> int:
    """
    Count all entities in the graph.

    Args:
        driver: Neo4j driver instance

    Returns:
        Total number of entities
    """
    with driver.session() as session:
        query = "MATCH (e:Entity) RETURN count(e) as cnt"
        result = session.run(query)
        record = result.single()
        return record["cnt"] if record else 0


def delete_entities_for_document(driver, doc_id: str) -> int:
    """
    Delete all entities for a specific document.

    Args:
        driver: Neo4j driver instance
        doc_id: Document UUID

    Returns:
        Number of entities deleted
    """
    with driver.session() as session:
        # Count first
        count = count_entities_for_document(driver, doc_id)

        if count == 0:
            return 0

        # Delete with DETACH (removes relationships too)
        delete_query = "MATCH (e:Entity {group_id: $doc_id}) DETACH DELETE e"
        session.run(delete_query, doc_id=doc_id)

        return count


def delete_all_entities(driver) -> int:
    """
    Delete ALL entities from the graph.

    Args:
        driver: Neo4j driver instance

    Returns:
        Number of entities deleted
    """
    with driver.session() as session:
        # Count first
        count = count_all_entities(driver)

        if count == 0:
            return 0

        # Delete all entities with DETACH
        delete_query = "MATCH (e:Entity) DETACH DELETE e"
        session.run(delete_query)

        return count


def main():
    parser = argparse.ArgumentParser(
        description='Cleanup Graphiti knowledge graph entities',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show what would be deleted for a document (dry-run)
  %(prog)s --document-id 550e8400-e29b-41d4-a716-446655440000

  # Actually delete entities for a document
  %(prog)s --document-id 550e8400-e29b-41d4-a716-446655440000 --confirm

  # Delete all entities (requires --confirm)
  %(prog)s --all --confirm

  # List all documents with entity counts
  %(prog)s --list
        """
    )

    # Mutually exclusive group for operation mode
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--document-id',
        type=str,
        metavar='UUID',
        help='Document UUID to clean up'
    )
    group.add_argument(
        '--all',
        action='store_true',
        help='Delete ALL entities (use with caution, requires --confirm)'
    )
    group.add_argument(
        '--list',
        action='store_true',
        help='List all documents with entity counts'
    )

    # Confirmation flag
    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Actually perform deletion (default is dry-run)'
    )

    args = parser.parse_args()

    # REQ-013: Check Docker environment
    check_docker_environment()

    # Validate environment variables
    neo4j_uri, neo4j_user, neo4j_password = validate_environment()

    # Connect to Neo4j
    try:
        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )
    except Exception as e:
        print(f"ERROR: Failed to connect to Neo4j: {e}")
        print("")
        print("Action required:")
        print(f"  - Check NEO4J_URI: {neo4j_uri}")
        print("  - Verify Neo4j is running: docker ps | grep txtai-neo4j")
        print("  - Check NEO4J_PASSWORD in .env")
        sys.exit(1)

    try:
        # Verify connection
        driver.verify_connectivity()

        # Handle --list mode
        if args.list:
            documents = list_documents_with_entities(driver)

            if not documents:
                print("No documents found with entities in the knowledge graph.")
                return 0

            print(f"Found {len(documents)} document(s) with entities:")
            print("")
            print(f"{'Document ID':<40} {'Entity Count':>15}")
            print("-" * 57)
            for doc_id, count in documents:
                print(f"{doc_id:<40} {count:>15,}")

            total_entities = sum(count for _, count in documents)
            print("-" * 57)
            print(f"{'TOTAL':<40} {total_entities:>15,}")

            return 0

        # Handle --document-id mode
        if args.document_id:
            doc_id = args.document_id
            count = count_entities_for_document(driver, doc_id)

            if count == 0:
                print(f"No entities found for document: {doc_id}")
                return 0

            if not args.confirm:
                # Dry-run mode (default)
                print(f"[DRY RUN] Would delete {count:,} entit{'y' if count == 1 else 'ies'} for document: {doc_id}")
                print("")
                print("To actually perform deletion, add --confirm flag:")
                print(f"  {sys.argv[0]} --document-id {doc_id} --confirm")
                return 0

            # Confirmation mode - actually delete
            print(f"Deleting {count:,} entit{'y' if count == 1 else 'ies'} for document: {doc_id}")
            deleted = delete_entities_for_document(driver, doc_id)
            print(f"✓ Successfully deleted {deleted:,} entit{'y' if deleted == 1 else 'ies'}")
            return 0

        # Handle --all mode
        if args.all:
            count = count_all_entities(driver)

            if count == 0:
                print("Knowledge graph is already empty.")
                return 0

            if not args.confirm:
                # Dry-run mode (default) or missing confirmation
                print(f"[DRY RUN] Would delete ALL {count:,} entities from the knowledge graph")
                print("")
                print("⚠️  WARNING: This will delete the entire knowledge graph!")
                print("")
                print("To actually perform deletion, add --confirm flag:")
                print(f"  {sys.argv[0]} --all --confirm")
                return 0

            # Confirmation mode - actually delete
            print(f"⚠️  Deleting ALL {count:,} entities from the knowledge graph...")
            deleted = delete_all_entities(driver)
            print(f"✓ Successfully deleted {deleted:,} entit{'y' if deleted == 1 else 'ies'}")
            print("")
            print("Knowledge graph has been reset.")
            return 0

    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    finally:
        driver.close()


if __name__ == '__main__':
    sys.exit(main())
