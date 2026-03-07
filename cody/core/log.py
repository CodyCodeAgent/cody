"""Unified logging setup for Cody.

Provides file-based logging so problems can be diagnosed after the fact.
Logs are written to ``~/.cody/logs/cody.log`` with automatic rotation
(5 MB per file, 3 backups kept).

Usage — call once at process startup::

    from cody.core.log import setup_logging
    setup_logging()              # INFO to file
    setup_logging(verbose=True)  # DEBUG to file + stderr
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Defaults
LOG_DIR = Path.home() / ".cody" / "logs"
LOG_FILE = "cody.log"
MAX_BYTES = 5 * 1024 * 1024   # 5 MB per file
BACKUP_COUNT = 3               # keep 3 old files
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

_setup_done = False


def setup_logging(*, verbose: bool = False, log_dir: Path | None = None) -> None:
    """Configure the root logger with a rotating file handler.

    Parameters
    ----------
    verbose:
        When *True*, also add a stderr handler and set the root level to
        DEBUG.  When *False* (default), only write to the log file at INFO
        level — nothing is printed to the terminal.
    log_dir:
        Override the default log directory (``~/.cody/logs``).
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    target_dir = log_dir or LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    # File handler — always present
    file_handler = RotatingFileHandler(
        target_dir / LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    if verbose:
        # Also print to stderr when verbose
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
        stderr_handler.setLevel(logging.DEBUG)
        root.addHandler(stderr_handler)
        root.setLevel(logging.DEBUG)
    else:
        root.setLevel(logging.INFO)
