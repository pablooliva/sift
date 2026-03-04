#!/bin/bash
#
# Restore script for txtai Semantic Search system
# Restores all three storage layers: PostgreSQL, Qdrant, and txtai data
#
# Usage:
#   ./scripts/restore.sh ./backups/backup_20240101_120000.tar.gz
#   ./scripts/restore.sh ./backups/backup_20240101_120000/
#   ./scripts/restore.sh --dry-run ./backups/backup_20240101_120000.tar.gz
#
# IMPORTANT: This will OVERWRITE existing data!
#
# The script will:
#   1. Stop all services
#   2. Restore PostgreSQL, Qdrant, and txtai data
#   3. Restart services
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

# Default options
DRY_RUN=false
SKIP_CONFIRM=false
BACKUP_PATH=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --yes|-y)
            SKIP_CONFIRM=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] BACKUP_PATH"
            echo ""
            echo "Arguments:"
            echo "  BACKUP_PATH         Path to backup archive (.tar.gz) or directory"
            echo ""
            echo "Options:"
            echo "  --dry-run           Show what would be restored without making changes"
            echo "  --yes, -y           Skip confirmation prompt"
            echo "  --help, -h          Show this help message"
            echo ""
            echo "WARNING: This will OVERWRITE existing data!"
            echo ""
            echo "Examples:"
            echo "  $0 ./backups/backup_20240101_120000.tar.gz"
            echo "  $0 --dry-run ./backups/backup_20240101_120000/"
            exit 0
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
        *)
            BACKUP_PATH="$1"
            shift
            ;;
    esac
done

# Validate backup path
if [ -z "$BACKUP_PATH" ]; then
    echo -e "${RED}Error: No backup path provided${NC}"
    echo "Usage: $0 [OPTIONS] BACKUP_PATH"
    echo "Use --help for more information"
    exit 1
fi

if [ ! -e "$BACKUP_PATH" ]; then
    echo -e "${RED}Error: Backup not found: $BACKUP_PATH${NC}"
    exit 1
fi

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

