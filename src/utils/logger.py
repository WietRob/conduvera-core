"""Logging utilities for Matrix OS."""
import logging
from pathlib import Path
from datetime import datetime
from rich.logging import RichHandler


def setup_logger(name: str = "matrix-os", level: int = logging.INFO) -> logging.Logger:
    """Setup logger with Rich handler."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Console handler with Rich
    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=True,
    )
    console_handler.setLevel(level)

    # File handler
    log_dir = Path.home() / ".local" / "share" / "matrix-os" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"matrix-os-{datetime.now().strftime('%Y%m%d')}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Global logger instance
logger = setup_logger()
