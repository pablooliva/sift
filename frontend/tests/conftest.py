"""
Global pytest fixtures for txtai frontend tests (SPEC-024).

CRITICAL SAFETY FEATURES:
- Verifies test databases contain '_test' in their names
- Prevents accidental execution against production databases
- Provides cleanup fixtures for test isolation

Test Database Configuration:
- PostgreSQL: txtai_test (NOT txtai)
- Qdrant: txtai_test_embeddings (NOT txtai_embeddings)
- Neo4j: neo4j_test (NOT neo4j)
"""

import os
import sys
from pathlib import Path

# Disable Graphiti for functional tests to prevent Neo4j connection attempts
# Must be set BEFORE any imports that might trigger graphiti_core loading
os.environ['GRAPHITI_ENABLED'] = 'false'

import pytest
import requests

# Add frontend directory to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# =============================================================================
# TEST ENVIRONMENT CONFIGURATION
# =============================================================================
# These environment variables MUST contain '_test' in database/collection names
# Default values use test databases from docker-compose.test.yml - NEVER point to production
#
# Test service ports (from docker-compose.test.yml) - all in 9000 range:
#   - PostgreSQL: 9433 (test) vs 5432 (prod)
#   - Qdrant: 9333 (test) vs 7333 (prod)
#   - txtai API: 9301 (test) vs 8300 (prod)
#   - Frontend: 9502 (test) vs 8501 (prod)

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:9433/txtai_test"
)
TEST_QDRANT_URL = os.getenv("TEST_QDRANT_URL", "http://localhost:9333")
TEST_QDRANT_COLLECTION = os.getenv("TEST_QDRANT_COLLECTION", "txtai_test_embeddings")

# Neo4j test configuration
TEST_NEO4J_URI = os.getenv("TEST_NEO4J_URI", "bolt://localhost:7687")
TEST_NEO4J_USER = os.getenv("TEST_NEO4J_USER", "neo4j")
TEST_NEO4J_PASSWORD = os.getenv("TEST_NEO4J_PASSWORD", "password")
TEST_NEO4J_DATABASE = os.getenv("TEST_NEO4J_DATABASE", "neo4j_test")

# Frontend URL for E2E tests (test services on port 9502)
TEST_FRONTEND_URL = os.getenv("TEST_FRONTEND_URL", "http://localhost:9502")

# txtai API URL for E2E tests (test services on port 9301)
TEST_TXTAI_API_URL = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# =============================================================================
# SAFETY CHECK FIXTURE (CRITICAL - RUNS FIRST)
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def verify_test_environment():
    """
    SAFETY CHECK: Abort immediately if pointing at production database.

    This fixture runs before ANY test and prevents accidental data loss.
    Implements SEC-003, SEC-004, SEC-005, SEC-006.

    Safety rules:
    1. TEST_DATABASE_URL must contain '_test'
    2. TEST_QDRANT_COLLECTION must contain '_test'
    3. TEST_NEO4J_DATABASE must contain '_test'

    If any check fails, pytest exits immediately with clear error message.
    """
    errors = []

    # Check PostgreSQL database name
    if "_test" not in TEST_DATABASE_URL.lower():
        errors.append(
            f"PostgreSQL: TEST_DATABASE_URL must contain '_test'.\n"
            f"  Current: {TEST_DATABASE_URL}\n"
            f"  Expected: Should contain 'txtai_test' or similar"
        )

    # Check Qdrant collection name
    if "_test" not in TEST_QDRANT_COLLECTION.lower():
        errors.append(
            f"Qdrant: TEST_QDRANT_COLLECTION must contain '_test'.\n"
            f"  Current: {TEST_QDRANT_COLLECTION}\n"
            f"  Expected: Should contain 'txtai_test_embeddings' or similar"
        )

    # Check Neo4j database name
    if "_test" not in TEST_NEO4J_DATABASE.lower():
        errors.append(
            f"Neo4j: TEST_NEO4J_DATABASE must contain '_test'.\n"
            f"  Current: {TEST_NEO4J_DATABASE}\n"
            f"  Expected: Should contain 'neo4j_test' or similar"
        )

    if errors:
        error_msg = (
            "\n" + "=" * 70 + "\n"
            "SAFETY ERROR: Refusing to run tests against production databases!\n"
            "=" * 70 + "\n\n"
            + "\n\n".join(errors) + "\n\n"
            "To fix:\n"
            "1. Create test databases (see docs/TESTING.md)\n"
            "2. Set environment variables with '_test' in database names\n"
            "3. Re-run tests\n"
            + "=" * 70
        )
        pytest.exit(error_msg, returncode=1)

    # Log successful safety check
    print("\n" + "-" * 50)
    print("Safety check PASSED - Using test databases:")
    print(f"  PostgreSQL: {TEST_DATABASE_URL.split('@')[-1] if '@' in TEST_DATABASE_URL else TEST_DATABASE_URL}")
    print(f"  Qdrant collection: {TEST_QDRANT_COLLECTION}")
    print(f"  Neo4j database: {TEST_NEO4J_DATABASE}")
    print("-" * 50 + "\n")

    yield


