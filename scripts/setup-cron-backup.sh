#!/bin/bash
# Setup script for automated txtai backups
# Adds cron entries and captures environment variables for notifications
# Usage: ./scripts/setup-cron-backup.sh [--dry-run]

set -e

# Detect project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
    DRY_RUN=true
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

echo "========================================="
echo "txtai Automated Backup Setup"
echo "========================================="
echo ""

# REQ-027: Create required directories
log_info "Creating required directories..."
mkdir -p "$PROJECT_ROOT/logs/backup"
log_success "Created logs/backup/ directory"

# Verify required files exist
log_info "Verifying required files..."

if [ ! -f "$PROJECT_ROOT/scripts/cron-backup.sh" ]; then
    log_error "cron-backup.sh not found at $PROJECT_ROOT/scripts/cron-backup.sh"
    exit 1
fi

if [ ! -x "$PROJECT_ROOT/scripts/cron-backup.sh" ]; then
    log_error "cron-backup.sh is not executable"
    log_info "Run: chmod +x $PROJECT_ROOT/scripts/cron-backup.sh"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/scripts/service-monitor.sh" ]; then
    log_error "service-monitor.sh not found at $PROJECT_ROOT/scripts/service-monitor.sh"
    log_error "This script will be created in the next step of Phase 5"
    exit 1
fi

if [ ! -x "$PROJECT_ROOT/scripts/service-monitor.sh" ]; then
    log_error "service-monitor.sh is not executable"
    log_info "Run: chmod +x $PROJECT_ROOT/scripts/service-monitor.sh"
    exit 1
fi

log_success "All required files found and executable"

# Check .env file
log_info "Checking .env configuration..."
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    log_error ".env file not found"
    exit 1
fi

# Source .env to check BACKUP_EXTERNAL_DIR
set -a
source "$PROJECT_ROOT/.env"
set +a

if [ -z "${BACKUP_EXTERNAL_DIR:-}" ]; then
    log_error "BACKUP_EXTERNAL_DIR not set in .env"
    log_info "Add to .env: BACKUP_EXTERNAL_DIR=/path/to/external/backups"
    exit 1
fi

log_success "BACKUP_EXTERNAL_DIR=$BACKUP_EXTERNAL_DIR"
log_info "BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30} (default: 30)"

# REQ-026: Capture DISPLAY and DBUS_SESSION_BUS_ADDRESS
log_info "Capturing environment variables for desktop notifications..."

CAPTURED_DISPLAY="${DISPLAY:-}"
CAPTURED_DBUS="${DBUS_SESSION_BUS_ADDRESS:-}"

if [ -z "$CAPTURED_DISPLAY" ]; then
    log_warning "DISPLAY not set - desktop notifications will not work"
    log_info "This is normal if running via SSH or without a GUI session"
else
    log_success "DISPLAY=$CAPTURED_DISPLAY"
fi

if [ -z "$CAPTURED_DBUS" ]; then
    log_warning "DBUS_SESSION_BUS_ADDRESS not set - desktop notifications may not work"
    log_info "This is normal if running via SSH or without a GUI session"
else
    log_success "DBUS_SESSION_BUS_ADDRESS=$CAPTURED_DBUS"
fi

# Build crontab entries
log_info "Building crontab entries..."

# REQ-025: Two backup entries (primary + catch-up)
CRON_BACKUP_PRIMARY="0 3 * * * DISPLAY=\"$CAPTURED_DISPLAY\" DBUS_SESSION_BUS_ADDRESS=\"$CAPTURED_DBUS\" $PROJECT_ROOT/scripts/cron-backup.sh >> $PROJECT_ROOT/logs/backup/cron-output.log 2>&1"
CRON_BACKUP_CATCHUP="0 */6 * * * DISPLAY=\"$CAPTURED_DISPLAY\" DBUS_SESSION_BUS_ADDRESS=\"$CAPTURED_DBUS\" $PROJECT_ROOT/scripts/cron-backup.sh --if-stale 24 >> $PROJECT_ROOT/logs/backup/cron-output.log 2>&1"

# REQ-030: Service monitor entry
CRON_SERVICE_MONITOR="*/5 * * * * $PROJECT_ROOT/scripts/service-monitor.sh >> $PROJECT_ROOT/logs/backup/service-monitor.log 2>&1"

echo ""
echo "========================================="
echo "Crontab Entries to Install"
echo "========================================="
echo ""
echo "1. Primary Backup (daily at 3 AM):"
echo "   $CRON_BACKUP_PRIMARY"
echo ""
echo "2. Catch-up Backup (every 6 hours, only if stale):"
echo "   $CRON_BACKUP_CATCHUP"
echo ""
echo "3. Service Monitor (every 5 minutes, defense-in-depth):"
echo "   $CRON_SERVICE_MONITOR"
echo ""

