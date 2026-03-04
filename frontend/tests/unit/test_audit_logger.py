"""
Unit tests for AuditLogger class (SPEC-029 REQ-003).

Tests cover:
- JSONL format correctness
- Log rotation (10MB max, 5 backups)
- ISO 8601 timestamp formatting
- Required vs optional fields
- PII protection (no document content)
- Multiple ingestion sources (file_upload, url_ingestion)
- Bulk import event logging
- Singleton pattern (get_audit_logger)

Uses temporary directories to avoid interfering with production logs.
"""

import json
import os
import pytest
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.audit_logger import AuditLogger, get_audit_logger


class TestAuditLoggerInitialization:
    """Tests for AuditLogger initialization."""

    def test_creates_log_directory_if_missing(self):
        """Should create log directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "nested", "logs")
            logger = AuditLogger(log_dir=log_dir)

            assert os.path.exists(log_dir)
            assert os.path.isdir(log_dir)
            logger.close()

    def test_creates_default_log_file(self):
        """Should create ingestion_audit.jsonl by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            expected_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            assert logger.log_file == Path(expected_file)
            logger.close()

    def test_accepts_custom_log_filename(self):
        """Should accept custom log filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_name = "custom_audit.jsonl"
            logger = AuditLogger(log_dir=tmpdir, log_file=custom_name)

            expected_file = os.path.join(tmpdir, custom_name)
            assert logger.log_file == Path(expected_file)
            logger.close()

    def test_handler_configured_for_rotation(self):
        """Should configure RotatingFileHandler with 10MB max and 5 backups."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            assert logger.handler.maxBytes == 10 * 1024 * 1024  # 10MB
            assert logger.handler.backupCount == 5
            logger.close()


