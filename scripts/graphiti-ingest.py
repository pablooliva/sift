#!/usr/bin/env python3
"""
Graphiti Knowledge Graph Ingestion Tool (SPEC-038 Phase 2)

Populates knowledge graph (Neo4j) for documents already indexed in txtai.
Independent of import script, can run for backfill or selective ingestion.

Prerequisites:
- Documents must be in PostgreSQL (via import or frontend upload)
- Must run inside txtai-mcp Docker container (required dependencies)

Usage:
    docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py [options]

Environment Variables:
    NEO4J_URI: Neo4j connection URI (e.g., bolt://neo4j:7687)
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_PASSWORD: Neo4j password
    TOGETHERAI_API_KEY: Together AI API key (for entity extraction)
    TXTAI_API_URL: txtai API base URL (default: http://txtai:8000)
    GRAPHITI_BATCH_SIZE: Chunks per batch (default: 3)
    GRAPHITI_BATCH_DELAY: Delay between batches in seconds (default: 45)
"""

import argparse
import asyncio
import json
import logging
import os
import random
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from neo4j import AsyncGraphDatabase

# Import GraphitiClient from frontend utils (copied to scripts/)
try:
    from graphiti_client import GraphitiClient
except ImportError:
    print("ERROR: graphiti_client.py not found in scripts/ directory")
    print("Copy frontend/utils/graphiti_client.py to scripts/ directory:")
    print("  cp frontend/utils/graphiti_client.py scripts/")
    sys.exit(1)

# Configuration constants (REQ-007a: hardcoded after verification)
CHUNK_SIZE = 4000  # Verified from frontend/utils/api_client.py:42
CHUNK_OVERLAP = 400  # Verified from frontend/utils/api_client.py:43

# Rate limiting defaults (REQ-009)
DEFAULT_BATCH_SIZE = 3  # chunks per batch
DEFAULT_BATCH_DELAY = 45  # seconds between batches

# Reactive backoff settings (REQ-009 Tier 2)
BACKOFF_TIMES = [60, 120, 240]  # seconds (exponential backoff)
BACKOFF_JITTER = 0.2  # 20% jitter to avoid thundering herd

# Transient error retry settings (REQ-012)
TRANSIENT_BACKOFF_TIMES = [5, 10, 20]  # seconds
TRANSIENT_MAX_RETRIES = 3

# Cost estimation (from research, $0.017 per chunk)
COST_PER_CHUNK = 0.017


# REQ-012: Error categorization helpers
def is_rate_limit_error(error: Exception) -> bool:
    """Check if error is a rate limit error (429 or 503)."""
    error_str = str(error).lower()
    return ('429' in error_str or
            '503' in error_str or
            'rate limit' in error_str or
            'too many requests' in error_str)


def is_transient_error(error: Exception) -> bool:
    """Check if error is transient (network timeout, temporary service unavailable)."""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Network/connection errors
    if any(keyword in error_type for keyword in ['timeout', 'connectionerror', 'connectionrefused']):
        return True

    # Neo4j ServiceUnavailable (but not AuthError)
    if 'serviceunavailable' in error_type and 'auth' not in error_str:
        return True

    # Timeout in error message
    if 'timeout' in error_str or 'timed out' in error_str:
        return True

    return False


def is_permanent_error(error: Exception) -> bool:
    """Check if error is permanent (auth errors, config errors)."""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Authentication errors
    if any(keyword in error_type for keyword in ['autherror', 'unauthorized']):
        return True

    if '401' in error_str or 'unauthorized' in error_str:
        return True

    # Configuration errors
    if any(keyword in error_str for keyword in ['invalid api key', 'authentication failed']):
        return True

    return False


def is_per_document_error(error: Exception) -> bool:
    """Check if error is specific to a document (malformed data, empty text)."""
    error_str = str(error).lower()

    # Data validation errors
    if any(keyword in error_str for keyword in ['none', 'empty', 'malformed', 'invalid']):
        return True

    return False


def check_docker_environment():
    """
    REQ-013: Verify script is running inside Docker container.

    Exits with error if not in Docker environment.
    """
    if not os.path.exists('/.dockerenv'):
        print("ERROR: graphiti-ingest.py must run inside txtai-mcp container")
        print("")
        print("Usage:")
        print("  docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py [options]")
        print("")
        print("Reason: This script requires dependencies installed in txtai-mcp image")
        print("  - graphiti-core==0.26.3")
        print("  - neo4j>=5.0.0")
        print("  - OpenAI SDK")
        print("  - langchain (for RecursiveCharacterTextSplitter)")
        print("")
        sys.exit(1)


