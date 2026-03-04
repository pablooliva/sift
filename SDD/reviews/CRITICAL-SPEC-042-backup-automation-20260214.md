# Critical Review: SPEC-042-backup-automation

**Date:** 2026-02-14
**Reviewer:** Claude Sonnet 4.5 (adversarial review)
**Artifact:** `SDD/requirements/SPEC-042-backup-automation.md`
**Phase:** Planning/Specification

## Executive Summary

The specification is **comprehensive but contains critical flaws** that would cause implementation problems and production failures. Most notably: (1) the core assumption that `trap cleanup EXIT` handles "ANY exit" is **false** — SIGKILL cannot be trapped, creating an unmitigated service outage risk; (2) the requirement for "2x expected backup size" free space is **unimplementable** because "expected" is never defined; (3) missing validation for `.env` file syntax errors would cause cryptic failures. Additionally, 7 edge cases are missing, 8 failure scenarios are unspecified, 4 requirements are ambiguous/untestable, and 9 new risks were identified. **Recommendation: REVISE BEFORE PROCEEDING** — address critical findings, clarify ambiguities, add missing scenarios.

**Severity: HIGH** — Critical design flaw (untrapable SIGKILL), unimplementable requirement (undefined "expected size"), and multiple high-severity gaps that would cause production issues.

---

## Critical Findings

### 1. CRITICAL: SIGKILL Cannot Be Trapped

**Finding:**
The entire specification assumes `trap cleanup EXIT` handles "ANY exit" (REQ-006, EDGE-002, RISK-001 mitigation, implementation notes). This is **fundamentally false**. SIGKILL (kill -9) and SIGSTOP cannot be trapped in bash.

**Evidence:**
- REQ-006: "Wrapper must use `trap cleanup EXIT` to guarantee service restart on **ANY exit**"
- EDGE-002: "Wrapper's trap catches **ANY exit** (success, failure, kill signal)"
- RISK-001 mitigation: "trap guarantees restart on **ANY exit** (success, failure, SIGTERM, **SIGKILL**)"
- Implementation notes: "trap cleanup EXIT # ... Now errors will trigger EXIT, which runs cleanup"

**Reality:**
```bash
# This is TRUE:
trap cleanup EXIT  # Catches: normal exit, SIGTERM, SIGINT, errors with 'set -e'

# This is FALSE:
# SIGKILL (kill -9) cannot be trapped
# SIGSTOP (kill -STOP) cannot be trapped
# OOM killer sends SIGKILL → services stay down
```

**Impact:**
- If user or system kills backup with `kill -9`, services stay stopped indefinitely
- OOM killer (out of memory) sends SIGKILL → untrapable
- Docker stop with timeout sends SIGKILL after grace period → untrapable
- This is the **exact CRITICAL risk** identified in RESEARCH-042 Finding #1, but the mitigation is incomplete

**Why This Matters:**
The research identified "services left stopped" as CRITICAL severity. The spec claims to solve it with trap handlers, but the solution has a known failure mode. This gives false confidence.

**Recommendation:**
1. **Rewrite REQ-006** to clarify: "trap handles most exits (SIGTERM, SIGINT, errors) but **cannot** handle SIGKILL"
2. **Add RISK-011**: SIGKILL leaves services stopped (CRITICAL severity)
   - Mitigation: Systemd watchdog, separate monitoring script, or "cron job checks service status every 5 min and restarts if down"
