# Backup Automation Test Suite (SPEC-042)

This directory contains comprehensive tests for the automated backup system.

## Test Organization

```
tests/
├── unit/backup/
│   └── test-cron-backup.sh          # Unit tests for validation functions (33 tests)
├── integration/backup/
│   └── test-edge-cases.sh           # Edge case tests from SPEC-042 (19 tests)
└── backup/
    └── README.md                     # This file
```

## Running Tests

### Quick Test (Recommended)
```bash
./scripts/test-backup-automation.sh --quick
```
Runs unit tests + edge case tests (~10 seconds, 51 tests)

### All Options
```bash
./scripts/test-backup-automation.sh           # Run all automated tests (default: unit + edge)
./scripts/test-backup-automation.sh --unit    # Run unit tests only (33 tests)
./scripts/test-backup-automation.sh --edge    # Run edge case tests only (19 tests)
./scripts/test-backup-automation.sh --all     # Run all tests including integration (future)
./scripts/test-backup-automation.sh --help    # Show usage
```

## Test Coverage

### Unit Tests (33 tests)

**Mount Validation (6 tests)**
- Mountpoint detection (mounted vs non-mounted)
- Writable directory checks
- Directory existence checks

**.env Validation (5 tests)**
- Syntax validation (unclosed quotes, malformed files)
- Command injection detection ($(), backticks)
- Required variable checks (BACKUP_EXTERNAL_DIR)
- Type validation (numeric BACKUP_RETENTION_DAYS)

**Staleness Check (5 tests)**
- Recent timestamp (<24h) vs stale (>24h)
- Corrupted sentinel file (defensive parsing)
- Missing sentinel (first backup)
- Future timestamp (clock skew detection)

**Expected Backup Size Calculation - DEF-004 (4 tests)**
- First backup (default 200MB)
- Subsequent backups (use last-backup-size sentinel)
- Free space requirement (3x expected size)
- Insufficient space detection

**File Count Tolerance - DEF-005 (5 tests)**
- Exact match (success)
- 1-2 file difference <5% (warning level)
- 3+ files or ≥5% difference (error level)
- Zero files in both (success)

**Stale Lock Detection (3 tests)**
- Fresh lock (<12h) - not stale
- Old lock (≥12h) - stale, should be removed
- Boundary case (exactly 12h)

**Archive Integrity (5 tests)**
- Valid tar.gz archive
- Corrupted archive detection
- Zero-byte file detection
- Missing file detection
- Archive size validation (>0 bytes)

### Edge Case Tests (19 tests)

**From SPEC-042:**
- EDGE-001: External drive not mounted (exit 2, skip with warning)
- EDGE-003: Concurrent backup runs (lock file prevents)
- EDGE-004: Corrupt sentinel file (defensive parsing, treat as stale)
- EDGE-011: First backup (no size sentinel, use default)
- EDGE-012: Command injection in .env (detect $(), backticks, unclosed quotes)
- EDGE-013: Corrupted archive (integrity check fails)
- EDGE-014: Stale lock >12h (remove and proceed)
- EDGE-015: BACKUP_EXTERNAL_DIR on root filesystem (reject)
- EDGE-016: Future timestamp (clock skew detection)
- EDGE-019: Special characters in filenames (null-terminated find)
- EDGE-020: Docker Compose version detection (v1 vs v2)
- EDGE-021: Simultaneous cron execution (lock prevents)

**Additional Tests:**
- Missing .env file detection
- BACKUP_RETENTION_DAYS=0 (keep all backups)
- Log directory creation

## Manual Testing Checklist

Some scenarios require manual verification:

### Production Workflow Testing

**Setup and Installation:**
- [ ] Run `./scripts/setup-cron-backup.sh --dry-run` - verify crontab entries preview
- [ ] Run `./scripts/setup-cron-backup.sh` - install cron entries with confirmation
- [ ] Verify three cron entries created: primary (3 AM), catch-up (every 6h), service monitor (every 5 min)
- [ ] Check environment variable capture: DISPLAY and DBUS_SESSION_BUS_ADDRESS

