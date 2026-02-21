import logging
import sys
from collections.abc import Mapping
from typing import ClassVar

from config import default_configs

logging_config = default_configs.get("LOGGING")


class CustomFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = logging_config.get("FORMATTER")

    FORMATS: ClassVar[Mapping[int, str]] = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record: logging.LogRecord) -> logging.Formatter:
        log_fmt = self.FORMATS.get(record.levelno)
        date_fmt = logging_config.get("DATE_FORMATTER")
        formatter = logging.Formatter(log_fmt, date_fmt)
        return formatter.format(record)


class Handlers:
    def __init__(self) -> None:
        self.formatter = CustomFormatter()
        self.rotation = logging_config.get("ROTATION")

    def get_console_handler(self) -> logging.StreamHandler:
        """
        :return:
        """
        console_handler = logging.StreamHandler(sys.stdout.flush())
        console_handler.setFormatter(self.formatter)
        return console_handler

    def get_handlers(self) -> list[logging.StreamHandler]:
        return [self.get_console_handler()]
