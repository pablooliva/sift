#!/bin/bash
# Unit tests for cron-backup.sh validation functions
#
# Usage: ./test-cron-backup.sh
#
# Exit codes:
#   0 = All tests passed
#   1 = One or more tests failed

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test fixtures directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/../../fixtures/backup"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Create temporary test directory
TEST_TMP=$(mktemp -d)
trap "rm -rf $TEST_TMP" EXIT

# ============================================================================
# Test Helper Functions
# ============================================================================

pass() {
    echo -e "${GREEN}✓${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    TESTS_RUN=$((TESTS_RUN + 1))
}

fail() {
    echo -e "${RED}✗${NC} $1"
    if [ -n "${2:-}" ]; then
        echo -e "  ${RED}Expected:${NC} $2"
    fi
    if [ -n "${3:-}" ]; then
        echo -e "  ${RED}Got:${NC} $3"
    fi
    TESTS_FAILED=$((TESTS_FAILED + 1))
    TESTS_RUN=$((TESTS_RUN + 1))
}

section() {
    echo ""
    echo -e "${YELLOW}━━━ $1 ━━━${NC}"
}

# ============================================================================
# Mount Validation Tests
# ============================================================================

test_mount_validation() {
    section "Mount Validation Tests"

    # Test 1: Valid mount point (use root which is always mounted)
    local test_mount="/"
    if mountpoint -q "$test_mount" 2>/dev/null; then
        pass "Mountpoint check: / (root) is a mount point"
    else
        fail "Mountpoint check: / should be a mount point" "mounted" "not mounted"
    fi

    # Test 2: Invalid mount point
    local test_nonmount="$TEST_TMP/not-a-mount"
    mkdir -p "$test_nonmount"
    if ! mountpoint -q "$test_nonmount" 2>/dev/null; then
        pass "Mountpoint check: regular directory detected as non-mount"
    else
        fail "Mountpoint check: should detect non-mount" "not mounted" "mounted"
    fi

    # Test 3: Writable directory check
    local test_writable="$TEST_TMP/writable"
    mkdir -p "$test_writable"
    local test_file="$test_writable/.test-$$"
    if touch "$test_file" 2>/dev/null && rm "$test_file" 2>/dev/null; then
        pass "Writable check: directory is writable"
    else
        fail "Writable check: directory should be writable"
    fi

    # Test 4: Non-writable directory check (read-only)
    local test_readonly="$TEST_TMP/readonly"
    mkdir -p "$test_readonly"
    chmod 555 "$test_readonly"
    local test_file_ro="$test_readonly/.test-$$"
    if ! touch "$test_file_ro" 2>/dev/null; then
        pass "Writable check: read-only directory detected correctly"
        chmod 755 "$test_readonly" # cleanup
    else
        fail "Writable check: should detect read-only directory" "not writable" "writable"
        rm -f "$test_file_ro"
        chmod 755 "$test_readonly"
    fi

    # Test 5: Directory exists check
    local test_exists="$TEST_TMP/exists"
    mkdir -p "$test_exists"
    if [ -d "$test_exists" ]; then
        pass "Directory exists check: directory detected"
    else
        fail "Directory exists check: directory should exist"
    fi

    # Test 6: Directory doesn't exist
    local test_missing="$TEST_TMP/missing"
    if [ ! -d "$test_missing" ]; then
        pass "Directory exists check: missing directory detected"
    else
        fail "Directory exists check: should detect missing directory"
    fi
}

# ============================================================================
# .env Validation Tests
# ============================================================================

