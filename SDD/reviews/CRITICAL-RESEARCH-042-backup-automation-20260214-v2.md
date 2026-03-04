# Research Critical Review (v2): RESEARCH-042 Backup Automation

**Reviewed:** 2026-02-14
**Document:** `SDD/research/RESEARCH-042-backup-automation.md` (post-v1 revision)
**Reviewer Role:** Adversarial critical review (second pass after v1 findings were addressed)
**Prior review:** `CRITICAL-RESEARCH-042-backup-automation-20260214.md` (9 findings, all marked resolved)

## Executive Summary

The v1 critical review findings have been addressed well — the trap handler design, staleness-based catch-up, LUKS investigation, and dual-layer notification are all sound. However, the revision introduced a **significant gap**: the research proposes adding `shared_uploads/`, `logs/frontend/archive/`, and `audit.jsonl` to `backup.sh` without addressing that `restore.sh` doesn't know about these items. A backup that includes data which can't be restored is a false safety net. Additionally, the root ownership of `shared_uploads/` creates a permission asymmetry that could cause silent data loss during backup or restore.

### Overall Severity: **MEDIUM** (1 important, 3 medium, 2 low findings)

The core design is solid. These are gaps to close during specification, not blockers to the overall approach.

---

## Finding 1: `restore.sh` incompatibility with backup gap fix (IMPORTANT)

### What the research proposes

Add `shared_uploads/`, `logs/frontend/archive/`, and `audit.jsonl` to `backup.sh` (Option A, "Backup Gap Resolution" section). This is the right call — these are core data that should be in every backup.

### What the research misses

`restore.sh` (400 lines) has **no awareness** of these items. It checks for and restores:
- `postgres.sql` / `postgres_data/`
- `qdrant_storage/`
- `txtai_data/`
- `document_archive/`
- `neo4j.dump` / `neo4j_data/`
- `config.yml`, `.env`

**Not mentioned anywhere in restore.sh:** `shared_uploads/`, `logs/frontend/archive/`, `audit.jsonl`.

### Why this matters

After a disaster recovery:
1. User runs `backup.sh` → archive now includes `shared_uploads/` (good)
2. Disaster occurs
3. User runs `restore.sh backup.tar.gz` → `shared_uploads/` is in the archive but NOT extracted/restored
4. User thinks restore is complete but original media files are missing
5. Transcriptions/captions reference missing originals — silent data corruption

The research correctly says these files are "**Irreplaceable** — transcriptions/captions are derived data, originals cannot be reconstructed." But then doesn't ensure they're restorable.

### Recommendation

The spec MUST include updating `restore.sh` to handle:
- `shared_uploads/` → restore to `$PROJECT_ROOT/shared_uploads/`
- `logs/frontend/archive/` → restore to `$PROJECT_ROOT/logs/frontend/archive/`
- `audit.jsonl` → restore to `$PROJECT_ROOT/audit.jsonl`

This also affects the MANIFEST.txt generation in `backup.sh` — new items need manifest entries.

### Severity: **IMPORTANT** — breaks the backup/restore contract for irreplaceable data

---

## Finding 2: `shared_uploads/` root ownership creates permission asymmetry (MEDIUM)

### Current state

```
drwxr-xr-x  root root  shared_uploads/
```

Created by Docker (mounted as `./shared_uploads:/uploads` in both `txtai-api` and `frontend` containers). Files uploaded through the frontend will be created by the container's user (typically root inside Docker).

### Backup direction (reading)

`backup.sh` runs as `pablo`. Root-owned directory with `r-x` for others — `cp -r` can READ the directory. Files inside should also be world-readable (Docker default `umask` is typically 022). **Backup should work** but depends on Docker not creating restrictive file permissions.

### Restore direction (writing)

After restore:
- `cp -r` as `pablo` → restored `shared_uploads/` owned by `pablo:pablo`
- Docker containers expect root ownership (they wrote the originals as root)
- Containers mount `./shared_uploads:/uploads` — if the container process writes as root, it can still access pablo-owned files (root can read anything). **Probably fine** but represents an ownership divergence from the original state.

### Edge case

If a Docker container creates files with `chmod 600 root:root` (restrictive permissions):
- `backup.sh` as `pablo` → `cp -r` silently skips unreadable files (no error with `set -e` because `cp -r` continues copying other files)
- Backup appears to succeed but is missing files
- No warning in logs

### Recommendation

The spec should note this risk and recommend either:
- Using `sudo cp -r` for `shared_uploads/` (requires sudo access from cron)
- Verifying file count before/after backup as a sanity check
- Documenting the assumption that Docker creates world-readable files

### Severity: **MEDIUM** — unlikely with default Docker behavior, but silent data loss if it occurs

---

## Finding 3: Desktop notification (`notify-send`) is fragile in cron (MEDIUM)

### What the research proposes

```bash
DISPLAY=:0
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
```

Hardcoded in crontab for `notify-send` on failure.

### Problems

1. **Wayland sessions**: The research checks for `WAYLAND_DISPLAY` but the crontab only captures `DISPLAY=:0`. On Wayland (default on Ubuntu 22.04+), the X display variable may not be `:0` or may not exist at all. `WAYLAND_DISPLAY` is the relevant variable but isn't captured for crontab.

