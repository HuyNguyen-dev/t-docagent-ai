from abc import ABC, abstractmethod
from typing import Protocol

from handlers.llm_configuration import LLMConfigurationHandler
from schemas.chunks import ChunkingConfig
from utils.logger.custom_logging import LoggerMixin


class VectorDBCreator(ABC, LoggerMixin):
    """Abstract base class for vector database creators."""

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    async def create_vector_datasource(self, config: any) -> bool:
        """Abstract method to create a vector datasource."""


class ParserStrategy(Protocol):
    """Protocol for parser strategies."""

    async def parse(
        self,
        file_path: str,
        file_bytes: bytes | None = None,
        chunking_config: ChunkingConfig | None = None,
        llm_handler: LLMConfigurationHandler | None = None,
        number_page: int | None = None,
    ) -> list[dict]:
        """Parse the file with specified parameters."""
        ...
