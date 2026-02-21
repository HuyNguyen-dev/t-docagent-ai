from os import PathLike
from pathlib import Path

from helpers.parser.file_processor import (
    BasePartition,
    DocFilePartition,
)
from helpers.parser.file_processor.table import TablePartition
from helpers.parser.file_processor.url import URLPartition
from utils.enums import DocumentExtension, DocumentSourceType


def partition_factory(
    file_name: str | None = None,
    source_type: DocumentSourceType = DocumentSourceType.DOC_FILE,
) -> BasePartition | None:
    source_type_mapping = {
        DocumentSourceType.URL: URLPartition,
    }
    partition_class = source_type_mapping.get(source_type)
    if partition_class:
        return partition_class()
    if not file_name:
        return None
    # Ensure file_name is a string-like path
    if not isinstance(file_name, (str, Path, PathLike)):
        return None
    file_extension = Path(file_name).suffix.lower()
    extension_mapping = {
        DocumentExtension.DOCX.value: DocFilePartition,
        DocumentExtension.DOC.value: DocFilePartition,
        DocumentExtension.HTML.value: DocFilePartition,
        DocumentExtension.PDF.value: DocFilePartition,
        DocumentExtension.TXT.value: DocFilePartition,
        DocumentExtension.EXCEL_NEW.value: TablePartition,
        DocumentExtension.EXCEL_OLD.value: TablePartition,
        DocumentExtension.CSV.value: TablePartition,
    }
    partition_class = extension_mapping.get(file_extension)
    return partition_class() if partition_class is not None else None
