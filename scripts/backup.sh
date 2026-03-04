#!/bin/bash
#
# Backup script for txtai Semantic Search system
# Backs up all three storage layers: PostgreSQL, Qdrant, and txtai data
#
# Usage:
#   ./scripts/backup.sh                    # Full backup (services stay running)
#   ./scripts/backup.sh --stop             # Stop services during backup (recommended for consistency)
#   ./scripts/backup.sh --output ./mydir   # Custom backup directory
#   ./scripts/backup.sh --no-compress      # Skip compression (faster, larger files)
#
# Backup includes:
#   - PostgreSQL database (pg_dump)
#   - Qdrant vector storage (directory copy)
#   - txtai data/BM25 index (directory copy)
#   - Document archive (content recovery)
#   - Shared uploads (frontend upload directory)
#   - Frontend archived logs
#   - Audit log (audit.jsonl)
#   - Neo4j database (knowledge graph)
#   - Configuration files (config.yml, .env)
#
# Output:
#   Creates timestamped backup in ./backups/ (or custom directory)
#   Format: backup_YYYYMMDD_HHMMSS/
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
BACKUP_DIR="$PROJECT_ROOT/backups"
STOP_SERVICES=false
COMPRESS=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --stop)
            STOP_SERVICES=true
            shift
            ;;
        --output|-o)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --no-compress)
            COMPRESS=false
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --stop              Stop services during backup (recommended for consistency)"
            echo "  --output, -o DIR    Custom backup directory (default: ./backups)"
            echo "  --no-compress       Skip compression (faster, larger files)"
            echo "  --help, -h          Show this help message"
            echo ""
            echo "Backup includes:"
            echo "  - PostgreSQL database (document content & metadata)"
            echo "  - Qdrant vector storage (embeddings)"
            echo "  - txtai data (BM25 scoring index)"
            echo "  - Document archive (content recovery)"
            echo "  - Shared uploads (frontend upload directory)"
            echo "  - Frontend archived logs"
            echo "  - Audit log (audit.jsonl)"
            echo "  - Neo4j database (knowledge graph)"
            echo "  - Configuration files (config.yml, .env)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Helper functions
print_header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "  $1"
}

check_container() {
    local name=$1
    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        return 0
    else
        return 1
    fi
}

# Main execution
print_header "txtai Backup Tool"

cd "$PROJECT_ROOT"

# Create backup directory
BACKUP_PATH="$BACKUP_DIR/backup_$TIMESTAMP"
mkdir -p "$BACKUP_PATH"

echo "Configuration:"
echo "  Backup location:   $BACKUP_PATH"
echo "  Stop services:     $([ "$STOP_SERVICES" = true ] && echo "Yes" || echo "No")"
echo "  Compress:          $([ "$COMPRESS" = true ] && echo "Yes" || echo "No")"

# Check if containers are running
print_header "Checking Services"

POSTGRES_RUNNING=false
QDRANT_RUNNING=false
NEO4J_RUNNING=false

if check_container "txtai-postgres"; then
    print_success "PostgreSQL container is running"
    POSTGRES_RUNNING=true
else
    print_warning "PostgreSQL container is not running"
fi

if check_container "txtai-qdrant"; then
    print_success "Qdrant container is running"
    QDRANT_RUNNING=true
else
    print_warning "Qdrant container is not running"
fi

if check_container "txtai-neo4j"; then
    print_success "Neo4j container is running"
    NEO4J_RUNNING=true
else
    print_warning "Neo4j container is not running"
fi

# Stop services if requested
SERVICES_STOPPED=false
if [ "$STOP_SERVICES" = true ]; then
    print_header "Stopping Services"

    if check_container "txtai-api" || check_container "txtai-frontend"; then
        # Use service names (txtai, frontend), not container names (txtai-api, txtai-frontend)
        docker compose stop txtai frontend 2>/dev/null || true
        SERVICES_STOPPED=true
        print_success "Stopped txtai and frontend services"
    else
        print_info "Services already stopped"
    fi
fi

