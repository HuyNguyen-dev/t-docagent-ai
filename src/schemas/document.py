from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from schemas.chunks import ChunkingConfigBase
from utils.constants import TIMEZONE
from utils.enums import ChunkingMode, InsertKBDocState


class DocumentInDB(BaseModel):
    """Document model for knowledge base documents."""

    id: str = Field(
        default_factory=lambda: f"kb_doc-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
        description="Unique identifier for the document",
    )
    name: str = Field(..., max_length=255, description="Name of the document")
    kb_name: str = Field(..., max_length=255, description="Name of the knowledge base")
    chunking_mode: ChunkingMode = Field(..., description="Chunking mode used for processing")
    chunking_config: ChunkingConfigBase = Field(
        default_factory=ChunkingConfigBase,
        description="Configuration for document chunking",
    )
    words_count: int = Field(..., ge=0, description="Total number of words in the document")
    upload_time: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp when the document was uploaded",
    )
    state: InsertKBDocState = InsertKBDocState.IN_PROCESS
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for the document",
    )


class DocumentCreate(BaseModel):
    """Model for creating a new document."""

    name: str = Field(..., max_length=255, description="Name of the document")
    chunking_mode: ChunkingMode = Field(..., description="Chunking mode to use for processing")
    words_count: int = Field(..., ge=0, description="Total number of words in the document")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for the document",
    )


class DocumentUpdate(BaseModel):
    """Model for updating an existing document."""

    name: str | None = Field(None, max_length=255, description="Name of the document")
    chunking_mode: ChunkingMode | None = Field(None, description="Chunking mode used for processing")
    chunking_config: ChunkingConfigBase | None = Field(
        None,
        description="Configuration for document chunking",
    )
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata for the document")


class DocumentResponse(BaseModel):
    """Response model for document operations."""

    id: str = Field(..., description="Unique identifier for the document")
    name: str = Field(..., description="Name of the document")
    chunking_mode: str = Field(..., description="Chunking mode used for processing")
    words_count: int = Field(..., description="Total number of words in the document")
    upload_time: datetime = Field(..., description="Upload timestamp")
    metadata: dict[str, Any] = Field(..., description="Additional metadata for the document")


class DocumentListResponse(BaseModel):
    """Response model for listing documents."""

    documents: list[DocumentResponse] = Field(..., description="List of documents")
    total_count: int = Field(..., description="Total number of documents")


class KBDocumentDetailResponse(BaseModel):
    """Response model for detailed KBDocument information."""

    id: str = Field(..., description="Unique identifier for the document")
    name: str = Field(..., description="Name of the document")
    chunking_mode: str = Field(..., description="Chunking mode used for processing")
    words_count: int = Field(..., description="Total number of words in the document")
    upload_time: datetime | None = Field(None, description="Upload timestamp")
    metadata: dict[str, Any] = Field(..., description="Additional metadata for the document")
    state: InsertKBDocState = InsertKBDocState.IN_PROCESS