3. **Add FAIL-009**: Backup killed with SIGKILL
   - Expected behavior: Services stay stopped (trap doesn't run)
   - Recovery: Separate monitoring detects and restarts services
4. **Update EDGE-002** to test SIGTERM (trapable), not just "kill"
5. **Add new requirement REQ-025**: Separate service health monitor checks every 5 minutes, restarts if down (defense-in-depth)

---

### 2. CRITICAL: "Expected Backup Size" Is Undefined

**Finding:**
REQ-016 and EDGE-007 require checking for "2x expected backup size" free space before backup, but **never define what "expected" means**.

**Evidence:**
- REQ-016: "Wrapper must check minimum free space **(2x expected backup size)** before backup"
- EDGE-007: "If less than **2x expected backup size (200MB initially)**, log error and skip backup"

**Questions:**
- Is "expected" hardcoded to 200MB forever?
- Is "expected" the size of the last backup (but first backup has no previous)?
- Is "expected" the current `du -sh` of source directories (but adds processing time)?
- Does "expected" grow with actual data or stay at 200MB even when backups are 2GB?

**Impact:**
- If hardcoded to 200MB: Check becomes useless when backups grow to 1GB (need 2GB free, but check only requires 400MB)
- If based on last backup: First backup has no previous reference
- If based on current du: Adds processing time and doesn't account for compression ratio

**The spec itself acknowledges this contradiction:**
- EDGE-007: "200MB initially" (implies it changes, but doesn't say how)
- Data Size Notes: "50-100MB compressed initially, could grow to 500MB+ with media"
- REQ-016: No definition of how to calculate "expected"

**Recommendation:**
1. **Add REQ-016a**: Define "expected backup size" calculation:
   ```
   if [ -f "$SENTINEL_DIR/last-backup-size" ]; then
       EXPECTED_SIZE=$(cat "$SENTINEL_DIR/last-backup-size")
   else
       EXPECTED_SIZE=209715200  # 200MB default for first run
   fi
   MIN_FREE=$((EXPECTED_SIZE * 2))
   ```
2. **Add REQ-016b**: Update `last-backup-size` sentinel after each successful backup with actual archive size
3. **Update EDGE-007** to specify the above logic
4. **Add EDGE-011**: First backup (no previous size) uses 200MB default

---

### 3. HIGH: Missing .env Validation

**Finding:**
REQ-008 requires sourcing `.env` with `set -a`, but **no requirement validates .env syntax** before sourcing. A malformed .env (syntax error, unclosed quote, invalid bash) will cause cryptic failures.

**Evidence:**
- REQ-008: "Wrapper must source `.env` with `set -a` pattern for child process variable inheritance"
- Implementation notes show: `source .env` with no error handling
- No requirement for validating BACKUP_EXTERNAL_DIR format, BACKUP_RETENTION_DAYS is numeric, etc.

**Scenarios Not Handled:**
```bash
# .env examples that break sourcing:
BACKUP_EXTERNAL_DIR="/path/with/unclosed/quote
BACKUP_RETENTION_DAYS=thirty  # Not a number
BACKUP_EXTERNAL_DIR=$(rm -rf /)  # Command injection
export BACKUP_EXTERNAL_DIR=/path  # 'export' prefix will work but inconsistent with research
```

**Impact:**
- `source .env` fails with cryptic error: "unexpected EOF", "command not found"
- Backup doesn't run, but error message is unhelpful
- User doesn't know if it's a .env syntax error or something else
- BACKUP_RETENTION_DAYS=thirty could cause `find` command to fail unexpectedly

**Recommendation:**
1. **Add REQ-026**: Validate `.env` file before sourcing:
   - File exists and is readable
   - Required variables present (BACKUP_EXTERNAL_DIR)
   - BACKUP_RETENTION_DAYS is numeric (if present)
   - Test-source in subshell to catch syntax errors: `(set -a; source .env; set +a) 2>/dev/null`
2. **Add FAIL-010**: .env file malformed or missing
   - Expected: Clear error message "BACKUP_EXTERNAL_DIR not set in .env" or ".env syntax error at line X"
   - Exit code 1, failure marker created
3. **Add EDGE-012**: .env contains command injection attempts
   - Expected: Validation catches and rejects

---

### 4. HIGH: No Backup Verification (Archive Integrity)

**Finding:**
REQ-011 updates sentinel file on "success", but success is defined as `backup.sh` exiting with code 0. **No requirement verifies the backup archive actually exists, is non-empty, or is valid.**

**Evidence:**
- REQ-011: "Wrapper must update sentinel file (`logs/backup/last-successful-backup`) on success"
- No requirement to check if `backup_YYYYMMDD_HHMMSS.tar.gz` file exists
- No requirement to verify archive is non-zero size
- No requirement to test archive validity (e.g., `tar -tzf` to list contents)

**Scenarios Not Handled:**
- backup.sh has a bug, exits 0 but doesn't create archive → sentinel updated, user thinks backup succeeded
- Archive created but corrupted (disk error during write, tar bug) → sentinel updated, restore fails months later
- Archive created but empty (0 bytes or missing content) → sentinel updated, no actual backup

**Impact:**
- False sense of security: sentinel says "backup succeeded 2 hours ago" but no valid backup exists
- Discovered only during restore, potentially months later
- Violates the principle "trust but verify"

**Recommendation:**
1. **Add REQ-027**: Verify backup archive after backup.sh completes:
   - Archive file exists at expected path
   - Archive size > 1MB (sanity check, even empty DBs compress to ~50MB)
   - Archive passes `tar -tzf` integrity check (can list contents without error)
   - MANIFEST.txt exists inside archive
2. **Update REQ-011**: Only update sentinel if backup.sh exits 0 **AND** archive verification passes
3. **Add FAIL-011**: Archive verification fails
   - Expected: Log error "Archive created but failed integrity check", failure marker, no sentinel update
4. **Add EDGE-013**: Archive created but corrupted mid-write
   - Expected: Integrity check catches, marked as failure

---

### 5. HIGH: File Count Mismatch Threshold Undefined

**Finding:**
REQ-001a requires verifying `shared_uploads/` source and backup file counts match, but **doesn't define "match"**. Is 1 file different acceptable? 10%? 50%?

**Evidence:**
- REQ-001a: "After backing up `shared_uploads/`, verify source and backup file counts **match** (detect permission issues)"
- Implementation notes: `if [ "$SRC_COUNT" -ne "$DST_COUNT" ]` — this is exact match (0 tolerance)
- EDGE-005: "If counts differ, log warning" — but how much difference is a warning vs. error?

**Ambiguity:**
- 100 files in source, 99 in backup → Is this a warning or error?
- 0 files in source, 0 in backup → Is this success? (Yes, but should be documented)
- 1000 files in source, 500 in backup → Is this just a warning? (Should be critical!)

**Impact:**
- Exact match (0 tolerance) might be too strict: race conditions during backup could cause harmless differences
- But too loose (50% tolerance) would miss serious permission issues
- No guidance for implementer on what threshold is acceptable

**Recommendation:**
1. **Add REQ-001b**: Define file count match tolerance:
   - 0 files in both → success (empty directory is valid)
   - SRC_COUNT == DST_COUNT → success
   - 1-2 file difference AND <5% of total → warning (possible race condition)
   - 3+ file difference OR >5% of total → error (likely permission issue)
2. **Update EDGE-005** to test both warning and error thresholds
3. **Add FAIL-012**: Severe file count mismatch (>5% or >10 files)
   - Expected: Error logged, backup marked as failed (partial backup is not valid)

---

### 6. MEDIUM: Lock File Staleness Not Handled

**Finding:**
REQ-009 requires lock file to prevent concurrent runs, but **no requirement for detecting and cleaning stale locks**. If backup crashes (e.g., OOM killer SIGKILL), lock file stays forever and all future backups are blocked.

**Evidence:**
- REQ-009: "Wrapper must use lock file (`flock`) on local filesystem to prevent concurrent runs"
- FAIL-003 says "or manually remove stale lock file if crashed" — this is a manual recovery, not automatic
- No requirement for age-based stale lock detection

**Scenarios:**
- Backup process killed with SIGKILL (OOM, `kill -9`) → lock file never released
- All future backups skip with "Lock held" message
- User doesn't notice for days/weeks (logs aren't actively monitored)
- Backup gap grows, data loss risk increases

**Comparison:**
- systemd uses timeout-based locks
- Many production systems use PID-in-lockfile + check if PID exists
- flock with timeout (but bash's flock doesn't support timeout directly)

**Recommendation:**
1. **Add REQ-028**: Stale lock detection
   - If lock file age >12 hours (2x max expected backup duration), consider stale
   - Check if process holding lock still exists (PID in lock file + `kill -0 $PID`)
   - If stale, remove and log warning "Removed stale lock from crashed backup"
2. **Update FAIL-003** to include automatic stale lock detection, not just manual removal
3. **Add EDGE-014**: Lock file left from crashed backup (>12h old)
   - Expected: Detected as stale, removed, backup proceeds with warning

**Alternative (simpler):**
- Use `flock --timeout 60` (wait up to 60 seconds, then fail)
- No PID tracking needed, just timeout

---

### 7. MEDIUM: No Validation of BACKUP_EXTERNAL_DIR

**Finding:**
REQ-023 says `BACKUP_EXTERNAL_DIR` is required, but **no requirement validates it's actually a directory, writable, on external drive, etc.**

**Evidence:**
- REQ-023: "`.env` must include `BACKUP_EXTERNAL_DIR` (required)"
- REQ-004: "Wrapper must validate external drive is mounted" — but this checks the mount point, not BACKUP_EXTERNAL_DIR
- No requirement that BACKUP_EXTERNAL_DIR is a subdirectory of the mount point

**Scenarios Not Handled:**
- `BACKUP_EXTERNAL_DIR=/tmp/backups` (on root filesystem, not external drive) → defeats entire purpose
- `BACKUP_EXTERNAL_DIR=/path/to/external/backups/backup_20260214.tar.gz` (points to a file, not directory)
- `BACKUP_EXTERNAL_DIR=/path/to/external` (exists but not writable)
- `BACKUP_EXTERNAL_DIR=/path/to/external` (wrong drive)

**Impact:**
- Backups silently go to wrong location (e.g., /tmp on root filesystem)
- Fills up root filesystem instead of external drive
- Defeats the "offsite-adjacent" protection goal

**Recommendation:**
1. **Add REQ-029**: Validate BACKUP_EXTERNAL_DIR on every run:
   - Is a directory (not a file)
   - Is writable (can create test file)
   - Is on the external drive mount point (starts with `/path/to/external`)
2. **Update REQ-004** to include BACKUP_EXTERNAL_DIR validation, not just mount point
3. **Add FAIL-013**: BACKUP_EXTERNAL_DIR invalid
   - Expected: Clear error "BACKUP_EXTERNAL_DIR points to root filesystem, not external drive"
   - Exit code 1, failure marker created
4. **Add EDGE-015**: BACKUP_EXTERNAL_DIR misconfigured to root filesystem
   - Expected: Validation catches, backup skipped with error

---

### 8. MEDIUM: Inconsistent Exit Codes

**Finding:**
FAIL-001 (intentional skip) uses exit code 0, but FAIL-008 (service restart failed) uses exit code 1. Both are failure conditions, so why different codes?

**Evidence:**
- FAIL-001: "Expected behavior: ... Exit code **0** (intentional skip, not an error)"
- FAIL-002: "Exit code **1**"
- FAIL-005: "Exit code **1**"
- FAIL-008: "Exit code **1** (backup may have succeeded, but services down is a failure)"

**Confusion:**
- If cron monitoring checks exit codes, exit 0 means "success" in unix convention
- But drive-not-mounted is not a success, it's a failure (backup didn't happen)
- Inconsistent with standard cron monitoring tools that alert on non-zero exit