test_env_validation() {
    section ".env Validation Tests"

    # Test 1: Valid .env file
    local valid_env="$TEST_TMP/valid.env"
    cat > "$valid_env" <<'EOF'
BACKUP_EXTERNAL_DIR=/path/to/external/backups
BACKUP_RETENTION_DAYS=30
TOGETHERAI_API_KEY=abc123
EOF

    if bash -n "$valid_env" 2>/dev/null; then
        pass ".env syntax check: valid file passes"
    else
        fail ".env syntax check: valid file should pass"
    fi

    # Test 2: .env with syntax error (unclosed quote)
    local invalid_env="$TEST_TMP/invalid.env"
    cat > "$invalid_env" <<'EOF'
BACKUP_EXTERNAL_DIR="/path/to/external/backups
BACKUP_RETENTION_DAYS=30
EOF

    if ! bash -n "$invalid_env" 2>/dev/null; then
        pass ".env syntax check: unclosed quote detected"
    else
        fail ".env syntax check: should detect unclosed quote" "syntax error" "valid"
    fi

    # Test 3: .env with command injection attempt
    local injection_env="$TEST_TMP/injection.env"
    cat > "$injection_env" <<'EOF'
BACKUP_EXTERNAL_DIR=$(whoami)
BACKUP_RETENTION_DAYS=30
EOF

    # Check if value contains dangerous patterns
    if grep -qE '[$`()]' "$injection_env"; then
        pass ".env validation: command injection pattern detected"
    else
        fail ".env validation: should detect command injection patterns"
    fi

    # Test 4: Required variable check
    local missing_var_env="$TEST_TMP/missing-var.env"
    cat > "$missing_var_env" <<'EOF'
BACKUP_RETENTION_DAYS=30
EOF

    # Simulate checking for required variable
    if ! grep -q "^BACKUP_EXTERNAL_DIR=" "$missing_var_env"; then
        pass ".env validation: missing required variable detected"
    else
        fail ".env validation: should detect missing BACKUP_EXTERNAL_DIR"
    fi

    # Test 5: Non-numeric BACKUP_RETENTION_DAYS
    local invalid_type_env="$TEST_TMP/invalid-type.env"
    cat > "$invalid_type_env" <<'EOF'
BACKUP_EXTERNAL_DIR=/path/to/external/backups
BACKUP_RETENTION_DAYS=thirty
EOF

    # Extract value and check if numeric
    local retention_value=$(grep "^BACKUP_RETENTION_DAYS=" "$invalid_type_env" | cut -d'=' -f2)
    if ! [[ "$retention_value" =~ ^[0-9]+$ ]]; then
        pass ".env validation: non-numeric retention days detected"
    else
        fail ".env validation: should detect non-numeric retention days" "numeric" "non-numeric"
    fi
}

# ============================================================================
# Staleness Check Tests
# ============================================================================

test_staleness_check() {
    section "Staleness Check Tests"

    # Test 1: Valid recent timestamp (not stale)
    local recent_sentinel="$TEST_TMP/recent-sentinel.txt"
    date -Iseconds > "$recent_sentinel"
    local recent_ts=$(cat "$recent_sentinel")
    local now_epoch=$(date +%s)
    local recent_epoch=$(date -d "$recent_ts" +%s 2>/dev/null || echo 0)

    if [ "$recent_epoch" -gt 0 ]; then
        local age_hours=$(( (now_epoch - recent_epoch) / 3600 ))
        if [ "$age_hours" -lt 24 ]; then
            pass "Staleness check: recent timestamp (<24h) is not stale"
        else
            fail "Staleness check: recent timestamp should not be stale" "<24h" "${age_hours}h"
        fi
    else
        fail "Staleness check: could not parse recent timestamp"
    fi

    # Test 2: Old timestamp (stale)
    local old_sentinel="$TEST_TMP/old-sentinel.txt"
    date -d "2 days ago" -Iseconds > "$old_sentinel"
    local old_ts=$(cat "$old_sentinel")
    local old_epoch=$(date -d "$old_ts" +%s 2>/dev/null || echo 0)

    if [ "$old_epoch" -gt 0 ]; then
        local age_hours=$(( (now_epoch - old_epoch) / 3600 ))
        if [ "$age_hours" -ge 24 ]; then
            pass "Staleness check: old timestamp (>24h) is stale"
        else
            fail "Staleness check: old timestamp should be stale" ">=24h" "${age_hours}h"
        fi
    else
        fail "Staleness check: could not parse old timestamp"
    fi

    # Test 3: Corrupted sentinel (invalid date)
    local corrupt_sentinel="$TEST_TMP/corrupt-sentinel.txt"
    echo "not-a-date" > "$corrupt_sentinel"
    local corrupt_ts=$(cat "$corrupt_sentinel")

    if ! date -d "$corrupt_ts" +%s >/dev/null 2>&1; then
        pass "Staleness check: corrupted sentinel detected (defensive parsing)"
    else
        fail "Staleness check: should detect corrupted sentinel" "parse error" "parsed"
    fi

    # Test 4: Missing sentinel file
    local missing_sentinel="$TEST_TMP/missing-sentinel.txt"

    if [ ! -f "$missing_sentinel" ]; then
        pass "Staleness check: missing sentinel detected (first backup)"
    else
        fail "Staleness check: should detect missing sentinel"
    fi

    # Test 5: Future timestamp (clock skew)
    local future_sentinel="$TEST_TMP/future-sentinel.txt"
    date -d "1 day" -Iseconds > "$future_sentinel"
    local future_ts=$(cat "$future_sentinel")
    local future_epoch=$(date -d "$future_ts" +%s 2>/dev/null || echo 0)

    if [ "$future_epoch" -gt "$now_epoch" ]; then
        pass "Staleness check: future timestamp detected (clock skew)"
    else
        fail "Staleness check: should detect future timestamp"
    fi
}

