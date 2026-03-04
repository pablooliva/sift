"""
Audit logger for document ingestion tracking.

SPEC-029 REQ-003: Records all document ingestion events to independent JSONL log.

Features:
- JSONL format (one JSON object per line)
- Automatic log rotation (10MB max, 5 backups)
- ISO 8601 timestamp formatting
- PII protection (no document content logged)
- Independent storage (survives database corruption)

Location: /logs/ingestion_audit.jsonl (Docker: ./logs/frontend/ingestion_audit.jsonl on host)
"""

import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st


class AuditLogger:
    """
    Audit logger for document ingestion events.

    Logs all document additions to independent JSONL file for audit trail.
    Separate from database to survive corruption/restore scenarios.
    """

    def __init__(self, log_dir: str = "/logs", log_file: str = "ingestion_audit.jsonl", archive_dir: str = "/archive"):
        """
        Initialize audit logger.

        Args:
            log_dir: Directory for log files (default: /logs - Docker mount point)
            log_file: Log filename (default: ingestion_audit.jsonl)
            archive_dir: Directory for document archives (default: /archive - Docker mount point)
        """
        self.log_dir = Path(log_dir)
        self.log_file = self.log_dir / log_file
        self.archive_dir = Path(archive_dir)

        # Create log directory if it doesn't exist
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # SPEC-036 REQ-003: Clean up orphaned temp files from previous crashes
        # Delete .tmp_* files older than 1 hour in archive directory
        self._cleanup_temp_files()

        # Set up rotating file handler (10MB max, 5 backups)
        # SEC-001: Audit logs have 644 permissions (user rw, group/other r for debugging)
        self.handler = RotatingFileHandler(
            self.log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )

        # Use Python's logging module but with custom formatting
        self.logger = logging.getLogger('audit.ingestion')
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()  # Remove any existing handlers

        # Custom formatter: JSONL format (no timestamp prefix, just raw JSON)
        formatter = logging.Formatter('%(message)s')
        self.handler.setFormatter(formatter)
        self.logger.addHandler(self.handler)

        # Don't propagate to root logger (avoid duplicate logs)
        self.logger.propagate = False

    def _cleanup_temp_files(self) -> None:
        """
        Clean up orphaned temporary archive files from previous crashes.

        SPEC-036 REQ-003: Delete .tmp_* files older than 1 hour to prevent disk leaks.
        """
        try:
            if not self.archive_dir.exists():
                return

            current_time = time.time()
            one_hour_ago = current_time - 3600  # 1 hour in seconds

            for temp_file in self.archive_dir.glob('.tmp_*'):
                try:
                    # Check file age via mtime (modification time)
                    file_age = temp_file.stat().st_mtime
                    if file_age < one_hour_ago:
                        temp_file.unlink()
                except Exception as e:
                    # Non-blocking: cleanup failures are logged but don't stop initialization
                    pass
        except Exception:
            # Non-blocking: archive directory issues don't stop audit logger initialization
            pass

    def _archive_document(self, doc: Dict[str, Any], source: str) -> Optional[str]:
        """
        Archive document content + metadata to independent JSON file.

        SPEC-036 REQ-001, REQ-003, REQ-005, REQ-007: Archive parent documents with
        atomic write pattern and fresh content hash.

        Args:
            doc: Document dict (must be a parent, not a chunk)
            source: Ingestion source ("file_upload" or "url_ingestion")

        Returns:
            Archive path (container path) on success, None on failure
        """
        try:
            # Verify archive directory exists and is writable
            if not self.archive_dir.exists() or not os.access(self.archive_dir, os.W_OK):
                st.warning("⚠️ Archive directory not accessible - archive skipped")
                return None

            document_id = doc.get('id')
            if not document_id:
                return None

            # REQ-005: Recompute content hash from actual content (don't trust metadata)
            content = doc.get('text', '')
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

            # REQ-007: Build archive JSON with strict schema
            archive_data = {
                # Version field first for easy format detection
                "archive_format_version": "1.0",
                "document_id": document_id,
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "filename": doc.get('filename', ''),
                "source": source,
                "content_hash": content_hash,
                "content": content,
                "metadata": {
                    # Required metadata fields
                    "indexed_at": doc.get('indexed_at'),
                    "size_bytes": doc.get('size_bytes'),
                    "type": doc.get('type'),
                    "title": doc.get('title'),
                    "edited": doc.get('edited', False),
                    # Optional metadata fields (REQ-004: AI-generated fields)
                    "categories": doc.get('categories'),
                    "auto_labels": doc.get('auto_labels'),
                    "classification_model": doc.get('classification_model'),
                    "summary": doc.get('summary'),
                    "url": doc.get('url'),
                    "media_type": doc.get('media_type'),
                    "image_caption": doc.get('image_caption'),
                    "ocr_text": doc.get('ocr_text'),
                    "transcription": doc.get('transcription'),
                }
            }

            # REQ-003: Atomic write pattern (temp file + rename)
            final_path = self.archive_dir / f"{document_id}.json"

            # Create temp file in same directory (required for atomic rename)
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=self.archive_dir,
                prefix='.tmp_',
                suffix='.json',
                delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                # REQ-007: Human-readable JSON with UTF-8 encoding
                json.dump(archive_data, temp_file, ensure_ascii=False, indent=2)
                temp_file.flush()
                os.fsync(temp_file.fileno())  # Ensure data is on disk

            # Atomic rename (overwrites existing file if re-upload)
            os.rename(temp_path, final_path)

            # BUGFIX: Set readable permissions (0o644 = rw-r--r--)
            # Allows non-root users to read archive files via VS Code, etc.
            try:
                os.chmod(final_path, 0o644)
            except Exception:
                pass  # Non-blocking: permission failure doesn't stop archiving

            # Return container path for audit log reference
            return f"/archive/{document_id}.json"

        except Exception as e:
            # REL-001: Non-blocking - archive failure doesn't stop upload
            st.warning(f"⚠️ Document archive failed: {e}")
            # Clean up temp file if it exists
            try:
                if 'temp_path' in locals() and temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            return None

    def log_ingestion(
        self,
        documents: List[Dict[str, Any]],
        add_result: Dict[str, Any],
        source: str = "file_upload"
    ) -> None:
        """
        Log document ingestion event.

        SPEC-029 REQ-003: Records successful document additions to audit log.
        SPEC-029 SEC-002: Does not include document content (PII protection).
        SPEC-036 REQ-001, REQ-002: Archives parent document content before audit logging.

        Args:
            documents: Original documents that were uploaded (before chunking)
            add_result: Result from api_client.add_documents()
            source: Ingestion source ("file_upload" or "url_ingestion")
        """
        # Only log if ingestion succeeded (fully or partially)
        if not add_result.get('success', False):
            return

        # SPEC-036 REQ-001: Archive parent documents BEFORE audit logging
        # Iterate over original documents (pre-chunking, parents only)
        archive_paths = {}  # Maps document_id -> archive_path
        for doc in documents:
            # Parent identification: no 'parent_doc_id' field
            if 'parent_doc_id' not in doc:
                archive_path = self._archive_document(doc, source)
                if archive_path:
                    archive_paths[doc.get('id')] = archive_path

        # Get prepared documents (after chunking) if available
        prepared_documents = add_result.get('prepared_documents', documents)

        # Current timestamp in ISO 8601 format (UTC)
        timestamp = datetime.now(timezone.utc).isoformat()

        # Log each document that was successfully indexed
        # Note: If chunked, this logs the chunks (actual indexed documents)
        for doc in prepared_documents:
            # Build audit entry according to SPEC-029 schema
            entry = {
                # Required fields
                "timestamp": timestamp,
                "event": "document_indexed",
                "document_id": doc.get('id'),
                "filename": doc.get('filename'),
                "source": source,
            }

            # Optional fields (only include if present)
            if 'size_bytes' in doc:
                entry['size_bytes'] = doc['size_bytes']

            if 'content_hash' in doc:
                entry['content_hash'] = doc['content_hash']

            if 'categories' in doc:
                entry['categories'] = doc['categories']

            if 'auto_labels' in doc:
                # For classified documents
                entry['categories'] = doc['auto_labels']

            if 'url' in doc:
                entry['url'] = doc['url']

            if 'media_type' in doc:
                entry['media_type'] = doc['media_type']

            # Additional context for chunks (not in spec, but useful for debugging)
            if doc.get('is_chunk'):
                entry['is_chunk'] = True
                entry['parent_doc_id'] = doc.get('parent_doc_id')
                entry['chunk_index'] = doc.get('chunk_index')

            # SPEC-036 REQ-002: Add archive_path for parent documents (conditional)
            # Only include if this document has an archive (parent-only, success-only)
            doc_id = doc.get('id')
            if doc_id in archive_paths:
                entry['archive_path'] = archive_paths[doc_id]

            # Write JSONL entry (one JSON object per line)
            # SEC-002: No document content (text field) is logged
            self.logger.info(json.dumps(entry, ensure_ascii=False))

    def log_bulk_import(
        self,
        document_ids: List[str],
        source_file: str,
        success_count: int,
        failure_count: int
    ) -> None:
        """
        Log bulk import event (for import-documents.sh).

        Args:
            document_ids: List of document IDs that were imported
            source_file: Path to source export file
            success_count: Number of successfully imported documents
            failure_count: Number of failed documents
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "timestamp": timestamp,
            "event": "bulk_import",
            "source_file": source_file,
            "document_count": len(document_ids),
            "success_count": success_count,
            "failure_count": failure_count,
            "document_ids": document_ids
        }

        self.logger.info(json.dumps(entry, ensure_ascii=False))

    def close(self) -> None:
        """Close the audit logger and release file handles."""
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)


# Global singleton instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get global audit logger instance (singleton pattern).

    Returns:
        AuditLogger instance
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
