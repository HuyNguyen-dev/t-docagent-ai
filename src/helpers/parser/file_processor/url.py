import re

import html2text

from helpers.parser.file_processor.base import BasePartition
from schemas.chunks import ChunkingConfig
from services.knowledge_base.chunk import ChunkingStrategyFactory
from utils.enums import DocumentSourceType


class URLPartition(BasePartition):
    def __init__(self) -> None:
        super().__init__(source_type=DocumentSourceType.URL)

    @staticmethod
    async def validate_and_process() -> None:
        pass

    async def get_chunks(
        self,
        file_path: str,
        source: str,
        chunking_config: ChunkingConfig,
    ) -> list[dict] | None:
        index = -1
        page_text = html2text.html2text(source)
        chunks = []
        cleaned_page_text = await self.remove_hyperlinks_and_brackets(page_text)
        if cleaned_page_text != "":
            # Apply text chunking with specified configuration
            chunking_strategy_obj = ChunkingStrategyFactory.create_strategy(
                chunking_config,
            )

            if chunking_strategy_obj is None:
                self.logger.error(
                    ('event=chunking-strategy-creation-failed strategy=%s message="Failed to create chunking strategy"'),
                    chunking_config.chunking_mode.value,
                )
            page_chunks = (
                [cleaned_page_text]
                if chunking_strategy_obj is None
                else await chunking_strategy_obj.split_text(cleaned_page_text)
            )
            # Add chunk metadata
            for chunk_text in page_chunks:
                index = index + 1
                chunk = {
                    "content": chunk_text,
                    "metadata": {
                        "source": file_path,
                        "index": index,
                    },
                }
                chunks.append(chunk)
        if not chunks:
            self.logger.error(
                'event=extraction-failed file=%s message="No content could be extracted from this file"',
                file_path,
            )
            return None

        self.logger.info(
            'event=extraction-success file=%s message="Successfully extracted and chunked"',
            file_path,
        )
        return chunks

    async def remove_hyperlinks_and_brackets(self, text: str) -> str:
        # Regular expression to match the pattern [title](url) and keep the title only
        # remove [Australian](https:/...) -> Australian
        cleaned_text = re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", text)
        # [![Australian](https:/...)] -> Australian
        return re.sub(r"!\[([^\]]*)\]\([^\)]*\)", r"\1", cleaned_text)