print_dry_run() {
    echo -e "${YELLOW}[DRY RUN]${NC} $1"
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
print_header "txtai Restore Tool"

cd "$PROJECT_ROOT"

# Handle compressed archives
RESTORE_DIR=""
TEMP_DIR=""

if [[ "$BACKUP_PATH" == *.tar.gz ]]; then
    echo "Extracting backup archive..."

    TEMP_DIR=$(mktemp -d)
    tar -xzf "$BACKUP_PATH" -C "$TEMP_DIR"

    # Find the backup directory inside
    RESTORE_DIR=$(find "$TEMP_DIR" -maxdepth 1 -type d -name "backup_*" | head -1)

    if [ -z "$RESTORE_DIR" ]; then
        # Maybe files are directly in temp dir
        RESTORE_DIR="$TEMP_DIR"
    fi

    print_success "Archive extracted to temporary directory"
else
    RESTORE_DIR="$BACKUP_PATH"
fi

# Show what's in the backup
print_header "Backup Contents"

if [ -f "$RESTORE_DIR/MANIFEST.txt" ]; then
    cat "$RESTORE_DIR/MANIFEST.txt"
    echo ""
fi

echo "Files found:"
[ -f "$RESTORE_DIR/postgres.sql" ] && echo "  - postgres.sql (PostgreSQL dump)"
[ -d "$RESTORE_DIR/postgres_data" ] && echo "  - postgres_data/ (PostgreSQL data directory)"
[ -d "$RESTORE_DIR/qdrant_storage" ] && echo "  - qdrant_storage/ (Qdrant vectors)"
[ -d "$RESTORE_DIR/txtai_data" ] && echo "  - txtai_data/ (BM25 index)"
[ -d "$RESTORE_DIR/document_archive" ] && echo "  - document_archive/ (Document content recovery)"
[ -d "$RESTORE_DIR/shared_uploads" ] && echo "  - shared_uploads/ (Frontend upload directory)"
[ -d "$RESTORE_DIR/logs/frontend/archive" ] && echo "  - logs/frontend/archive/ (Frontend archived logs)"
[ -f "$RESTORE_DIR/audit.jsonl" ] && echo "  - audit.jsonl (Audit log)"
[ -f "$RESTORE_DIR/neo4j.dump" ] && echo "  - neo4j.dump (Neo4j dump)"
[ -d "$RESTORE_DIR/neo4j_data" ] && echo "  - neo4j_data/ (Neo4j data directory)"
[ -f "$RESTORE_DIR/config.yml" ] && echo "  - config.yml"
[ -f "$RESTORE_DIR/.env" ] && echo "  - .env"

# Confirmation
if [ "$DRY_RUN" = false ] && [ "$SKIP_CONFIRM" = false ]; then
    echo ""
    echo -e "${YELLOW}WARNING: This will OVERWRITE existing data!${NC}"
    echo ""
    read -p "Are you sure you want to restore? (yes/no): " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        echo "Restore cancelled."
        [ -n "$TEMP_DIR" ] && rm -rf "$TEMP_DIR"
        exit 0
    fi
fi

if [ "$DRY_RUN" = true ]; then
    echo ""
    print_warning "DRY RUN MODE - No changes will be made"
fi

# Stop services
print_header "Stopping Services"

if [ "$DRY_RUN" = true ]; then
    print_dry_run "Would stop all txtai services"
else
    docker compose down 2>/dev/null || true
    print_success "All services stopped"
fi

# Restore Qdrant storage
if [ -d "$RESTORE_DIR/qdrant_storage" ]; then
    print_header "Restoring Qdrant Storage"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would remove $PROJECT_ROOT/qdrant_storage"
        print_dry_run "Would copy $RESTORE_DIR/qdrant_storage to $PROJECT_ROOT/"
    else
        rm -rf "$PROJECT_ROOT/qdrant_storage"
        cp -r "$RESTORE_DIR/qdrant_storage" "$PROJECT_ROOT/"
        print_success "Qdrant storage restored"
    fi
fi

# Restore txtai data
if [ -d "$RESTORE_DIR/txtai_data" ]; then
    print_header "Restoring txtai Data"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would remove $PROJECT_ROOT/txtai_data"
        print_dry_run "Would copy $RESTORE_DIR/txtai_data to $PROJECT_ROOT/"
    else
        rm -rf "$PROJECT_ROOT/txtai_data"
        cp -r "$RESTORE_DIR/txtai_data" "$PROJECT_ROOT/"
        print_success "txtai data restored"
    fi
fi

# Restore document archive
if [ -d "$RESTORE_DIR/document_archive" ]; then
    print_header "Restoring Document Archive"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would remove $PROJECT_ROOT/document_archive"
        print_dry_run "Would copy $RESTORE_DIR/document_archive to $PROJECT_ROOT/"
    else
        rm -rf "$PROJECT_ROOT/document_archive"
        cp -r "$RESTORE_DIR/document_archive" "$PROJECT_ROOT/"
        print_success "Document archive restored"
    fi
fi

# Restore shared uploads (REQ-002)
if [ -d "$RESTORE_DIR/shared_uploads" ]; then
    print_header "Restoring Shared Uploads"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would remove $PROJECT_ROOT/shared_uploads"
        print_dry_run "Would copy $RESTORE_DIR/shared_uploads to $PROJECT_ROOT/"
    else
        rm -rf "$PROJECT_ROOT/shared_uploads"
        cp -r "$RESTORE_DIR/shared_uploads" "$PROJECT_ROOT/"
        print_success "Shared uploads restored"
    fi
fi

# Restore frontend archived logs (REQ-002)
if [ -d "$RESTORE_DIR/logs/frontend/archive" ]; then
    print_header "Restoring Frontend Archived Logs"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would remove $PROJECT_ROOT/logs/frontend/archive"
        print_dry_run "Would copy $RESTORE_DIR/logs/frontend/archive to $PROJECT_ROOT/logs/frontend/"
    else
        rm -rf "$PROJECT_ROOT/logs/frontend/archive"
        mkdir -p "$PROJECT_ROOT/logs/frontend"
        cp -r "$RESTORE_DIR/logs/frontend/archive" "$PROJECT_ROOT/logs/frontend/"
        print_success "Frontend archived logs restored"
    fi
fi

# Restore audit log (REQ-002)
if [ -f "$RESTORE_DIR/audit.jsonl" ]; then
    print_header "Restoring Audit Log"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would copy $RESTORE_DIR/audit.jsonl to $PROJECT_ROOT/"
    else
        cp "$RESTORE_DIR/audit.jsonl" "$PROJECT_ROOT/"
        print_success "Audit log restored"
    fi
fi

# Restore Neo4j data (if present)
if [ -d "$RESTORE_DIR/neo4j_data" ]; then
    print_header "Restoring Neo4j Data"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would remove $PROJECT_ROOT/neo4j_data"
        print_dry_run "Would copy $RESTORE_DIR/neo4j_data to $PROJECT_ROOT/"
    else
        rm -rf "$PROJECT_ROOT/neo4j_data"
        cp -r "$RESTORE_DIR/neo4j_data" "$PROJECT_ROOT/"
        print_success "Neo4j data restored"
    fi
fi

# Start databases first
print_header "Starting Database Services"

if [ "$DRY_RUN" = true ]; then
    print_dry_run "Would start postgres, qdrant services"
else
    # Use service names (postgres, qdrant), not container names (txtai-postgres, txtai-qdrant)
    docker compose up -d postgres qdrant 2>/dev/null || true

    # Also start Neo4j if we have data for it
    if [ -d "$PROJECT_ROOT/neo4j_data" ] || [ -f "$RESTORE_DIR/neo4j.dump" ]; then
        docker compose up -d neo4j 2>/dev/null || true
    fi

    echo "Waiting for databases to be ready..."
    sleep 10
    print_success "Database services started"
fi

# Restore PostgreSQL
if [ -f "$RESTORE_DIR/postgres.sql" ]; then
    print_header "Restoring PostgreSQL"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would drop and recreate txtai database"
        print_dry_run "Would restore from postgres.sql"
    else
        echo "Dropping existing database..."
        docker exec txtai-postgres psql -U postgres -c "DROP DATABASE IF EXISTS txtai;" 2>/dev/null || true
        docker exec txtai-postgres psql -U postgres -c "CREATE DATABASE txtai;" 2>/dev/null || true

        echo "Restoring database from dump..."
        docker exec -i txtai-postgres psql -U postgres txtai < "$RESTORE_DIR/postgres.sql"
        print_success "PostgreSQL restored"
    fi
elif [ -d "$RESTORE_DIR/postgres_data" ]; then
    print_header "Restoring PostgreSQL Data Directory"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would stop postgres container"
        print_dry_run "Would replace postgres_data directory"
        print_dry_run "Would restart postgres container"
    else
        # Use service name (postgres), not container name (txtai-postgres)
        docker compose stop postgres 2>/dev/null || true
        rm -rf "$PROJECT_ROOT/postgres_data"
        cp -r "$RESTORE_DIR/postgres_data" "$PROJECT_ROOT/"
        docker compose up -d postgres
        sleep 5
        print_success "PostgreSQL data directory restored"
    fi
fi

# Restore Neo4j from dump (if present)
if [ -f "$RESTORE_DIR/neo4j.dump" ]; then
    print_header "Restoring Neo4j from Dump"

    if [ "$DRY_RUN" = true ]; then
        print_dry_run "Would restore Neo4j from neo4j.dump"
    else
        echo "Restoring Neo4j database..."
        docker exec -i txtai-neo4j neo4j-admin database load neo4j --from-stdin < "$RESTORE_DIR/neo4j.dump" 2>/dev/null || {
            print_warning "Neo4j dump restore failed, database may need manual recovery"
        }
        print_success "Neo4j restored"
    fi
fi

# Restore configuration files (optional - ask first)
if [ -f "$RESTORE_DIR/config.yml" ] || [ -f "$RESTORE_DIR/.env" ]; then
    print_header "Configuration Files"

    if [ "$DRY_RUN" = true ]; then
        [ -f "$RESTORE_DIR/config.yml" ] && print_dry_run "Would restore config.yml"
        [ -f "$RESTORE_DIR/.env" ] && print_dry_run "Would restore .env"
    else
        echo "Configuration files found in backup."
        echo "Current config files will be backed up to *.bak before overwriting."
        echo ""

        if [ "$SKIP_CONFIRM" = true ]; then
            RESTORE_CONFIG="yes"
        else
            read -p "Restore configuration files? (yes/no): " RESTORE_CONFIG
        fi

        if [ "$RESTORE_CONFIG" = "yes" ]; then
            if [ -f "$RESTORE_DIR/config.yml" ]; then
                [ -f "$PROJECT_ROOT/config.yml" ] && cp "$PROJECT_ROOT/config.yml" "$PROJECT_ROOT/config.yml.bak"
                cp "$RESTORE_DIR/config.yml" "$PROJECT_ROOT/"
                print_success "config.yml restored (original backed up to config.yml.bak)"
            fi

            if [ -f "$RESTORE_DIR/.env" ]; then
                [ -f "$PROJECT_ROOT/.env" ] && cp "$PROJECT_ROOT/.env" "$PROJECT_ROOT/.env.bak"
                cp "$RESTORE_DIR/.env" "$PROJECT_ROOT/"
                print_success ".env restored (original backed up to .env.bak)"
            fi
        else
            print_info "Skipping configuration files"
        fi
    fi
fi

# Start remaining services
print_header "Starting All Services"

if [ "$DRY_RUN" = true ]; then
    print_dry_run "Would start all txtai services"
else
    docker compose up -d
    print_success "All services started"
fi

# Cleanup temp directory
if [ -n "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
fi

# Summary
print_header "Restore Complete"

if [ "$DRY_RUN" = true ]; then
    echo "This was a dry run. No changes were made."
    echo ""
    echo "To perform the actual restore, run:"
    echo "  $0 $BACKUP_PATH"
else
    echo "All data has been restored from backup."
    echo ""
    echo "Services status:"
    docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || true
    echo ""
    echo "You may want to verify:"
    echo "  - Frontend: http://localhost:8501"
    echo "  - API health: curl http://localhost:8300/count"
    echo ""
    print_success "Restore completed successfully!"
fi
