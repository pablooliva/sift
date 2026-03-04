#!/bin/bash
#
# Reset database script for txtai Semantic Search system
# Archives audit log and clears all data storage layers
#
# Usage:
#   ./scripts/reset-database.sh              # Interactive reset with confirmation
#   ./scripts/reset-database.sh --yes        # Skip confirmation prompts
#   ./scripts/reset-database.sh --keep-audit # Don't archive audit log
#
# What gets cleared:
#   - PostgreSQL data (./postgres_data)
#   - Qdrant vectors (./qdrant_storage)
#   - txtai/BM25 index (./txtai_data/index)
#   - Neo4j graph (./neo4j_data, ./neo4j_logs)
#   - Document archives (./document_archive)
#   - Uploaded files (./shared_uploads)
#
# What gets archived (not deleted):
#   - Audit log → ./logs/frontend/archive/ingestion_audit_YYYYMMDD_HHMMSS.jsonl
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Default options
SKIP_CONFIRM=false
KEEP_AUDIT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --yes|-y)
            SKIP_CONFIRM=true
            shift
            ;;
        --keep-audit)
            KEEP_AUDIT=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Reset all database storage and optionally archive audit log."
            echo ""
            echo "Options:"
            echo "  --yes, -y       Skip confirmation prompts"
            echo "  --keep-audit    Don't archive audit log (leave in place)"
            echo "  --help, -h      Show this help message"
            echo ""
            echo "What gets cleared:"
            echo "  - PostgreSQL data (./postgres_data)"
            echo "  - Qdrant vectors (./qdrant_storage)"
            echo "  - txtai/BM25 index (./txtai_data/index)"
            echo "  - Neo4j graph (./neo4j_data, ./neo4j_logs)"
            echo "  - Document archives (./document_archive)"
            echo "  - Uploaded files (./shared_uploads)"
            echo ""
            echo "What gets archived (not deleted):"
            echo "  - Audit log → ./logs/frontend/archive/"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

cd "$PROJECT_ROOT"

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Database Reset Script${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Check what exists
echo -e "${YELLOW}Current data status:${NC}"
[[ -d "postgres_data" ]] && echo "  - postgres_data: $(du -sh postgres_data 2>/dev/null | cut -f1)" || echo "  - postgres_data: (not found)"
[[ -d "qdrant_storage" ]] && echo "  - qdrant_storage: $(du -sh qdrant_storage 2>/dev/null | cut -f1)" || echo "  - qdrant_storage: (not found)"
[[ -d "txtai_data/index" ]] && echo "  - txtai_data/index: $(du -sh txtai_data/index 2>/dev/null | cut -f1)" || echo "  - txtai_data/index: (not found)"
[[ -d "neo4j_data" ]] && echo "  - neo4j_data: $(du -sh neo4j_data 2>/dev/null | cut -f1)" || echo "  - neo4j_data: (not found)"
[[ -d "neo4j_logs" ]] && echo "  - neo4j_logs: $(du -sh neo4j_logs 2>/dev/null | cut -f1)" || echo "  - neo4j_logs: (not found)"
[[ -d "document_archive" ]] && echo "  - document_archive: $(du -sh document_archive 2>/dev/null | cut -f1) ($(find document_archive -name "*.json" 2>/dev/null | wc -l) archives)" || echo "  - document_archive: (not found)"
[[ -d "shared_uploads" ]] && echo "  - shared_uploads: $(du -sh shared_uploads 2>/dev/null | cut -f1) ($(find shared_uploads -type f 2>/dev/null | wc -l) files)" || echo "  - shared_uploads: (not found)"

AUDIT_LOG="logs/frontend/ingestion_audit.jsonl"
if [[ -f "$AUDIT_LOG" ]]; then
    AUDIT_SIZE=$(du -sh "$AUDIT_LOG" 2>/dev/null | cut -f1)
    AUDIT_LINES=$(wc -l < "$AUDIT_LOG" 2>/dev/null || echo "0")
    echo "  - ingestion_audit.jsonl: $AUDIT_SIZE ($AUDIT_LINES entries)"
else
    echo "  - ingestion_audit.jsonl: (not found)"
fi
echo ""

# Confirmation
if [[ "$SKIP_CONFIRM" != "true" ]]; then
    echo -e "${RED}WARNING: This will delete ALL indexed documents!${NC}"
    if [[ "$KEEP_AUDIT" != "true" ]]; then
        echo -e "${YELLOW}The audit log will be archived (not deleted).${NC}"
    fi
    echo ""
    read -p "Are you sure you want to continue? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Aborted.${NC}"
        exit 0
    fi
fi

# Stop services
echo ""
echo -e "${BLUE}Stopping services...${NC}"
docker compose down 2>/dev/null || true

# Archive audit log
if [[ "$KEEP_AUDIT" != "true" && -f "$AUDIT_LOG" ]]; then
    echo ""
    echo -e "${BLUE}Archiving audit log...${NC}"
    ARCHIVE_DIR="logs/frontend/archive"
    mkdir -p "$ARCHIVE_DIR"
    ARCHIVE_FILE="$ARCHIVE_DIR/ingestion_audit_${TIMESTAMP}.jsonl"
    mv "$AUDIT_LOG" "$ARCHIVE_FILE"
    echo -e "${GREEN}  ✓ Archived to: $ARCHIVE_FILE${NC}"
fi

# Clear data directories
echo ""
echo -e "${BLUE}Clearing data directories...${NC}"

if [[ -d "qdrant_storage" ]]; then
    sudo rm -rf qdrant_storage
    echo -e "${GREEN}  ✓ Cleared qdrant_storage${NC}"
fi

if [[ -d "postgres_data" ]]; then
    sudo rm -rf postgres_data
    echo -e "${GREEN}  ✓ Cleared postgres_data${NC}"
fi

if [[ -d "txtai_data/index" ]]; then
    sudo rm -rf txtai_data/index
    echo -e "${GREEN}  ✓ Cleared txtai_data/index${NC}"
fi

if [[ -d "neo4j_data" ]]; then
    sudo rm -rf neo4j_data
    echo -e "${GREEN}  ✓ Cleared neo4j_data${NC}"
fi

if [[ -d "neo4j_logs" ]]; then
    sudo rm -rf neo4j_logs
    echo -e "${GREEN}  ✓ Cleared neo4j_logs${NC}"
fi

if [[ -d "document_archive" ]]; then
    sudo rm -rf document_archive
    echo -e "${GREEN}  ✓ Cleared document_archive${NC}"
fi

if [[ -d "shared_uploads" ]]; then
    sudo rm -rf shared_uploads
    echo -e "${GREEN}  ✓ Cleared shared_uploads${NC}"
fi

# Start services
echo ""
echo -e "${BLUE}Starting services...${NC}"
docker compose up -d

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Reset Complete${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "All data has been cleared. The system is ready for fresh uploads."
if [[ "$KEEP_AUDIT" != "true" && -n "$ARCHIVE_FILE" ]]; then
    echo ""
    echo -e "Previous audit log archived to:"
    echo -e "  ${BLUE}$ARCHIVE_FILE${NC}"
    echo ""
    echo "Use this to see what documents were previously indexed:"
    echo "  cat $ARCHIVE_FILE | jq -s 'group_by(.parent_doc_id // .document_id) | .[] | {filename: .[0].filename, count: length}'"
fi
echo ""
