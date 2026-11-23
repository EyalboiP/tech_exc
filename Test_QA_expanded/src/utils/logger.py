import logging
import os
import sys
from datetime import datetime
from typing import Optional

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure console logging for the whole process (emulators, client, sampler...)."""
    logging.basicConfig(level=getattr(logging, str(level).upper(), logging.INFO),
                        format=LOG_FORMAT, stream=sys.stderr)


class TestLogger:
    __test__ = False  # not a pytest test class, despite the name

    def __init__(self, test_name: str, log_dir: str = "results/logs", level: str = "INFO", console: bool = True):
        self._test_name = test_name
        self._log_dir = log_dir
        self._level = getattr(logging, str(level).upper(), logging.INFO)
        self._console = console
        self.log_file: Optional[str] = None
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """
        Set up the logger with a custom format, writing to a file (and optionally the console).
        """
        # Create the logs directory
        os.makedirs(self._log_dir, exist_ok=True)

        # File name = timestamp + test name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = f"{self._log_dir}/{timestamp}_{self._test_name}.log"

        logger = logging.getLogger(f"test_{self._test_name}_{timestamp}_{id(self)}")
        logger.setLevel(self._level)
        logger.propagate = False  # avoid duplicate lines when the root logger is configured too

        formatter = logging.Formatter(LOG_FORMAT)
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        if self._console:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        return logger

    def close(self) -> None:
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)

    def info(self, message: str):
        self.logger.info(message)

    def error(self, message: str):
        self.logger.error(message)

    def debug(self, message: str):
        self.logger.debug(message)

    def warning(self, message: str):
        self.logger.warning(message)
