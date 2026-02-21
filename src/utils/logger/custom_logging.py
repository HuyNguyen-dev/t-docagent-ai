import logging

from config import settings
from utils.logger.handlers import Handlers


class LogHandler:
    def __init__(self) -> None:
        self.available_handlers: list = Handlers().get_handlers()

    def get_logger(self, logger_name: str) -> logging.Logger:
        logger = logging.getLogger(logger_name)
        logger.setLevel(settings.LOG_LEVEL)
        if logger.hasHandlers():
            logger.handlers.clear()
        for handler in self.available_handlers:
            logger.addHandler(handler)
        logger.propagate = False
        return logger


class LoggerMixin:
    def __init__(self) -> None:
        log_handler = LogHandler()
        self.logger = log_handler.get_logger(__name__)
        self.logger.setLevel(settings.LOG_LEVEL)
