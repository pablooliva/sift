"""
Logging Configuration for txtai Frontend

Configures file-based logging with rotation for the Streamlit frontend.
Logs are written to /app/logs/ directory which is mounted to the host.
"""

import logging
import logging.handlers
from pathlib import Path
import os


def setup_logging(log_level: str = None):
    """
    Configure application logging with file rotation.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                   Defaults to INFO, or DEBUG if DEBUG env var is set
    """
    # Determine log level
    if log_level is None:
        debug_mode = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
        log_level = 'DEBUG' if debug_mode else 'INFO'

    # Create logs directory if it doesn't exist
    # Using /logs instead of /app/logs to avoid conflict with /app volume mount
    log_dir = Path('/logs')
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers = []

    # Console handler (stdout) - for docker logs command
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation - main application log
    app_log_file = log_dir / 'frontend.log'
    file_handler = logging.handlers.RotatingFileHandler(
        app_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,  # Keep 5 backup files
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Separate error log file - only errors and critical
    error_log_file = log_dir / 'errors.log'
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    root_logger.addHandler(error_handler)

    # Reduce noise from third-party libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('firecrawl').setLevel(logging.INFO)

    # Log startup message
    logging.info(f"Logging initialized - Level: {log_level}, Log directory: {log_dir}")
    logging.info(f"Application logs: {app_log_file}")
    logging.info(f"Error logs: {error_log_file}")

    return root_logger
