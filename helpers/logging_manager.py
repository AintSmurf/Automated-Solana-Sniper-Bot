import os
import sys
import logging
from logging.handlers import RotatingFileHandler


class LineCountFilter(logging.Filter):
    """Custom filter to count log lines and trigger file rotation every 10,000 lines."""

    def __init__(self, max_lines=10_000):
        super().__init__()
        self.max_lines = max_lines
        self.line_count = 0

    def filter(self, record):
        self.line_count += 1
        if self.line_count >= self.max_lines:
            self.line_count = 0  # Reset counter
            return False  # Stop logging to this file (forces rotation)
        return True


class LoggingHandler:
    _logger = None

    def __init__(self):
        if LoggingHandler._logger is None:
            LoggingHandler._logger = self._setup_logger()

    @staticmethod
    def _setup_logger():
        # Define log directories
        LOG_DIR = "logs/info"
        DEBUG_DIR = "logs/debug"
        ERROR_DIR = "logs/errors"

        # Create directories if they don't exist
        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs(DEBUG_DIR, exist_ok=True)
        os.makedirs(ERROR_DIR, exist_ok=True)

        # Define log file paths with a numbering system for rotation
        log_file = os.path.join(LOG_DIR, "log.log")
        debug_file = os.path.join(DEBUG_DIR, "debug.log")
        error_file = os.path.join(ERROR_DIR, "errors.log")

        # Define log format
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
        formatter = logging.Formatter(log_format)

        # Create a custom filter for line-based rotation
        line_filter = LineCountFilter(max_lines=10_000)

        # Handlers with rotation based on line count
        log_handler = RotatingFileHandler(
            log_file, maxBytes=0, backupCount=10, encoding="utf-8"
        )
        log_handler.addFilter(line_filter)
        log_handler.setFormatter(formatter)
        log_handler.setLevel(logging.INFO)

        debug_handler = RotatingFileHandler(debug_file, maxBytes=0, encoding="utf-8")
        debug_handler.addFilter(line_filter)
        debug_handler.setFormatter(formatter)
        debug_handler.setLevel(logging.DEBUG)

        error_handler = RotatingFileHandler(error_file, maxBytes=0, encoding="utf-8")
        error_handler.addFilter(line_filter)
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.WARNING)

        # Console handler (Only logs INFO and above)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)

        # Create logger
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        # Add handlers
        logger.addHandler(log_handler)
        logger.addHandler(debug_handler)
        logger.addHandler(error_handler)
        logger.addHandler(console_handler)

        return logger

    @staticmethod
    def get_logger():
        """Return the initialized logger."""
        if LoggingHandler._logger is None:
            LoggingHandler()
        return LoggingHandler._logger