**Best Practice:**
- Exit 0: Actual success (backup created, verified, sentinel updated)
- Exit 1: Error (backup failed, should alert)
- Exit 2: Intentional skip (not an error, but not success either)

**Recommendation:**
1. **Add REQ-030**: Standardize exit codes
   - 0 = Success (backup completed and verified)
   - 1 = Failure (error occurred, alert needed)
   - 2 = Intentional skip (drive unmounted, lock held, staleness check says not needed)
2. **Update FAIL-001, FAIL-003** to use exit 2
3. **Update FAIL-002, FAIL-005, FAIL-008** to confirm exit 1
4. Document exit codes in README for cron monitoring setup

---

## Ambiguities That Will Cause Problems

### AMB-001: ISO 8601 Timestamp Format

**Requirement:** UX-001: "Sentinel file timestamp must be human-readable ISO 8601 format"

**Ambiguity:** ISO 8601 has multiple valid formats:
- `2026-02-14T15:30:45-05:00` (with timezone)
- `2026-02-14T15:30:45Z` (UTC)
- `2026-02-14T15:30:45` (no timezone)
- `2026-02-14T15:30:45.123456` (with microseconds)

**Why It Matters:**
- `date -Iseconds` produces `2026-02-14T15:30:45-05:00` (with timezone)
- Parsing with `date -d` handles all variants, but should be specified for consistency
- Different formats make log analysis harder

