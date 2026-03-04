#!/usr/bin/env python3
"""Helper script to write audit log entry for import-documents.sh"""
import sys
import os

# Add frontend to path to import AuditLogger
sys.path.append(os.path.join(os.path.dirname(__file__), '../frontend'))

from utils.audit_logger import AuditLogger


def main():
    if len(sys.argv) != 5:
        print("Usage: audit-import.py <source_file> <success_count> <failure_count> <doc_ids_file>", file=sys.stderr)
        sys.exit(1)

    source_file = sys.argv[1]
    success_count = int(sys.argv[2])
    failure_count = int(sys.argv[3])
    doc_ids_file = sys.argv[4]

    # Read document IDs from temp file (avoids ARG_MAX limit)
    with open(doc_ids_file) as f:
        document_ids = [line.strip() for line in f if line.strip()]

    # Write audit log entry to project root (not Docker /logs)
    # Support test environment isolation
    test_audit_dir = os.getenv('TEST_AUDIT_LOG_DIR')
    if test_audit_dir:
        # Test mode: use isolated temporary directory
        logger = AuditLogger(log_dir=test_audit_dir, log_file="audit.jsonl")
    else:
        # Production mode: use project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logger = AuditLogger(log_dir=project_root, log_file="audit.jsonl")
    logger.log_bulk_import(document_ids, source_file, success_count, failure_count)


if __name__ == '__main__':
    main()
