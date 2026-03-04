#!/bin/bash
# Service monitor - defense-in-depth for untrapable SIGKILL (REQ-030)
# Runs every 5 minutes via cron
# Detects and restarts txtai services if they're unexpectedly stopped

# Detect project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Ensure log directory exists
mkdir -p "$PROJECT_ROOT/logs/backup"

LOG_FILE="$PROJECT_ROOT/logs/backup/service-monitor.log"

log() {
    echo "$(date -Iseconds) $*" >> "$LOG_FILE"
}

# Note: We removed the time-based maintenance window check (2 AM - 4 AM)
# because it created a race condition (CRITICAL-003).
# The service monitor now always checks if services should be running.
# If cron-backup.sh is managing services, it's fine - docker compose start
# on an already-running service is harmless and completes quickly.

# Detect Docker Compose command (v2 vs v1)
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    log "ERROR: Neither 'docker compose' nor 'docker-compose' found"
    exit 1
fi

# Change to project directory for docker compose commands
cd "$PROJECT_ROOT"

# Check txtai-api container (with timeout to prevent hangs)
TXTAI_RUNNING=false
if timeout 30s docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^txtai-api$"; then
    TXTAI_RUNNING=true
fi

# Check txtai-frontend container (with timeout to prevent hangs)
FRONTEND_RUNNING=false
if timeout 30s docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^txtai-frontend$"; then
    FRONTEND_RUNNING=true
fi

# Restart txtai-api if not running
if [ "$TXTAI_RUNNING" = false ]; then
    # Check if container exists (stopped vs doesn't exist)
    if timeout 30s docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^txtai-api$"; then
        log "WARNING: txtai-api container stopped unexpectedly, restarting..."
        if timeout 60s $DOCKER_COMPOSE start txtai 2>&1 | while read line; do log "  $line"; done; then
            # Verify restart
            if timeout 30s docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^txtai-api$"; then
                log "SUCCESS: txtai-api restarted"
            else
                log "ERROR: txtai-api restart failed after start command"
            fi
        else
            log "WARNING: 'docker compose start' failed, trying 'docker compose up -d --no-recreate'..."
            if timeout 60s $DOCKER_COMPOSE up -d --no-recreate txtai 2>&1 | while read line; do log "  $line"; done; then
                log "SUCCESS: txtai-api recreated"
            else
                log "ERROR: txtai-api recovery failed (both start and up failed)"
            fi
        fi
    else
        log "INFO: txtai-api container does not exist (not an error if services are down for maintenance)"
    fi
fi

# Restart txtai-frontend if not running
if [ "$FRONTEND_RUNNING" = false ]; then
    # Check if container exists (stopped vs doesn't exist)
    if timeout 30s docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^txtai-frontend$"; then
        log "WARNING: txtai-frontend container stopped unexpectedly, restarting..."
        if timeout 60s $DOCKER_COMPOSE start frontend 2>&1 | while read line; do log "  $line"; done; then
            # Verify restart
            if timeout 30s docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^txtai-frontend$"; then
                log "SUCCESS: txtai-frontend restarted"
            else
                log "ERROR: txtai-frontend restart failed after start command"
            fi
        else
            log "WARNING: 'docker compose start' failed, trying 'docker compose up -d --no-recreate'..."
            if timeout 60s $DOCKER_COMPOSE up -d --no-recreate frontend 2>&1 | while read line; do log "  $line"; done; then
                log "SUCCESS: txtai-frontend recreated"
            else
                log "ERROR: txtai-frontend recovery failed (both start and up failed)"
            fi
        fi
    else
        log "INFO: txtai-frontend container does not exist (not an error if services are down for maintenance)"
    fi
fi

# Exit successfully (cron will run again in 5 minutes)
exit 0
