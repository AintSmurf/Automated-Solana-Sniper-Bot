import os
import sys
import logging
from logging.handlers import RotatingFileHandler


class LoggingHandler:
    _logger = None

    def __init__(self):
        if LoggingHandler._logger is None:
            LoggingHandler._logger = self._setup_logger()

    @staticmethod
    def _setup_logger():

        LOG_DIR = "logs/info"
        DEBUG_DIR = "logs/debug"
        ERROR_DIR = "logs/errors"
        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs(DEBUG_DIR, exist_ok=True)
        os.makedirs(ERROR_DIR, exist_ok=True)

        # ✅ Define log file paths
        log_file = os.path.join(LOG_DIR, "log.log")
        debug_file = os.path.join(DEBUG_DIR, "debug.log")
        error_file = os.path.join(ERROR_DIR, "errors.log")

        # ✅ Rotating handlers (Max size: 10MB, 5 backups)
        log_handler = RotatingFileHandler(
            log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
        )
        debug_handler = RotatingFileHandler(
            debug_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
        )
        error_handler = logging.FileHandler(error_file, mode="a", encoding="utf-8")

        # ✅ Set log formats
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
        formatter = logging.Formatter(log_format)

        log_handler.setFormatter(formatter)
        log_handler.setLevel(logging.INFO)

        debug_handler.setFormatter(formatter)
        debug_handler.setLevel(logging.DEBUG)

        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.WARNING)

        # ✅ Console handler (Only logs INFO and above)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)

        # ✅ Create logger
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        # ✅ Add handlers
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
