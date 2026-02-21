from datetime import datetime
from typing import Any

from pydantic import BaseModel
from typing_extensions import TypedDict

from models.document_format import DocumentFormat
from models.document_type import DocumentType
from schemas.document_type import DocumentTypeTable
from schemas.training import DocumentTable, PerformanceMetrics


class TrainingState(TypedDict, total=False):
    """
    State object for the training agent.
    """

    system_message: str
    base64_images: list[str]
    output_parser: BaseModel
    document_type: DocumentType
    document_format: DocumentFormat
    document_fields_schema: Any
    extracted_fields: dict[str, str] | None
    mapped_fields: dict | None
    has_no_match: bool
    detected_tables: list[DocumentTypeTable]
    extracted_tables: list[DocumentTable] | None
    mapped_tables: dict | None
    no_tables: bool
    error: str | None
    metrics: PerformanceMetrics | None
    result_summary: dict[str, Any] | None
    start_time: datetime
    is_pdf: bool
