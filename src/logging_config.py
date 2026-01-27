"""
Centralized logging configuration for all services.

Usage:
    from src.logging_config import setup_logging
    logger = setup_logging("service_name")

    logger.info("Message")
    logger.warning("Warning message")
    logger.error("Error message", exc_info=True)
"""

import logging
import sys
from datetime import datetime
from typing import Optional


class ServiceFormatter(logging.Formatter):
    """Custom formatter with timestamps, levels, and service context."""

    def format(self, record: logging.LogRecord) -> str:
        # Add timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Format level name
        level = record.levelname

        # Get service name from logger name
        service = record.name

        # Build the base message
        base_msg = f"[{timestamp}] [{level}] [{service}] {record.getMessage()}"

        # Add exception info if present
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            base_msg = f"{base_msg}\n{exc_text}"

        return base_msg


def setup_logging(
    service_name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Set up logging for a service.

    Args:
        service_name: Name of the service (e.g., "monitor", "orchestrator")
        level: Logging level (default: INFO)
        log_file: Optional file path to write logs to

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ServiceFormatter())
    logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(ServiceFormatter())
        logger.addHandler(file_handler)

    # Don't propagate to root logger
    logger.propagate = False

    return logger


def get_logger(service_name: str) -> logging.Logger:
    """
    Get an existing logger or create a new one.

    Use this when you need to get a logger in a module that has already
    been set up by setup_logging().

    Args:
        service_name: Name of the service

    Returns:
        Logger instance
    """
    logger = logging.getLogger(service_name)

    # If no handlers, set up with defaults
    if not logger.handlers:
        return setup_logging(service_name)

    return logger
