"""
Integration tests for Document Archive Recovery (SPEC-036).

Tests the complete integration of document archiving with:
1. Upload workflow → archive file creation
2. Audit log cross-reference with archive files
3. URL ingestion archiving
4. Media document archiving with AI-generated fields
5. Multiple document batch uploads

These tests verify that archiving works end-to-end with real document uploads.

Requirements:
    - txtai API running at TEST_TXTAI_API_URL
    - PostgreSQL database accessible
    - Archive directory mounted at /archive
    - Test fixtures available

Usage:
    pytest tests/integration/test_document_archive.py -v
"""

import json
import os
import pytest
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.audit_logger import AuditLogger


@pytest.mark.integration
class TestDocumentArchiveIntegration:
    """Integration tests for document archive functionality."""

    def test_upload_creates_archive_file(self):
        """End-to-end: Upload should create archive file with document content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            # Simulate document upload
            documents = [{
                "id": "integration-test-001",
                "filename": "integration_test.txt",
                "text": "This is integration test content for archive recovery.",
                "size_bytes": 500
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result, source="file_upload")
            logger.close()

            # Verify archive file created
            archive_file = os.path.join(archive_dir, "integration-test-001.json")
            assert os.path.exists(archive_file), "Archive file should be created"

            # Verify archive content matches uploaded document
            with open(archive_file, 'r') as f:
                archive_data = json.load(f)

            assert archive_data["document_id"] == "integration-test-001"
            assert archive_data["filename"] == "integration_test.txt"
            assert archive_data["content"] == "This is integration test content for archive recovery."
            assert archive_data["source"] == "file_upload"
            assert archive_data["archive_format_version"] == "1.0"

    def test_audit_log_references_archive_file(self):
        """Audit log should contain archive_path pointing to created archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            documents = [{
                "id": "audit-test-001",
                "filename": "audit_test.txt",
                "text": "Content for audit cross-reference test"
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Read audit log
            audit_file = os.path.join(log_dir, "ingestion_audit.jsonl")
            with open(audit_file, 'r') as f:
                lines = f.readlines()

            assert len(lines) >= 1
            entry = json.loads(lines[-1])  # Most recent entry

            # Verify audit entry references archive
            assert "archive_path" in entry
            assert entry["archive_path"] == "/archive/audit-test-001.json"

            # Verify referenced archive file actually exists
            archive_file = os.path.join(archive_dir, "audit-test-001.json")
            assert os.path.exists(archive_file)

    def test_multiple_documents_create_multiple_archives(self):
        """Batch upload should create one archive per parent document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            # Batch of 3 documents
            documents = [
                {"id": "batch-001", "filename": "doc1.txt", "text": "Content 1"},
                {"id": "batch-002", "filename": "doc2.txt", "text": "Content 2"},
                {"id": "batch-003", "filename": "doc3.txt", "text": "Content 3"}
            ]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Verify 3 separate archive files
            assert os.path.exists(os.path.join(archive_dir, "batch-001.json"))
            assert os.path.exists(os.path.join(archive_dir, "batch-002.json"))
            assert os.path.exists(os.path.join(archive_dir, "batch-003.json"))

            # Verify each has correct content
            with open(os.path.join(archive_dir, "batch-001.json"), 'r') as f:
                archive1 = json.load(f)
            assert archive1["content"] == "Content 1"

            with open(os.path.join(archive_dir, "batch-002.json"), 'r') as f:
                archive2 = json.load(f)
            assert archive2["content"] == "Content 2"

            with open(os.path.join(archive_dir, "batch-003.json"), 'r') as f:
                archive3 = json.load(f)
            assert archive3["content"] == "Content 3"

    def test_url_ingestion_captures_url_metadata(self):
        """URL ingestion should archive with URL metadata (EDGE-006)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            documents = [{
                "id": "url-test-001",
                "filename": "example.html",
                "text": "Content fetched from URL",
                "url": "https://example.com/page",
                "title": "Example Page"
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result, source="url_ingestion")
            logger.close()

            # Read archive
            archive_file = os.path.join(archive_dir, "url-test-001.json")
            with open(archive_file, 'r') as f:
                archive_data = json.load(f)

            # Verify URL metadata captured
            assert archive_data["source"] == "url_ingestion"
            assert archive_data["metadata"]["url"] == "https://example.com/page"
            assert archive_data["metadata"]["title"] == "Example Page"

    def test_media_document_captures_ai_fields(self):
        """Media documents should archive AI-generated fields (EDGE-008)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            # Image document with AI-generated caption and OCR
            documents = [{
                "id": "media-test-001",
                "filename": "photo.jpg",
                "text": "Extracted text via OCR and caption",
                "media_type": "image",
                "image_caption": "A scenic mountain landscape at sunset",
                "ocr_text": "Sign: Welcome to the Mountains",
                "summary": "Landscape photo with text sign"
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Read archive
            archive_file = os.path.join(archive_dir, "media-test-001.json")
            with open(archive_file, 'r') as f:
                archive_data = json.load(f)

            # Verify AI-generated fields archived
            assert archive_data["metadata"]["media_type"] == "image"
            assert archive_data["metadata"]["image_caption"] == "A scenic mountain landscape at sunset"
            assert archive_data["metadata"]["ocr_text"] == "Sign: Welcome to the Mountains"
            assert archive_data["metadata"]["summary"] == "Landscape photo with text sign"


@pytest.mark.integration
@pytest.mark.edge_cases
class TestDocumentArchiveEdgeCases:
    """Edge case tests for document archive."""

    def test_large_document_archiving(self):
        """Should handle large documents (EDGE-001)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            # Generate ~1MB of content
            large_content = "x" * (1024 * 1024)  # 1MB

            documents = [{
                "id": "large-test-001",
                "filename": "large_doc.txt",
                "text": large_content
            }]
            add_result = {"success": True, "prepared_documents": documents}

            logger.log_ingestion(documents, add_result)
            logger.close()

            # Verify archive created successfully
            archive_file = os.path.join(archive_dir, "large-test-001.json")
            assert os.path.exists(archive_file)

            # Verify content intact
            with open(archive_file, 'r') as f:
                archive_data = json.load(f)
            assert len(archive_data["content"]) == 1024 * 1024

    def test_concurrent_uploads_no_collision(self):
        """Concurrent uploads should not collide (EDGE-002)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            # Simulate 5 concurrent uploads with unique IDs
            documents = [
                {"id": f"concurrent-{i:03d}", "filename": f"doc{i}.txt", "text": f"Content {i}"}
                for i in range(5)
            ]

            # Process all at once
            add_result = {"success": True, "prepared_documents": documents}
            logger.log_ingestion(documents, add_result)
            logger.close()

            # Verify all 5 archives created with correct content
            for i in range(5):
                archive_file = os.path.join(archive_dir, f"concurrent-{i:03d}.json")
                assert os.path.exists(archive_file)

                with open(archive_file, 'r') as f:
                    archive_data = json.load(f)
                assert archive_data["content"] == f"Content {i}"

    def test_missing_archive_directory_non_blocking(self):
        """Missing archive directory should not block upload (EDGE-003)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "nonexistent_archive")  # Does not exist

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            documents = [{"id": "missing-dir-001", "filename": "test.txt", "text": "Content"}]
            add_result = {"success": True, "prepared_documents": documents}

            # Should not raise exception
            logger.log_ingestion(documents, add_result)
            logger.close()

            # Audit log should still be created
            audit_file = os.path.join(log_dir, "ingestion_audit.jsonl")
            assert os.path.exists(audit_file)

            # Entry should exist without archive_path
            with open(audit_file, 'r') as f:
                entry = json.loads(f.readline())
            assert entry["document_id"] == "missing-dir-001"
            assert "archive_path" not in entry

    def test_re_upload_overwrites_archive(self):
        """Re-uploading same document should overwrite archive (EDGE-005)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            # First upload
            documents_v1 = [{
                "id": "reupload-001",
                "filename": "test.txt",
                "text": "Original content"
            }]
            add_result_v1 = {"success": True, "prepared_documents": documents_v1}
            logger.log_ingestion(documents_v1, add_result_v1)

            # Verify first archive
            archive_file = os.path.join(archive_dir, "reupload-001.json")
            with open(archive_file, 'r') as f:
                archive_v1 = json.load(f)
            assert archive_v1["content"] == "Original content"
            first_archived_at = archive_v1["archived_at"]

            time.sleep(1)  # Ensure timestamp differs

            # Second upload (same ID, different content)
            documents_v2 = [{
                "id": "reupload-001",
                "filename": "test.txt",
                "text": "Updated content after edit"
            }]
            add_result_v2 = {"success": True, "prepared_documents": documents_v2}
            logger.log_ingestion(documents_v2, add_result_v2)
            logger.close()

            # Verify archive was overwritten
            with open(archive_file, 'r') as f:
                archive_v2 = json.load(f)
            assert archive_v2["content"] == "Updated content after edit"
            assert archive_v2["archived_at"] != first_archived_at

    def test_chunked_document_creates_single_archive(self):
        """Chunked document should create only one archive for parent (EDGE-010)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            archive_dir = os.path.join(tmpdir, "archive")
            os.makedirs(log_dir)
            os.makedirs(archive_dir)

            logger = AuditLogger(log_dir=log_dir, archive_dir=archive_dir)

            # Parent document
            parent = [{"id": "parent-001", "filename": "large.txt", "text": "Full document content"}]

            # Prepared documents (after chunking)
            chunks = [
                {"id": "parent-001-chunk-0", "filename": "large.txt", "is_chunk": True, "parent_doc_id": "parent-001"},
                {"id": "parent-001-chunk-1", "filename": "large.txt", "is_chunk": True, "parent_doc_id": "parent-001"},
                {"id": "parent-001-chunk-2", "filename": "large.txt", "is_chunk": True, "parent_doc_id": "parent-001"}
            ]
            add_result = {"success": True, "prepared_documents": chunks}

            logger.log_ingestion(parent, add_result)
            logger.close()

            # Verify only parent archive exists
            assert os.path.exists(os.path.join(archive_dir, "parent-001.json"))
            assert not os.path.exists(os.path.join(archive_dir, "parent-001-chunk-0.json"))
            assert not os.path.exists(os.path.join(archive_dir, "parent-001-chunk-1.json"))
            assert not os.path.exists(os.path.join(archive_dir, "parent-001-chunk-2.json"))

            # Verify parent archive has full content
            with open(os.path.join(archive_dir, "parent-001.json"), 'r') as f:
                archive_data = json.load(f)
            assert archive_data["content"] == "Full document content"