def validate_dependencies():
    """
    REQ-014: Check dependency versions and Neo4j compatibility.

    Validates:
    - graphiti-core version (must be 0.26.3)
    - Neo4j database version (must be 5.x)
    - Neo4j schema compatibility (group_id field)
    """
    import graphiti_core
    from neo4j import GraphDatabase
    import importlib.metadata

    # 1. Check graphiti-core version (BUG-E2E-004 fix: updated to 0.26.3)
    REQUIRED_GRAPHITI = "0.26.3"
    installed_version = importlib.metadata.version('graphiti-core')
    if installed_version != REQUIRED_GRAPHITI:
        logging.error(f"graphiti-core version mismatch")
        logging.error(f"  Required: {REQUIRED_GRAPHITI}")
        logging.error(f"  Installed: {installed_version}")
        sys.exit(1)

    # 2. Check Neo4j database version
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://neo4j:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD')

    if not neo4j_password:
        logging.error("NEO4J_PASSWORD environment variable not set")
        sys.exit(1)

    try:
        with GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password)) as driver:
            with driver.session() as session:
                # Check Neo4j version
                result = session.run("CALL dbms.components() YIELD versions RETURN versions")
                version = result.single()["versions"][0]
                major_version = int(version.split('.')[0])
                if major_version != 5:
                    logging.error(f"Unsupported Neo4j version {version}")
                    logging.error(f"  Required: Neo4j 5.x")
                    logging.error(f"  Installed: Neo4j {version}")
                    sys.exit(1)

                logging.info(f"Neo4j version: {version}")

                # Check schema compatibility (if graph not empty)
                result = session.run("MATCH (e:Entity) RETURN e LIMIT 1")
                if result.peek():  # Graph has entities
                    entity = result.single()["e"]
                    if "group_id" not in entity:
                        logging.error("Neo4j schema mismatch")
                        logging.error("  Expected Entity nodes with group_id field")
                        logging.error("  Your graph may have been created with a different Graphiti version")
                        sys.exit(1)

    except Exception as e:
        logging.error(f"Cannot connect to Neo4j at {neo4j_uri}")
        logging.error(f"  Check NEO4J_URI environment variable")
        logging.error(f"  Verify Neo4j is running: docker ps | grep txtai-neo4j")
        logging.error(f"  Verify credentials: NEO4J_PASSWORD in .env")
        logging.error(f"  Error: {e}")
        sys.exit(1)


def setup_logging(log_file: Optional[str] = None):
    """
    REQ-010: Configure logging to stdout (progress), stderr (errors), and optional file.

    Args:
        log_file: Optional path to debug log file
    """
    # Root logger (DEBUG level for file, INFO for console)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Stdout handler (INFO level, no timestamps - human-readable progress)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
    stdout_formatter = logging.Formatter('%(message)s')
    stdout_handler.setFormatter(stdout_formatter)
    root_logger.addHandler(stdout_handler)

    # Stderr handler (WARNING+ level, with timestamps)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%dT%H:%M:%SZ')
    stderr_handler.setFormatter(stderr_formatter)
    root_logger.addHandler(stderr_handler)

    # Optional file handler (DEBUG level, with timestamps)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s', datefmt='%Y-%m-%dT%H:%M:%SZ')
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        logging.info(f"Debug logging to: {log_file}")


def parse_arguments():
    """
    REQ-005: Parse command-line arguments.

    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Populate Graphiti knowledge graph from txtai-indexed documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest all documents
  docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all --confirm

  # Ingest specific category
  docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --category technical --confirm

  # Re-ingest documents (force overwrite)
  docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all --force --confirm

  # Dry run (show what would be ingested)
  docker exec txtai-mcp uv run python /app/scripts/graphiti-ingest.py --all

Environment Variables:
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD - Neo4j connection
  TOGETHERAI_API_KEY - Together AI API key
  TXTAI_API_URL - txtai API base URL
  GRAPHITI_BATCH_SIZE - Chunks per batch (default: 3)
  GRAPHITI_BATCH_DELAY - Delay between batches in seconds (default: 45)
        """
    )

    # Document selection
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--all', action='store_true',
                           help='Ingest all documents in txtai')
    selection.add_argument('--document-id', metavar='UUID',
                           help='Ingest specific document by ID')
    selection.add_argument('--category', metavar='NAME',
                           help='Ingest documents in specific category')

    # Filters
    parser.add_argument('--since-date', metavar='YYYY-MM-DD',
                        help='Only ingest documents uploaded after this date')

    # Behavior
    parser.add_argument('--force', action='store_true',
                        help='Re-ingest documents that already have entities in graph')
    parser.add_argument('--confirm', action='store_true',
                        help='Confirm ingestion (without this, runs in dry-run mode)')

    # Rate limiting
    parser.add_argument('--batch-size', type=int, metavar='N',
                        default=int(os.getenv('GRAPHITI_BATCH_SIZE', DEFAULT_BATCH_SIZE)),
                        help=f'Chunks per batch (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--batch-delay', type=int, metavar='SECONDS',
                        default=int(os.getenv('GRAPHITI_BATCH_DELAY', DEFAULT_BATCH_DELAY)),
                        help=f'Delay between batches (default: {DEFAULT_BATCH_DELAY}s)')

    # Logging
    parser.add_argument('--log-file', metavar='PATH',
                        help='Write debug log to file')

    args = parser.parse_args()

    # Validate batch size
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")

    if args.batch_delay < 0:
        parser.error("--batch-delay must be >= 0")

    return args


