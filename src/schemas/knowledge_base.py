from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from schemas.chunks import ChunkingConfigBase
from schemas.datasource import VectorDBConfig
from utils.constants import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_HYBRID_WEIGHT,
    DEFAULT_RELEVANCE_THRESHOLD,
    DEFAULT_TOP_K,
    TIMEZONE,
)
from utils.enums import (
    ChunkingMode,
    DataSourceType,
    EmbeddingModel,
    KnowledgeBaseSearchMethod,
    ParserType,
    VectorType,
)


class RetrievalMode(BaseModel):
    """Configuration for retrieval model."""

    search_method: KnowledgeBaseSearchMethod = Field(KnowledgeBaseSearchMethod.SEMANTIC, description="Search method to use")
    rerank_enabled: bool = Field(default=False, description="Whether reranking is enabled")
    top_k: int = Field(default=DEFAULT_TOP_K, description="Number of top results to retrieve")
    relevance_enabled: bool = Field(default=False, description="Whether relevance scoring is enabled")
    relevance_threshold: float = Field(
        default=DEFAULT_RELEVANCE_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Relevance threshold for filtering results",
    )
    hybrid_alpha_search_enabled: bool = Field(default=False, description="Hybrid alpha search is enabled")
    hybrid_weight: float = Field(
        default=DEFAULT_HYBRID_WEIGHT,
        ge=0.0,
        le=1.0,
        description="Weight for hybrid search (0.0 to 1.0)",
    )


class BaseKnowledgeBaseConfig(BaseModel):
    """Base configuration for knowledge base with common fields."""

    retrieval_mode: RetrievalMode = Field(..., description="Retrieval model configuration")


class BaseEmbeddingConfig(BaseModel):
    """Base configuration with embedding model and related properties."""

    embedding_model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        description="Configuration for embedding models",
    )

    @property
    def embedding_dimensions(self) -> int:
        """Get the embedding dimensions from the embedding model configuration."""
        if self.embedding_model:
            return EmbeddingModel.get_dimensions(self.embedding_model)
        return EmbeddingModel.get_dimensions(DEFAULT_EMBEDDING_MODEL)

    @property
    def provider(self) -> int:
        """Get the embedding provider from the embedding model configuration."""
        if self.embedding_model:
            return EmbeddingModel.get_provider(self.embedding_model)
        return EmbeddingModel.get_provider(DEFAULT_EMBEDDING_MODEL)


class KnowledgeBaseConfig(BaseEmbeddingConfig, BaseKnowledgeBaseConfig):
    """Configuration for knowledge base."""


class KnowledgeBaseInDB(BaseModel):
    """Knowledge base model."""

    id: str = Field(
        default_factory=lambda: f"kb-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
        description="Unique identifier for the knowledge base",
    )
    name: str = Field(..., max_length=100, description="Unique name for the knowledge base")
    tags: list[str] = Field(default_factory=list, description="Tags of the knowledge base")
    description: str = Field(default="", description="Description of the knowledge base")
    engine: VectorType = Field(..., description="Vector database engine")
    documents: list[str] = Field(default_factory=list, description="List of documents")
    config: KnowledgeBaseConfig = Field(..., description="Knowledge base configuration")
    data_source_type: DataSourceType = Field(..., description="Type of data source")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp when the knowledge base was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(TIMEZONE),
        description="Timestamp when the knowledge base was last updated",
    )
    created_by: str = Field(default="Admin", description="User who created the knowledge base")
    is_active: bool = Field(default=True, description="Whether the knowledge base is active")


class KnowledgeBaseConfigInput(BaseKnowledgeBaseConfig):
    """Configuration for knowledge base input."""


class KnowledgeBaseInput(BaseModel):
    """Model for creating a new knowledge base."""

    id: str = Field(
        default_factory=lambda: f"kb-{uuid4()!s}",
        alias="_id",
        alias_priority=2,
        description="Unique identifier for the knowledge base",
    )
    tags: list[str] = Field(default_factory=list, description="Tags of the knowledge base")
    description: str = Field(default="", description="Description of the knowledge base")
    engine: VectorType = Field(..., description="Vector database engine")
    config: KnowledgeBaseConfigInput = Field(..., description="Knowledge base configuration")


