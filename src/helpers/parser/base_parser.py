from abc import ABC, abstractmethod

from handlers.llm_configuration import LLMConfigurationHandler
from schemas.chunks import ChunkingConfig
from utils.logger.custom_logging import LoggerMixin


class BaseParser(ABC, LoggerMixin):
    """
    Abstract base class for document parsers.

    This class defines the common interface that all parser implementations
    must follow. It provides shared functionality for document upload and
    knowledge base operations.
    """

    @abstractmethod
    async def parse(
        self,
        file_path: str,
        file_bytes: bytes | None = None,
        chunking_config: ChunkingConfig | None = None,
        llm_handler: LLMConfigurationHandler | None = None,
        number_page: int | None = None,
    ) -> list[dict]:
        """
        Parse the document and return structured data.

        This is an abstract method that must be implemented by all parser
        subclasses. Each parser should implement its own parsing logic
        based on the document type and requirements.

        :param chunking_config: Configuration for chunking strategy
        :return: Result containing parsed data.
        """
