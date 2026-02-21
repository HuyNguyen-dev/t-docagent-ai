from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from utils.constants import TIMEZONE
from utils.enums import DocumentContentState


class DocumentContentTable(BaseModel):
    id: str
    columns: list[dict[str, str]] = Field(default_factory=list)


class ExtractedContent(BaseModel):
    fields: dict[str, str] = Field(default_factory=dict)
    tables: list[DocumentContentTable] = Field(default_factory=list)


class TransformedContent(ExtractedContent):
    computed_fields: dict[str, str] = Field(default_factory=dict)


class DocumentContentInDB(BaseModel):
    id: str = Field(
        default_factory=lambda: f"dc-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
    )
    dwi_id: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp at the time of object creation",
    )
    state: DocumentContentState = DocumentContentState.IN_PROCESS
    extracted_content: ExtractedContent = Field(default_factory=ExtractedContent)
    transformed_content: TransformedContent = Field(default_factory=TransformedContent)
    computed_content: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
