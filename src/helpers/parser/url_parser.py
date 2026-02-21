from bs4 import BeautifulSoup
from httpx import AsyncClient

from helpers.parser.base_parser import BaseParser
from helpers.parser.file_processor.factory import partition_factory
from initializer import http_client
from schemas.chunks import ChunkingConfig
from utils.enums import DocumentExtension, DocumentSourceType


class URLParser(BaseParser):
    def __init__(self, file_path: str) -> None:
        super().__init__()
        self._document_partition = partition_factory(
            file_name=file_path,
            source_type=DocumentSourceType.URL,
        )

    async def _extract_content(self, url: str, client: AsyncClient) -> tuple[str, str, str]:
        try:
            response = await client.get(url)
            # Check for response status
            if response.status_code == 200:
                # Parse the title
                soup = BeautifulSoup(response.text, "lxml")
                title = soup.title.string if soup.title else None
                return response.text, title, "Valid URL"

        except Exception as e:
            return "", "", f"An unexpected error occurred: {e!s}"
        return (
            "",
            "",
            f"Error occurred while fetching the URL: {url}. "
            f"Status code: {response.status_code}. "
            "Please check the URL you provided.",
        )

    async def parse(
        self,
        file_path: str,
        chunking_config: ChunkingConfig,
    ) -> tuple[dict | None, str]:
        try:
            self.logger.debug(
                'event=start-extract-text-from-url message="Start URL parse: %s"',
                file_path,
            )

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
            text, _, _ = await self._extract_content(file_path, http_client)
            chunks = await self._document_partition.get_chunks(
                file_path=file_path,
                source=text,
                chunking_config=chunking_config,
            )

        except Exception:
            self.logger.exception(
                'event=extract-text-from-file-failure message="Process failed." message="Unexpected error!"',
            )
            return []
        return chunks
