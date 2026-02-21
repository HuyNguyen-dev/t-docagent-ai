from handlers.llm_configuration import LLMConfigurationHandler
from helpers.parser.base_parser import BaseParser
from helpers.parser.file_processor.factory import partition_factory
from schemas.chunks import ChunkingConfig
from utils.constants import KEY_SCHEMA_EMBEDDING_CONFIG
from utils.enums import ChunkingMode, DocumentExtension, DocumentSourceType


class FileParser(BaseParser):
    def __init__(self, file_path: str) -> None:
        super().__init__()
        self._document_partition = partition_factory(
            file_name=file_path,
            source_type=DocumentSourceType.DOC_FILE,
        )

    async def parse(
        self,
        file_bytes: bytes,
        file_path: str,
        chunking_config: ChunkingConfig,
        llm_handler: LLMConfigurationHandler,
        number_page: int | None = None,
    ) -> list[dict] | None:
        try:
            embedding_model = None
            if chunking_config.chunking_mode == ChunkingMode.SEMANTIC:
                owner_config = await llm_handler.get_owner_llm_config()
                embedding_model = llm_handler.get_llm_config_by_key(
                    owner_config=owner_config,
                    key=KEY_SCHEMA_EMBEDDING_CONFIG,
                )
                chunking_config.embeddings_model = embedding_model

            if self._document_partition is None:
                message = (
                    "Partition text from file failed. Unsupported object parser for your input. "
                    f"Only support for {DocumentExtension.to_string()}"
                )
                self.logger.error(
                    'event=extract-text-from-file-failure filename="%s" message="%s"',
                    self.object_path,
                    message,
                )
                return None, message
            chunks = await self._document_partition.get_chunks(
                file_path=file_path,
                source=file_bytes,
                chunking_config=chunking_config,
                number_page=number_page,
            )

        except Exception:
            self.logger.exception(
                'event=extract-text-from-file-failure message="Process failed." message="Unexpected error!"',
            )
            return []
        return chunks