# Backup PostgreSQL
print_header "Backing Up PostgreSQL"

if [ "$POSTGRES_RUNNING" = true ]; then
    echo "Dumping database..."
    if docker exec txtai-postgres pg_dump -U postgres txtai > "$BACKUP_PATH/postgres.sql" 2>/dev/null; then
        SIZE=$(du -h "$BACKUP_PATH/postgres.sql" | cut -f1)
        print_success "PostgreSQL backup complete ($SIZE)"
    else
        print_error "PostgreSQL backup failed"
    fi
else
    if [ -d "$PROJECT_ROOT/postgres_data" ]; then
        echo "Container not running, copying data directory..."
        cp -r "$PROJECT_ROOT/postgres_data" "$BACKUP_PATH/postgres_data"
        print_success "PostgreSQL data directory copied"
    else
        print_warning "No PostgreSQL data found"
    fi
fi

# Backup Qdrant
print_header "Backing Up Qdrant"

if [ -d "$PROJECT_ROOT/qdrant_storage" ]; then
    echo "Copying Qdrant storage..."
    cp -r "$PROJECT_ROOT/qdrant_storage" "$BACKUP_PATH/qdrant_storage"
    SIZE=$(du -sh "$BACKUP_PATH/qdrant_storage" | cut -f1)
    print_success "Qdrant backup complete ($SIZE)"
else
    print_warning "No Qdrant storage found at $PROJECT_ROOT/qdrant_storage"
fi

# Backup txtai data (BM25 index)
print_header "Backing Up txtai Data"

if [ -d "$PROJECT_ROOT/txtai_data" ]; then
    echo "Copying txtai data..."
    cp -r "$PROJECT_ROOT/txtai_data" "$BACKUP_PATH/txtai_data"
    SIZE=$(du -sh "$BACKUP_PATH/txtai_data" | cut -f1)
    print_success "txtai data backup complete ($SIZE)"
else
    print_warning "No txtai data found at $PROJECT_ROOT/txtai_data"
fi

# Backup document archive
print_header "Backing Up Document Archive"

if [ -d "$PROJECT_ROOT/document_archive" ]; then
    echo "Copying document archive..."
    cp -r "$PROJECT_ROOT/document_archive" "$BACKUP_PATH/document_archive"
    SIZE=$(du -sh "$BACKUP_PATH/document_archive" | cut -f1)
    print_success "Document archive backup complete ($SIZE)"
else
    print_warning "No document archive found at $PROJECT_ROOT/document_archive"
fi

# Backup shared uploads (REQ-001)
print_header "Backing Up Shared Uploads"

if [ -d "$PROJECT_ROOT/shared_uploads" ]; then
    echo "Copying shared uploads..."
    cp -r "$PROJECT_ROOT/shared_uploads" "$BACKUP_PATH/shared_uploads" 2>/dev/null || {
        print_error "Failed to copy shared_uploads (permission issues?)"
        exit 1
    }

    # REQ-001a/REQ-001b: File count verification per DEF-005
    echo "Verifying file count..."
    SRC_COUNT=$(find "$PROJECT_ROOT/shared_uploads" -type f -print0 2>/dev/null | tr '\0' '\n' | wc -l)
    DST_COUNT=$(find "$BACKUP_PATH/shared_uploads" -type f -print0 2>/dev/null | tr '\0' '\n' | wc -l)

    # DEF-005: File count match tolerance
    if [ "$SRC_COUNT" -eq 0 ] && [ "$DST_COUNT" -eq 0 ]; then
        # Both empty → success
        SIZE=$(du -sh "$BACKUP_PATH/shared_uploads" | cut -f1)
        print_success "Shared uploads backup complete ($SIZE, 0 files)"
    elif [ "$SRC_COUNT" -eq "$DST_COUNT" ]; then
        # Exact match → success
        SIZE=$(du -sh "$BACKUP_PATH/shared_uploads" | cut -f1)
        print_success "Shared uploads backup complete ($SIZE, $DST_COUNT files)"
    else
        # Calculate difference and percentage
        if [ "$SRC_COUNT" -gt "$DST_COUNT" ]; then
            DIFF=$((SRC_COUNT - DST_COUNT))
        else
            DIFF=$((DST_COUNT - SRC_COUNT))
        fi

        if [ "$SRC_COUNT" -gt 0 ]; then
            PERCENT=$((DIFF * 100 / SRC_COUNT))
        else
            PERCENT=0
        fi

        if [ "$DIFF" -le 2 ] && [ "$PERCENT" -lt 5 ]; then
            # 1-2 file difference AND <5% → warning (possible race condition)
            SIZE=$(du -sh "$BACKUP_PATH/shared_uploads" | cut -f1)
            print_warning "Shared uploads file count mismatch: source=$SRC_COUNT backup=$DST_COUNT (possible race condition)"
            print_success "Shared uploads backup complete ($SIZE, $DST_COUNT files)"
        else
            # 3+ files OR ≥5% → error (likely permission issue, backup failed)
            print_error "Shared uploads file count mismatch: source=$SRC_COUNT backup=$DST_COUNT ($PERCENT% missing)"
            print_error "Possible permission issue - backup failed"
            exit 1
        fi
    fi