**Recommendation:**
- **Clarify UX-001**: Use `date -Iseconds` format (RFC 3339 profile of ISO 8601 with timezone)
- **Example**: `2026-02-14T15:30:45-05:00`

---

### AMB-002: "Services Were Running" Definition

**Requirement:** REQ-007: "Wrapper must check if services were running before stopping them (only restart if we stopped them)"

**Ambiguity:**
- Does "services" mean BOTH txtai AND frontend, or EITHER?
- What if txtai is running but frontend is stopped?
- What if containers exist but are paused/restarting?

**Why It Matters:**
- Trap handler needs to know which services to restart
- Edge case: user manually stopped frontend for debugging, backup shouldn't restart it

**Recommendation:**
- **Clarify REQ-007**: "Check status of txtai AND frontend independently. Only restart the ones that were running."
- **Add logic**: Track `TXTAI_WAS_RUNNING` and `FRONTEND_WAS_RUNNING` separately
- **Update trap handler**:
  ```bash
  [ "$TXTAI_WAS_RUNNING" = true ] && docker compose start txtai
  [ "$FRONTEND_WAS_RUNNING" = true ] && docker compose start frontend
  ```

---

### AMB-003: "Backup Succeeded" Definition

**Requirement:** Multiple (REQ-011, REQ-015, FAIL-002, FAIL-007)

