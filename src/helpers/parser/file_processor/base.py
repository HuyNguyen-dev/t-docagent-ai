from abc import ABC, abstractmethod

from schemas.chunks import ChunkingConfig
from utils.enums import DocumentSourceType
from utils.logger.custom_logging import LoggerMixin


class BasePartition(ABC, LoggerMixin):
    def __init__(self, source_type: DocumentSourceType) -> None:
        super().__init__()
        self.source_type = source_type

    @abstractmethod
    async def get_chunks(
        self,
        file_path: str,
        source: str,
        chunking_config: ChunkingConfig | None = None,
        number_page: int | None = None,
        **kwargs: any,
    ) -> list[dict] | None:
        """Parse and format documents from the source."""
        raise NotImplementedError