else
    print_warning "No shared uploads found at $PROJECT_ROOT/shared_uploads"
fi

# Backup frontend archived logs (REQ-001)
print_header "Backing Up Frontend Archived Logs"

if [ -d "$PROJECT_ROOT/logs/frontend/archive" ]; then
    echo "Copying frontend archived logs..."
    mkdir -p "$BACKUP_PATH/logs/frontend"
    cp -r "$PROJECT_ROOT/logs/frontend/archive" "$BACKUP_PATH/logs/frontend/archive"
    SIZE=$(du -sh "$BACKUP_PATH/logs/frontend/archive" | cut -f1)
    print_success "Frontend archived logs backup complete ($SIZE)"
else
    print_warning "No frontend archived logs found at $PROJECT_ROOT/logs/frontend/archive"
fi

# Backup audit log (REQ-001)
print_header "Backing Up Audit Log"

if [ -f "$PROJECT_ROOT/audit.jsonl" ]; then
    echo "Copying audit log..."
    cp "$PROJECT_ROOT/audit.jsonl" "$BACKUP_PATH/audit.jsonl"
    SIZE=$(du -h "$BACKUP_PATH/audit.jsonl" | cut -f1)
    print_success "Audit log backup complete ($SIZE)"
else
    print_warning "No audit log found at $PROJECT_ROOT/audit.jsonl"
fi

# Backup Neo4j
print_header "Backing Up Neo4j"

if [ "$NEO4J_RUNNING" = true ]; then
    echo "Dumping Neo4j database..."
    # Neo4j requires stopping for consistent backup, or use neo4j-admin
    if docker exec txtai-neo4j neo4j-admin database dump neo4j --to-stdout > "$BACKUP_PATH/neo4j.dump" 2>/dev/null; then
        SIZE=$(du -h "$BACKUP_PATH/neo4j.dump" | cut -f1)
        print_success "Neo4j backup complete ($SIZE)"
    else
        print_warning "Neo4j dump failed, copying data directory instead..."
        if [ -d "$PROJECT_ROOT/neo4j_data" ]; then
            cp -r "$PROJECT_ROOT/neo4j_data" "$BACKUP_PATH/neo4j_data"
            print_success "Neo4j data directory copied"
        fi
    fi
else
    if [ -d "$PROJECT_ROOT/neo4j_data" ]; then
        echo "Container not running, copying data directory..."
        cp -r "$PROJECT_ROOT/neo4j_data" "$BACKUP_PATH/neo4j_data"
        print_success "Neo4j data directory copied"
    else
        print_warning "No Neo4j data found"
    fi
fi

# Backup configuration files
print_header "Backing Up Configuration"