**Backup Execution:**
- [ ] Run `./scripts/cron-backup.sh` manually - verify successful backup
- [ ] Check sentinel file updated with ISO 8601 timestamp
- [ ] Check size sentinel updated with archive size (MB)
- [ ] Verify archive integrity: `tar -tzf <archive>` lists all contents
- [ ] Verify MANIFEST.txt includes all backup items

**Staleness and Catch-up:**
- [ ] Delete last-backup sentinel, run `./scripts/cron-backup.sh --if-stale 24` - verify backup runs
- [ ] With fresh sentinel, run `./scripts/cron-backup.sh --if-stale 24` - verify skip (exit 2)

**Failure Scenarios:**
- [ ] Unmount drive, run backup - verify skip (exit 2), log warning
- [ ] Remount drive, run backup - verify resumes normally
- [ ] Make backup.sh non-executable, run cron-backup.sh - verify failure marker created
- [ ] Fix permissions, run backup - verify failure marker removed

**Service Monitor (Defense-in-Depth):**
- [ ] Stop frontend container: `docker compose stop frontend`
- [ ] Wait 5 minutes, verify service monitor restarts frontend
- [ ] Check logs: `cat logs/backup/service-monitor.log`

**Retention Policy:**
- [ ] Create old test backups: `touch -d "40 days ago" /path/to/old-backup.tar.gz`
- [ ] Run cron-backup.sh with BACKUP_RETENTION_DAYS=30 - verify old backup deleted
- [ ] Verify recent backups (within 30 days) are preserved

**Full Restore:**
- [ ] Create test data in shared_uploads/, logs/frontend/archive/, and audit.jsonl
- [ ] Run backup: `./scripts/cron-backup.sh`
- [ ] Delete test data
- [ ] Run restore: `./scripts/restore.sh /path/to/backup.tar.gz`
- [ ] Verify all test data recovered

### Performance Validation

- [ ] Measure backup duration (should be <10 min for empty databases, expect 2-5 min)
- [ ] Measure service restart time after trap handler (should be <30s for trapable signals)
- [ ] SIGKILL test: Kill cron-backup.sh with `kill -9 <pid>`, verify service monitor restarts within 5 min

## Continuous Integration

To add these tests to CI:

```bash
# Add to .github/workflows/test.yml or similar
- name: Run backup automation tests
  run: ./scripts/test-backup-automation.sh --quick
```

## Test Maintenance

**When to update tests:**
- After modifying validation logic in cron-backup.sh
- After adding new edge cases to SPEC-042
- After discovering bugs in production

**Adding new tests:**
1. Unit tests: Add to `tests/unit/backup/test-cron-backup.sh`
2. Edge cases: Add to `tests/integration/backup/test-edge-cases.sh`
3. Update test counts in this README

## Test Results Summary

| Test Suite | Tests | Status | Coverage |
|------------|-------|--------|----------|
| Unit Tests | 33 | ✅ All Pass | Validation functions (100%) |
| Edge Cases | 19 | ✅ All Pass | Critical scenarios from SPEC-042 |
| **Total** | **52** | **✅ 100%** | **Comprehensive** |

## Known Limitations

- **EDGE-015** may skip on some test environments (root filesystem detection is system-dependent)
- Integration tests require Docker services running
- SIGKILL testing must be done manually (can't simulate reliably in automated tests)
- Performance validation requires production-like data volumes

## Troubleshooting

**Tests fail with permission errors:**
```bash
chmod +x tests/unit/backup/test-cron-backup.sh
chmod +x tests/integration/backup/test-edge-cases.sh
chmod +x scripts/test-backup-automation.sh
```

**Tests timeout:**
- Check Docker is running if integration tests are enabled
- Verify external drive is accessible if testing mount validation

**False positives/negatives:**
- Review test output for skipped tests
- Some edge cases may behave differently on different systems (documented in test output)