# Check for existing entries
log_info "Checking for existing cron entries..."
EXISTING_CRON=$(crontab -l 2>/dev/null || echo "")

FOUND_BACKUP=false
FOUND_MONITOR=false

if echo "$EXISTING_CRON" | grep -q "cron-backup.sh"; then
    FOUND_BACKUP=true
    log_warning "Found existing cron-backup.sh entries in crontab"
fi

if echo "$EXISTING_CRON" | grep -q "service-monitor.sh"; then
    FOUND_MONITOR=true
    log_warning "Found existing service-monitor.sh entry in crontab"
fi

if [ "$FOUND_BACKUP" = true ] || [ "$FOUND_MONITOR" = true ]; then
    echo ""
    log_warning "Existing entries found. These will be replaced with new entries."
    echo ""
fi

# Dry-run mode
if [ "$DRY_RUN" = true ]; then
    echo ""
    log_info "DRY-RUN mode: No changes will be made"
    log_info "Run without --dry-run to install cron entries"
    exit 0
fi

# Confirm with user (UX-004)
echo ""
echo "========================================="
echo "Confirmation Required"
echo "========================================="
echo ""
echo "This will modify your crontab. The following entries will be added:"
echo "  • Daily backup at 3 AM"
echo "  • Catch-up backup every 6 hours (if stale)"
echo "  • Service monitor every 5 minutes"
echo ""
echo "External drive: $BACKUP_EXTERNAL_DIR"
echo "Retention: ${BACKUP_RETENTION_DAYS:-30} days"
echo ""

read -p "Continue with installation? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    log_info "Installation cancelled by user"
    exit 0
fi

# Install crontab entries
log_info "Installing crontab entries..."

# Remove old entries first (if any)
TEMP_CRON=$(mktemp)
if [ -n "$EXISTING_CRON" ]; then
    echo "$EXISTING_CRON" | grep -v "cron-backup.sh" | grep -v "service-monitor.sh" > "$TEMP_CRON" || true
fi

# Add new entries
echo "# txtai automated backup - primary (3 AM daily)" >> "$TEMP_CRON"
echo "$CRON_BACKUP_PRIMARY" >> "$TEMP_CRON"
echo "" >> "$TEMP_CRON"
echo "# txtai automated backup - catch-up (every 6h if stale)" >> "$TEMP_CRON"
echo "$CRON_BACKUP_CATCHUP" >> "$TEMP_CRON"
echo "" >> "$TEMP_CRON"
echo "# txtai service monitor - defense-in-depth (every 5 min)" >> "$TEMP_CRON"
echo "$CRON_SERVICE_MONITOR" >> "$TEMP_CRON"

# Install new crontab
crontab "$TEMP_CRON"
rm "$TEMP_CRON"

log_success "Crontab entries installed successfully"

# Verify installation
log_info "Verifying installation..."
NEW_CRON=$(crontab -l 2>/dev/null || echo "")

if echo "$NEW_CRON" | grep -q "cron-backup.sh"; then
    log_success "Backup cron entries verified"
else
    log_error "Backup entries not found in crontab after installation"
    exit 1
fi

if echo "$NEW_CRON" | grep -q "service-monitor.sh"; then
    log_success "Service monitor entry verified"
else
    log_error "Service monitor entry not found in crontab after installation"
    exit 1
fi

echo ""
echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
log_success "Automated backups configured successfully"
echo ""
echo "Next Steps:"
echo "  1. Ensure external drive is mounted before 3 AM"
echo "  2. Monitor logs: tail -f $PROJECT_ROOT/logs/backup/cron-backup.log"
echo "  3. Check backup status: ls -lh $BACKUP_EXTERNAL_DIR"
echo ""
echo "Testing:"
echo "  • Test backup manually: $PROJECT_ROOT/scripts/cron-backup.sh"
echo "  • Test staleness check: $PROJECT_ROOT/scripts/cron-backup.sh --if-stale 24"
echo "  • View crontab: crontab -l"
echo ""
echo "Rollback (if needed):"
echo "  • Remove entries: crontab -e  # delete the txtai lines"
echo "  • Or disable: crontab -r  # removes entire crontab"
echo ""

# Final notes
if [ -z "$CAPTURED_DISPLAY" ]; then
    log_warning "Desktop notifications will NOT work (DISPLAY not set)"
    log_info "This is expected for headless/SSH setups"
    log_info "You can still monitor via:"
    log_info "  - Sentinel file: logs/backup/last-successful-backup"
    log_info "  - Failure marker: logs/backup/BACKUP_FAILED"
    log_info "  - Log file: logs/backup/cron-backup.log"
fi

exit 0
