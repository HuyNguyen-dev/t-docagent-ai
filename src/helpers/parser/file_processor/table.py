from pyexcel_xlsx import get_data

from helpers.parser.file_processor.base import BasePartition
from schemas.chunks import ChunkingConfig
from services.knowledge_base.chunk import ChunkingStrategyFactory
from utils.enums import DocumentSourceType, TableIngestionMode


class TablePartition(BasePartition):
    def __init__(self) -> None:
        super().__init__(source_type=DocumentSourceType.DOC_FILE)

    async def get_chunks(
        self,
        file_path: str,
        source: str,
        chunking_config: ChunkingConfig,
        **kwargs: any,
    ) -> list[dict] | None:
        """Parse and format documents from the source."""
        header = kwargs.get("include_header", True)
        mode = kwargs.get("mode", TableIngestionMode.DEFAULT.value)
        tables = get_data(source, file_type=file_path.split(".")[-1], encoding="ISO-8859-1")

        start_index = 1 if header else 0
        chunks = []
        index = -1
        for table in tables.values():
            rows = []
            for row in table:
                if row:
                    process_row = [str(cell).replace("\n", " ") for cell in row if str(cell)]
                    rows.append(process_row)
            for row in rows[start_index:]:
                template = self.create_template(row, header, rows, mode)
                if template != "":
                    # Apply text chunking with specified configuration
                    chunking_strategy_obj = ChunkingStrategyFactory.create_strategy(
                        chunking_config,
                    )

                    if chunking_strategy_obj is None:
                        self.logger.error(
                            ('event=chunking-strategy-creation-failed strategy=%s message="Failed to create chunking strategy"'),
                            chunking_config.chunking_mode.value,
                        )
                        page_chunks = [template]  # Fallback to original content
                    else:
                        page_chunks = await chunking_strategy_obj.split_text(template)
                    # Add chunk metadata
                    for chunk_text in page_chunks:
                        index += 1
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
                'event=table-extraction-failed file=%s message="No chunks could be extracted from this file"',
                file_path,
            )
            return None

        self.logger.info(
            'event=table-extraction-success file=%s message="Successfully extracted and chunked"',
            file_path,
        )
        return chunks

    def create_template(self, row: list, header: bool, rows: list, mode: TableIngestionMode) -> str:
        """
        Create a formatted string template for the document. Format:
        columns_name_1: answer_column_1
        columns_name_2: answer_column_2
        """

        row = [str(cell).replace("\n", " ") for cell in row]
        if header:
            return "\n".join(f"{rows[0][i] if i < len(rows[0]) else 'Text'}: {row[i]}" for i in range(len(row)))
        # Create a template with just the row values
        # answer_column_1
        # answer_column_2
        if mode == TableIngestionMode.QNA:
            return f"Question: {row[0]} \n Answer: {row[1]}"
        return "\n".join(cell for cell in row)
