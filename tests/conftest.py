"""
Backend test configuration with environment verification.

Prevents test pollution of production audit logs by enforcing test isolation.
"""

import os
import pytest
import tempfile
from pathlib import Path


# Test audit log should use temp directory
TEST_AUDIT_LOG_DIR = None  # Will be set by fixture


@pytest.fixture(scope="session", autouse=True)
def verify_test_environment():
    """
    SAFETY CHECK: Ensure tests don't pollute production audit logs.

    Sets up isolated test audit log directory and verifies environment.
    """
    global TEST_AUDIT_LOG_DIR

    # Create temporary directory for test audit logs
    TEST_AUDIT_LOG_DIR = tempfile.mkdtemp(prefix="txtai_test_audit_")

    # Set environment variable for scripts to use
    os.environ['TEST_AUDIT_LOG_DIR'] = TEST_AUDIT_LOG_DIR

    # Verify we're not pointing at production
    project_root = Path(__file__).parent.parent
    production_audit = project_root / "audit.jsonl"

    # Warning if production audit.jsonl exists (shouldn't for clean tests)
    if production_audit.exists():
        pytest.fail(
            f"Production audit.jsonl found at {production_audit}.\n"
            "Tests should not write to production audit log.\n"
            "Please remove it before running tests."
        )

    yield TEST_AUDIT_LOG_DIR

    # Cleanup: Remove test audit directory
    import shutil
    shutil.rmtree(TEST_AUDIT_LOG_DIR, ignore_errors=True)


@pytest.fixture
def test_audit_log_dir():
    """Provide test audit log directory to individual tests."""
    return TEST_AUDIT_LOG_DIR