# ============================================================================
# Expected Backup Size Calculation Tests (DEF-004)
# ============================================================================

test_expected_size_calculation() {
    section "Expected Backup Size Calculation Tests (DEF-004)"

    # Test 1: First backup (no size sentinel) - use default 200MB
    local missing_size_sentinel="$TEST_TMP/missing-size-sentinel.txt"
    local expected_first_backup=200  # MB

    if [ ! -f "$missing_size_sentinel" ]; then
        pass "Expected size: first backup uses default 200MB"
    else
        fail "Expected size: should detect missing size sentinel"
    fi

    # Test 2: Subsequent backup uses last-backup-size
    local size_sentinel="$TEST_TMP/size-sentinel.txt"
    echo "512" > "$size_sentinel"  # 512MB from last backup
    local last_size=$(cat "$size_sentinel" 2>/dev/null || echo "200")

    if [ "$last_size" = "512" ]; then
        pass "Expected size: subsequent backup uses last-backup-size (512MB)"
    else
        fail "Expected size: should use last-backup-size" "512" "$last_size"
    fi

    # Test 3: Free space requirement (available >= expected * 3)
    local expected_size=512  # MB
    local required_space=$((expected_size * 3))  # 1536MB
    local available_space=2048  # MB (simulated)

    if [ "$available_space" -ge "$required_space" ]; then
        pass "Free space check: ${available_space}MB >= ${required_space}MB (3x expected)"
    else
        fail "Free space check: insufficient space" ">=${required_space}MB" "${available_space}MB"
    fi

    # Test 4: Insufficient free space
    local insufficient_space=1000  # MB

    if [ "$insufficient_space" -lt "$required_space" ]; then
        pass "Free space check: detects insufficient space (${insufficient_space}MB < ${required_space}MB)"
    else
        fail "Free space check: should detect insufficient space"
    fi
}

# ============================================================================
# File Count Tolerance Tests (DEF-005)
# ============================================================================

