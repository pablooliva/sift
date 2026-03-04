# Research Critical Review: RESEARCH-042 Backup Automation

**Reviewed:** 2026-02-14
**Document:** `SDD/research/RESEARCH-042-backup-automation.md`
**Reviewer Role:** Adversarial critical review

## Executive Summary

The research is solid in its core approach (thin cron wrapper around existing `backup.sh`), but has **one critical gap** and **several important oversights**. The most dangerous issue is that `backup.sh --stop` combined with `set -e` can leave services permanently stopped if any backup step fails — at 3 AM unattended, this means hours of downtime. The research also understates the LUKS auto-unlock problem, provides misleading data size estimates (all databases are empty), and lacks any failure notification mechanism.

### Overall Severity: **HIGH** (1 critical, 4 important, 3 minor findings)

---

## Critical Gaps Found

### 1. **CRITICAL: `backup.sh --stop` + `set -e` = unrecoverable service outage**

`backup.sh` line 25 sets `set -e` (exit on any error). Lines 162-173 stop `txtai` and `frontend` services. Lines 321-328 restart them — but only if the script reaches that point. **There is no `trap` handler.**

If ANY command between lines 173 and 320 fails (PostgreSQL dump error, disk full during copy, tar compression failure, permission error), the script exits immediately and **services stay stopped indefinitely**.

At 3 AM unattended, this means:
- txtai API down until someone manually notices and restarts
- Frontend inaccessible
- No automatic recovery

**Evidence:** `grep -n 'trap' backup.sh` returns nothing. Line 25: `set -e`. Lines 180, 184 show `pg_dump` failure is caught with `if/else` but `cp -r` commands at lines 189, 201, 213, 225 are NOT wrapped — any disk error causes immediate exit with services stopped.

**Risk:** Multi-hour production outage from a routine backup

**Recommendation:** The cron wrapper MUST add a `trap` to ensure services are restarted on any exit. This is a specification-level requirement, not an implementation detail. Alternatively, consider fixing `backup.sh` itself, though the research explicitly chose not to modify it.

---

### 2. **IMPORTANT: No failure notification mechanism**

The research mentions logging to `logs/backup/cron-backup.log` but proposes no mechanism for alerting when backups fail. "Who reads logs at 3 AM?"