echo "Copying configuration files..."
[ -f "$PROJECT_ROOT/config.yml" ] && cp "$PROJECT_ROOT/config.yml" "$BACKUP_PATH/"
[ -f "$PROJECT_ROOT/.env" ] && cp "$PROJECT_ROOT/.env" "$BACKUP_PATH/"
[ -f "$PROJECT_ROOT/docker-compose.yml" ] && cp "$PROJECT_ROOT/docker-compose.yml" "$BACKUP_PATH/"

print_success "Configuration files backed up"

# Create manifest
echo "Creating backup manifest..."
cat > "$BACKUP_PATH/MANIFEST.txt" << EOF
txtai Backup Manifest
=====================
Created: $(date)
Host: $(hostname)

Contents:
EOF

[ -f "$BACKUP_PATH/postgres.sql" ] && echo "  - postgres.sql (PostgreSQL dump)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -d "$BACKUP_PATH/postgres_data" ] && echo "  - postgres_data/ (PostgreSQL data directory)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -d "$BACKUP_PATH/qdrant_storage" ] && echo "  - qdrant_storage/ (Qdrant vectors)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -d "$BACKUP_PATH/txtai_data" ] && echo "  - txtai_data/ (BM25 index)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -d "$BACKUP_PATH/document_archive" ] && echo "  - document_archive/ (Document content recovery)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -d "$BACKUP_PATH/shared_uploads" ] && echo "  - shared_uploads/ (Frontend upload directory)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -d "$BACKUP_PATH/logs/frontend/archive" ] && echo "  - logs/frontend/archive/ (Frontend archived logs)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -f "$BACKUP_PATH/audit.jsonl" ] && echo "  - audit.jsonl (Audit log)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -f "$BACKUP_PATH/neo4j.dump" ] && echo "  - neo4j.dump (Neo4j dump)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -d "$BACKUP_PATH/neo4j_data" ] && echo "  - neo4j_data/ (Neo4j data directory)" >> "$BACKUP_PATH/MANIFEST.txt"
[ -f "$BACKUP_PATH/config.yml" ] && echo "  - config.yml" >> "$BACKUP_PATH/MANIFEST.txt"
[ -f "$BACKUP_PATH/.env" ] && echo "  - .env" >> "$BACKUP_PATH/MANIFEST.txt"
[ -f "$BACKUP_PATH/docker-compose.yml" ] && echo "  - docker-compose.yml" >> "$BACKUP_PATH/MANIFEST.txt"

cat >> "$BACKUP_PATH/MANIFEST.txt" << EOF

Restore with:
  ./scripts/restore.sh $BACKUP_PATH
EOF

print_success "Manifest created"

# Compress if requested
if [ "$COMPRESS" = true ]; then
    print_header "Compressing Backup"

    echo "Creating compressed archive..."
    ARCHIVE_NAME="backup_$TIMESTAMP.tar.gz"

    cd "$BACKUP_DIR"
    tar -czf "$ARCHIVE_NAME" "backup_$TIMESTAMP"

    ARCHIVE_SIZE=$(du -h "$ARCHIVE_NAME" | cut -f1)

    # Remove uncompressed directory
    rm -rf "backup_$TIMESTAMP"

    print_success "Compressed to $ARCHIVE_NAME ($ARCHIVE_SIZE)"

    FINAL_PATH="$BACKUP_DIR/$ARCHIVE_NAME"
else
    FINAL_PATH="$BACKUP_PATH"
fi

# Restart services if we stopped them
if [ "$SERVICES_STOPPED" = true ]; then
    print_header "Restarting Services"

    cd "$PROJECT_ROOT"
    # Use service names (txtai, frontend), not container names
    docker compose start txtai frontend
    print_success "Services restarted"
fi

# Summary
print_header "Backup Complete"

echo "Backup location: $FINAL_PATH"
echo ""
TOTAL_SIZE=$(du -sh "$FINAL_PATH" | cut -f1)
echo "Total size: $TOTAL_SIZE"
echo ""
echo "To restore this backup, run:"
echo "  ./scripts/restore.sh $FINAL_PATH"
echo ""
print_success "Backup completed successfully!"
