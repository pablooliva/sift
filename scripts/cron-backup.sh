#!/bin/bash
# cron-backup.sh - Automated backup wrapper for txtai
#
# This script wraps backup.sh to provide:
# - Automatic scheduling via cron
# - Service restart safety (trap handler)
# - Lock file to prevent concurrent runs
# - Mount validation to prevent writing to root filesystem
# - Archive integrity verification
# - Retention policy enforcement
# - Triple-layer failure notification
#
# Usage:
#   ./cron-backup.sh                    # Run backup now
#   ./cron-backup.sh --if-stale HOURS   # Run only if last backup older than HOURS
#   ./cron-backup.sh --dry-run          # Test validation without running backup
#
# Exit codes:
#   0 = Success (backup completed and verified)
#   1 = Failure (error occurred, alert needed)
#   2 = Intentional skip (drive unmounted, lock held, staleness check says not needed)
#
# Requirements:
#   - .env file with BACKUP_EXTERNAL_DIR set
#   - backup.sh script exists and is executable
#   - External drive mounted (or will skip with exit 2)
#   - Docker and Docker Compose available
#
# Cron setup (via setup-cron-backup.sh):
#   0 3 * * * /path/to/cron-backup.sh                # Primary backup at 3 AM
#   0 */6 * * * /path/to/cron-backup.sh --if-stale 24 # Catch-up every 6 hours
#

# ============================================================================
# CRITICAL: Trap handler and set -e order
# ============================================================================
# REQ-012: Trap handler MUST be set BEFORE set -e
# This ensures cleanup runs on ANY exit (normal, error, signal)
# Cleanup restarts only services that were running before backup

# Track which services were running (REQ-011: independent tracking)
TXTAI_WAS_RUNNING=false
FRONTEND_WAS_RUNNING=false
SERVICES_TRACKED=false

# Track backup status for cleanup function (initialize before trap)
BACKUP_STATUS="initializing"  # Will be set to "running" after validation, "success" at end

# Docker Compose command detection (EDGE-020)
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "ERROR: Neither 'docker compose' nor 'docker-compose' found"
    exit 1
fi

# Cleanup function - restarts services that were running (REQ-012, DEF-003)
cleanup() {
    # REQ-016, REQ-017: Handle failure marker and notification
    if [ "$BACKUP_STATUS" != "success" ]; then
        # Backup failed or was interrupted - create failure marker
        echo "$(date -Iseconds) Backup failed or interrupted" > "$FAILURE_MARKER" 2>/dev/null || true

        # REQ-017: Best-effort desktop notification (don't fail if notification fails)
        if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
            notify-send --urgency=critical "txtai Backup Failed" "Check logs: $LOG_FILE" 2>/dev/null || \
                echo "$(date -Iseconds) Desktop notification failed (no active session?)" >> "$LOG_FILE" 2>/dev/null || true
        fi
    else
        # Backup succeeded - remove failure marker if it exists
        rm -f "$FAILURE_MARKER" 2>/dev/null || true
    fi

    # Only restart if we tracked services (prevents restart on early validation failures)
    if [ "$SERVICES_TRACKED" = true ]; then
        # Restart only services that were running before backup (with timeout to prevent hangs)
        if [ "$TXTAI_WAS_RUNNING" = true ]; then
            echo "$(date -Iseconds) Restarting txtai-api (was running before backup)" | tee -a "$LOG_FILE" 2>/dev/null || true
            if ! timeout 30s $DOCKER_COMPOSE start txtai 2>&1 | tee -a "$LOG_FILE" 2>/dev/null; then
                echo "$(date -Iseconds) WARNING: Failed to restart txtai-api (see above for details)" | tee -a "$LOG_FILE" 2>/dev/null || true
            fi
        fi

        if [ "$FRONTEND_WAS_RUNNING" = true ]; then
            echo "$(date -Iseconds) Restarting txtai-frontend (was running before backup)" | tee -a "$LOG_FILE" 2>/dev/null || true
            if ! timeout 30s $DOCKER_COMPOSE start frontend 2>&1 | tee -a "$LOG_FILE" 2>/dev/null; then
                echo "$(date -Iseconds) WARNING: Failed to restart txtai-frontend (see above for details)" | tee -a "$LOG_FILE" 2>/dev/null || true
            fi
        fi
    fi
}