Failure scenarios that would go unnoticed:
- Drive not mounted for weeks (no backup taken, no alert)
- Backup consistently failing (disk errors, Docker issues)
- Services left stopped (see finding #1)

**Evidence:** Research section "Operations Perspective" says "Need monitoring to detect silent failures" but proposes no solution beyond file logging.

**Risk:** Backup failures accumulate silently until a disaster reveals there are no recent backups.

**Recommendation:** Spec should require at minimum one notification channel — options include:
- Desktop notification via `notify-send` (if session active)
- Email via `mail` / `sendmail`
- Write a "last successful backup" timestamp file that a health check can monitor
- Simplest: create/update a sentinel file on success; absence or staleness = problem

---

### 3. **IMPORTANT: Data size estimates are misleading**

The research states "Total current data size: ~520MB" and bases all retention math on this. But we verified that **all databases are currently empty**:
- PostgreSQL: tables don't exist yet (0 documents)
- Qdrant: 0 vectors
- Neo4j: 0 nodes

The 518MB is Neo4j engine overhead (transaction logs, store files), not data. When the knowledge base is populated (74 entities was the previous state), actual backup sizes will differ significantly. With hundreds of documents, PostgreSQL and Qdrant will dominate over Neo4j overhead.

**Evidence:** Direct queries confirmed 0 counts across all databases. `du -sh` sizes reflect empty database engine files.

**Risk:** Retention calculations and disk space estimates are unreliable. Not dangerous (8TB is vast), but the research presents false precision.

**Recommendation:** Document that sizes are engine overhead from empty databases. Estimate realistic populated sizes based on previous state (74 entities, N documents) or acknowledge unknowns.

---

### 4. **IMPORTANT: Cron missed-run behavior dismissed too quickly**

The research dismisses systemd timers in favor of cron, citing the user's explicit request. However, the comparison table acknowledges that cron **silently skips** missed runs while systemd timers can catch up with `Persistent=true`.

For a home server that might:
- Be powered off overnight (power save, UPS event)
- Reboot for kernel updates (unattended-upgrades)
- Be suspended/hibernated

...missing a 3 AM backup with no notification (see finding #2) means backups silently stop working after any disruption.

**Evidence:** Research table shows "Missed runs: Skipped" for cron vs "Can catch up" for systemd timers.

**Risk:** Backup gap after any reboot/power event. Combined with no notification, could mean days of missed backups.

**Recommendation:** Either (a) add anacron-like retry logic to the cron wrapper (check last backup age, run if >24h stale), or (b) document this limitation explicitly in the spec so the user makes an informed choice.

---

### 5. **IMPORTANT: LUKS auto-unlock after reboot not investigated**

The research correctly identifies LUKS as a risk but doesn't investigate whether auto-unlock is configured or configurable. If the server reboots (kernel update, power outage), the LUKS volume requires manual password entry before the drive is available. This could mean days of missed backups if the user doesn't notice.

Questions not answered:
- Is there a `/etc/crypttab` entry for this drive?
- Could a keyfile-based LUKS unlock be configured for automatic mount?
- Is the drive connected via USB (could be disconnected accidentally)?

**Evidence:** Mount shows `uhelper=udisks2` (user-space, not fstab). `lsblk` shows `/dev/sdb` (likely USB). No investigation of `/etc/crypttab` or `/etc/fstab`.

**Risk:** After any reboot, backups silently stop (drive not mounted) with no notification.

**Recommendation:** Check `/etc/crypttab` and `/etc/fstab`. Document whether auto-mount is feasible. At minimum, the spec should address what happens after reboot — even if the answer is "manual unlock required, user accepts this."

---

## Questionable Assumptions

### 1. **"No automated tests needed"**

The research states "No automated tests needed for cron configuration itself." This contradicts `CLAUDE.md` testing requirements: "All new functionality MUST include tests before being considered complete."

While cron jobs and shell scripts are harder to test, the cron wrapper script has testable logic:
- Mount validation behavior
- Lock file behavior
- Retention policy (delete old backups)
- ENV variable handling
- Exit codes and error paths

**Alternative possibility:** Unit-testable functions can be extracted and tested. Dry-run mode can verify logic without side effects.

---

### 2. **"Compression happens on target drive" not considered**

`backup.sh` lines 305-311: after `cd "$BACKUP_DIR"`, it creates the tar archive in the same directory, then deletes the uncompressed copy. When `--output` points to the external drive, this means:
1. Write uncompressed backup to external drive (~520MB+)
2. Write compressed archive to external drive (~additional compressed size)
3. Delete uncompressed copy

Temporarily requires ~1.5-2x backup size on the external drive. Not a problem with 4.7TB free, but worth documenting — and could matter if the drive is nearly full or the dataset grows large.

---

### 3. **"`.env` is directly sourceable"**

The `.env` file format varies. The current `.env` doesn't use `export` prefixes. When the cron wrapper does `source .env`, variables are set in the shell but NOT exported to child processes (like `backup.sh`) unless explicitly exported. The wrapper needs `set -a` (auto-export) before sourcing, or explicit `export` of needed variables.

**Evidence:** `.env` lines like `TXTAI_API_URL=http://YOUR_SERVER_IP:8300` — no `export` keyword.

---

## Missing Perspectives

### Disaster Recovery Perspective
- What's the restore workflow from the external drive? Is `restore.sh` tested with backups created via `--output`?
- Should there be a periodic automated restore test (verify backups are valid)?
- No backup verification (checksum, test extract) after creation

### Long-term Maintenance Perspective
- What happens when the external drive fails? (SMART monitoring?)
- What if the drive fills up despite retention? (Minimum free space check?)
- What if `backup.sh` changes in the future? (Wrapper relies on its interface)

---

## Recommended Actions Before Proceeding to Specification

### BLOCKING (must address)

1. **[CRITICAL]** Define how the cron wrapper guarantees service restart on failure. Either:
   - Add `trap` in the wrapper to restart services if backup.sh exits non-zero
   - Or fix `backup.sh` to add its own `trap`
   - Spec must be explicit about this

2. **[HIGH]** Define a failure notification mechanism (at minimum, a staleness-detection approach)

### IMPORTANT (should address)

3. **[MEDIUM]** Investigate `/etc/crypttab` and `/etc/fstab` for the external drive. Document post-reboot behavior.

4. **[MEDIUM]** Correct data size estimates or acknowledge they're from empty databases

5. **[MEDIUM]** Address missed-run behavior: document the limitation or add staleness-based retry

### NICE TO HAVE

6. **[LOW]** Add backup verification (test extract or checksum) to the wrapper

7. **[LOW]** Handle `set -a` / export when sourcing `.env` for child process inheritance

8. **[LOW]** Document compression temp-space behavior

---

## Proceed/Hold Decision

**HOLD — address findings #1 and #2 before specification.**

Finding #1 (service outage from failed backup) is a safety issue that must be explicitly designed for in the spec. Finding #2 (no notification) is important for an unattended system. The remaining findings can be addressed during specification.

The core approach (cron wrapper around backup.sh) is sound. The research just needs to fill these gaps before it can properly inform a robust specification.
