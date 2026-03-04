"""
Unit tests for ingestion_lock module.

Tests cover:
- write_ingestion_lock: happy path, permission error, directory missing
- remove_ingestion_lock: happy path, already removed, other OS error
- Content format: pid and started fields present and parseable
- Non-blocking contract: all exceptions are silently swallowed
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import utils.ingestion_lock as lock_module
from utils.ingestion_lock import write_ingestion_lock, remove_ingestion_lock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_lock(path: str) -> dict:
    """Parse lock file content into a dict of key=value pairs."""
    result = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                result[k] = v
    return result


# ---------------------------------------------------------------------------
# write_ingestion_lock
# ---------------------------------------------------------------------------

class TestWriteIngestionLock:

    def test_creates_lock_file(self, tmp_path):
        """Happy path: lock file is created at the configured path."""
        lock_path = str(tmp_path / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            write_ingestion_lock()
        assert os.path.exists(lock_path)

    def test_lock_file_contains_pid(self, tmp_path):
        """Lock file must contain pid= field matching the current process."""
        lock_path = str(tmp_path / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            write_ingestion_lock()
        data = _read_lock(lock_path)
        assert 'pid' in data
        assert int(data['pid']) == os.getpid()

    def test_lock_file_contains_started_timestamp(self, tmp_path):
        """Lock file must contain started= field as a Unix epoch integer."""
        lock_path = str(tmp_path / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            write_ingestion_lock()
        data = _read_lock(lock_path)
        assert 'started' in data
        started = int(data['started'])
        # Sanity check: epoch is in a plausible range (after 2020, before 2100)
        assert 1_577_836_800 < started < 4_102_444_800

    def test_permission_error_is_silent(self, tmp_path):
        """PermissionError on open must not propagate — non-blocking contract."""
        lock_path = str(tmp_path / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            with patch('builtins.open', side_effect=PermissionError("read-only")):
                write_ingestion_lock()  # must not raise

    def test_directory_missing_is_silent(self, tmp_path):
        """FileNotFoundError (missing directory) must not propagate."""
        lock_path = str(tmp_path / "nonexistent_dir" / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            write_ingestion_lock()  # must not raise

    def test_generic_os_error_is_silent(self):
        """Any unexpected OSError must not propagate."""
        with patch('builtins.open', side_effect=OSError("disk full")):
            write_ingestion_lock()  # must not raise

    def test_overwrites_existing_lock(self, tmp_path):
        """Writing a second lock over an existing one succeeds (last write wins)."""
        lock_path = str(tmp_path / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            write_ingestion_lock()
            first_mtime = os.path.getmtime(lock_path)
            write_ingestion_lock()
            second_mtime = os.path.getmtime(lock_path)
        # File still exists and is readable
        data = _read_lock(lock_path)
        assert 'pid' in data


# ---------------------------------------------------------------------------
# remove_ingestion_lock
# ---------------------------------------------------------------------------

class TestRemoveIngestionLock:

    def test_removes_existing_lock_file(self, tmp_path):
        """Happy path: existing lock file is deleted."""
        lock_path = str(tmp_path / ".ingestion.lock")
        lock_path_obj = Path(lock_path)
        lock_path_obj.write_text("pid=1\nstarted=1000\n")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            remove_ingestion_lock()
        assert not os.path.exists(lock_path)

    def test_file_not_found_is_silent(self, tmp_path):
        """FileNotFoundError (already removed) must not propagate."""
        lock_path = str(tmp_path / ".ingestion.lock")
        # File does not exist
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            remove_ingestion_lock()  # must not raise

    def test_permission_error_is_silent(self, tmp_path):
        """PermissionError on remove must not propagate — non-blocking contract."""
        lock_path = str(tmp_path / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            with patch('os.remove', side_effect=PermissionError("read-only fs")):
                remove_ingestion_lock()  # must not raise

    def test_generic_os_error_is_silent(self):
        """Any unexpected OSError on remove must not propagate."""
        with patch('os.remove', side_effect=OSError("device busy")):
            remove_ingestion_lock()  # must not raise


# ---------------------------------------------------------------------------
# Write → remove round-trip
# ---------------------------------------------------------------------------

class TestLockRoundTrip:

    def test_write_then_remove_leaves_no_file(self, tmp_path):
        """Full round-trip: lock file exists after write and is gone after remove."""
        lock_path = str(tmp_path / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            write_ingestion_lock()
            assert os.path.exists(lock_path)
            remove_ingestion_lock()
            assert not os.path.exists(lock_path)

    def test_remove_after_failed_write_is_safe(self, tmp_path):
        """If write silently fails, remove is still safe (file never existed)."""
        lock_path = str(tmp_path / ".ingestion.lock")
        with patch.object(lock_module, 'INGESTION_LOCK_FILE', lock_path):
            with patch('builtins.open', side_effect=PermissionError):
                write_ingestion_lock()  # silently fails
            remove_ingestion_lock()  # must not raise; file doesn't exist
        assert not os.path.exists(lock_path)