# Set trap BEFORE set -e (CRITICAL ORDER)
trap cleanup EXIT

# Now set -e so errors trigger EXIT signal → cleanup runs
set -e

# NOTE: SIGKILL and SIGSTOP cannot be trapped (bash limitation)
# REQ-030 service monitor (Phase 5) provides defense-in-depth for untrapable signals

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs/backup"
LOG_FILE="$LOG_DIR/cron-backup.log"
LOCK_FILE="$LOG_DIR/.cron-backup.lock"
SENTINEL_FILE="$LOG_DIR/last-successful-backup"
SIZE_SENTINEL="$LOG_DIR/last-backup-size"
FAILURE_MARKER="$LOG_DIR/BACKUP_FAILED"

# REQ-032: Create log directory early (BEFORE trap is set)
# This ensures cleanup() can write to log files even if early validation fails
mkdir -p "$LOG_DIR" || {
    echo "ERROR: Failed to create log directory: $LOG_DIR" >&2
    exit 1
}

# Parse command-line arguments
DRY_RUN=false
STALENESS_HOURS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --if-stale)
            STALENESS_HOURS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--if-stale HOURS] [--dry-run]"
            exit 1
            ;;
    esac
done

# ============================================================================
# Helper Functions
# ============================================================================

# Log function with ISO 8601 timestamps (UX-001)
log() {
    # REQ-023: Rotate log when >10MB (atomic mv, keep current + .1)
    if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt 10485760 ]; then
        mv "$LOG_FILE" "${LOG_FILE}.1" 2>/dev/null || true
    fi

    echo "$(date -Iseconds) $*" | tee -a "$LOG_FILE"
}

# Check if a Docker container is running (with timeout to prevent hangs)
check_container() {
    local container_name="$1"
    timeout 30s docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container_name}$"
}

# ============================================================================
# REQ-024: Track backup start time for duration calculation
# ============================================================================

BACKUP_START_TIME=$(date +%s)

# Update backup status now that validation is complete
BACKUP_STATUS="running"

# ============================================================================
# REQ-006: Validate .env before sourcing
# ============================================================================

log "Starting backup validation"

# Check .env exists and is readable
if ! [ -f "$PROJECT_ROOT/.env" ] || ! [ -r "$PROJECT_ROOT/.env" ]; then
    log "ERROR: .env file not found or not readable at $PROJECT_ROOT/.env"
    exit 1
fi