2. **Session bus path**: `/run/user/1000/bus` is correct for uid 1000, but the bus may not be active at 3 AM if the user logged out, the session expired, or the system uses a login manager that tears down sessions.

3. **Multi-session**: If the user has multiple sessions (SSH + GUI), the captured DISPLAY/DBUS may point to a stale session.

4. **False confidence**: The notification layer is presented as complementary to the sentinel file, but users may think "I'd get a notification if backup fails" without realizing it's unreliable at 3 AM.

### What's not a problem

The sentinel file (Layer 1) is rock-solid and covers all failure modes. The desktop notification is a nice-to-have that sometimes works.

### Recommendation

- Document in the spec that desktop notification is best-effort, not guaranteed
- Don't invest heavy engineering into making it reliable (capture scripts, etc.)
- Consider adding a simpler secondary mechanism: a `BACKUP_FAILED` marker file that the frontend Home page can check (similar to how it checks config validation)

### Severity: **MEDIUM** — false confidence issue, but sentinel file mitigates

---

## Finding 4: Lock file location unspecified (LOW)

The research says "Lock file (`flock`) prevents concurrent runs" but doesn't specify where the lock file lives.

If the lock file is on the external drive (which might not be mounted), `flock` fails before the mount check can run. It should be on the local filesystem.

### Recommendation

Specify lock file location in the spec: `$PROJECT_ROOT/logs/backup/.lock` or `/tmp/txtai-backup.lock`.

### Severity: **LOW** — implementation detail, but could cause confusion if not specified

---

## Finding 5: Sentinel file parsing robustness (LOW)

The `--if-stale` check reads the sentinel file and parses a timestamp. If the file exists but contains garbage (truncated write, concurrent access, filesystem error), `date` parsing could fail.

With `set -e` in the cron wrapper, a parsing failure would exit the script — meaning a corrupt sentinel file prevents ALL future backups until manually fixed.

### Recommendation

Defensive parsing: if the sentinel file can't be parsed, treat as stale (backup needed). Pseudocode:

```bash
if ! last_backup=$(date -d "$(cat "$SENTINEL_FILE")" +%s 2>/dev/null); then
    # Corrupt or unreadable — treat as stale
    last_backup=0
fi
```

### Severity: **LOW** — rare edge case, but easy to handle defensively

---

## Finding 6: Log rotation approach could lose data (LOW)

The research proposes: "Log rotation: built into the wrapper script (truncate if >10MB, keep last 1000 lines)."

In-place truncation of a log file that's actively being appended to (if another cron instance starts via staleness check) can corrupt the file. The `flock` should prevent this, but if the lock fails for any reason, data loss occurs.

### Recommendation

Use `logrotate` (already installed on most Ubuntu systems) or rotate to a `.1` file atomically, rather than in-place truncation. Or simply rely on `flock` and document that the log rotation assumes exclusive access.

### Severity: **LOW** — mitigated by flock, but worth noting

---

## v1 Resolution Adequacy Check

| # | v1 Finding | Resolution | Adequate? |
|---|-----------|------------|-----------|
| 1 | `backup.sh --stop` + `set -e` = service outage | Trap handler design | **Yes** — sound approach, well-documented |
| 2 | No failure notification | Dual-layer: sentinel + notify-send | **Mostly** — sentinel is solid, notify-send is fragile (see finding 3) |
| 3 | Data size misleading | Corrected with actual queries | **Yes** — honest about empty state + growth projections |
| 4 | Missed-run behavior | Staleness-based catch-up | **Yes** — equivalent to systemd Persistent=true |
| 5 | LUKS auto-unlock | crypttab/fstab investigated | **Yes** — thorough, security trade-off well-reasoned |
| 6 | No tests | Testing strategy expanded | **Yes** — automated + manual test plan |
| 7 | `.env` sourcing | `set -a` pattern documented | **Yes** |
| 8 | Compression temp-space | Documented with 2x check | **Yes** |
| 9 | `shared_uploads/` gap | Audit completed, fix in backup.sh | **Partially** — backup fixed but restore.sh not addressed (see finding 1) |

---

## Recommended Actions Before Proceeding to Specification

### Must address in spec

1. **[IMPORTANT]** Include `restore.sh` update as a specification requirement. The backup/restore contract must be symmetrical — anything backup.sh adds, restore.sh must handle.

### Should document in spec

2. **[MEDIUM]** Note `shared_uploads/` ownership asymmetry and specify the assumed permission model (world-readable files created by Docker). Add a backup verification step (file count sanity check) if feasible.

3. **[MEDIUM]** Document desktop notification as best-effort. Don't over-engineer it. Consider adding a `BACKUP_FAILED` marker file for frontend health check integration.

### Nice to have in spec

4. **[LOW]** Specify lock file location (local filesystem, not external drive).

5. **[LOW]** Specify defensive sentinel file parsing (corrupt → treat as stale).

6. **[LOW]** Specify log rotation approach compatible with flock.

---

## Proceed/Hold Decision

**PROCEED to specification** — with finding #1 (restore.sh) explicitly included as a requirement.

The v1 review's blocking issues have been well-resolved. The remaining findings are spec-level concerns, not research gaps. The core approach (cron wrapper around backup.sh, trap handler, staleness catch-up, sentinel file) is sound and ready for specification.