# =============================================================================
# DATABASE CONNECTION FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def postgres_connection(verify_test_environment):
    """
    Provide PostgreSQL connection to test database.
    Only available after safety check passes.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(TEST_DATABASE_URL, connect_timeout=5)
        yield conn
        conn.close()
    except ImportError:
        pytest.skip("psycopg2 not installed - PostgreSQL tests skipped")
    except Exception as e:
        pytest.skip(f"PostgreSQL test database not accessible: {e}")


@pytest.fixture(scope="session")
def neo4j_driver(verify_test_environment):
    """
    Provide Neo4j driver for test database.
    Only available after safety check passes.
    """
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            TEST_NEO4J_URI,
            auth=(TEST_NEO4J_USER, TEST_NEO4J_PASSWORD)
        )
        # Verify connection works
        with driver.session(database=TEST_NEO4J_DATABASE) as session:
            session.run("RETURN 1")
        yield driver
        driver.close()
    except ImportError:
        pytest.skip("neo4j driver not installed - Neo4j tests skipped")
    except Exception as e:
        pytest.skip(f"Neo4j test database not accessible: {e}")


# =============================================================================
# DATABASE CLEANUP FIXTURES
# =============================================================================

@pytest.fixture
def clean_postgres(postgres_connection):
    """
    Clean PostgreSQL test data before and after each test.
    Uses DELETE instead of TRUNCATE to avoid exclusive lock conflicts with
    txtai API's open transactions (which hold shared locks on tables).

    Implements SEC-002: Test fixtures isolated; tests clean up after themselves.
    """
    cursor = postgres_connection.cursor()

    def clean_tables():
        try:
            # Check if tables exist before cleaning (avoids noisy error logs)
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'documents'
                );
            """)
            tables_exist = cursor.fetchone()[0]

            if tables_exist:
                # Use DELETE instead of TRUNCATE to avoid exclusive lock requirements
                # TRUNCATE requires AccessExclusiveLock which blocks on any open transactions
                # DELETE only requires RowExclusiveLock which is compatible with SELECT
                cursor.execute("DELETE FROM sections;")
                cursor.execute("DELETE FROM documents;")
                # Reset sequences for predictable IDs (optional but nice for tests)
                cursor.execute("ALTER SEQUENCE IF EXISTS documents_id_seq RESTART WITH 1;")
                cursor.execute("ALTER SEQUENCE IF EXISTS sections_id_seq RESTART WITH 1;")
            postgres_connection.commit()
        except Exception:
            postgres_connection.rollback()

    # Clean before test
    clean_tables()

    yield postgres_connection

    # Clean after test
    clean_tables()