def fetch_documents_from_api(
    api_url: str,
    category: Optional[str] = None,
    since_date: Optional[str] = None,
    document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    REQ-006: Fetch documents from txtai API with pagination.

    Uses /search endpoint with query="*" to retrieve all documents.
    Supports filtering by category and date.

    Args:
        api_url: txtai API base URL
        category: Filter by category metadata
        since_date: Filter by documents uploaded after this date
        document_id: Fetch specific document by ID

    Returns:
        List of documents with structure:
            {
                'id': str,
                'text': str,
                'data': {metadata dict}
            }

    Raises:
        urllib.error.HTTPError: If API returns 404 or other error
        KeyError: If response lacks required fields
    """
    documents = []
    limit = 100
    offset = 0

    # Build query
    if document_id:
        # Search by specific ID
        query = f"id:{document_id}"
    else:
        # Search all
        query = "*"

    logging.info(f"Fetching documents from txtai API: {api_url}")

    while True:
        try:
            # Build URL with query parameters
            params = urllib.parse.urlencode({
                'query': query,
                'limit': limit,
                'offset': offset
            })
            url = f"{api_url}/search?{params}"

            # Make API request
            with urllib.request.urlopen(url, timeout=30) as response:
                response_data = response.read()
                results = json.loads(response_data)

            # Check if results is empty (end of pagination)
            if not results or len(results) == 0:
                break

            # Validate response structure
            for result in results:
                if 'text' not in result:
                    raise KeyError("API response lacks 'text' field - triggering PostgreSQL fallback")

                # Apply filters
                if document_id:
                    # Filter by exact document ID match
                    if result.get('id') != document_id:
                        continue

                if category:
                    doc_category = result.get('data', {}).get('category')
                    if doc_category != category:
                        continue

                if since_date:
                    upload_date = result.get('data', {}).get('upload_date', '')
                    if upload_date < since_date:
                        continue

                documents.append(result)

            logging.debug(f"Fetched {len(results)} documents (offset {offset})")

            # If searching for specific document and found it, stop pagination
            if document_id and len(documents) > 0:
                break

            # Check if we got less than limit (last page)
            if len(results) < limit:
                break

            offset += limit

        except urllib.error.HTTPError as e:
            if e.code == 404:
                logging.warning(f"/search endpoint not available (404) - triggering PostgreSQL fallback")
                raise
            else:
                logging.error(f"API error: {e}")
                raise

    logging.info(f"✓ Fetched {len(documents)} documents from API")
    return documents


def fetch_documents_from_postgresql(
    category: Optional[str] = None,
    since_date: Optional[str] = None,
    document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    REQ-006: Fallback to direct PostgreSQL query when API unavailable.

    Requires:
        - psycopg2-binary installed
        - PostgreSQL connection details in environment

    Args:
        category: Filter by category metadata
        since_date: Filter by documents uploaded after this date
        document_id: Fetch specific document by ID

    Returns:
        List of documents (same structure as API)

    Raises:
        ImportError: If psycopg2 not installed
    """
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        raise ImportError("psycopg2-binary not installed")

    # Build connection string from environment
    # Format: postgresql://user:password@host:port/database
    pg_uri = os.getenv('POSTGRES_URI')
    if not pg_uri:
        # Build from components
        pg_host = os.getenv('POSTGRES_HOST', 'postgres')
        pg_port = os.getenv('POSTGRES_PORT', '5432')
        pg_user = os.getenv('POSTGRES_USER', 'postgres')
        pg_password = os.getenv('POSTGRES_PASSWORD', 'postgres')
        pg_database = os.getenv('POSTGRES_DB', 'txtai')
        pg_uri = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"

    logging.info(f"Falling back to PostgreSQL: {pg_uri.split('@')[1]}")  # Hide credentials

    # Connect and query
    conn = psycopg2.connect(pg_uri)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Build query with filters (join sections for text and documents for metadata)
    query = """
        SELECT s.id, s.text, d.data
        FROM sections s
        LEFT JOIN documents d ON s.id = d.id
        WHERE 1=1
    """
    params = []

    if document_id:
        query += " AND s.id = %s"
        params.append(document_id)

    if category:
        query += " AND d.data->>'category' = %s"
        params.append(category)

    if since_date:
        query += " AND d.data->>'upload_date' >= %s"
        params.append(since_date)

    query += " ORDER BY s.id"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    # Convert to list of dicts
    documents = [dict(row) for row in rows]

    logging.info(f"✓ Fetched {len(documents)} documents from PostgreSQL")
    return documents


def fetch_documents(
    api_url: str,
    category: Optional[str] = None,
    since_date: Optional[str] = None,
    document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    REQ-006: Fetch documents with automatic API → PostgreSQL fallback.

    Tries API first, falls back to PostgreSQL if:
    - API returns 404 (endpoint not implemented)
    - API response lacks 'text' field

    Args:
        api_url: txtai API base URL
        category: Filter by category
        since_date: Filter by upload date (YYYY-MM-DD)
        document_id: Fetch specific document

    Returns:
        List of documents

    Raises:
        SystemExit: If both methods fail
    """
    # Optimization: Use PostgreSQL directly for single document ID lookups
    # (Much faster than API pagination with text search)
    if document_id:
        logging.debug(f"Using PostgreSQL for single document lookup (faster than API)")
        try:
            return fetch_documents_from_postgresql(category, since_date, document_id)
        except ImportError:
            logging.warning("psycopg2 not available, falling back to API")
            # Fall through to API method below
        except Exception as db_e:
            logging.warning(f"PostgreSQL lookup failed: {db_e}, trying API")
            # Fall through to API method below

    try:
        # Try API first (for bulk/category queries)
        return fetch_documents_from_api(api_url, category, since_date, document_id)

    except (urllib.error.HTTPError, KeyError) as e:
        logging.warning(f"API retrieval failed: {e}, falling back to PostgreSQL")

        try:
            return fetch_documents_from_postgresql(category, since_date, document_id)

        except ImportError:
            logging.error("ERROR: Cannot retrieve documents")
            logging.error("  - txtai API unavailable")
            logging.error("  - psycopg2 not installed")
            logging.error("  Run: pip install psycopg2-binary")
            sys.exit(1)

        except Exception as db_e:
            logging.error(f"PostgreSQL fallback failed: {db_e}")
            sys.exit(1)


def _recursive_split(
    text: str,
    separators: List[str],
    chunk_size: int,
    chunk_overlap: int
) -> List[str]:
    """
    Recursive text splitting algorithm (simplified LangChain RecursiveCharacterTextSplitter).

    Tries each separator in order until chunks are small enough.
    """
    if not text:
        return []

    # If text fits in chunk size, return it
    if len(text) <= chunk_size:
        return [text]

    # Try each separator
    for i, separator in enumerate(separators):
        if separator == "":
            # Character-level split (last resort)
            chunks = []
            start = 0
            while start < len(text):
                end = min(start + chunk_size, len(text))
                chunks.append(text[start:end])
                # Fix: Ensure start never goes negative or backwards
                if chunk_overlap > 0 and end < len(text):
                    start = max(0, end - chunk_overlap)
                else:
                    start = end
            return chunks

        # Split by this separator
        if separator in text:
            parts = text.split(separator)
            good_chunks = []
            current_chunk = ""

            for part in parts:
                # Add separator back (except for empty parts)
                if part:
                    part_with_sep = part + separator if separator != "" else part
                else:
                    part_with_sep = separator

                # Check if adding this part would exceed chunk size
                if len(current_chunk) + len(part_with_sep) <= chunk_size:
                    current_chunk += part_with_sep
                else:
                    # Current chunk is full
                    if current_chunk:
                        good_chunks.append(current_chunk)

                    # Start new chunk with overlap
                    if chunk_overlap > 0 and current_chunk:
                        # Take last chunk_overlap chars from previous chunk
                        overlap_text = current_chunk[-chunk_overlap:]
                        current_chunk = overlap_text + part_with_sep
                    else:
                        current_chunk = part_with_sep

                    # If even this part is too large, recursively split it
                    if len(part_with_sep) > chunk_size:
                        # Use remaining separators
                        remaining_seps = separators[i+1:] if i+1 < len(separators) else [""]
                        sub_chunks = _recursive_split(part_with_sep, remaining_seps, chunk_size, chunk_overlap)
                        if current_chunk and current_chunk != part_with_sep:
                            good_chunks.append(current_chunk)
                        good_chunks.extend(sub_chunks)
                        current_chunk = ""

            # Don't forget the last chunk
            if current_chunk:
                good_chunks.append(current_chunk)

            return good_chunks

    # Fallback: no separator worked, split by character
    return _recursive_split(text, [""], chunk_size, chunk_overlap)


def chunk_text(text: str) -> List[Dict[str, Any]]:
    """
    REQ-007: Chunk text using recursive character splitting.

    Uses verified parameters from REQ-007a:
    - chunk_size: 4000 characters
    - chunk_overlap: 400 characters

    Implements same algorithm as LangChain RecursiveCharacterTextSplitter.

    Args:
        text: Full document text to chunk

    Returns:
        List of chunk dictionaries with keys:
            - text: Chunk text content
            - chunk_index: 0-based index
            - start: Start character position
            - end: End character position
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # Short text doesn't need chunking
    if len(text) <= CHUNK_SIZE:
        return [{
            "text": text,
            "chunk_index": 0,
            "start": 0,
            "end": len(text)
        }]

    # Define separators (matches frontend exactly)
    separators = [
        "\n---\n",   # Horizontal rule (major section break)
        "\n***\n",   # Alternate horizontal rule
        "\n# ",      # H1 header
        "\n## ",     # H2 header
        "\n### ",    # H3 header
        "\n\n",      # Paragraph break
        "\n",        # Line break
        ". ",        # Sentence boundary
        " ",         # Word boundary
        ""           # Character-level (last resort)
    ]

    # Split text
    chunks_text = _recursive_split(text, separators, CHUNK_SIZE, CHUNK_OVERLAP)

    # Build chunk metadata
    chunks = []
    current_pos = 0

    for i, chunk_text in enumerate(chunks_text):
        # Find chunk position in original text
        start = text.find(chunk_text, current_pos)
        if start == -1:
            # Fallback: couldn't find exact match (can happen with overlap)
            start = current_pos
        end = start + len(chunk_text)

        chunks.append({
            "text": chunk_text,
            "chunk_index": i,
            "start": start,
            "end": end
        })

        current_pos = max(0, end - CHUNK_OVERLAP)  # Account for overlap

    return chunks


def fetch_child_chunks(parent_id: str) -> List[Dict[str, Any]]:
    """
    REQ-007: Fetch child chunks from PostgreSQL for a parent document.

    Args:
        parent_id: Parent document UUID

    Returns:
        List of chunk dictionaries with 'text' and 'chunk_index' keys
        Returns empty list if no chunks found or on error
    """
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        logging.warning("psycopg2-binary not installed, cannot fetch child chunks")
        return []

    # Build connection string from environment
    pg_uri = os.getenv('POSTGRES_URI')
    if not pg_uri:
        pg_host = os.getenv('POSTGRES_HOST', 'postgres')
        pg_port = os.getenv('POSTGRES_PORT', '5432')
        pg_user = os.getenv('POSTGRES_USER', 'postgres')
        pg_password = os.getenv('POSTGRES_PASSWORD', 'postgres')
        pg_database = os.getenv('POSTGRES_DB', 'txtai')
        pg_uri = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"

    try:
        # Connect and query
        conn = psycopg2.connect(pg_uri)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Query for child chunks (ID pattern: {parent_id}_chunk_{index})
        # Need to join sections for text content
        query = """
            SELECT s.id, s.text, d.data
            FROM documents d
            LEFT JOIN sections s ON d.id = s.id
            WHERE d.id LIKE %s
              AND d.data->>'is_chunk' = 'true'
            ORDER BY (d.data->>'chunk_index')::int
        """
        chunk_pattern = f"{parent_id}_chunk_%"
        cursor.execute(query, (chunk_pattern,))
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        # Convert to chunk format
        chunks = []
        for row in rows:
            data = row.get('data', {})
            chunks.append({
                'text': row['text'],
                'chunk_index': data.get('chunk_index', 0),
                'id': row['id']  # Include chunk ID for debugging
            })

        if chunks:
            logging.debug(f"Fetched {len(chunks)} child chunks for parent {parent_id[:8]}...")

        return chunks

    except Exception as e:
        logging.warning(f"Failed to fetch child chunks for {parent_id[:8]}...: {e}")
        return []


def detect_chunk_state(doc: Dict[str, Any]) -> Tuple[str, List[Dict]]:
    """
    REQ-007: Detect document chunk state.

    Three states:
    1. CHUNK_ONLY: Document itself is a chunk (ingest directly)
    2. PARENT_WITH_CHUNKS: Document is parent with existing chunks (ingest chunks)
    3. PARENT_WITHOUT_CHUNKS: Document needs chunking (chunk then ingest)

    Args:
        doc: Document dictionary with 'id', 'text', 'data' keys

    Returns:
        Tuple of (state_string, chunks_list)
        - state: "CHUNK_ONLY", "PARENT_WITH_CHUNKS", or "PARENT_WITHOUT_CHUNKS"
        - chunks: List of chunk dicts (empty for CHUNK_ONLY)
    """
    data = doc.get('data', {})
    # Handle both boolean and string values (PostgreSQL JSON may return strings)
    is_chunk = data.get('is_chunk') in (True, 'true')
    is_parent = data.get('is_parent') in (True, 'true')


    if is_chunk:
        # Edge case: Both is_chunk and is_parent (conflicting metadata)
        if is_parent:
            logging.warning(
                f"Document {doc['id']} has conflicting metadata "
                "(is_chunk and is_parent both true), treating as CHUNK_ONLY"
            )
        return "CHUNK_ONLY", []

    elif is_parent:
        # Parent document - fetch child chunks from PostgreSQL
        chunks = fetch_child_chunks(doc['id'])

        if chunks:
            logging.debug(f"Parent doc {doc['id'][:8]}... has {len(chunks)} existing chunks")
            return "PARENT_WITH_CHUNKS", chunks
        else:
            # Parent flag set but no chunks found - may be legacy or corrupted
            logging.warning(
                f"Parent doc {doc['id'][:8]}... has is_parent=true but no child chunks found "
                "- will re-chunk"
            )
            return "PARENT_WITHOUT_CHUNKS", []

    else:
        # Legacy document (pre-chunking era) or parent without chunks
        return "PARENT_WITHOUT_CHUNKS", []


async def is_already_ingested(driver, doc_id: str) -> Tuple[bool, int]:
    """
    REQ-011: Check if document already has entities in Neo4j.

    Args:
        driver: Neo4j driver instance
        doc_id: Document UUID to check

    Returns:
        Tuple of (already_ingested, entity_count)
    """
    async with driver.session() as session:
        query = "MATCH (e:Entity {group_id: $doc_id}) RETURN count(e) as cnt"
        result = await session.run(query, doc_id=doc_id)
        record = await result.single()
        count = record["cnt"] if record else 0
        return (count > 0, count)


async def delete_existing_entities(driver, doc_id: str) -> int:
    """
    REQ-011: Delete existing entities for document (--force flag).

    Args:
        driver: Neo4j driver instance
        doc_id: Document UUID

    Returns:
        Number of entities deleted
    """
    async with driver.session() as session:
        # Count first
        count_query = "MATCH (e:Entity {group_id: $doc_id}) RETURN count(e) as cnt"
        result = await session.run(count_query, doc_id=doc_id)
        record = await result.single()
        count = record["cnt"] if record else 0

        if count == 0:
            return 0

        # Delete with DETACH (removes relationships too)
        delete_query = "MATCH (e:Entity {group_id: $doc_id}) DETACH DELETE e"
        await session.run(delete_query, doc_id=doc_id)

        logging.debug(f"Deleted {count} existing entities for document {doc_id}")
        return count


async def ingest_document_async(
    graphiti_client: GraphitiClient,
    neo4j_driver,
    doc: Dict[str, Any],
    batch_size: int,
    batch_delay: int,
    force: bool,
    dry_run: bool
) -> Dict[str, Any]:
    """
    REQ-008: Ingest a single document to Graphiti.

    Handles chunking, idempotency, and rate limiting.

    Args:
        graphiti_client: Initialized GraphitiClient
        neo4j_driver: Neo4j driver for idempotency checks
        doc: Document dictionary
        batch_size: Chunks per batch (for rate limiting)
        batch_delay: Delay between batches
        force: Re-ingest even if already ingested
        dry_run: Don't actually ingest

    Returns:
        Dict with ingestion results:
            - success: bool
            - chunks_ingested: int
            - entities_created: int
            - skipped: bool (if already ingested)
            - error: Optional error message
    """
    doc_id = doc['id']
    doc_text = doc.get('text', '')
    doc_data = doc.get('data', {})
    doc_title = doc_data.get('title', doc_id[:8])

    # REQ-011: Check if already ingested
    already_ingested, entity_count = await is_already_ingested(neo4j_driver, doc_id)

    if already_ingested and not force:
        logging.info(f"Skipping document {doc_id} ({doc_title}): {entity_count} entities already in graph")
        return {
            'success': True,
            'chunks_ingested': 0,
            'entities_created': 0,
            'skipped': True
        }

    if already_ingested and force:
        if not dry_run:
            deleted_count = await delete_existing_entities(neo4j_driver, doc_id)
            logging.info(f"Deleted {deleted_count} existing entities for {doc_id} (--force)")
        else:
            logging.info(f"[DRY RUN] Would delete {entity_count} entities for {doc_id}")

    # REQ-007: Detect chunk state and get chunks
    state, existing_chunks = detect_chunk_state(doc)

    if state == "CHUNK_ONLY":
        # Document is already a chunk - ingest directly
        chunks = [{"text": doc_text, "chunk_index": 0}]

    elif state == "PARENT_WITH_CHUNKS":
        # Use existing chunks
        chunks = existing_chunks

    else:  # PARENT_WITHOUT_CHUNKS
        # Need to chunk the document
        if len(doc_text) <= CHUNK_SIZE:
            # Short document, no chunking needed
            chunks = [{"text": doc_text, "chunk_index": 0}]
        else:
            chunks = chunk_text(doc_text)

    logging.info(f"Processing document '{doc_title}' ({doc_id[:8]}...): {len(chunks)} chunk(s)")

    if dry_run:
        logging.info(f"[DRY RUN] Would ingest {len(chunks)} chunk(s) for {doc_id}")
        return {
            'success': True,
            'chunks_ingested': len(chunks),
            'entities_created': 0,
            'skipped': False
        }

    # REQ-008: Ingest chunks
    total_entities = 0
    chunks_ingested = 0

    for i, chunk in enumerate(chunks):
        chunk_content = chunk['text']

        # Build episode metadata (matches frontend exactly)
        episode_kwargs = {
            'name': f"{doc_title} (chunk {i+1}/{len(chunks)})",
            'content': chunk_content,
            'source': f"Document: {doc_title} ({doc_id[:8]}...)",
            'timestamp': datetime.now(timezone.utc),
            'group_id': doc_id  # Critical: enables per-document scoping
        }

        # REQ-009 Tier 2 + REQ-012: Retry with categorized error handling
        result = None
        last_error = None
        rate_limit_retries = 0
        transient_retries = 0
        total_attempts = 0
        max_total_attempts = max(len(BACKOFF_TIMES), TRANSIENT_MAX_RETRIES) + 1

        while total_attempts < max_total_attempts:
            try:
                # Ingest episode
                result = await graphiti_client.add_episode(**episode_kwargs)

                # Success - break out of retry loop
                if result:
                    entities = result.get('entities', 0)
                    relationships = result.get('relationships', 0)
                    total_entities += entities
                    chunks_ingested += 1

                    logging.debug(
                        f"  Chunk {i+1}/{len(chunks)}: {entities} entities, {relationships} relationships"
                    )

                    # If this was a successful retry, log it
                    if total_attempts > 0:
                        logging.info(f"  Retry successful, continuing with chunk {i+2}/{len(chunks)}")

                break  # Success - exit retry loop

            except Exception as e:
                last_error = e
                total_attempts += 1

                # REQ-012: Categorize error
                if is_permanent_error(e):
                    # Permanent error - fail immediately
                    logging.error(f"  Permanent error on chunk {i+1}: {e}")
                    logging.error(f"  Cannot retry permanent errors. Check configuration and credentials.")
                    break

                elif is_rate_limit_error(e):
                    # Rate limit error - use long backoff
                    if rate_limit_retries < len(BACKOFF_TIMES):
                        backoff_base = BACKOFF_TIMES[rate_limit_retries]
                        jitter = random.uniform(0, backoff_base * BACKOFF_JITTER)
                        wait_time = backoff_base + jitter

                        logging.warning(
                            f"  Rate limit hit on chunk {i+1}, waiting {wait_time:.0f}s before retry "
                            f"(rate limit attempt {rate_limit_retries+1}/{len(BACKOFF_TIMES)})..."
                        )
                        await asyncio.sleep(wait_time)
                        rate_limit_retries += 1
                        # Continue to next retry
                    else:
                        # Exhausted rate limit retries
                        logging.error(
                            f"  Rate limit persists after {sum(BACKOFF_TIMES)}s total wait. "
                            f"Check if other processes are using the same API key."
                        )
                        break

                elif is_transient_error(e):
                    # Transient error - use short backoff
                    if transient_retries < TRANSIENT_MAX_RETRIES:
                        wait_time = TRANSIENT_BACKOFF_TIMES[transient_retries]

                        logging.warning(
                            f"  Transient error on chunk {i+1} ({type(e).__name__}), "
                            f"waiting {wait_time}s before retry "
                            f"(transient attempt {transient_retries+1}/{TRANSIENT_MAX_RETRIES})..."
                        )
                        await asyncio.sleep(wait_time)
                        transient_retries += 1
                        # Continue to next retry
                    else:
                        # Exhausted transient retries
                        logging.error(
                            f"  Transient error persists after {sum(TRANSIENT_BACKOFF_TIMES)}s: {e}"
                        )
                        break

                else:
                    # Unknown/per-document error - log and continue with next chunk
                    logging.error(f"  Failed to ingest chunk {i+1}: {e}")
                    logging.debug(f"  Error type: {type(e).__name__}", exc_info=True)
                    break

        # REQ-009 Tier 1: Proactive batch delay
        if (i + 1) % batch_size == 0 and (i + 1) < len(chunks):
            logging.info(f"  Batch complete ({i+1}/{len(chunks)} chunks) — waiting {batch_delay}s...")
            await asyncio.sleep(batch_delay)

    return {
        'success': True,
        'chunks_ingested': chunks_ingested,
        'entities_created': total_entities,
        'skipped': False
    }


async def async_main(args, neo4j_uri, neo4j_user, neo4j_password, api_key, api_url, ollama_url, llm_model, small_llm_model, embedding_model, embedding_dim):
    """
    Async main function that handles ingestion.

    Args:
        args: Parsed command-line arguments
        neo4j_uri: Neo4j connection URI
        neo4j_user: Neo4j username
        neo4j_password: Neo4j password
        api_key: Together AI API key
        api_url: txtai API URL
        ollama_url: Ollama API URL
        llm_model: Primary LLM model (BUG-E2E-004 fix)
        small_llm_model: Smaller LLM model (BUG-E2E-004 fix)
        embedding_model: Embedding model (BUG-E2E-004 fix)
        embedding_dim: Embedding dimension (BUG-E2E-004 fix)
    """
    # REQ-006: Fetch documents
    logging.info("Fetching documents...")
    documents = fetch_documents(
        api_url=api_url,
        category=args.category,
        since_date=args.since_date,
        document_id=args.document_id
    )

    if not documents:
        logging.error("No documents found in PostgreSQL")
        logging.error("Ensure documents have been imported or uploaded via frontend")
        return 1

    logging.info(f"✓ Found {len(documents)} document(s)")
    logging.info("")

    # Show cost estimate
    estimated_chunks = sum(
        max(1, len(doc.get('text', '')) // CHUNK_SIZE)
        for doc in documents
    )
    estimated_cost = estimated_chunks * COST_PER_CHUNK

    logging.info(f"Cost estimate:")
    logging.info(f"  Estimated chunks: {estimated_chunks}")
    logging.info(f"  Cost per chunk: ${COST_PER_CHUNK}")
    logging.info(f"  Total estimated cost: ${estimated_cost:.2f}")
    logging.info("")

    if estimated_chunks > 100 and not args.confirm:
        logging.warning(
            f"WARNING: {estimated_chunks} chunks will cost ~${estimated_cost:.2f}"
        )
        logging.warning("Add --confirm flag to proceed with ingestion")
        return 1

    # Initialize GraphitiClient
    logging.info("Initializing Graphiti client...")

    # REQ-012: Initialize with error handling (BUG-E2E-004 fix: include model config)
    try:
        graphiti_client = GraphitiClient(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            together_api_key=api_key,
            ollama_api_url=ollama_url,
            llm_model=llm_model,
            small_llm_model=small_llm_model,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim
        )
        # Async initialization (must be done in same event loop)
        await graphiti_client.initialize()
    except Exception as e:
        logging.error(f"Failed to initialize Graphiti client: {e}")
        if is_permanent_error(e):
            logging.error("Authentication error detected. Action required:")
            logging.error(f"  - Verify NEO4J_PASSWORD in .env is correct")
            logging.error(f"  - Verify TOGETHERAI_API_KEY is valid")
            logging.error(f"  - Check Neo4j is running: docker ps | grep txtai-neo4j")
        return 1

    # Create async Neo4j driver for idempotency checks
    try:
        neo4j_driver = AsyncGraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )
    except Exception as e:
        logging.error(f"Failed to create Neo4j driver: {e}")
        logging.error("Action required:")
        logging.error(f"  - Check NEO4J_URI: {neo4j_uri}")
        logging.error(f"  - Verify Neo4j is running: docker ps | grep txtai-neo4j")
        logging.error(f"  - Check NEO4J_PASSWORD in .env")
        return 1

    try:
        logging.info("✓ Graphiti client initialized")
        logging.info("")

        # Process documents
        total_chunks = 0
        total_entities = 0
        skipped_count = 0

        for i, doc in enumerate(documents):
            logging.info(f"Document {i+1}/{len(documents)}")

            result = await ingest_document_async(
                graphiti_client=graphiti_client,
                neo4j_driver=neo4j_driver,
                doc=doc,
                batch_size=args.batch_size,
                batch_delay=args.batch_delay,
                force=args.force,
                dry_run=not args.confirm
            )

            if result['skipped']:
                skipped_count += 1
            else:
                total_chunks += result['chunks_ingested']
                total_entities += result['entities_created']

            logging.info("")

        # Summary
        logging.info("=" * 60)
        logging.info("Ingestion complete!")
        logging.info(f"  Documents processed: {len(documents)}")
        logging.info(f"  Documents skipped: {skipped_count}")
        logging.info(f"  Chunks ingested: {total_chunks}")
        logging.info(f"  Entities created: {total_entities}")
        logging.info(f"  Actual cost: ${total_chunks * COST_PER_CHUNK:.2f}")

        return 0

    finally:
        await neo4j_driver.close()


def validate_environment():
    """
    Validate required environment variables and return their values.

    REQ-012: Check required environment variables with actionable messages.
    BUG-E2E-004 fix: Also reads Graphiti model configuration.

    Returns:
        tuple: (neo4j_uri, neo4j_user, neo4j_password, api_key, api_url, ollama_url,
                llm_model, small_llm_model, embedding_model, embedding_dim)

    Raises:
        SystemExit: If required environment variables are missing.
    """
    # Check required environment variables
    missing_vars = []
    if not os.getenv('TOGETHERAI_API_KEY'):
        missing_vars.append('TOGETHERAI_API_KEY')
    if not os.getenv('NEO4J_PASSWORD'):
        missing_vars.append('NEO4J_PASSWORD')

    if missing_vars:
        logging.error("Missing required environment variables:")
        for var in missing_vars:
            logging.error(f"  - {var}")
        logging.error("")
        logging.error("Action required:")
        logging.error("  1. Create/edit .env file in project root")
        logging.error("  2. Add missing variables:")
        for var in missing_vars:
            if var == 'TOGETHERAI_API_KEY':
                logging.error(f"     {var}=your_api_key_here  # Get from together.ai")
            elif var == 'NEO4J_PASSWORD':
                logging.error(f"     {var}=your_password_here  # Neo4j database password")
        logging.error("  3. Restart Docker containers: docker compose restart")
        sys.exit(1)

    # Get environment values with defaults
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://neo4j:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD')
    api_key = os.getenv('TOGETHERAI_API_KEY')
    api_url = os.getenv('TXTAI_API_URL', 'http://txtai:8000')
    ollama_url = os.getenv('OLLAMA_API_URL', 'http://localhost:11434')

    # BUG-E2E-004 fix: Read Graphiti model configuration from environment
    llm_model = os.getenv('GRAPHITI_LLM_MODEL', 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo')
    small_llm_model = os.getenv('GRAPHITI_SMALL_LLM_MODEL', 'Qwen/Qwen2.5-7B-Instruct-Turbo')
    embedding_model = os.getenv('GRAPHITI_EMBEDDING_MODEL', 'nomic-embed-text')
    embedding_dim = int(os.getenv('GRAPHITI_EMBEDDING_DIM', '768'))

    return neo4j_uri, neo4j_user, neo4j_password, api_key, api_url, ollama_url, llm_model, small_llm_model, embedding_model, embedding_dim


def main():
    """Main entry point."""
    # REQ-013: Check Docker environment first
    check_docker_environment()

    # Parse arguments
    args = parse_arguments()

    # REQ-010: Setup logging
    setup_logging(args.log_file)

    logging.info("Graphiti Ingestion Tool (SPEC-038 Phase 2)")
    logging.info("=" * 60)

    # REQ-014: Validate dependencies
    logging.info("Validating dependencies...")
    validate_dependencies()
    logging.info("✓ Dependencies validated")

    # REQ-012: Validate environment variables (BUG-E2E-004 fix: includes model config)
    neo4j_uri, neo4j_user, neo4j_password, api_key, api_url, ollama_url, llm_model, small_llm_model, embedding_model, embedding_dim = validate_environment()

    # Show configuration
    logging.info("")
    logging.info("Configuration:")
    logging.info(f"  Neo4j URI: {neo4j_uri}")
    logging.info(f"  txtai API: {api_url}")
    logging.info(f"  Batch size: {args.batch_size} chunks")
    logging.info(f"  Batch delay: {args.batch_delay}s")
    logging.info(f"  Force re-ingest: {args.force}")
    logging.info(f"  Dry run: {not args.confirm}")

    if not args.confirm:
        logging.info("")
        logging.info("NOTE: Running in DRY RUN mode (no changes will be made)")
        logging.info("      Add --confirm flag to actually ingest documents")

    logging.info("")

    # Run async main
    try:
        return asyncio.run(async_main(
            args=args,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            api_key=api_key,
            api_url=api_url,
            ollama_url=ollama_url,
            llm_model=llm_model,
            small_llm_model=small_llm_model,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim
        ))
    except KeyboardInterrupt:
        logging.warning("Interrupted by user")
        return 130
    except Exception as e:
        # REQ-012: Categorize fatal errors with actionable messages
        logging.error(f"Fatal error: {e}", exc_info=True)

        if is_permanent_error(e):
            logging.error("")
            logging.error("Permanent error detected. Action required:")
            logging.error("  - Check authentication credentials (API keys, passwords)")
            logging.error("  - Verify environment variables in .env file")
            logging.error("  - Ensure all services are running: docker compose ps")
        elif is_transient_error(e):
            logging.error("")
            logging.error("Network/connection error. Suggestions:")
            logging.error("  - Verify services are running: docker compose ps")
            logging.error("  - Check network connectivity")
            logging.error("  - Try again in a few moments")
        else:
            logging.error("")
            logging.error("For help, run with --help or check logs above")

        return 1


if __name__ == '__main__':
    sys.exit(main())