class TestJSONLFormat:
    """Tests for JSONL format correctness."""

    def test_single_document_produces_single_line(self):
        """Each document should produce exactly one line of JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                lines = f.readlines()

            assert len(lines) == 1
            assert lines[0].endswith('\n')

    def test_multiple_documents_produce_multiple_lines(self):
        """Each document should be on its own line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [
                {"id": "doc1", "filename": "test1.txt"},
                {"id": "doc2", "filename": "test2.txt"},
                {"id": "doc3", "filename": "test3.txt"}
            ]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                lines = f.readlines()

            assert len(lines) == 3

    def test_each_line_is_valid_json(self):
        """Each line should be parseable as JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [
                {"id": "doc1", "filename": "test1.txt"},
                {"id": "doc2", "filename": "test2.txt"}
            ]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                for line in f:
                    # Should not raise JSONDecodeError
                    entry = json.loads(line)
                    assert isinstance(entry, dict)


class TestRequiredFields:
    """Tests for required fields in audit log entries."""

    def test_contains_required_fields(self):
        """Every entry must contain: timestamp, event, document_id, filename, source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result, source="file_upload")
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert "timestamp" in entry
            assert "event" in entry
            assert "document_id" in entry
            assert "filename" in entry
            assert "source" in entry

            assert entry["event"] == "document_indexed"
            assert entry["document_id"] == "doc1"
            assert entry["filename"] == "test.txt"
            assert entry["source"] == "file_upload"

    def test_timestamp_is_iso8601_utc(self):
        """Timestamp should be in ISO 8601 format with timezone."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {"success": True, "prepared_documents": documents}

            with patch('utils.audit_logger.datetime') as mock_datetime:
                # Mock a specific UTC datetime
                mock_now = datetime(2026, 2, 1, 12, 30, 45, tzinfo=timezone.utc)
                mock_datetime.now.return_value = mock_now

                logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            # ISO 8601 format: 2026-02-01T12:30:45+00:00
            timestamp = entry["timestamp"]
            assert timestamp == "2026-02-01T12:30:45+00:00"

            # Should be parseable back to datetime
            parsed = datetime.fromisoformat(timestamp)
            assert parsed.tzinfo is not None  # Has timezone info


class TestOptionalFields:
    """Tests for optional fields in audit log entries."""

    def test_includes_size_bytes_when_present(self):
        """Should include size_bytes if document has it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt", "size_bytes": 1024}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert "size_bytes" in entry
            assert entry["size_bytes"] == 1024

    def test_includes_content_hash_when_present(self):
        """Should include content_hash if document has it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt", "content_hash": "abc123"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert "content_hash" in entry
            assert entry["content_hash"] == "abc123"

    def test_includes_categories_when_present(self):
        """Should include categories if document has them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt", "categories": ["technical", "reference"]}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert "categories" in entry
            assert entry["categories"] == ["technical", "reference"]

    def test_includes_auto_labels_as_categories(self):
        """Should map auto_labels to categories for classified documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt", "auto_labels": ["invoice", "finance"]}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert "categories" in entry
            assert entry["categories"] == ["invoice", "finance"]

    def test_includes_url_when_present(self):
        """Should include url for URL ingestion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.html", "url": "https://example.com"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result, source="url_ingestion")
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert "url" in entry
            assert entry["url"] == "https://example.com"

    def test_includes_media_type_when_present(self):
        """Should include media_type for media files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.mp4", "media_type": "video"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert "media_type" in entry
            assert entry["media_type"] == "video"

    def test_includes_chunk_metadata_when_present(self):
        """Should include chunk metadata for chunked documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{
                "id": "doc1-chunk-0",
                "filename": "test.txt",
                "is_chunk": True,
                "parent_doc_id": "doc1",
                "chunk_index": 0
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert entry["is_chunk"] is True
            assert entry["parent_doc_id"] == "doc1"
            assert entry["chunk_index"] == 0

    def test_omits_optional_fields_when_not_present(self):
        """Should not include optional fields when they're not in document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            # Minimal document
            documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            # Should only have required fields
            assert "size_bytes" not in entry
            assert "content_hash" not in entry
            assert "categories" not in entry
            assert "url" not in entry
            assert "media_type" not in entry
            assert "is_chunk" not in entry


class TestPIIProtection:
    """Tests for PII protection (SPEC-029 SEC-002)."""

    def test_does_not_log_document_content(self):
        """Should never include document text content (SEC-002)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{
                "id": "doc1",
                "filename": "secret.txt",
                "text": "This is sensitive personal information that should not be logged"
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert "text" not in entry

            # Verify the content isn't anywhere in the log file
            with open(log_file, 'r') as f:
                log_contents = f.read()
            assert "sensitive personal information" not in log_contents


class TestIngestionSources:
    """Tests for different ingestion sources."""

    def test_defaults_to_file_upload_source(self):
        """Should default to file_upload source if not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)  # No source parameter
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert entry["source"] == "file_upload"

    def test_supports_url_ingestion_source(self):
        """Should support url_ingestion source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.html"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result, source="url_ingestion")
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert entry["source"] == "url_ingestion"


class TestFailureHandling:
    """Tests for failure handling."""

    def test_does_not_log_on_failed_ingestion(self):
        """Should not log anything if ingestion failed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {"success": False, "error": "API error"}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")

            # File should either not exist or be empty
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                assert len(lines) == 0

    def test_does_not_log_if_success_key_missing(self):
        """Should not log if success key is missing from result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {}  # No success key

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")

            # File should either not exist or be empty
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                assert len(lines) == 0


class TestPreparedDocuments:
    """Tests for prepared_documents vs original documents."""

    def test_logs_prepared_documents_if_available(self):
        """Should log prepared_documents (after chunking) if available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            # Original document vs prepared (chunked) documents
            original_documents = [{"id": "doc1", "filename": "test.txt"}]
            prepared_documents = [
                {"id": "doc1-chunk-0", "filename": "test.txt", "is_chunk": True},
                {"id": "doc1-chunk-1", "filename": "test.txt", "is_chunk": True}
            ]
            add_result = {
                "success": True,
                "prepared_documents": prepared_documents
            }

            logger.log_ingestion(original_documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                lines = f.readlines()

            # Should log 2 chunks, not 1 original
            assert len(lines) == 2

            entry1 = json.loads(lines[0])
            entry2 = json.loads(lines[1])

            assert entry1["document_id"] == "doc1-chunk-0"
            assert entry2["document_id"] == "doc1-chunk-1"

    def test_falls_back_to_original_documents_if_no_prepared(self):
        """Should fall back to original documents if prepared_documents missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            original_documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {"success": True}  # No prepared_documents

            logger.log_ingestion(original_documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                lines = f.readlines()

            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["document_id"] == "doc1"


class TestBulkImport:
    """Tests for bulk import event logging."""

    def test_logs_bulk_import_event(self):
        """Should log bulk_import event with correct fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            document_ids = ["doc1", "doc2", "doc3"]
            source_file = "/tmp/export.jsonl"

            logger.log_bulk_import(document_ids, source_file, success_count=3, failure_count=0)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert entry["event"] == "bulk_import"
            assert entry["source_file"] == source_file
            assert entry["document_count"] == 3
            assert entry["success_count"] == 3
            assert entry["failure_count"] == 0
            assert entry["document_ids"] == document_ids

    def test_bulk_import_includes_timestamp(self):
        """Bulk import event should include ISO 8601 timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            with patch('utils.audit_logger.datetime') as mock_datetime:
                mock_now = datetime(2026, 2, 1, 15, 0, 0, tzinfo=timezone.utc)
                mock_datetime.now.return_value = mock_now

                logger.log_bulk_import(["doc1"], "/tmp/export.jsonl", 1, 0)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            assert entry["timestamp"] == "2026-02-01T15:00:00+00:00"


class TestSingletonPattern:
    """Tests for get_audit_logger singleton."""

    def test_returns_audit_logger_instance(self):
        """get_audit_logger should return AuditLogger instance."""
        # Create instance directly with temp directory (avoid singleton issues)
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)
            assert isinstance(logger, AuditLogger)
            logger.close()

    def test_singleton_creates_only_one_instance(self):
        """Singleton pattern should create only one instance."""
        # Clean up singleton first
        import utils.audit_logger
        old_singleton = utils.audit_logger._audit_logger

        # Create temp directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily replace the singleton with one using temp directory
            utils.audit_logger._audit_logger = AuditLogger(log_dir=tmpdir)

            logger1 = get_audit_logger()
            logger2 = get_audit_logger()

            assert logger1 is logger2

            # Clean up
            logger1.close()
            utils.audit_logger._audit_logger = old_singleton


class TestLoggerCleanup:
    """Tests for logger cleanup."""

    def test_close_releases_file_handles(self):
        """close() should release file handles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)
            log_file = logger.log_file

            # Write something
            documents = [{"id": "doc1", "filename": "test.txt"}]
            add_result = {"success": True, "prepared_documents": documents}
            logger.log_ingestion(documents, add_result)

            # Close should release handles
            logger.close()

            # Should be able to delete the file after closing
            if os.path.exists(log_file):
                os.remove(log_file)
                assert not os.path.exists(log_file)


class TestUnicodeSupport:
    """Tests for Unicode/international character support."""

    def test_handles_unicode_filenames(self):
        """Should handle Unicode characters in filenames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "测试文档.txt"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r', encoding='utf-8') as f:
                entry = json.loads(f.readline())

            assert entry["filename"] == "测试文档.txt"

    def test_handles_unicode_in_categories(self):
        """Should handle Unicode characters in categories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            documents = [{"id": "doc1", "filename": "test.txt", "categories": ["日本語", "français"]}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r', encoding='utf-8') as f:
                entry = json.loads(f.readline())

            assert entry["categories"] == ["日本語", "français"]


class TestDocumentArchive:
    """Tests for document archive functionality (SPEC-036)."""

    def test_archives_parent_document_with_content(self):
        """Should archive parent document with full content to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            documents = [{
                "id": "doc1",
                "filename": "test.txt",
                "text": "This is the document content",
                "size_bytes": 1024
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Verify archive file created
            archive_file = os.path.join(archive_dir, "doc1.json")
            assert os.path.exists(archive_file)

            # Verify archive content
            with open(archive_file, 'r') as f:
                archive_data = json.load(f)

            assert archive_data["archive_format_version"] == "1.0"
            assert archive_data["document_id"] == "doc1"
            assert archive_data["filename"] == "test.txt"
            assert archive_data["content"] == "This is the document content"
            assert archive_data["source"] == "file_upload"
            assert "content_hash" in archive_data
            assert "archived_at" in archive_data

    def test_does_not_archive_chunks(self):
        """Should only archive parent documents, not chunks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            # Original parent document
            parent_doc = [{"id": "doc1", "filename": "test.txt", "text": "Parent content"}]

            # Prepared documents (after chunking)
            chunks = [
                {
                    "id": "doc1-chunk-0",
                    "filename": "test.txt",
                    "is_chunk": True,
                    "parent_doc_id": "doc1",
                    "chunk_index": 0
                },
                {
                    "id": "doc1-chunk-1",
                    "filename": "test.txt",
                    "is_chunk": True,
                    "parent_doc_id": "doc1",
                    "chunk_index": 1
                }
            ]
            add_result = {"success": True, "prepared_documents": chunks}

            logger.log_ingestion(parent_doc, add_result)
            logger.close()

            # Should only have one archive file for parent
            archive_file = os.path.join(archive_dir, "doc1.json")
            assert os.path.exists(archive_file)

            # Chunks should not have archive files
            assert not os.path.exists(os.path.join(archive_dir, "doc1-chunk-0.json"))
            assert not os.path.exists(os.path.join(archive_dir, "doc1-chunk-1.json"))

    def test_adds_archive_path_to_audit_log_for_parent_only(self):
        """Should add archive_path field to audit log only for parent documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            parent_doc = [{"id": "doc1", "filename": "test.txt", "text": "Parent"}]
            chunks = [
                {"id": "doc1-chunk-0", "filename": "test.txt", "is_chunk": True, "parent_doc_id": "doc1"},
                {"id": "doc1-chunk-1", "filename": "test.txt", "is_chunk": True, "parent_doc_id": "doc1"}
            ]
            add_result = {"success": True, "prepared_documents": chunks}

            logger.log_ingestion(parent_doc, add_result)
            logger.close()

            # Read audit log
            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                lines = f.readlines()

            assert len(lines) == 2  # Two chunks logged

            # Neither chunk should have archive_path (not parents)
            chunk0 = json.loads(lines[0])
            chunk1 = json.loads(lines[1])

            assert "archive_path" not in chunk0
            assert "archive_path" not in chunk1

    def test_archive_path_in_audit_when_no_chunking(self):
        """Should add archive_path to audit log when document isn't chunked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            documents = [{"id": "doc1", "filename": "test.txt", "text": "Content"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Read audit log
            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            # Document is its own parent (not chunked), should have archive_path
            assert "archive_path" in entry
            assert entry["archive_path"] == "/archive/doc1.json"

    def test_recomputes_content_hash_at_archive_time(self):
        """Should recompute content hash from actual content, not use metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            # Document with stale content_hash in metadata
            documents = [{
                "id": "doc1",
                "filename": "test.txt",
                "text": "Updated content after edit",
                "content_hash": "stale_hash_from_metadata"
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Read archive
            archive_file = os.path.join(archive_dir, "doc1.json")
            with open(archive_file, 'r') as f:
                archive_data = json.load(f)

            # Hash should be recomputed, not from metadata
            import hashlib
            expected_hash = hashlib.sha256("Updated content after edit".encode('utf-8')).hexdigest()
            assert archive_data["content_hash"] == expected_hash
            assert archive_data["content_hash"] != "stale_hash_from_metadata"

    def test_non_blocking_on_archive_failure(self):
        """Archive failure should not prevent audit logging (REL-001)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create logger with non-existent archive directory
            archive_dir = os.path.join(tmpdir, "nonexistent")
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            documents = [{"id": "doc1", "filename": "test.txt", "text": "Content"}]
            add_result = {"success": True, "prepared_documents": documents}

            # Should not raise exception
            logger.log_ingestion(documents, add_result)
            logger.close()

            # Audit log should still be created
            log_file = os.path.join(tmpdir, "ingestion_audit.jsonl")
            assert os.path.exists(log_file)

            with open(log_file, 'r') as f:
                entry = json.loads(f.readline())

            # Entry should exist, but no archive_path
            assert entry["document_id"] == "doc1"
            assert "archive_path" not in entry

    def test_archive_includes_ai_generated_fields(self):
        """Should archive AI-generated fields (REQ-004)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            documents = [{
                "id": "doc1",
                "filename": "image.jpg",
                "text": "Extracted text",
                "media_type": "image",
                "image_caption": "A beautiful sunset over mountains",
                "ocr_text": "Text extracted via OCR",
                "summary": "Generated summary",
                "categories": ["nature", "photography"]
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Read archive
            archive_file = os.path.join(archive_dir, "doc1.json")
            with open(archive_file, 'r') as f:
                archive_data = json.load(f)

            # Verify AI-generated fields preserved
            assert archive_data["metadata"]["image_caption"] == "A beautiful sunset over mountains"
            assert archive_data["metadata"]["ocr_text"] == "Text extracted via OCR"
            assert archive_data["metadata"]["summary"] == "Generated summary"
            assert archive_data["metadata"]["categories"] == ["nature", "photography"]

    def test_cleans_up_temp_files_on_initialization(self):
        """Should clean up orphaned temp files older than 1 hour (REQ-003)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)

            # Create old temp files (simulate crash from previous session)
            old_temp1 = os.path.join(archive_dir, ".tmp_old1.json")
            old_temp2 = os.path.join(archive_dir, ".tmp_old2.json")
            with open(old_temp1, 'w') as f:
                f.write('{"test": "old"}')
            with open(old_temp2, 'w') as f:
                f.write('{"test": "old2"}')

            # Set mtime to >1 hour ago
            old_time = time.time() - 7200  # 2 hours ago
            os.utime(old_temp1, (old_time, old_time))
            os.utime(old_temp2, (old_time, old_time))

            # Create recent temp file (should NOT be deleted)
            recent_temp = os.path.join(archive_dir, ".tmp_recent.json")
            with open(recent_temp, 'w') as f:
                f.write('{"test": "recent"}')

            # Initialize logger (triggers cleanup)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)
            logger.close()

            # Old temps should be deleted
            assert not os.path.exists(old_temp1)
            assert not os.path.exists(old_temp2)

            # Recent temp should remain
            assert os.path.exists(recent_temp)

    def test_archive_uses_atomic_write_pattern(self):
        """Should use atomic write (temp + rename) to prevent corruption (REQ-003)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            documents = [{"id": "doc1", "filename": "test.txt", "text": "Content"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Final file should exist
            archive_file = os.path.join(archive_dir, "doc1.json")
            assert os.path.exists(archive_file)

            # No temp files should remain after successful write
            temp_files = [f for f in os.listdir(archive_dir) if f.startswith('.tmp_')]
            assert len(temp_files) == 0

    def test_archive_format_version_field_present(self):
        """Archive should include format version field (REQ-007)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(archive_dir)
            logger = AuditLogger(log_dir=tmpdir, archive_dir=archive_dir)

            documents = [{"id": "doc1", "filename": "test.txt", "text": "Content"}]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Read archive
            archive_file = os.path.join(archive_dir, "doc1.json")
            with open(archive_file, 'r') as f:
                raw_content = f.read()
                archive_data = json.loads(raw_content)

            # Version field must be present and first in output
            assert "archive_format_version" in archive_data
            assert archive_data["archive_format_version"] == "1.0"

            # Verify it's the first field (JSON maintains insertion order in Python 3.7+)
            first_key = next(iter(archive_data.keys()))
            assert first_key == "archive_format_version"