class KnowledgeBaseConfigUpdate(BaseKnowledgeBaseConfig):
    """Configuration for knowledge base update."""


class KnowledgeBaseUpdate(BaseModel):
    """Model for updating an existing knowledge base."""

    tags: list[str] = Field(default_factory=list, description="Tags of the knowledge base")
    description: str = Field(default="", description="Description of the knowledge base")
    config: KnowledgeBaseConfigUpdate | None = Field(None, description="Knowledge base configuration")
    is_active: bool | None = Field(None, description="Whether the knowledge base is active")


class KnowledgeBaseDetailResponse(BaseModel):
    """Response model for detailed knowledge base information."""

    id: str = Field(..., description="Unique identifier for the knowledge base")
    name: str = Field(..., description="Name of the knowledge base")
    tags: list[str] = Field(default_factory=list, description="Tags of the knowledge base")
    description: str = Field(default="", description="Description of the knowledge base")
    engine: str = Field(..., description="Vector database engine")
    document_count: int = Field(..., description="Number of documents in the knowledge base")
    chunk_count: int = Field(..., description="Number of chunks in the knowledge base")
    is_active: bool = Field(..., description="Status of the vector database")
    created_at: datetime | None = Field(None, description="Creation timestamp")
    last_updated: datetime | None = Field(None, description="Last update timestamp")


class KnowledgeBaseCreateResponse(BaseModel):
    """Response model for knowledge base creation with document and settings details."""

    id: str = Field(..., description="Unique identifier for the knowledge base")
    name: str = Field(..., description="Name of the knowledge base")
    tags: list[str] = Field(default_factory=list, description="Tags of the knowledge base")
    description: str = Field(..., description="Description of the knowledge base")
    engine: str = Field(..., description="Vector database engine")
    document_name: str | None = Field(None, description="Name of the uploaded document")
    document_id: str | None = Field(..., description="ID of the uploaded document")
    chunking_mode: str | None = Field(..., description="Chunking mode used for the knowledge base")
    chunking_length: int | None = Field(..., description="Chunk length used for the knowledge base")
    chunking_overlap: int | None = Field(..., description="Chunk overlap used for the knowledge base")
    settings: dict = Field(..., description="Processing settings used for the knowledge base")
    created_at: datetime = Field(..., description="Creation timestamp")


class DocumentWithKnowledgeBaseInfo(KnowledgeBaseCreateResponse):
    """Model for document with associated knowledge base information."""

    state: str = Field(..., description="Status of document")


class PreviewChunkResponse(BaseModel):
    """Response model for preview chunk with total chunks count."""

    chunks: list[dict] = Field(..., description="List of preview chunks")
    total_chunks: int = Field(..., description="Total number of chunks that would be created")
    document_name: str = Field(..., description="Name of the document being previewed")


class EmptyKnowledgeBaseRequest(BaseModel):
    """Request model for creating an empty knowledge base."""

    kb_name: str = Field(..., max_length=100, description="Name of the knowledge base to create")
    description: str = Field(None, description="Description of the knowledge base")


class CreateKnowledgeBaseInput(KnowledgeBaseInput, ChunkingConfigBase):
    """Request model for creating a knowledge base with file."""

    kb_name: str = Field(..., max_length=100, description="Name of the knowledge base to create")
    parser_type: ParserType = Field(..., description="Type of parser to use")
    chunking_mode: ChunkingMode = Field(..., description="Chunking mode used for the knowledge base")
    kb_doc_id: str = Field(
        default_factory=lambda: f"kb-{uuid4()!s}",
        description="Unique identifier for the knowledge base document",
    )


class ExternalKnowledgeBaseRequest(BaseModel):
    """Request model for creating a knowledge base from external source."""

    kb_name: str = Field(..., max_length=100, description="Name of the knowledge base to create")
    description: str = Field(None, description="Description of the knowledge base")
    vector_db_config: VectorDBConfig | None = Field(None, description="Vector database configuration")


class QueryKBInput(BaseModel):
    query: str = Field(..., description="The search query or question to find relevant information.")


class KnowledgeBaseToolView(BaseModel):
    name: str
    description: str = ""