@pytest.fixture
def clean_qdrant(verify_test_environment):
    """
    Clean Qdrant test collection before and after each test.
    Deletes all points in the test collection if it exists.

    Implements SEC-002: Test fixtures isolated; tests clean up after themselves.
    """
    def delete_all_points():
        try:
            # First check if collection exists
            check_response = requests.get(
                f"{TEST_QDRANT_URL}/collections/{TEST_QDRANT_COLLECTION}",
                timeout=10
            )
            if check_response.status_code == 404:
                # Collection doesn't exist yet - nothing to clean
                return

            # Delete all points using filter (empty filter = all points)
            response = requests.post(
                f"{TEST_QDRANT_URL}/collections/{TEST_QDRANT_COLLECTION}/points/delete",
                json={"filter": {}},
                timeout=10
            )
            if response.status_code not in (200, 404):
                print(f"Warning: Qdrant cleanup returned {response.status_code}")
        except requests.RequestException:
            pass  # Silently ignore connection errors during cleanup

    # Clean before test
    delete_all_points()

    yield

    # Clean after test
    delete_all_points()


@pytest.fixture
def clean_neo4j(neo4j_driver):
    """
    Clean Neo4j test database before and after each test.
    Deletes all nodes and relationships.

    Implements SEC-002: Test fixtures isolated; tests clean up after themselves.
    """
    def clear_database():
        try:
            with neo4j_driver.session(database=TEST_NEO4J_DATABASE) as session:
                session.run("MATCH (n) DETACH DELETE n")
        except Exception as e:
            print(f"Warning: Neo4j cleanup failed: {e}")

    # Clean before test
    clear_database()

    yield neo4j_driver

    # Clean after test
    clear_database()