**Ambiguity:**
- Does "success" mean backup.sh exited 0?
- Or does it mean archive exists?
- Or does it mean archive is verified valid?
- Or does it mean retention cleanup also succeeded?

**Why It Matters:**
- REQ-015: "run backup BEFORE applying retention (ensure new backup exists before deleting old)"
- But what if backup.sh exits 0, archive exists, then retention fails? Is the overall run a success or failure?
- FAIL-007: "Retention cleanup fails ... Backup considered successful" — this contradicts FAIL-002 and FAIL-005 which mark failures as exit 1

**Recommendation:**
- **Add DEF-001 (Definition)**: "Backup success" means:
  1. backup.sh exited with code 0
  2. Archive file exists at expected path
  3. Archive passes integrity check (tar -tzf)
  4. Sentinel file updated
- **Add DEF-002**: "Overall run success" means backup succeeded AND retention succeeded (or was skipped)
- **Clarify FAIL-007**: Retention failure downgrades overall run to "partial success" (exit 0 but warning logged)

---

### AMB-004: Lock Staleness Timeout

**Requirement:** FAIL-003: "manually remove stale lock file if crashed"

**Ambiguity:**
- How long before a lock is considered stale?
- What if backup legitimately takes 8 hours (huge database)?

**Recommendation:**
- **Add REQ-028** (from finding #6 above): Stale lock timeout = 12 hours (2x expected max)

---

## Missing Edge Cases

### EDGE-011: .env File Malformed (covered in finding #3)

### EDGE-012: Backup Archive Verification Fails (covered in finding #4)

### EDGE-013: System Time Goes Backwards

**Scenario:** NTP correction, timezone change, user manually sets clock back

**Impact:**
- Staleness check breaks: sentinel says "last backup: 2026-02-15", current time "2026-02-14" → negative age
- Retention cleanup could delete all backups (all appear "in the future")
- BACKUP_FAILED marker timestamp could be in the future

**Recommendation:**
- **Add EDGE-016**: Detect negative time difference in staleness check
  - If sentinel timestamp > current time, treat as stale (assume clock issue, run backup)
  - Log warning "Sentinel file timestamp is in the future, possible clock skew"

---

### EDGE-014: External Drive Mounted Read-Only

**Scenario:** Filesystem errors, emergency read-only remount, USB issue

**Impact:**
- `mountpoint -q` succeeds (drive IS mounted)
- `[ -w "$BACKUP_EXTERNAL_DIR" ]` fails (not writable)
- But what if this check is missing? backup.sh tries to write, fails cryptically

**Recommendation:**
- **Add EDGE-017**: Mount point exists but read-only
- **Update REQ-004**: Mount validation must include write test (create/delete temp file)

---

### EDGE-015: System Runs Out of Inodes (Not Just Disk Space)

**Scenario:** Many small files on external drive (previous backups, other data)

**Impact:**
- Free space check passes (GB available)
- tar fails with "No space left on device" (actually "no inodes left")
- Cryptic error, backup fails

**Recommendation:**
- **Add EDGE-018**: Inode exhaustion
- **Add REQ-031**: Check free inodes in addition to free space
  - `df -i "$BACKUP_EXTERNAL_DIR"` to get IAvail%
  - Require >10% inodes free

---

### EDGE-016: Filenames with Special Characters in shared_uploads/

**Scenario:** User uploads file named `file\nwith\nnewlines.pdf` or `file with spaces and "quotes".mp4`

**Impact:**
- File count check using `find | wc -l` might miscount (newlines in filenames)
- `cp -r` might fail on certain characters
- Archive creation might fail

**Recommendation:**
- **Add EDGE-019**: Filenames with newlines, quotes, special characters
- **Update file count verification**: Use `find -print0 | wc -l` (null-terminated, handles newlines)

---

### EDGE-017: Docker Compose Command Syntax Changes

**Scenario:** System upgraded from `docker-compose` (v1) to `docker compose` (v2)

**Impact:**
- Wrapper uses `docker compose` but system only has `docker-compose`
- Commands fail, backup doesn't run
- Or vice versa

**Recommendation:**
- **Add EDGE-020**: Docker Compose version compatibility
- **Add logic**: Try `docker compose` first, fall back to `docker-compose` if command not found

---

### EDGE-018: Both Primary and Catch-up Cron Fire Simultaneously

**Scenario:** System suspended/resumed at exactly 3:00 AM when 6-hour catch-up also fires

**Impact:**
- Both cron entries execute simultaneously
- Lock file prevents actual concurrent backup (good)
- But logs might be confusing (two "lock held" messages)

**Recommendation:**
- **Add EDGE-021**: Simultaneous cron entry execution
- Expected: Lock file prevents concurrent runs, second instance logs "lock held" and exits
- Already covered by REQ-009, but should be explicitly tested

---

## Missing Failure Scenarios

### FAIL-009: Backup Killed with SIGKILL (covered in finding #1)

### FAIL-010: .env File Malformed (covered in finding #3)

### FAIL-011: Archive Verification Fails (covered in finding #4)

### FAIL-012: Severe File Count Mismatch (covered in finding #5)

### FAIL-013: BACKUP_EXTERNAL_DIR Invalid (covered in finding #7)

### FAIL-014: Docker Daemon Stopped During Backup

**Trigger:** Docker daemon crashes, manually stopped, systemd kills it

**Expected Behavior:**
- backup.sh detects Docker is down, falls back to directory copy method (already supported)
- Trap handler's `docker compose start` fails (docker not running)
- Error logged: "Failed to restart services, docker daemon not running"
- Exit code 1, failure marker created

**User Communication:** Log entry with clear error

**Recovery:** User restarts docker daemon, manually starts services, next backup succeeds

---

### FAIL-015: Log Directory Deleted During Run

**Trigger:** User or script deletes `logs/backup/` directory while wrapper is running

**Expected Behavior:**
- Log writes fail (directory doesn't exist)
- Sentinel file update fails
- Lock file release might fail
- Wrapper should create directory if missing at startup

**Recommendation:**
- **Add REQ-032**: Create required directories at startup if missing:
  - `mkdir -p "$PROJECT_ROOT/logs/backup"`

---

### FAIL-016: Backup.sh Modified/Deleted Between Wrapper Start and Execution

**Trigger:** Concurrent git pull, user error, corrupted filesystem

**Expected Behavior:**
- Wrapper checks if `backup.sh` exists and is executable before calling it
- If missing: clear error "backup.sh not found at $PROJECT_ROOT/scripts/backup.sh"
- If not executable: clear error "backup.sh is not executable"
- Exit code 1, failure marker created

**Recommendation:**
- **Add REQ-033**: Validate backup.sh exists and is executable before calling

---

### FAIL-017: External Drive Becomes Read-Only Mid-Backup

**Trigger:** Filesystem error during backup, USB issue, drive failure

**Expected Behavior:**
- backup.sh's `cp` or `tar` commands fail with permission errors
- Trap handler runs (service restart)
- Partial backup files left on drive (should be cleaned up)
- Error logged, failure marker created

**Recommendation:**
- **Add cleanup logic**: If backup fails, delete partial `backup_$TIMESTAMP/` directory from external drive

---

## Missing Risks

### RISK-011: SIGKILL Leaves Services Stopped (covered in finding #1, CRITICAL)

### RISK-012: .env Syntax Error Causes Wrapper Crash (covered in finding #3, HIGH)

### RISK-013: Stale Lock Blocks All Future Backups (covered in finding #6, HIGH)

**Severity:** HIGH (currently marked as N/A)
**Likelihood:** LOW (requires SIGKILL or crash)
**Impact:** All future backups blocked until manual intervention
**Mitigation:** Stale lock detection (age >12h) with automatic removal
**Verification:** Kill backup with SIGKILL, wait 12h, verify next run detects and removes stale lock

---

### RISK-014: Backups Silently Go to Root Filesystem

**Severity:** HIGH
**Likelihood:** MEDIUM (user misconfigures BACKUP_EXTERNAL_DIR)
**Impact:** Fills root filesystem, defeats offsite-adjacent protection
**Mitigation:** Validate BACKUP_EXTERNAL_DIR is on external drive mount point
**Verification:** Set BACKUP_EXTERNAL_DIR=/tmp/backups, verify wrapper rejects with error

---

### RISK-015: Archive Corruption Not Detected Until Restore

**Severity:** HIGH
**Likelihood:** LOW (disk errors, tar bugs)
**Impact:** Months of backups exist but are not restorable
**Mitigation:** Archive integrity verification after creation (tar -tzf)
**Verification:** Create corrupted archive (truncate file), verify wrapper detects and marks as failed

---

### RISK-016: System Time Skew Breaks Staleness/Retention

**Severity:** MEDIUM
**Likelihood:** LOW (NTP issues, user error)
**Impact:** Unnecessary backups or deleted backups
**Mitigation:** Detect negative time differences, log warnings
**Verification:** Set system time backwards, verify wrapper handles gracefully

---

### RISK-017: Docker Compose Version Incompatibility

**Severity:** MEDIUM
**Likelihood:** MEDIUM (system upgrades)
**Impact:** Wrapper can't start/stop services
**Mitigation:** Try `docker compose`, fall back to `docker-compose`
**Verification:** Test on system with docker-compose v1, verify wrapper works

---

### RISK-018: Cron Service Stops/Crashes

**Severity:** MEDIUM
**Likelihood:** LOW (cron is stable)
**Impact:** No scheduled backups until cron restarted
**Mitigation:** Monitor sentinel file age externally (e.g., systemd timer checks sentinel every 12h)
**Verification:** Stop cron, verify external monitoring detects stale sentinel

---

### RISK-019: Multiple Users on System, Wrong Cron Modified

**Severity:** LOW
**Likelihood:** LOW (single-user system)
**Impact:** Setup script modifies wrong user's crontab
**Mitigation:** Setup script confirms current user before modifying crontab
**Verification:** Run setup as different user, verify confirmation prompt

---

### RISK-020: Backup.sh Exits 0 But Didn't Create Archive

**Severity:** HIGH (covered in finding #4)
**Mitigation:** Archive integrity verification

---

### RISK-021: Inode Exhaustion (Not Just Disk Space)

**Severity:** LOW
**Likelihood:** LOW (lots of small files on external drive)
**Impact:** Backup fails with cryptic "no space" error
**Mitigation:** Check free inodes in addition to free space
**Verification:** Create filesystem with low inodes, verify wrapper detects

---

## Research Disconnects

### Research Finding Not Addressed: "Compression Temp-Space"

**Research:** RESEARCH-042, "Compression Temp-Space" section notes that compression requires ~2x backup size temporarily on the external drive.

**Spec:** REQ-016 requires "2x expected backup size" free space check.

**Disconnect:** REQ-016 uses undefined "expected" size (see Finding #2). If "expected" is based on last compressed archive, then the check is wrong: need 2x **uncompressed** size, not 2x compressed size.

**Recommendation:**
- Clarify REQ-016: "2x expected **uncompressed** backup size"
- Or: "3x expected compressed backup size" (assuming ~50% compression ratio)

---

### Research Finding Not Addressed: Lock File Location Rationale

**Research:** "Lock file location (Critical Review v2 Finding #4 — LOW): Must be on the local filesystem, NOT on the external drive (which may not be mounted). Location: `$PROJECT_ROOT/logs/backup/.cron-backup.lock`."

**Spec:** REQ-009 specifies lock file on local filesystem, but doesn't explain WHY (rationale missing).

**Disconnect:** Spec doesn't clarify what happens if `$PROJECT_ROOT` itself is on NFS or network mount.

**Recommendation:**
- **Add note to REQ-009**: Lock file must be on local filesystem because external drive may not be mounted at startup. If PROJECT_ROOT is on NFS, flock may not work reliably (NFS flock behavior is implementation-dependent).

---

## Test Coverage Gaps

### Missing Tests

1. **SIGTERM vs SIGKILL**: Test trap handler with SIGTERM (works), then SIGKILL (doesn't work), verify different behavior
2. **Future timestamp in sentinel**: Create sentinel with `date -d "2099-01-01"`, run with `--if-stale`, verify backup runs (treats future timestamp as invalid)
3. **.env syntax errors**: Create .env with unclosed quote, verify wrapper gives clear error
4. **Symbolic links in shared_uploads/**: Create symlink, verify backup handles it (copies target or symlink itself?)
5. **Very long filenames**: Create file with 255-char name, verify backup works
6. **Filenames with newlines**: Create file with `$'file\nwith\nnewline.txt'`, verify file count check handles it
7. **Read-only external drive**: Remount drive read-only, verify wrapper detects and skips
8. **Inode exhaustion**: Create many small files to exhaust inodes, verify wrapper detects
9. **docker-compose v1 vs docker compose v2**: Test on both systems
10. **Stale lock (12h old)**: Create old lock file, verify automatic removal
11. **Archive integrity check**: Create corrupted tar.gz, verify wrapper detects
12. **Negative test for archive size**: Create 0-byte archive, verify rejected
13. **BACKUP_EXTERNAL_DIR on root filesystem**: Set to /tmp, verify rejected
14. **File count mismatch thresholds**: Test with 1, 10, 100 file differences, verify warning vs error

---

## Recommendations

### CRITICAL Priority (Must Fix Before Implementation)

1. **[Finding #1]** Fix SIGKILL assumption: Update REQ-006, add RISK-011, add FAIL-009, add defense-in-depth service monitoring (REQ-025)
2. **[Finding #2]** Define "expected backup size": Add REQ-016a (calculation logic), REQ-016b (update sentinel), EDGE-011 (first backup default)
3. **[Finding #3]** Add .env validation: Add REQ-026 (validation), FAIL-010 (malformed .env), EDGE-012 (command injection)
4. **[Finding #4]** Add backup verification: Add REQ-027 (integrity check), update REQ-011 (only update sentinel if verified), FAIL-011 (verification fails)
5. **[Finding #5]** Define file count match: Add REQ-001b (tolerance thresholds), update EDGE-005, add FAIL-012 (severe mismatch)

### HIGH Priority (Should Fix Before Implementation)

6. **[Finding #6]** Add stale lock handling: Add REQ-028 (staleness detection), update FAIL-003, add EDGE-014 (stale lock)
7. **[Finding #7]** Validate BACKUP_EXTERNAL_DIR: Add REQ-029 (validation), update REQ-004, FAIL-013 (invalid path), EDGE-015 (misconfigured)
8. **[Finding #8]** Standardize exit codes: Add REQ-030 (0=success, 1=error, 2=skip), update FAIL-001, FAIL-003

### MEDIUM Priority (Should Address)

9. **[AMB-001 through AMB-004]** Clarify all ambiguities listed
10. Add missing edge cases: EDGE-013 through EDGE-021
11. Add missing failure scenarios: FAIL-014 through FAIL-017
12. Add missing risks: RISK-013 through RISK-021
13. Address research disconnects (temp-space calculation, lock file location rationale)
14. Add missing test cases (14 tests listed in "Test Coverage Gaps")

### LOW Priority (Nice to Have)

15. Add REQ-031 (inode check)
16. Add REQ-032 (create directories if missing)
17. Add REQ-033 (validate backup.sh exists)
18. Docker Compose version fallback logic

---

## Proceed/Hold Decision

**RECOMMENDATION: REVISE BEFORE PROCEEDING**

The specification is comprehensive and well-researched, but contains **5 critical issues** that would cause production failures:

1. SIGKILL assumption (services stay down, defeats core requirement)
2. Undefined "expected backup size" (requirement is unimplementable)
3. Missing .env validation (cryptic failures)
4. No backup verification (false sense of security)
5. Undefined file count match (ambiguous requirement)

Additionally, **8 high-priority issues** and **multiple missing scenarios** should be addressed.

**Estimated revision time:** 2-3 hours to address critical and high-priority findings.

**After revision:** Specification will be implementation-ready with clear, testable requirements and comprehensive edge case coverage.

---

## Positive Aspects (What's Good)

- Comprehensive research foundation with two rounds of critical review
- Well-structured requirements with clear numbering (REQ-XXX, EDGE-XXX, FAIL-XXX, RISK-XXX)
- Most edge cases identified from research are well-specified
- Failure scenarios include recovery approaches
- Implementation notes provide helpful code examples
- Validation strategy is thorough (unit + integration + manual tests)
- Risk assessment identifies most major risks with mitigations

**The foundation is strong. These critical findings are fixable and will make the spec excellent.**
