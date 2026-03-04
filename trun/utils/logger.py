"""
Logging utilities.
"""

import logging
import os
from datetime import datetime
from pathlib import Path


class TeamRunLogger:
    """Logger for TeamRun with daily log files."""

    def __init__(self, log_dir: str | Path = ".team_run/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._logger = self._setup_logger()

    def _get_log_file(self) -> Path:
        """Get today's log file path."""
        today = datetime.now().strftime("%Y_%m_%d")
        return self.log_dir / f"{today}.log"

    def _setup_logger(self) -> logging.Logger:
        """Setup logger with file and console handlers."""
        logger = logging.getLogger("trun")
        logger.setLevel(logging.DEBUG)

        # Clear existing handlers
        logger.handlers.clear()

        # File handler (daily log file)
        file_handler = logging.FileHandler(
            self._get_log_file(),
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler (INFO and above by default, configurable via TRUN_LOG_LEVEL)
        console_handler = logging.StreamHandler()
        console_level = os.getenv("TRUN_LOG_LEVEL", "INFO")
        console_handler.setLevel(getattr(logging, console_level.upper(), logging.INFO))
        console_formatter = logging.Formatter(
            "%(levelname)s: %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        return logger

    def debug(self, message: str) -> None:
        """Log debug message."""
        self._logger.debug(message)

    def info(self, message: str) -> None:
        """Log info message."""
        self._logger.info(message)

    def warning(self, message: str) -> None:
        """Log warning message."""
        self._logger.warning(message)

    def error(self, message: str) -> None:
        """Log error message."""
        self._logger.error(message)

    def step(self, step_id: str, status: str, message: str) -> None:
        """Log step execution."""
        self._logger.info(f"[{step_id}] {status}: {message}")


# Global logger instance
_logger: TeamRunLogger | None = None


def get_logger(log_dir: str | Path = ".team_run/logs") -> TeamRunLogger:
    """Get or create the global logger instance."""
    global _logger
    if _logger is None:
        _logger = TeamRunLogger(log_dir)
    return _logger
