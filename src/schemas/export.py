from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from schemas.agent import AgentInDB
from schemas.document_content import DocumentContentInDB
from schemas.document_format import DocumentFormatInDB
from schemas.document_type import DocumentTypeInDB
from schemas.document_work_item import DocumentWorkItemInDB
from schemas.runbook import RunbookInDB
from utils.constants import TIMEZONE


class MetadataExport(BaseModel):
    """Metadata for export operations."""

    export_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp when the export was created",
    )


class DocumentTypeExport(BaseModel):
    """Export structure for Document Type."""

    metadata: MetadataExport
    document_type: DocumentTypeInDB | None = Field(default=None, description="Document type information")
    document_formats: list[DocumentFormatInDB] = Field(default_factory=list, description="Related document formats")
    document_work_items: list[DocumentWorkItemInDB] = Field(default_factory=list, description="Related document work items")
    document_contents: list[DocumentContentInDB] = Field(default_factory=list, description="Related document contents")


class AgentExport(BaseModel):
    """Export structure for Agent."""

    metadata: MetadataExport
    agent: dict[str, Any] | AgentInDB | None = Field(default=None, description="Agent information with runbook content")
    runbooks: list[RunbookInDB] = Field(default_factory=list, description="All related runbooks for this agent")