# =============================================================================
# SERVICE AVAILABILITY FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def txtai_api_available(verify_test_environment):
    """
    Check if txtai API is available for E2E tests.
    Returns True if API responds, False otherwise.
    """
    try:
        response = requests.get(f"{TEST_TXTAI_API_URL}/count", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def frontend_available(verify_test_environment):
    """
    Check if Streamlit frontend is available for E2E tests.
    Returns True if frontend responds, False otherwise.
    """
    try:
        response = requests.get(TEST_FRONTEND_URL, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


@pytest.fixture
def require_services(txtai_api_available, frontend_available):
    """
    Skip test if required services are not available.
    Use this fixture for E2E tests that need running services.
    """
    if not txtai_api_available:
        pytest.skip("txtai API not available")
    if not frontend_available:
        pytest.skip("Streamlit frontend not available")


# =============================================================================
# SHARED API CLIENT FIXTURE
# =============================================================================

@pytest.fixture(scope="session")
def api_client(verify_test_environment):
    """
    Shared TxtAIClient for all integration tests.

    Provides a single API client instance configured for test services:
    - Uses TEST_TXTAI_API_URL (port 9301, not production 8300)
    - Sets QDRANT_URL to test service (port 9333, not production 7333)
    - Sets QDRANT_COLLECTION to test collection

    This eliminates the need for individual tests to:
    - Define their own client fixtures
    - Set environment variables manually
    - Hardcode port numbers

    Usage in tests:
        def test_something(api_client):
            result = api_client.search("query")
            assert result["success"]
    """
    from utils.api_client import TxtAIClient

    # Configure environment for test services
    os.environ['QDRANT_URL'] = TEST_QDRANT_URL
    os.environ['QDRANT_COLLECTION'] = TEST_QDRANT_COLLECTION

    # Create client connected to test API
    return TxtAIClient(base_url=TEST_TXTAI_API_URL, timeout=30)


# =============================================================================
# TEST FIXTURES DIRECTORY
# =============================================================================

@pytest.fixture(scope="session")
def fixtures_dir():
    """Provide path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def sample_txt_path(fixtures_dir):
    """Path to sample.txt test fixture."""
    return fixtures_dir / "sample.txt"


@pytest.fixture(scope="session")
def sample_pdf_path(fixtures_dir):
    """Path to small.pdf test fixture."""
    return fixtures_dir / "small.pdf"


@pytest.fixture(scope="session")
def large_pdf_path(fixtures_dir):
    """Path to large.pdf test fixture (1.4MB)."""
    return fixtures_dir / "large.pdf"


@pytest.fixture(scope="session")
def large_document_path(fixtures_dir):
    """Path to large_document.txt test fixture (~5,100 words, generates 12-13 chunks)."""
    return fixtures_dir / "large_document.txt"


@pytest.fixture(scope="session")
def sample_image_path(fixtures_dir):
    """Path to sample.jpg test fixture (for image captioning)."""
    return fixtures_dir / "sample.jpg"


@pytest.fixture(scope="session")
def screenshot_path(fixtures_dir):
    """Path to screenshot_with_text.png test fixture (for OCR path)."""
    return fixtures_dir / "screenshot_with_text.png"


@pytest.fixture(scope="session")
def sample_audio_path(fixtures_dir):
    """Path to sample.wav test fixture."""
    return fixtures_dir / "sample.wav"


@pytest.fixture(scope="session")
def sample_video_path(fixtures_dir):
    """Path to short.mp4 test fixture."""
    return fixtures_dir / "short.mp4"


@pytest.fixture(scope="session")
def url_fixture_path(fixtures_dir):
    """Path to url.txt fixture containing test URL."""
    return fixtures_dir / "url.txt"


# =============================================================================
# PARAMETRIZED FIXTURE FOR ALL FILE TYPES
# =============================================================================

@pytest.fixture(scope="session")
def all_test_files(fixtures_dir):
    """
    Return dict mapping file type to fixture path.
    Used for parametrized tests covering all 16 supported file types.
    """
    return {
        "txt": fixtures_dir / "sample.txt",
        "md": fixtures_dir / "sample.md",
        "pdf": fixtures_dir / "small.pdf",
        "docx": fixtures_dir / "sample.docx",
        "mp3": fixtures_dir / "large.mp3",  # Note: large file, use @pytest.mark.slow
        "wav": fixtures_dir / "sample.wav",
        "m4a": fixtures_dir / "sample.m4a",
        "mp4": fixtures_dir / "short.mp4",
        "webm": fixtures_dir / "large.webm",  # Note: large file, use @pytest.mark.slow
        "jpg": fixtures_dir / "sample.jpg",
        "png": fixtures_dir / "sample.png",
        "gif": fixtures_dir / "sample.gif",
        # Note: These types don't have fixtures yet
        # "jpeg": fixtures_dir / "sample.jpeg",
        # "webp": fixtures_dir / "sample.webp",
        # "bmp": fixtures_dir / "sample.bmp",
        # "heic": fixtures_dir / "sample.heic",
    }


# =============================================================================
# STREAMLIT APPTEST HELPERS
# =============================================================================

@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    """
    Clear Streamlit's cache before each test to ensure mocks are applied fresh.

    This is necessary because @st.cache_resource captures function references
    at decoration time, which can bypass mocks applied later.
    """
    try:
        import streamlit as st
        # Clear all caches to ensure fresh state for each test
        st.cache_resource.clear()
        st.cache_data.clear()
    except (ImportError, AttributeError):
        # Streamlit not available or cache methods don't exist
        pass

    yield

    # Also clear after test to prevent leakage
    try:
        import streamlit as st
        st.cache_resource.clear()
        st.cache_data.clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture
def home_page_app():
    """
    Create Streamlit AppTest instance for Home page.
    Returns None if AppTest is not available.
    """
    try:
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(PROJECT_ROOT / "Home.py"))
        return app
    except ImportError:
        pytest.skip("Streamlit AppTest not available (requires streamlit>=1.28.0)")


# =============================================================================
# GRAPHITI WORKER CLEANUP
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def cleanup_graphiti_worker():
    """
    Session-scoped fixture to properly shut down GraphitiWorker at test completion.

    This ensures all async operations complete before pytest closes the event loop,
    preventing RuntimeError: Event loop is closed warnings.

    Runs automatically for all test sessions (autouse=True).
    """
    yield  # Run all tests first

    # Cleanup after all tests complete
    try:
        from utils.graphiti_worker import GraphitiWorker

        # Get the singleton instance if it exists
        if GraphitiWorker._instance is not None:
            worker = GraphitiWorker._instance
            worker.shutdown()

            # Reset the singleton so it can be recreated if needed
            GraphitiWorker.reset_instance()
    except ImportError:
        # graphiti_worker not imported, nothing to clean up
        pass
    except Exception as e:
        # Log but don't fail tests on cleanup errors
        print(f"Warning: Error during GraphitiWorker cleanup: {e}")


# =============================================================================
# SHARED MOCK DATA FIXTURES (SPEC-043 Phase 2)
# =============================================================================

@pytest.fixture(scope="session")
def realistic_graphiti_results():
    """
    Realistic mock Graphiti knowledge graph response.

    Structure matches production API responses from knowledge_graph_search.
    Used for testing graph building and rendering without live Neo4j.

    Returns dict matching production structure used in integration tests:
    - "success": bool
    - "entities": list of entity dicts with name, entity_type, entity_id, source_docs
    - "relationships": list of relationship dicts with source, target, fact, valid_at

    REQ-013, REQ-016 (SPEC-043 Phase 2)
    """
    return {
        "success": True,
        "entities": [
            {
                "name": "Acme Corp",
                "entity_type": "Organization",
                "entity_id": "ent_1",
                "source_docs": ["doc_123", "doc_456"]
            },
            {
                "name": "John Smith",
                "entity_type": "Person",
                "entity_id": "ent_2",
                "source_docs": ["doc_123"]
            },
            {
                "name": "Product Launch",
                "entity_type": "Event",
                "entity_id": "ent_3",
                "source_docs": ["doc_456", "doc_789"]
            },
            {
                "name": "Marketing Campaign",
                "entity_type": None,  # Null type (100% of production data)
                "entity_id": "ent_4",
                "source_docs": []
            }
        ],
        "relationships": [
            {
                "relationship_id": "rel_1",
                "source": "John Smith",
                "target": "Acme Corp",
                "fact": "John Smith is CEO of Acme Corp",
                "valid_at": "2024-01-15"
            },
            {
                "relationship_id": "rel_2",
                "source": "Acme Corp",
                "target": "Product Launch",
                "fact": "Acme Corp organized Product Launch event",
                "valid_at": "2024-02-01"
            },
            {
                "relationship_id": "rel_3",
                "source": "Product Launch",
                "target": "Marketing Campaign",
                "fact": "Product Launch included Marketing Campaign",
                "valid_at": "2024-02-01"
            }
        ]
    }


@pytest.fixture(scope="session")
def realistic_search_results():
    """
    Realistic mock search API response.

    Structure matches txtai search endpoint responses.
    Used for testing result processing without live index.

    Returns dict matching production structure:
    - "success": bool
    - "data": list of search result dicts with id, text, score, data (metadata)

    REQ-014, REQ-016 (SPEC-043 Phase 2)
    """
    return {
        "success": True,
        "data": [
            {
                "id": "doc_1",
                "text": "Sample document content about machine learning",
                "score": 0.95,
                "data": {
                    "filename": "ml_intro.txt",
                    "category": "technical",
                    "uploaded_at": "2026-01-15T10:00:00Z"
                }
            },
            {
                "id": "doc_2",
                "text": "Another document discussing neural networks",
                "score": 0.87,
                "data": {
                    "filename": "neural_nets.pdf",
                    "category": "research",
                    "uploaded_at": "2026-01-16T14:30:00Z"
                }
            }
        ]
    }


@pytest.fixture(scope="session")
def sample_test_documents():
    """
    Standard set of test documents with varied content.

    Returns list of (doc_id, content, filename) tuples.
    Useful for tests that need realistic document variety.

    REQ-015, REQ-016 (SPEC-043 Phase 2)
    """
    return [
        (
            "test-doc-1",
            "Machine learning enables computers to learn from data",
            "ml_basics.txt"
        ),
        (
            "test-doc-2",
            "Python is a popular programming language for data science",
            "python_intro.txt"
        ),
        (
            "test-doc-3",
            "Natural language processing analyzes human language",
            "nlp_overview.txt"
        )
    ]

