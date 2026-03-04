"""
Ingestion lock file helpers.

Writes a lock file to the shared volume (/uploads/.ingestion.lock) while
Graphiti ingestion is in progress. The backup cron script (scripts/cron-backup.sh)
reads this file before stopping containers to avoid interrupting active ingestion.

Lock file path (container):  /uploads/.ingestion.lock
Lock file path (host):       PROJECT_ROOT/shared_uploads/.ingestion.lock

Both paths resolve to the same file via the shared_uploads bind-mount in
docker-compose.yml.
"""

import os
import time

# Shared volume path inside the frontend container
INGESTION_LOCK_FILE = "/uploads/.ingestion.lock"


def write_ingestion_lock() -> None:
    """Write lock file to signal active Graphiti ingestion to backup scripts."""
    try:
        with open(INGESTION_LOCK_FILE, 'w') as f:
            f.write(f"pid={os.getpid()}\nstarted={time.time():.0f}\n")
    except Exception:
        pass  # Non-blocking: don't fail ingestion if lock file can't be written


def remove_ingestion_lock() -> None:
    """Remove ingestion lock file when ingestion completes or fails."""
    try:
        os.remove(INGESTION_LOCK_FILE)
    except FileNotFoundError:
        pass  # Already removed, that's fine
    except Exception:
        pass  # Non-blocking
