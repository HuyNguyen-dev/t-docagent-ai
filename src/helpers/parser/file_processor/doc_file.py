import io
import tempfile
from pathlib import Path

import aiofiles
import fitz
import pytesseract
from PIL import Image
from pymupdf import Page

from helpers.parser.file_processor.base import BasePartition
from schemas.chunks import ChunkingConfig
from services.knowledge_base.chunk import ChunkingStrategyFactory
from utils.common import convert_office_doc
from utils.enums import DocumentSourceType


class DocFilePartition(BasePartition):
    def __init__(self) -> None:
        super().__init__(source_type=DocumentSourceType.DOC_FILE)
        self.mat = fitz.Matrix(5, 5)  # High-resolution matrix for image rendering
        self.invalid_unicode = chr(0xFFFD)

    async def get_chunks(
        self,
        file_path: str,
        source: bytes,
        chunking_config: ChunkingConfig,
        number_page: int | None = None,
        **kwargs: any,
    ) -> list[dict] | None:
        """Parse and format documents from the source."""
        if kwargs:
            kwargs = None

        file_extension = file_path.split(".")[-1]
        doc = await self.open_document(source, file_extension)

        pages = number_page if number_page is not None else len(doc)
        chunks = []
        index = -1
        for page_number in range(pages):
            try:
                page = doc[page_number]
                page_text = await self.extract_page_text(page)

                if not page_text.strip():
                    page_text = await self.scan_ocr(page)
                if page_text != "":
                    # Apply text chunking with specified configuration
                    chunking_strategy_obj = ChunkingStrategyFactory.create_strategy(
                        chunking_config,
                    )

                    if chunking_strategy_obj is None:
                        self.logger.error(
                            ('event=chunking-strategy-creation-failed strategy=%s message="Failed to create chunking strategy"'),
                            chunking_config.chunking_mode.value,
                        )
                        page_chunks = [page_text]  # Fallback to original content
                    else:
                        page_chunks = await chunking_strategy_obj.split_text(page_text)
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

            except Exception:
                self.logger.warning(
                    'event=page-extraction-warning file=%s page=%d message="Failed to extract page %d"',
                    file_path,
                    page_number + 1,
                    page_number + 1,
                )
                continue

        if not chunks:
            self.logger.error(
                'event=pdf-pages-extraction-failed file=%s message="No pages could be extracted from PDF"',
                file_path,
            )
            return None

        self.logger.info(
            'event=pdf-pages-extraction-success file=%s message="Successfully extracted and chunked first"',
            file_path,
        )

        return chunks

    async def open_document(self, source: bytes, file_extension: str) -> fitz.Document:
        if file_extension in ["doc", "docx"]:
            source = await self.convert_doc_to_pdf(source, file_extension)
            return fitz.open(stream=source, filetype="pdf")
        return fitz.open(stream=source, filetype=file_extension)

    async def convert_doc_to_pdf(self, source: bytes, file_extension: str) -> io.BytesIO:
        with tempfile.TemporaryDirectory() as target_dir:
            source_file_path = f"{target_dir}/document.{file_extension}"

            async with aiofiles.open(source_file_path, "wb") as f:
                await f.write(source)

            await convert_office_doc(
                source_file_path,
                target_dir,
                target_format="pdf",
            )

            source_file_path = Path(source_file_path)
            target_dir = Path(target_dir)
            base_filename = source_file_path.stem
            target_file_path = target_dir / f"{base_filename}.pdf"
            async with aiofiles.open(target_file_path, "rb") as f:
                source = io.BytesIO(await f.read())
        return source

    async def extract_page_text(self, page: Page) -> str:
        """Extract text from a page, including handling invalid characters."""
        blocks = page.get_text("dict", flags=0)["blocks"]
        page_width = page.rect.width
        sorted_blocks = await self.sort_bboxes(blocks, page_width)
        page_text = ""

        for block in sorted_blocks:
            page_text += await self.process_block(page, block)
        return page_text

    async def process_block(self, page: Page, block: dict) -> str:
        """Process each text block."""
        text_inline = ""
        if "lines" not in block:
            return ""
        for line in block["lines"]:
            for span in line["spans"]:
                text_inline += await self.process_span(page, span)
        return text_inline + "\n"

    async def process_span(self, page: Page, span: dict) -> str:
        """Process each text span, including handling invalid characters."""
        text = span["text"]
        if self.invalid_unicode in text:
            return await self.handle_invalid_unicode(page, span["bbox"], text)
        return text + " "

    async def handle_invalid_unicode(self, page: Page, bbox: list, text: str) -> str:
        """Handle spans containing invalid Unicode characters."""
        leading_spaces = " " * (len(text) - len(text.lstrip()))
        trailing_spaces = " " * (len(text) - len(text.rstrip()))
        text_decoded = await self.decode_words(page, bbox)
        return f"{leading_spaces}{text_decoded}{trailing_spaces} "

    async def decode_words(self, page: Page, bbox: list) -> str:
        """Decode words from a specific bounding box using OCR."""
        pix = page.get_pixmap(matrix=self.mat, clip=bbox)
        ocrpdf = fitz.open("pdf", pix.pdfocr_tobytes())
        ocrpage = ocrpdf[0]
        return ocrpage.get_text().rstrip("\n")

    async def scan_ocr(self, page: Page) -> str:
        """Perform OCR on the entire page."""
        pix = page.get_pixmap(matrix=self.mat, dpi=300)
        image_data = io.BytesIO(pix.tobytes("ppm"))
        return pytesseract.image_to_string(Image.open(image_data))

    async def sort_bboxes(self, bboxes: list[dict], page_width: float) -> list[dict]:
        """Sort bounding boxes into left and right columns, ordered top to bottom."""
        mid_x = page_width / 2
        left_column, right_column = [], []

        for box in bboxes:
            bbox = box["bbox"]
            (left_column if bbox[0] < mid_x else right_column).append(box)

        left_column_sorted = sorted(left_column, key=lambda x: (x["bbox"][3], x["bbox"][0]))
        right_column_sorted = sorted(right_column, key=lambda x: (x["bbox"][3], x["bbox"][0]))
        return left_column_sorted + right_column_sorted