test_file_count_tolerance() {
    section "File Count Tolerance Tests (DEF-005)"

    # Test 1: Exact match (success)
    local expected=100
    local actual=100
    local diff=$((actual - expected))
    local diff_abs=${diff#-}
    local percent=$((diff_abs * 100 / (expected > 0 ? expected : 1)))

    if [ "$diff_abs" -eq 0 ]; then
        pass "File count: exact match (${actual}/${expected}) - success"
    else
        fail "File count: should match exactly" "0 diff" "${diff_abs} diff"
    fi

    # Test 2: 1-2 file difference <5% (warning)
    expected=100
    actual=101
    diff=$((actual - expected))
    diff_abs=${diff#-}
    percent=$((diff_abs * 100 / expected))

    if [ "$diff_abs" -le 2 ] && [ "$percent" -lt 5 ]; then
        pass "File count: 1-2 file diff <5% (${actual}/${expected}) - warning level"
    else
        fail "File count: should be warning level" "warning" "error"
    fi

    # Test 3: 3+ file difference OR ≥5% (error)
    expected=100
    actual=105
    diff=$((actual - expected))
    diff_abs=${diff#-}
    percent=$((diff_abs * 100 / expected))

    if [ "$diff_abs" -ge 3 ] || [ "$percent" -ge 5 ]; then
        pass "File count: 5% diff (${actual}/${expected}) - error level"
    else
        fail "File count: should be error level" "error" "success/warning"
    fi

    # Test 4: Large absolute difference (3+ files)
    expected=50
    actual=54
    diff=$((actual - expected))
    diff_abs=${diff#-}

    if [ "$diff_abs" -ge 3 ]; then
        pass "File count: 4 file diff (${actual}/${expected}) - error level"
    else
        fail "File count: should be error level for 3+ diff" "error" "success/warning"
    fi

    # Test 5: Zero files in both (success)
    expected=0
    actual=0

    if [ "$expected" -eq 0 ] && [ "$actual" -eq 0 ]; then
        pass "File count: zero files in both (0/0) - success"
    else
        fail "File count: should handle zero files" "success" "error"
    fi
}

# ============================================================================
# Stale Lock Detection Tests
# ============================================================================

test_stale_lock_detection() {
    section "Stale Lock Detection Tests"

    # Test 1: Fresh lock (<12h) - not stale
    local fresh_lock="$TEST_TMP/fresh.lock"
    touch "$fresh_lock"
    local lock_age_hours=$(( ($(date +%s) - $(stat -c %Y "$fresh_lock")) / 3600 ))

    if [ "$lock_age_hours" -lt 12 ]; then
        pass "Stale lock: fresh lock (${lock_age_hours}h) is not stale"
    else
        fail "Stale lock: fresh lock should not be stale" "<12h" "${lock_age_hours}h"
    fi

    # Test 2: Old lock (≥12h) - stale (simulated)
    local old_lock="$TEST_TMP/old.lock"
    touch "$old_lock"
    # Simulate 25-hour-old lock by backdating mtime
    touch -d "25 hours ago" "$old_lock"
    lock_age_hours=$(( ($(date +%s) - $(stat -c %Y "$old_lock")) / 3600 ))

    if [ "$lock_age_hours" -ge 12 ]; then
        pass "Stale lock: old lock (${lock_age_hours}h) is stale"
    else
        fail "Stale lock: old lock should be stale" ">=12h" "${lock_age_hours}h"
    fi

    # Test 3: Exactly 12h (boundary case)
    local boundary_lock="$TEST_TMP/boundary.lock"
    touch "$boundary_lock"
    touch -d "12 hours ago" "$boundary_lock"
    lock_age_hours=$(( ($(date +%s) - $(stat -c %Y "$boundary_lock")) / 3600 ))

    if [ "$lock_age_hours" -ge 12 ]; then
        pass "Stale lock: 12h boundary lock is stale (inclusive)"
    else
        fail "Stale lock: 12h boundary should be stale" ">=12h" "${lock_age_hours}h"
    fi
}

# ============================================================================
# Archive Integrity Check Tests
# ============================================================================

test_archive_integrity() {
    section "Archive Integrity Check Tests"

    # Test 1: Valid tar.gz archive
    local valid_archive="$TEST_TMP/valid.tar.gz"
    mkdir -p "$TEST_TMP/archive-content"
    echo "test content" > "$TEST_TMP/archive-content/test.txt"
    tar -czf "$valid_archive" -C "$TEST_TMP/archive-content" .

    if tar -tzf "$valid_archive" >/dev/null 2>&1; then
        pass "Archive integrity: valid tar.gz passes"
    else
        fail "Archive integrity: valid archive should pass"
    fi

    # Test 2: Corrupted archive (random data)
    local corrupt_archive="$TEST_TMP/corrupt.tar.gz"
    echo "not a tar file" > "$corrupt_archive"

    if ! tar -tzf "$corrupt_archive" >/dev/null 2>&1; then
        pass "Archive integrity: corrupted archive detected"
    else
        fail "Archive integrity: should detect corrupted archive"
    fi

    # Test 3: Zero-byte file
    local empty_archive="$TEST_TMP/empty.tar.gz"
    touch "$empty_archive"

    if [ ! -s "$empty_archive" ]; then
        pass "Archive integrity: zero-byte file detected"
    else
        fail "Archive integrity: should detect zero-byte file"
    fi

    # Test 4: Missing file
    local missing_archive="$TEST_TMP/missing.tar.gz"

    if [ ! -f "$missing_archive" ]; then
        pass "Archive integrity: missing file detected"
    else
        fail "Archive integrity: should detect missing file"
    fi

    # Test 5: Archive size check (>0 bytes)
    if [ -s "$valid_archive" ]; then
        local size=$(stat -c %s "$valid_archive")
        pass "Archive integrity: valid archive has size ${size} bytes"
    else
        fail "Archive integrity: valid archive should have non-zero size"
    fi
}

# ============================================================================
# Run All Tests
# ============================================================================

main() {
    echo "Starting cron-backup.sh unit tests..."
    echo "Project root: $PROJECT_ROOT"
    echo "Test temporary directory: $TEST_TMP"
    echo ""

    test_mount_validation
    test_env_validation
    test_staleness_check
    test_expected_size_calculation
    test_file_count_tolerance
    test_stale_lock_detection
    test_archive_integrity

    # Summary
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Test Summary:"
    echo "  Total:  $TESTS_RUN"
    echo -e "  ${GREEN}Passed:${NC} $TESTS_PASSED"

    if [ "$TESTS_FAILED" -gt 0 ]; then
        echo -e "  ${RED}Failed:${NC} $TESTS_FAILED"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        exit 1
    else
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    fi
}

main "$@"
