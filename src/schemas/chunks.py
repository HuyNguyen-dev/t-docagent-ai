from typing import Any

from pydantic import BaseModel, Field

from utils.constants import DEFAULT_CHUNK_LENGTH, DEFAULT_CHUNK_OVERLAP
from utils.enums import ChunkingMode


class ChunkingConfigBase(BaseModel):
    chunk_length: int = Field(
        default=DEFAULT_CHUNK_LENGTH,
        gt=0,
        description="Length of each chunk in characters",
    )
    chunk_overlap: int = Field(
        default=DEFAULT_CHUNK_OVERLAP,
        ge=0,
        description="Number of overlapping characters between chunks",
    )


class ChunkingConfig(ChunkingConfigBase):
    """Configuration for document chunking."""

    chunking_mode: ChunkingMode = Field(
        default=ChunkingMode.PARAGRAPH,
        description="Chunking strategy to use",
    )

    # Character-based chunking options
    separator: str | None = Field(
        default="\n\n",
        description="Separator for character-based splitting",
    )
    separators: list[str] | None = Field(
        default_factory=lambda: ["\n\n", "\n", " ", ""],
        description="List of separators for recursive character splitting",
    )

    # Semantic chunking options
    embeddings_model: str | None = Field(
        default="text-embedding-ada-002",
        description="Embeddings model for semantic chunking",
    )
    breakpoint_threshold_type: str | None = Field(
        default="percentile",
        description="Threshold type for semantic breakpoints",
    )
    breakpoint_threshold_amount: float | int | None = Field(
        default=95.0,
        description="Threshold amount for semantic breakpoints",
    )
    min_chunk_size: int | None = Field(
        default=100,
        gt=0,
        description="Minimum chunk size for semantic chunking",
    )

    # Keep separator option for paragraph/sentence chunking
    keep_separator: bool | None = Field(
        default=True,
        description="Whether to keep separators in chunks",
    )

    # Semantic chunking optimizations
    use_cache: bool | None = Field(
        default=True,
        description="Whether to use caching for semantic chunking to reduce API costs",
    )
    batch_size: int | None = Field(
        default=10,
        gt=0,
        description="Batch size for processing documents in semantic chunking",
    )
    embedding_config: dict | None = Field(default_factory=dict, description="Embedding config for semantic chunking")


class ParserOutput(BaseModel):
    """Unified output format for all document parsers."""

    content: str = Field(..., description="The parsed content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata associated with the content")
    chunk_index: int = Field(default=0, description="Index of this chunk in the document")
    source: str | None = Field(None, description="Source file path or identifier")


class ParserResult(BaseModel):
    """Result containing multiple parser outputs."""

    chunks: list[ParserOutput] = Field(default_factory=list, description="List of parsed chunks")
    total_chunks: int = Field(default=0, description="Total number of chunks")
    word_count: int = Field(default=0, description="Total word count")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Document-level metadata")


class ChunkInfo(BaseModel):
    """Model for individual chunk information."""

    index: int = Field(..., description="Unique identifier for the chunk (e.g., Chunk-01)")
    chunk_id: str | None = Field(None, description="Unique identifier for the chunk")
    content: str = Field(..., description="Content of the chunk")
    citation: str | dict | None = Field(None, description="Citation contains the chunk")


class ChunksPaginationInfo(BaseModel):
    """Model for chunks pagination information."""

    current_page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of chunks per page")
    total_pages: int = Field(..., description="Total number of pages")
    total_chunks: int = Field(..., description="Total number of chunks")


class DocumentChunksInfo(BaseModel):
    """Model for document chunks information."""

    doc_id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Original filename of the document")
    total_chunks: int = Field(..., description="Total number of chunks in the document")
    avg_chunk_length: float = Field(..., description="Average length of chunks in characters")


class ChunksResponse(BaseModel):
    """Response containing chunks with pagination."""

    chunks: list[ChunkInfo]
    pagination: ChunksPaginationInfo
    document_info: DocumentChunksInfo
    metadata: dict | None = None


# Schema for adding chunks
class AddChunkRequest(BaseModel):
    """Request model for adding a new chunk to a document."""

    content: str = Field(..., description="Content of the new chunk")


# Schema for deleting chunks
class DeleteChunksRequest(BaseModel):
    """Request model for deleting multiple chunks from a document."""

    chunk_ids: list[str] = Field(..., description="List of chunk IDs to delete")


class ChunksListResponse(BaseModel):
    """Response model for listing chunks."""

    status: str = Field(..., description="Response status (success/failed)")
    message: str = Field(..., description="Response message")
    data: ChunksResponse | None = Field(None, description="Chunks data with pagination")


# Schema for updating chunks
class UpdateChunkRequest(BaseModel):
    """Request model for updating an existing chunk in a document."""

    content: str = Field(..., description="New content for the chunk")