# SEC-004: Parse .env without executing code (prevents command injection)
# Extract BACKUP_EXTERNAL_DIR using grep/cut (safe parsing, no code execution)
BACKUP_EXTERNAL_DIR=$(grep -E '^BACKUP_EXTERNAL_DIR=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2- | head -1 | sed 's/^["'\'']\(.*\)["'\'']$/\1/')

# Extract BACKUP_RETENTION_DAYS (optional, default to 30)
BACKUP_RETENTION_DAYS=$(grep -E '^BACKUP_RETENTION_DAYS=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2- | head -1 | sed 's/^["'\'']\(.*\)["'\'']$/\1/')

# Check required variables
if [ -z "${BACKUP_EXTERNAL_DIR:-}" ]; then
    log "ERROR: Required variable BACKUP_EXTERNAL_DIR not set in .env"
    exit 1
fi

# Validate BACKUP_EXTERNAL_DIR contains only safe characters (path characters + hyphen/underscore)
# Allows: alphanumeric, /, -, _, .
if ! [[ "$BACKUP_EXTERNAL_DIR" =~ ^[a-zA-Z0-9/_.-]+$ ]]; then
    log "ERROR: BACKUP_EXTERNAL_DIR contains unsafe characters (found: $BACKUP_EXTERNAL_DIR)"
    log "ERROR: Only alphanumeric, /, -, _, . are allowed"
    exit 1
fi

# Validate BACKUP_RETENTION_DAYS is numeric (if present)
if [ -n "${BACKUP_RETENTION_DAYS:-}" ]; then
    if ! [[ "$BACKUP_RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
        log "ERROR: BACKUP_RETENTION_DAYS must be a positive integer (found: $BACKUP_RETENTION_DAYS)"
        exit 1
    fi
else
    # Set default retention if not specified
    BACKUP_RETENTION_DAYS=30
fi

log "Configuration validated: BACKUP_EXTERNAL_DIR=$BACKUP_EXTERNAL_DIR, RETENTION=${BACKUP_RETENTION_DAYS} days"

# ============================================================================
# REQ-007: Validate backup.sh exists and is executable
# ============================================================================

BACKUP_SCRIPT="$PROJECT_ROOT/scripts/backup.sh"

if ! [ -f "$BACKUP_SCRIPT" ]; then
    log "ERROR: backup.sh not found at $BACKUP_SCRIPT"
    exit 1
fi

if ! [ -x "$BACKUP_SCRIPT" ]; then
    log "ERROR: backup.sh is not executable: $BACKUP_SCRIPT"
    exit 1
fi

log "backup.sh validated: $BACKUP_SCRIPT"

# ============================================================================
# REQ-009, REQ-031: Lock file with stale detection
# ============================================================================

# Stale lock detection (REQ-031: >12h triggers removal)
if [ -f "$LOCK_FILE" ]; then
    # Get lock file modification time (fail if stat fails for any reason)
    if ! LOCK_MTIME=$(stat -c%Y "$LOCK_FILE" 2>/dev/null); then
        log "ERROR: Failed to stat lock file (permission denied or I/O error)"
        exit 1
    fi

    LOCK_AGE_SECONDS=$(($(date +%s) - LOCK_MTIME))
    LOCK_AGE_HOURS=$((LOCK_AGE_SECONDS / 3600))

    if [ $LOCK_AGE_HOURS -ge 12 ]; then
        log "WARNING: Removing stale lock file (age: ${LOCK_AGE_HOURS}h)"
        rm -f "$LOCK_FILE" || {
            log "ERROR: Failed to remove stale lock file"
            exit 1
        }
    fi
fi

# Acquire lock (non-blocking) - REQ-009
exec 200>"$LOCK_FILE"
if ! flock --nonblock 200; then
    log "Lock file held by another process, skipping run"
    exit 2  # Intentional skip
fi

log "Lock acquired successfully"

# ============================================================================
# REQ-011: Track which services are currently running
# ============================================================================

if check_container "txtai-api"; then
    TXTAI_WAS_RUNNING=true
    log "Service status: txtai-api is running"
else
    log "Service status: txtai-api is stopped"
fi

if check_container "txtai-frontend"; then
    FRONTEND_WAS_RUNNING=true
    log "Service status: txtai-frontend is running"
else
    log "Service status: txtai-frontend is stopped"
fi

# Mark that we've tracked services (enables cleanup on exit)
SERVICES_TRACKED=true

# ============================================================================
# REQ-004, REQ-005: 4-layer mount validation
# ============================================================================

MOUNT_POINT="/path/to/external/drive"

# Check 1: Is actually a mount point (EDGE-001)
if ! mountpoint -q "$MOUNT_POINT"; then
    log "External drive not mounted at $MOUNT_POINT, skipping backup"
    exit 2  # Intentional skip (drive not available)
fi

# Check 2: Target directory exists and is a directory
if ! [ -d "$BACKUP_EXTERNAL_DIR" ]; then
    log "ERROR: BACKUP_EXTERNAL_DIR=$BACKUP_EXTERNAL_DIR is not a directory or does not exist"
    exit 1
fi

# Check 3: Target directory is writable (EDGE-017: read-only filesystem)
TEST_FILE="$BACKUP_EXTERNAL_DIR/.write-test-$$"
if ! touch "$TEST_FILE" 2>/dev/null; then
    log "ERROR: BACKUP_EXTERNAL_DIR is not writable (read-only filesystem?)"
    exit 2  # Intentional skip
fi
rm -f "$TEST_FILE"

# Check 4: Target directory is on external drive (EDGE-015: prevent writing to root)
if ! [[ "$BACKUP_EXTERNAL_DIR" == "$MOUNT_POINT"* ]]; then
    log "ERROR: BACKUP_EXTERNAL_DIR=$BACKUP_EXTERNAL_DIR is not on external drive mount point $MOUNT_POINT"
    log "ERROR: This would write to root filesystem - aborting (SEC-001)"
    exit 1
fi

log "Mount validation passed: $BACKUP_EXTERNAL_DIR is writable on external drive"

# ============================================================================
# REQ-010, REQ-010a: Staleness check - skip if recent backup exists
# ============================================================================

if [ $STALENESS_HOURS -gt 0 ]; then
    log "Checking backup staleness (threshold: ${STALENESS_HOURS}h)"

    # Sanity check: current time must be reasonable (> 2024-01-01)
    # Prevents retention from deleting all backups if clock resets to 1970
    current_time=$(date +%s)
    if [ $current_time -lt 1704067200 ]; then
        log "ERROR: System clock appears incorrect (before 2024-01-01)"
        log "ERROR: Current time: $(date -Iseconds)"
        log "ERROR: Aborting to prevent data loss from incorrect timestamps"
        exit 1
    fi

    # REQ-010a: Defensive sentinel parsing
    last_backup=0
    if [ -s "$SENTINEL_FILE" ]; then
        # Try to parse sentinel timestamp
        if ! last_backup=$(date -d "$(cat "$SENTINEL_FILE" 2>/dev/null)" +%s 2>/dev/null); then
            log "WARNING: Failed to parse sentinel file, treating as stale"
            last_backup=0  # Corrupt/missing/empty → treat as stale
        else
            # Check for clock skew (future timestamp)
            current_time=$(date +%s)
            if [ $last_backup -gt $current_time ]; then
                log "WARNING: Clock skew detected - sentinel timestamp is in the future"
                last_backup=0  # Future timestamp → treat as stale
            fi
        fi
    else
        log "No sentinel file found, treating as stale (first backup)"
        last_backup=0  # Missing sentinel
    fi

    # Calculate time since last backup
    current_time=$(date +%s)

    # Special case: first backup (last_backup=0)
    if [ $last_backup -eq 0 ]; then
        log "No previous backup found (first backup), proceeding"
    else
        time_since_last=$((current_time - last_backup))
        hours_since_last=$((time_since_last / 3600))

        if [ $hours_since_last -lt $STALENESS_HOURS ]; then
            log "Backup is fresh (${hours_since_last}h old < ${STALENESS_HOURS}h threshold), skipping"
            exit 2  # Intentional skip
        else
            log "Backup is stale (${hours_since_last}h old >= ${STALENESS_HOURS}h threshold), proceeding"
        fi
    fi
fi

# ============================================================================
# REQ-020, REQ-021: Free space and inode checks
# ============================================================================

# Calculate expected backup size (DEF-004)
if [ -f "$SIZE_SENTINEL" ]; then
    EXPECTED_SIZE=$(cat "$SIZE_SENTINEL" 2>/dev/null || echo "209715200")
else
    EXPECTED_SIZE=209715200  # 200MB default for first run
fi

log "Expected backup size: $((EXPECTED_SIZE / 1048576))MB (from last backup)"

# REQ-020: Free space requirement: 3x expected (compressed + temp = ~3x)
# Use block-size=1M to avoid suffix parsing issues on some systems
MIN_FREE_MB=$((EXPECTED_SIZE * 3 / 1048576))
FREE_MB=$(df --output=avail --block-size=1M "$BACKUP_EXTERNAL_DIR" | tail -1)

if [ $FREE_MB -lt $MIN_FREE_MB ]; then
    log "ERROR: Insufficient free space: ${FREE_MB}MB available, need ${MIN_FREE_MB}MB"
    exit 1
fi

log "Free space check passed: ${FREE_MB}MB available >= ${MIN_FREE_MB}MB required"

# REQ-021: Inode check - require >10% inodes free
INODES_TOTAL=$(df --output=itotal "$BACKUP_EXTERNAL_DIR" | tail -1)
INODES_AVAIL=$(df --output=iavail "$BACKUP_EXTERNAL_DIR" | tail -1)
INODES_PERCENT_FREE=$((INODES_AVAIL * 100 / INODES_TOTAL))

if [ $INODES_PERCENT_FREE -lt 10 ]; then
    log "ERROR: Insufficient inodes: ${INODES_PERCENT_FREE}% free (need >10%)"
    exit 1
fi

log "Inode check passed: ${INODES_PERCENT_FREE}% free (${INODES_AVAIL}/${INODES_TOTAL})"

# ============================================================================
# Activity check: Wait if ingestion in progress
# ============================================================================
# The frontend writes shared_uploads/.ingestion.lock when add_documents() starts
# and removes it when complete (including Graphiti batch processing).
# Stale lock threshold: 2 hours (covers largest possible Graphiti ingestion).
# Wait policy: check every 5 minutes, skip after 30 minutes of waiting.

INGESTION_LOCK_FILE="$PROJECT_ROOT/shared_uploads/.ingestion.lock"
INGESTION_LOCK_STALE_SECONDS=7200   # 2h: treat lock as stale (crashed process)
ACTIVITY_CHECK_INTERVAL=300          # 5 minutes between checks
ACTIVITY_MAX_WAIT=1800               # 30 minutes max wait before skipping

if [ -f "$INGESTION_LOCK_FILE" ]; then
    LOCK_MTIME=$(stat -c%Y "$INGESTION_LOCK_FILE" 2>/dev/null || echo 0)
    LOCK_AGE=$(( $(date +%s) - LOCK_MTIME ))

    if [ "$LOCK_AGE" -ge "$INGESTION_LOCK_STALE_SECONDS" ]; then
        # Lock is old enough to be stale (crashed frontend or leftover from previous run)
        log "WARNING: Stale ingestion lock found (age: ${LOCK_AGE}s, threshold: ${INGESTION_LOCK_STALE_SECONDS}s)"
        if [ "$DRY_RUN" = true ]; then
            log "Dry-run: would remove stale lock and proceed with backup"
        else
            log "Removing stale lock and proceeding with backup"
            rm -f "$INGESTION_LOCK_FILE" 2>/dev/null || log "WARNING: Could not remove stale lock (proceeding anyway)"
        fi
    else
        # Lock is fresh — an upload/ingestion is actively running
        if [ "$DRY_RUN" = true ]; then
            log "Dry-run: active ingestion detected (lock age: ${LOCK_AGE}s). Would wait up to $((ACTIVITY_MAX_WAIT / 60)) minutes."
        else
            log "Active ingestion detected (lock age: ${LOCK_AGE}s). Waiting up to $((ACTIVITY_MAX_WAIT / 60)) minutes..."

            WAIT_ELAPSED=0
            while [ -f "$INGESTION_LOCK_FILE" ] && [ "$WAIT_ELAPSED" -lt "$ACTIVITY_MAX_WAIT" ]; do
                sleep "$ACTIVITY_CHECK_INTERVAL"
                WAIT_ELAPSED=$(( WAIT_ELAPSED + ACTIVITY_CHECK_INTERVAL ))

                if [ -f "$INGESTION_LOCK_FILE" ]; then
                    LOCK_MTIME=$(stat -c%Y "$INGESTION_LOCK_FILE" 2>/dev/null || echo 0)
                    LOCK_AGE=$(( $(date +%s) - LOCK_MTIME ))
                    log "Ingestion still in progress (lock age: ${LOCK_AGE}s, waited: ${WAIT_ELAPSED}s)"

                    # Check if lock became stale while we were waiting (frontend crashed)
                    if [ "$LOCK_AGE" -ge "$INGESTION_LOCK_STALE_SECONDS" ]; then
                        log "WARNING: Ingestion lock became stale during wait, removing and proceeding"
                        rm -f "$INGESTION_LOCK_FILE" 2>/dev/null || true
                        break
                    fi
                fi
            done

            if [ -f "$INGESTION_LOCK_FILE" ]; then
                # Still locked after max wait — skip this run, rely on catch-up cron
                log "Ingestion still in progress after $((ACTIVITY_MAX_WAIT / 60)) minute wait. Skipping this backup run."
                log "The catch-up cron (--if-stale) will retry when ingestion completes."
                exit 2  # Intentional skip
            else
                log "Ingestion completed. Proceeding with backup."
            fi
        fi
    fi
else
    log "No active ingestion detected, proceeding with backup"
fi

# ============================================================================
# Dry-run mode: All validations complete, exit before backup execution
# ============================================================================

if [ "$DRY_RUN" = true ]; then
    log "Dry-run mode: All validations passed successfully"
    log "Would proceed with backup to: $BACKUP_EXTERNAL_DIR"
    exit 0
fi

# ============================================================================
# Backup execution
# ============================================================================

# Generate timestamp for backup filename (UX-001: ISO 8601)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE_PATH="$BACKUP_EXTERNAL_DIR/backup_${TIMESTAMP}.tar.gz"

log "Starting backup: $ARCHIVE_PATH"
log "Calling backup.sh with --stop and --output flags"

# Call backup.sh with --stop (services will be managed by our trap handler)
cd "$PROJECT_ROOT"
if ! "$BACKUP_SCRIPT" --stop --output "$BACKUP_EXTERNAL_DIR"; then
    log "ERROR: backup.sh failed with exit code $?"
    exit 1
fi

log "backup.sh completed successfully"

# ============================================================================
# REQ-013: Archive integrity verification (DEF-001)
# ============================================================================

# Ensure all writes are flushed to disk before verification
sync
sleep 1

log "Verifying backup integrity..."

# Find the most recently created backup (backup.sh creates backup_YYYYMMDD_HHMMSS.tar.gz)
# Use the latest file since we just created it
LATEST_BACKUP=$(ls -t "$BACKUP_EXTERNAL_DIR"/backup_*.tar.gz 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    log "ERROR: No backup archive found after backup.sh completed"
    exit 1
fi

ARCHIVE_PATH="$LATEST_BACKUP"
log "Verifying archive: $ARCHIVE_PATH"

# Check 1: File exists (already verified above, but explicit check)
if ! [ -f "$ARCHIVE_PATH" ]; then
    log "ERROR: Archive file not found: $ARCHIVE_PATH"
    exit 1
fi

# Check 2: Size >100KB (sanity check - handles EDGE-010 empty databases)
ARCHIVE_SIZE=$(stat -c%s "$ARCHIVE_PATH")
if [ $ARCHIVE_SIZE -lt 102400 ]; then
    log "ERROR: Archive too small: $((ARCHIVE_SIZE / 1024))KB (expected >100KB)"
    exit 1
fi
log "Archive size check passed: $((ARCHIVE_SIZE / 1024))KB"

# Check 3: Integrity check (can list contents without errors, with timeout to prevent hangs)
if ! timeout 60s tar -tzf "$ARCHIVE_PATH" >/dev/null 2>&1; then
    log "ERROR: Archive failed integrity check (corrupt, truncated, or timeout)"
    exit 1
fi

# Check 4: MANIFEST.txt exists in archive (with timeout)
if ! timeout 60s tar -tzf "$ARCHIVE_PATH" 2>/dev/null | grep -q "MANIFEST.txt"; then
    log "ERROR: MANIFEST.txt not found in archive"
    exit 1
fi

log "Archive integrity verified: $((ARCHIVE_SIZE / 1048576))MB compressed"

# ============================================================================
# REQ-014, REQ-015: Update sentinels only after verification succeeds
# ============================================================================

echo "$(date -Iseconds)" > "$SENTINEL_FILE" || {
    log "WARNING: Failed to update last-successful-backup sentinel"
}

echo "$ARCHIVE_SIZE" > "$SIZE_SENTINEL" || {
    log "WARNING: Failed to update last-backup-size sentinel"
}

log "Sentinels updated successfully"

# ============================================================================
# REQ-018, REQ-019: Retention policy - delete old backups
# ============================================================================
# NOTE: Backup runs BEFORE retention (REQ-019 already satisfied by this ordering)

if [ "$BACKUP_RETENTION_DAYS" -eq 0 ]; then
    log "Retention policy disabled (BACKUP_RETENTION_DAYS=0), keeping all backups"
else
    log "Applying retention policy: deleting backups older than ${BACKUP_RETENTION_DAYS} days"

    # Find backups older than retention period
    # Use -mtime +N (modified more than N days ago)
    OLD_BACKUPS=$(find "$BACKUP_EXTERNAL_DIR" -name "backup_*.tar.gz" -type f -mtime +${BACKUP_RETENTION_DAYS} 2>/dev/null || true)

    if [ -n "$OLD_BACKUPS" ]; then
        # Count candidates for deletion
        CANDIDATE_COUNT=$(echo "$OLD_BACKUPS" | wc -l)
        log "Found ${CANDIDATE_COUNT} backup(s) matching retention criteria (>${BACKUP_RETENTION_DAYS} days old)"

        # Delete old backups with additional safety check
        CURRENT_TIME=$(date +%s)
        DELETED_COUNT=0
        echo "$OLD_BACKUPS" | while IFS= read -r old_backup; do
            if [ -f "$old_backup" ]; then
                BACKUP_AGE_SECONDS=$(( CURRENT_TIME - $(stat -c%Y "$old_backup") ))
                BACKUP_AGE_DAYS=$(( BACKUP_AGE_SECONDS / 86400 ))

                # Safety guard: Never delete backups <24h old regardless of mtime
                # Prevents deletion if clock jumps forward (EDGE-016, CRITICAL-007)
                if [ $BACKUP_AGE_SECONDS -lt 86400 ]; then
                    log "WARNING: Skipping deletion of $(basename "$old_backup") (only ${BACKUP_AGE_SECONDS}s old, possible clock skew)"
                else
                    log "Deleting old backup (age: ${BACKUP_AGE_DAYS} days): $(basename "$old_backup")"
                    rm -f "$old_backup" || log "WARNING: Failed to delete $old_backup"
                    DELETED_COUNT=$((DELETED_COUNT + 1))
                fi
            fi
        done

        log "Retention cleanup completed (deleted: ${DELETED_COUNT}, candidates: ${CANDIDATE_COUNT})"
    else
        log "No backups older than ${BACKUP_RETENTION_DAYS} days found"
    fi
fi

# ============================================================================
# Success
# ============================================================================

# REQ-024: Calculate backup duration
BACKUP_END_TIME=$(date +%s)
BACKUP_DURATION=$((BACKUP_END_TIME - BACKUP_START_TIME))
DURATION_MIN=$((BACKUP_DURATION / 60))
DURATION_SEC=$((BACKUP_DURATION % 60))

# Mark backup as successful (cleanup function will remove failure marker)
BACKUP_STATUS="success"

log "Backup completed successfully: $ARCHIVE_PATH"
log "Archive size: $((ARCHIVE_SIZE / 1048576))MB, Duration: ${DURATION_MIN}m ${DURATION_SEC}s"

# Exit code 0 (success) - cleanup function will run and remove failure marker
exit 0
