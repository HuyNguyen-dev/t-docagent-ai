from typing import ClassVar

import pandas as pd

from handlers.llm_configuration import LLMConfigurationHandler
from helpers.parser.file_parser import FileParser
from helpers.parser.url_parser import URLParser
from schemas.chunks import ChunkingConfig
from services.knowledge_base.base import ParserStrategy
from utils.enums import ChunkingMode, ParserType
from utils.logger.custom_logging import LoggerMixin


class ParserStrategyFactory:
    """Factory for creating parser strategies."""

    _strategies: ClassVar[dict] = {
        ParserType.FILE: FileParser,
        ParserType.URL: URLParser,
    }

    @classmethod
    def create_parser(cls, file_path: str, parser_type: ParserType, **kwargs: any) -> ParserStrategy | None:
        """Create a parser strategy based on the parser type."""
        parser_class = cls._strategies.get(parser_type)
        if not parser_class:
            return None
        return parser_class(file_path, **kwargs)


class ParseService(LoggerMixin):
    """Service for handling file parsing operations."""

    def __init__(self, llm_handler: LLMConfigurationHandler) -> None:
        super().__init__()
        self._llm_handler = llm_handler

    async def parse_file(
        self,
        file_path: str,
        parser_type: ParserType,
        chunking_config: ChunkingConfig,
        file_bytes: bytes | None = None,
    ) -> tuple[pd.DataFrame, int] | None:
        """Parse the file using the specified parser strategy and convert to DataFrame."""
        # Validate input parameters
        if parser_type == ParserType.FILE:
            is_valid = await self._validate_parser_input(file_path, parser_type, chunking_config)
            if not is_valid:
                self.logger.warning("Invalid file parser input: %s", file_path)
                return None

        parser = ParserStrategyFactory.create_parser(file_path, parser_type)
        if not parser:
            self.logger.error(
                'event=parser-strategy-not-found message="No parser strategy found"',
            )
            return None

        if parser_type == ParserType.FILE:
            parser_result = await parser.parse(
                file_bytes=file_bytes,
                file_path=file_path,
                chunking_config=chunking_config,
                llm_handler=self._llm_handler,
            )
        else:
            parser_result = await parser.parse(
                file_path=file_path,
                chunking_config=chunking_config,
            )
        if parser_result is None:
            self.logger.error(
                'event=knowledge-base-parse-failed message="Failed to parse document"',
            )
            return None

        # Convert ParserResult to DataFrame for backward compatibility
        df = pd.DataFrame(parser_result)
        word_count = int(df["content"].apply(lambda x: len(str(x).split()) if pd.notnull(x) else 0).sum())

        self.logger.info(
            'event=parse-file-success message="Successfully parsed file to unified format"',
        )

        return df, word_count

    async def _validate_parser_input(
        self,
        file_path: str,
        parser_type: ParserType,
        chunking_config: ChunkingConfig,
    ) -> bool:
        """
        Validate parser input parameters.

        :param file: Upload file to validate
        :param parser_type: Parser type to validate
        :param chunking_config: Chunking configuration to validate
        :return: True if all validations pass
        """
        # Validate file
        if not file_path:
            self.logger.error('event=validation-failed message="File is required"')
            return False

        # Validate parser type
        if parser_type not in ParserType.to_list():
            self.logger.error(
                'event=validation-failed parser_type=%s message="Unsupported parser type"',
                parser_type,
            )
            return False

        chunking_config = ChunkingConfig(**chunking_config.model_dump())

        self.logger.info(
            'event=input-validation-success file=%s parser_type=%s chunking_mode=%s message="Input validation passed"',
            file_path,
            parser_type,
            chunking_config.chunking_mode.value,
        )

        return True

    async def preview_chunk(
        self,
        parser_type: ParserType,
        file_path: str,
        chunking_mode: ChunkingMode,
        chunk_length: str,
        chunk_overlap: str,
        file_bytes: bytes | None = None,
    ) -> list[dict] | None:
        """Extract content from only the first 3 pages of a PDF document."""
        parser = ParserStrategyFactory.create_parser(file_path, parser_type)
        if not parser:
            self.logger.error(
                'event=parser-strategy-not-found message="No parser strategy found"',
            )
            return None
        if parser_type == ParserType.FILE:
            preview_chunk = await parser.parse(
                file_bytes=file_bytes,
                file_path=file_path,
                chunking_config=ChunkingConfig(
                    chunking_mode=chunking_mode,
                    chunk_length=chunk_length,
                    chunk_overlap=chunk_overlap,
                ),
                number_page=10,
                llm_handler=self._llm_handler,
            )
        else:
            preview_chunk = await parser.parse(
                file_path=file_path,
                chunking_config=ChunkingConfig(
                    chunking_mode=chunking_mode,
                    chunk_length=chunk_length,
                    chunk_overlap=chunk_overlap,
                ),
            )
        if preview_chunk is None:
            self.logger.error(
                'event=knowledge-base-parse-failed message="Failed to parse document"',
            )
            return None

        return preview_chunk
