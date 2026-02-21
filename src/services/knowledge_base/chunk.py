import asyncio
import hashlib
from abc import ABC, abstractmethod
from typing import ClassVar

import orjson
import pandas as pd
from langchain_core.documents import Document
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import (
    CharacterTextSplitter,
    RecursiveCharacterTextSplitter,
)

from helpers.llm.embedding import EmbeddingService
from initializer import mindsdb_client, pg_client
from models.kb_document import KBDocument
from models.knowledge_base import KnowledgeBase
from schemas.chunks import ChunkInfo, ChunkingConfig
from schemas.response import Page
from utils.enums import VectorType
from utils.logger.custom_logging import LoggerMixin


class BaseChunkingStrategy(ABC, LoggerMixin):
    """Abstract base class for chunking strategies."""

    @abstractmethod
    async def split_text(self, text: str, **kwargs: any) -> list[str]:
        """Split text into chunks."""

    @abstractmethod
    async def split_documents(self, documents: list[Document], **kwargs: any) -> list[Document]:
        """Split documents into chunks."""


class RecursiveCharacterSplitStrategy(BaseChunkingStrategy):
    """Recursive character-based text splitting strategy."""

    def __init__(
        self,
        separators: list[str] | None = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        if separators is None:
            separators = ["\n\n", "\n", " ", ""]
        super().__init__()
        self.separators = separators
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            separators=self.separators,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

    async def split_text(self, text: str, **kwargs: any) -> list[str]:
        """Split text using recursive character-based splitting."""
        # Update parameters if provided
        if "chunk_size" in kwargs:
            self.chunk_size = kwargs["chunk_size"]
        if "chunk_overlap" in kwargs:
            self.chunk_overlap = kwargs["chunk_overlap"]
        if "separators" in kwargs:
            self.separators = kwargs["separators"]

        # Create new splitter with updated parameters
        self._splitter = RecursiveCharacterTextSplitter(
            separators=self.separators,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

        chunks = await asyncio.to_thread(self._splitter.split_text, text)

        if not chunks:
            self.logger.error(
                'event=recursive-character-split-error message="Error during recursive character-based text splitting"',
            )
            return []
        self.logger.debug(
            "event=recursive-character-split-success chunks=%d chunk_size=%d chunk_overlap=%d "
            'message="Successfully split text using recursive character splitting"',
            len(chunks),
            self.chunk_size,
            self.chunk_overlap,
        )
        return chunks

    async def split_documents(self, documents: list[Document], **kwargs: any) -> list[Document]:
        """Split documents using recursive character-based splitting."""
        # Update parameters if provided
        if "chunk_size" in kwargs:
            self.chunk_size = kwargs["chunk_size"]
        if "chunk_overlap" in kwargs:
            self.chunk_overlap = kwargs["chunk_overlap"]
        if "separators" in kwargs:
            self.separators = kwargs["separators"]

        # Create new splitter with updated parameters
        self._splitter = RecursiveCharacterTextSplitter(
            separators=self.separators,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

        split_docs = self._splitter.split_documents(documents)

        if not split_docs:
            self.logger.error(
                (
                    "event=recursive-character-split-documents-error "
                    'message="Error during recursive character-based document splitting"'
                ),
            )
            return documents
        self.logger.debug(
            "event=recursive-character-split-documents-success input_docs=%d output_docs=%d "
            'message="Successfully split documents using recursive character splitting"',
            len(documents),
            len(split_docs),
        )
        return split_docs


class SemanticChunkingStrategy(BaseChunkingStrategy):
    """Semantic-based text splitting strategy using embeddings with optimizations."""

    def __init__(
        self,
        embedding_config: dict,
        embeddings_model: str = "text-embedding-ada-002",
        breakpoint_threshold_type: str = "percentile",
        breakpoint_threshold_amount: float = 95.0,
        min_chunk_size: int = 100,
        use_cache: bool = True,
        batch_size: int = 10,
    ) -> None:
        super().__init__()
        self.embeddings_model = embeddings_model
        self.breakpoint_threshold_type = breakpoint_threshold_type
        self.breakpoint_threshold_amount = breakpoint_threshold_amount
        self.min_chunk_size = min_chunk_size
        self.use_cache = use_cache
        self.batch_size = batch_size
        self.embedding_config = embedding_config
        # Initialize embeddings
        self._embeddings = EmbeddingService(emb=self.embeddings_model).create_embedding()

        # Initialize semantic chunker
        self._splitter = SemanticChunker(
            embeddings=self._embeddings,
            breakpoint_threshold_type=self.breakpoint_threshold_type,
            breakpoint_threshold_amount=self.breakpoint_threshold_amount,
            min_chunk_size=self.min_chunk_size,
        )

        # Cache for embeddings and chunks
        self._embedding_cache: dict[str, list[float]] = {}
        self._chunk_cache: dict[str, list[str]] = {}

    def _get_text_hash(self, text: str) -> str:
        """Generate hash for text content for caching."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for a batch of texts with caching."""
        if not self.use_cache:
            return await self._embeddings.aembed_documents(texts)

        # Check cache first
        uncached_texts = []
        uncached_indices = []

        for i, text in enumerate(texts):
            text_hash = self._get_text_hash(text)
            if text_hash in self._embedding_cache:
                continue
            uncached_texts.append(text)
            uncached_indices.append(i)

        # Get embeddings for uncached texts
        if uncached_texts:
            uncached_embeddings = await self._embeddings.aembed_documents(uncached_texts)

            # Cache the results
            for text, embedding, _ in zip(uncached_texts, uncached_embeddings, uncached_indices, strict=False):
                text_hash = self._get_text_hash(text)
                self._embedding_cache[text_hash] = embedding

            self.logger.debug(
                'event=embeddings-cached count=%d message="Cached embeddings for semantic chunking"',
                len(uncached_embeddings),
            )

        # Return embeddings from cache
        return [self._embedding_cache[self._get_text_hash(text)] for text in texts]

    async def _split_text_semantic(self, text: str) -> list[str]:
        """Split text using semantic chunking with optimizations."""
        text_hash = self._get_text_hash(text)

        # Check chunk cache
        if self.use_cache and text_hash in self._chunk_cache:
            self.logger.debug(
                'event=chunk-cache-hit hash=%s message="Using cached chunks for semantic splitting"',
                text_hash[:8],
            )
            return self._chunk_cache[text_hash]

        try:
            # Use optimized semantic chunker
            chunks = await asyncio.to_thread(self._splitter.split_text, text)

            # Cache the result
            if self.use_cache:
                self._chunk_cache[text_hash] = chunks
                self.logger.info(
                    'event=chunks-cached hash=%s chunks=%d message="Cached semantic chunks"',
                    text_hash[:8],
                    len(chunks),
                )

        except Exception as e:
            self.logger.warning(
                'event=semantic-split-failed message="Semantic splitting failed, falling back to character splitting"',
                exc_info=e,
            )
            # Fallback to character splitting
            fallback_splitter = CharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
            )
            return fallback_splitter.split_text(text)
        return chunks

    async def split_text(self, text: str, **kwargs: any) -> list[str]:
        """Split text using semantic-based splitting with embeddings and optimizations."""
        if "breakpoint_threshold_type" in kwargs:
            self.breakpoint_threshold_type = kwargs["breakpoint_threshold_type"]
        if "breakpoint_threshold_amount" in kwargs:
            self.breakpoint_threshold_amount = kwargs["breakpoint_threshold_amount"]
        if "min_chunk_size" in kwargs:
            self.min_chunk_size = kwargs["min_chunk_size"]
        if "use_cache" in kwargs:
            self.use_cache = kwargs["use_cache"]

        # Create new splitter with updated parameters
        self._splitter = SemanticChunker(
            embeddings=self._embeddings,
            breakpoint_threshold_type=self.breakpoint_threshold_type,
            breakpoint_threshold_amount=self.breakpoint_threshold_amount,
            min_chunk_size=self.min_chunk_size,
        )

        # Use optimized semantic splitting
        chunks = await self._split_text_semantic(text)

        if not chunks:
            self.logger.error(
                'event=semantic-split-error message="Error during semantic-based text splitting"',
            )
            return []
        self.logger.debug(
            "event=semantic-split-success chunks=%d model=%s threshold=%s cache=%s "
            'message="Successfully split text using optimized semantic chunking"',
            len(chunks),
            self.embeddings_model,
            self.breakpoint_threshold_type,
            self.use_cache,
        )
        return chunks

    async def split_documents(self, documents: list[Document], **kwargs: any) -> list[Document]:
        """Split documents using semantic-based splitting with embeddings and optimizations."""
        if "breakpoint_threshold_type" in kwargs:
            self.breakpoint_threshold_type = kwargs["breakpoint_threshold_type"]
        if "breakpoint_threshold_amount" in kwargs:
            self.breakpoint_threshold_amount = kwargs["breakpoint_threshold_amount"]
        if "min_chunk_size" in kwargs:
            self.min_chunk_size = kwargs["min_chunk_size"]
        if "use_cache" in kwargs:
            self.use_cache = kwargs["use_cache"]

        # Create new splitter with updated parameters
        self._splitter = SemanticChunker(
            embeddings=self._embeddings,
            breakpoint_threshold_type=self.breakpoint_threshold_type,
            breakpoint_threshold_amount=self.breakpoint_threshold_amount,
            min_chunk_size=self.min_chunk_size,
        )

        # Process documents in batches for better performance
        split_docs = []
        for i in range(0, len(documents), self.batch_size):
            batch = documents[i : i + self.batch_size]

            # Split batch
            batch_splits = []
            for doc in batch:
                chunks = await self._split_text_semantic(doc.page_content)
                batch_splits.extend(
                    Document(
                        page_content=chunk,
                        metadata=doc.metadata,
                    )
                    for chunk in chunks
                )

            split_docs.extend(batch_splits)

            self.logger.info(
                'event=batch-processed batch=%d-%d message="Processed batch of documents"',
                i + 1,
                min(i + self.batch_size, len(documents)),
            )

        if not split_docs:
            self.logger.error(
                'event=semantic-split-documents-error message="Error during semantic-based document splitting"',
            )
            return documents
        self.logger.debug(
            "event=semantic-split-documents-success input_docs=%d output_docs=%d "
            'message="Successfully split documents using optimized semantic chunking"',
            len(documents),
            len(split_docs),
        )
        return split_docs


class ParagraphChunkingStrategy(BaseChunkingStrategy):
    """Paragraph-based text splitting strategy."""

    def __init__(
        self,
        separator: str = "\n\n",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        keep_separator: bool = True,
    ) -> None:
        super().__init__()
        self.separator = separator
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.keep_separator = keep_separator

        self._splitter = RecursiveCharacterTextSplitter(
            separators=[self.separator],
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            keep_separator=self.keep_separator,
        )

    async def split_text(self, text: str, **kwargs: any) -> list[str]:
        """Split text using paragraph-based splitting."""
        # Update parameters if provided
        if "chunk_size" in kwargs:
            self.chunk_size = kwargs["chunk_size"]
        if "chunk_overlap" in kwargs:
            self.chunk_overlap = kwargs["chunk_overlap"]
        if "separator" in kwargs:
            self.separator = kwargs["separator"]
        if "keep_separator" in kwargs:
            self.keep_separator = kwargs["keep_separator"]

        self._splitter = RecursiveCharacterTextSplitter(
            separators=[self.separator],
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            keep_separator=self.keep_separator,
        )

        chunks = await asyncio.to_thread(self._splitter.split_text, text)

        if not chunks:
            self.logger.error(
                'event=paragraph-split-error message="Error during paragraph-based text splitting"',
            )
            return []
        self.logger.debug(
            "event=paragraph-split-success chunks=%d chunk_size=%d chunk_overlap=%d "
            'message="Successfully split text using paragraph chunking"',
            len(chunks),
            self.chunk_size,
            self.chunk_overlap,
        )
        return chunks

    async def split_documents(self, documents: list[Document], **kwargs: any) -> list[Document]:
        """Split documents using paragraph-based splitting."""
        # Update parameters if provided
        if "chunk_size" in kwargs:
            self.chunk_size = kwargs["chunk_size"]
        if "chunk_overlap" in kwargs:
            self.chunk_overlap = kwargs["chunk_overlap"]
        if "separator" in kwargs:
            self.separator = kwargs["separator"]
        if "keep_separator" in kwargs:
            self.keep_separator = kwargs["keep_separator"]

        self._splitter = RecursiveCharacterTextSplitter(
            separators=[self.separator],
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            keep_separator=self.keep_separator,
        )

        split_docs = self._splitter.split_documents(documents)

        if not split_docs:
            self.logger.error(
                'event=paragraph-split-documents-error message="Error during paragraph-based document splitting"',
            )
            return documents
        self.logger.debug(
            "event=paragraph-split-documents-success input_docs=%d output_docs=%d "
            'message="Successfully split documents using paragraph chunking"',
            len(documents),
            len(split_docs),
        )
        return split_docs


class SentenceChunkingStrategy(BaseChunkingStrategy):
    """Sentence-based text splitting strategy."""

    def __init__(
        self,
        separators: list[str] | None = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        keep_separator: bool = True,
    ) -> None:
        if separators is None:
            separators = [". ", "! ", "? ", "\n"]
        super().__init__()
        self.separators = separators
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.keep_separator = keep_separator

        self._splitter = RecursiveCharacterTextSplitter(
            separators=self.separators,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            keep_separator=self.keep_separator,
        )

    async def split_text(self, text: str, **kwargs: any) -> list[str]:
        """Split text using sentence-based splitting."""
        # Update parameters if provided
        if "chunk_size" in kwargs:
            self.chunk_size = kwargs["chunk_size"]
        if "chunk_overlap" in kwargs:
            self.chunk_overlap = kwargs["chunk_overlap"]
        if "separators" in kwargs:
            self.separators = kwargs["separators"]
        if "keep_separator" in kwargs:
            self.keep_separator = kwargs["keep_separator"]

        self._splitter = RecursiveCharacterTextSplitter(
            separators=self.separators,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            keep_separator=self.keep_separator,
        )

        chunks = await asyncio.to_thread(self._splitter.split_text, text)

        if not chunks:
            self.logger.error(
                'event=sentence-split-error message="Error during sentence-based text splitting"',
            )
            return []
        self.logger.debug(
            "event=sentence-split-success chunks=%d chunk_size=%d chunk_overlap=%d "
            'message="Successfully split text using sentence chunking"',
            len(chunks),
            self.chunk_size,
            self.chunk_overlap,
        )
        return chunks

    async def split_documents(self, documents: list[Document], **kwargs: any) -> list[Document]:
        """Split documents using sentence-based splitting."""
        # Update parameters if provided
        if "chunk_size" in kwargs:
            self.chunk_size = kwargs["chunk_size"]
        if "chunk_overlap" in kwargs:
            self.chunk_overlap = kwargs["chunk_overlap"]
        if "separators" in kwargs:
            self.separators = kwargs["separators"]
        if "keep_separator" in kwargs:
            self.keep_separator = kwargs["keep_separator"]

        self._splitter = RecursiveCharacterTextSplitter(
            separators=self.separators,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            keep_separator=self.keep_separator,
        )

        split_docs = self._splitter.split_documents(documents)
        self.logger.debug(
            "event=sentence-split-documents-success input_docs=%d output_docs=%d "
            'message="Successfully split documents using sentence chunking"',
            len(documents),
            len(split_docs),
        )

        if not split_docs:
            self.logger.error(
                'event=sentence-split-documents-error message="Error during sentence-based document splitting"',
            )
            return documents
        return split_docs


class ChunkingStrategyFactory:
    """Factory for creating chunking strategies."""

    _strategies: ClassVar[dict[str, type]] = {
        "recursive_character": RecursiveCharacterSplitStrategy,
        "semantic": SemanticChunkingStrategy,
        "paragraph": ParagraphChunkingStrategy,
        "sentence": SentenceChunkingStrategy,
    }

    @classmethod
    def create_strategy(
        cls,
        chunking_config: ChunkingConfig,
    ) -> BaseChunkingStrategy | None:
        """Create a chunking strategy based on the chunking configuration."""
        try:
            strategy_class = cls._strategies.get(chunking_config.chunking_mode.value.lower())
            if not strategy_class:
                return None

            # Build kwargs based on chunking mode
            kwargs = {
                "chunk_size": chunking_config.chunk_length,
                "chunk_overlap": chunking_config.chunk_overlap,
            }

            # Add mode-specific parameters
            if chunking_config.chunking_mode.value == "character":
                if chunking_config.separator:
                    kwargs["separator"] = chunking_config.separator
            elif chunking_config.chunking_mode.value == "recursive_character":
                if chunking_config.separators:
                    kwargs["separators"] = chunking_config.separators
            elif chunking_config.chunking_mode.value == "semantic":
                if chunking_config.embeddings_model:
                    kwargs["embeddings_model"] = chunking_config.embeddings_model
                if chunking_config.embedding_config:
                    kwargs["embedding_config"] = chunking_config.embedding_config
                if chunking_config.breakpoint_threshold_type:
                    kwargs["breakpoint_threshold_type"] = chunking_config.breakpoint_threshold_type
                if chunking_config.breakpoint_threshold_amount is not None:
                    kwargs["breakpoint_threshold_amount"] = chunking_config.breakpoint_threshold_amount
                if chunking_config.min_chunk_size:
                    kwargs["min_chunk_size"] = chunking_config.min_chunk_size
            elif chunking_config.chunking_mode.value in ["paragraph", "sentence"] and chunking_config.keep_separator is not None:
                kwargs["keep_separator"] = chunking_config.keep_separator

            return strategy_class(**kwargs)

        except Exception:
            # Fallback to default recursive character strategy if config is invalid
            return RecursiveCharacterSplitStrategy(
                chunk_size=chunking_config.chunk_length,
                chunk_overlap=chunking_config.chunk_overlap,
            )

    @classmethod
    def create_strategy_from_string(
        cls,
        strategy_type: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        **kwargs: any,
    ) -> BaseChunkingStrategy | None:
        """Create a chunking strategy from string (backward compatibility)."""
        strategy_class = cls._strategies.get(strategy_type.lower())
        if not strategy_class:
            return None
        return strategy_class(chunk_size=chunk_size, chunk_overlap=chunk_overlap, **kwargs)

    @classmethod
    def get_available_strategies(cls) -> list[str]:
        """Get list of available chunking strategies."""
        return list(cls._strategies.keys())

    @classmethod
    def register_strategy(cls, name: str, strategy_class: type) -> None:
        """Register a new chunking strategy."""
        cls._strategies[name.lower()] = strategy_class

    @classmethod
    def unregister_strategy(cls, name: str) -> bool:
        """Unregister a chunking strategy."""
        if name.lower() in cls._strategies:
            del cls._strategies[name.lower()]
            return True
        return False


class ChunkService(LoggerMixin):
    """Service for managing chunks in knowledge base documents."""

    async def _get_chunks_with_paging_postgresql(
        self,
        kb_name: str,
        doc: KBDocument,
        search: str,
        page: int,
        page_size: int,
    ) -> dict | None:
        if not await pg_client.table_exists(kb_name):
            self.logger.error(
                "event=pgvector-table-not-found kb_name=%s doc_id=%s",
                kb_name,
                doc.id,
            )
            return None

        doc_source = doc.metadata.get("source", "")
        metadata_filter = {"source": doc_source} if doc_source else None

        search_result = await pg_client.search_with_filter_and_paging(
            table_name=kb_name,
            keyword=search,
            metadata_filter=metadata_filter,
            page=page,
            page_size=page_size,
            search_in="content",
        )

        if search_result is None:
            self.logger.error(
                'event=failed-to-get-chunks-postgresql doc_id=%s message="Unexpected error in PostgreSQL chunk retrieval"',
                doc.id,
            )
            return None
        return search_result

    async def _get_chunks_with_paging_mindsdb(
        self,
        kb_name: str,
        doc: KBDocument,
        search: str,
        page: int,
        page_size: int,
    ) -> dict | None:
        """Get chunks with pagination for MindsDB engine."""
        # --- Get KB from MindsDB ---
        kb = await mindsdb_client.get_kb(kb_name)
        if not kb:
            self.logger.error(
                "event=get-all-chunks-kb-not-found-mindsdb kb_name=%s doc_id=%s",
                kb_name,
                doc.id,
            )
            return None

        # --- Build base query ---
        base_query = f"""
            SELECT *,
                JSON_EXTRACT(metadata, '$.source') AS source,
                JSON_EXTRACT(metadata, '$.index') AS idx
            FROM {kb_name}
        """  # noqa: S608

        if search:
            base_query += f" WHERE content = '{search}'"

        # --- Build final query with pagination ---
        query = f"""
            SELECT *
            FROM ({base_query}) AS SubqueryAlias
            WHERE SubqueryAlias.source = '"{doc.metadata["source"]}"'
            ORDER BY CAST(SubqueryAlias.idx AS INTEGER)
            LIMIT {page_size} OFFSET {(page - 1) * page_size}
        """  # noqa: S608

        # --- Execute query ---
        try:
            query_chunks = await mindsdb_client.custom_query(query)
        except Exception:
            self.logger.exception(
                "event=get-all-chunks-query-failed kb_name=%s doc_id=%s",
                kb_name,
                doc.id,
            )
            return None

        # --- Handle empty result ---
        if query_chunks.empty:
            return {
                "items": [],
                "metadata": {
                    "page": page,
                    "page_size": page_size,
                    "total_items": 0,
                    "total_pages": 0,
                },
            }

        # --- Build chunk list ---
        document_chunks = [
            {
                "chunk_id": str(query_chunks["id"][i]),
                "content": chunk_content,
                "retrieval_count": 0,
                "enabled": True,
            }
            for i, chunk_content in enumerate(query_chunks["chunk_content"])
        ]

        # --- Pagination metadata ---
        all_results = await mindsdb_client.custom_query(base_query)
        total_chunks = len(all_results)
        total_pages = (total_chunks + page_size - 1) // page_size

        return {
            "items": document_chunks,
            "metadata": {
                "page": page,
                "page_size": page_size,
                "total_items": total_chunks,
                "total_pages": total_pages,
            },
        }

    async def get_all_chunks_with_paging(
        self,
        kb_id: str,
        doc_id: str,
        search: str,
        page: int,
        page_size: int,
    ) -> Page | None:
        """Get all chunks for a specific document with pagination support."""
        # --- Input validation ---
        page = max(1, page)
        page_size = max(1, min(page_size, 100))

        # --- Fetch KB and Document ---
        kb, doc = await asyncio.gather(
            KnowledgeBase.get(kb_id),
            KBDocument.get(doc_id),
        )

        if not kb:
            self.logger.warning(
                'event=get-all-chunks-kb-not-found doc_id=%s message="Knowledge base not found"',
                doc_id,
            )
            return None

        if not doc:
            self.logger.warning(
                'event=get-all-chunks-doc-not-found doc_id=%s message="Document not found"',
                doc_id,
            )
            return None

        # --- Query engine ---
        if kb.engine == VectorType.POSTGRESQL:
            search_result = await self._get_chunks_with_paging_postgresql(
                kb_name=kb.name,
                doc=doc,
                search=search,
                page=page,
                page_size=page_size,
            )
        else:
            search_result = await self._get_chunks_with_paging_mindsdb(
                kb_name=kb.name,
                doc=doc,
                search=search,
                page=page,
                page_size=page_size,
            )

        # --- Handle empty results ---
        if not search_result or not search_result.get("items"):
            self.logger.info(
                "event=get-all-chunks-empty kb_name=%s doc_id=%s search=%s page=%d",
                kb.name,
                doc_id,
                search,
                page,
            )
            return Page(
                items=[],
                metadata={
                    "page": page,
                    "page_size": page_size,
                    "total_items": 0,
                    "total_pages": 0,
                },
            )

        # --- Normalize data ---
        document_chunks = [
            {
                "chunk_id": str(row.get("chunk_id", row.get("id", ""))),
                "content": str(row.get("content", "")),
            }
            for row in search_result["items"]
        ]

        # --- Build page response ---
        return Page(
            items=[
                ChunkInfo(
                    index=(page - 1) * page_size + idx + 1,
                    chunk_id=chunk["chunk_id"],
                    content=chunk["content"],
                )
                for idx, chunk in enumerate(document_chunks)
            ],
            metadata=search_result["metadata"],
        )

    async def add_chunk(self, kb_id: str, doc_id: str, content: str) -> bool:
        """Add a new chunk to a document in the knowledge base."""
        # Find the knowledge base containing this document
        kb_name = await self._get_kb_name_by_id(kb_id)
        if not kb_name:
            self.logger.error(
                'event=add-chunk-kb-not-found doc_id=%s message="Knowledge base not found for document"',
                doc_id,
            )
            return False

        # Get the document
        doc = await KBDocument.get(doc_id)
        if not doc:
            self.logger.error(
                'event=add-chunk-doc-not-found doc_id=%s message="Document not found"',
                doc_id,
            )
            return False

        # Get document metadata
        metadata = doc.metadata
        if not metadata or "source" not in metadata:
            self.logger.error(
                'event=add-chunk-no-source doc_id=%s message="Document has no source metadata"',
                doc_id,
            )
            return False

        new_chunk_index = -1

        # Prepare chunk data
        rows = []
        row = {
            "content": content,
            "metadata": {
                "source": metadata["source"],
                "index": new_chunk_index,
            },
        }
        rows.append(row)
        df = pd.DataFrame(rows)
        word_count = int(df["content"].apply(lambda x: len(str(x).split()) if pd.notnull(x) else 0).sum())
        doc = await KBDocument.find_one(KBDocument.id == doc_id)
        if doc:
            new_word_count = max(0, (doc.words_count or 0) + word_count)

            await doc.update({"$set": {"words_count": new_word_count}})

        # Insert chunk into knowledge base
        success = await mindsdb_client.insert_kb(kb_name, df, kb_id, doc_id)
        if not success:
            self.logger.error(
                'event=add-chunk-insert-failed doc_id=%s kb_name=%s message="Failed to insert chunk into knowledge base"',
                doc_id,
                kb_name,
            )
            return False

        self.logger.info(
            "event=add-chunk-success doc_id=%s kb_name=%s new_total_chunks=%d ",
            doc_id,
            kb_name,
            new_chunk_index,
        )
        return True

    async def delete_chunks(self, kb_id: str, doc_id: str, chunk_ids: list[str]) -> bool:
        """Delete multiple chunks from a document in the knowledge base."""
        # Get KB and document
        kb = await KnowledgeBase.get(kb_id)
        if not kb:
            self.logger.error("event=delete-chunks-kb-not-found kb_id=%s", kb_id)
            return False

        doc = await KBDocument.get(doc_id)
        if not doc:
            self.logger.error("event=delete-chunks-doc-not-found doc_id=%s", doc_id)
            return False

        kb_name = kb.name
        if not chunk_ids:
            self.logger.warning("event=delete-chunks-empty-list doc_id=%s", doc_id)
            return True

        self.logger.info(
            "event=delete-chunks-start doc_id=%s kb_name=%s chunk_count=%d",
            doc_id,
            kb_name,
            len(chunk_ids),
        )

        # Decide ID column based on engine
        id_col = "chunk_id" if kb.engine == VectorType.POSTGRESQL else "id"
        chunk_ids_str = ", ".join([f"'{cid}'" for cid in chunk_ids])

        # Select all target chunks
        select_query = f"SELECT * FROM {kb_name} WHERE {id_col} IN ({chunk_ids_str})"  # noqa: S608
        result = await mindsdb_client.execute_query(select_query)

        if result.empty:
            self.logger.warning(
                'event=delete-chunks-not-found doc_id=%s kb_name=%s message="No chunks found for given IDs"',
                doc_id,
                kb_name,
            )
            return True

        # Update document word count
        total_removed_words = sum(len(str(row[2]).split()) for _, row in result.iterrows())
        new_word_count = max(0, (doc.words_count or 0) - total_removed_words)
        await doc.update({"$set": {"words_count": new_word_count}})

        if kb.engine == VectorType.POSTGRESQL:
            deleted = await self._delete_document_chunks_from_postgresql_by_ids(kb_name, chunk_ids)
        else:
            deleted = await self._delete_document_chunks_from_mindsdb_by_ids(kb_name, chunk_ids)

        if not deleted:
            self.logger.error(
                "event=delete-chunks-failed doc_id=%s kb_name=%s chunk_count=%d",
                doc_id,
                kb_name,
                len(chunk_ids),
            )
            return False

        self.logger.info(
            "event=delete-chunks-success doc_id=%s kb_name=%s deleted_count=%d new_word_count=%d",
            doc_id,
            kb_name,
            len(chunk_ids),
            new_word_count,
        )
        return True

    async def update_chunk(self, kb_id: str, doc_id: str, chunk_id: str, content: str) -> bool:
        """Update a chunk in a document in the knowledge base."""
        # Get KB and Document
        kb = await KnowledgeBase.get(kb_id)
        if not kb:
            self.logger.error("event=update-chunk-kb-not-found kb_id=%s", kb_id)
            return False

        doc = await KBDocument.get(doc_id)
        if not doc:
            self.logger.error("event=update-chunk-doc-not-found doc_id=%s", doc_id)
            return False

        kb_name = kb.name
        id_col = "chunk_id" if kb.engine == VectorType.POSTGRESQL else "id"

        # Retrieve the old chunk
        select_query = f"""
            SELECT {id_col}, chunk_content, metadata
            FROM {kb_name}
            WHERE {id_col} = '{chunk_id}'
        """  # noqa: S608
        result = await mindsdb_client.execute_query(select_query)

        if result.empty:
            self.logger.error(
                "event=update-chunk-not-found doc_id=%s kb_name=%s chunk_id=%s",
                doc_id,
                kb_name,
                chunk_id,
            )
            return False

        old_row = result.iloc[0]
        old_content = str(old_row[1])
        metadata = orjson.loads(old_row[2])

        # Delete old chunk
        if kb.engine == VectorType.POSTGRESQL:
            deleted = await self._delete_document_chunks_from_postgresql_by_ids(kb_name, [chunk_id])
        else:
            deleted = await self._delete_document_chunks_from_mindsdb_by_ids(kb_name, [chunk_id])

        if not deleted:
            self.logger.error(
                "event=update-chunk-delete-failed doc_id=%s kb_name=%s chunk_id=%s",
                doc_id,
                kb_name,
                chunk_id,
            )
            return False

        # Insert new content
        new_row = {"content": content, "metadata": metadata}
        df = pd.DataFrame([new_row])

        inserted = await mindsdb_client.insert_kb(kb_name=kb_name, content_data=df, kb_id=kb_id, doc_id=doc_id)
        if not inserted:
            self.logger.error(
                "event=update-chunk-insert-failed doc_id=%s kb_name=%s chunk_id=%s",
                doc_id,
                kb_name,
                chunk_id,
            )
            return False

        # Update document word count
        old_wc = len(old_content.split())
        new_wc = len(content.split())
        word_diff = new_wc - old_wc

        new_total_wc = max(0, (doc.words_count or 0) + word_diff)
        await doc.update({"$set": {"words_count": new_total_wc}})

        self.logger.info(
            "event=update-chunk-success doc_id=%s kb_name=%s chunk_id=%s old_wc=%d new_wc=%d",
            doc_id,
            kb_name,
            chunk_id,
            old_wc,
            new_wc,
        )
        return True

    async def _get_kb_name_by_id(self, kb_id: str) -> str | None:
        """Get knowledge base name by ID."""
        kb = await KnowledgeBase.get(kb_id)
        if not kb:
            return None
        return kb.name

    async def _delete_document_chunks_from_mindsdb(self, kb_name: str, doc_name: str) -> bool:
        """Delete document chunks from MindsDB by filtering on source metadata."""
        # Delete chunks from this knowledge base using SQL DELETE FROM syntax
        select_sql = f"SELECT * FROM {kb_name}"  # noqa: S608

        result = await mindsdb_client.execute_query(select_sql)

        if not result.empty:
            deleted_ids = result[0].tolist()
            ids_str = ", ".join([f"'{id_}'" for id_ in deleted_ids])
            delete_sql = f"DELETE FROM {kb_name} WHERE id IN ({ids_str});"  # noqa: S608

            result = await mindsdb_client.execute_query(delete_sql)

        self.logger.info(
            "event=delete-document-chunks-mindsdb-complete doc_name=%s ",
            doc_name,
        )
        return True

    async def _delete_document_chunks_from_mindsdb_by_ids(self, kb_name: str, chunk_ids: list[str]) -> bool:
        """Delete document chunks from MindsDB by filtering on source metadata."""
        ids_str = ", ".join([f"'{id_}'" for id_ in chunk_ids])
        delete_sql = f"DELETE FROM {kb_name} WHERE id IN ({ids_str});"  # noqa: S608

        await mindsdb_client.execute_query(delete_sql)

        self.logger.info(
            "event=delete-document-chunks-mindsdb-complete ",
        )
        return True

    async def _delete_document_chunks_from_postgresql(
        self,
        table_name: str,
        source_path: str,
        doc_name: str,
    ) -> None:
        """Delete document chunks from PostgreSQL by filtering on source metadata."""
        deleted_count = await pg_client.delete_chunks_by_metadata(
            table_name=table_name,
            metadata_key="source",
            metadata_value=source_path,
        )

        self.logger.info(
            "event=delete-document-chunks-postgresql-complete doc_name=%s deleted_count=%d",
            doc_name,
            deleted_count,
        )

    async def _delete_document_chunks_from_postgresql_by_ids(
        self,
        table_name: str,
        chunk_ids: list[str] | None = None,
    ) -> bool:
        """Delete document chunks from PostgreSQL by filtering on source metadata."""
        deleted_count = await pg_client.delete_chunks_by_ids(
            table_name=table_name,
            chunk_ids=chunk_ids,
        )

        if deleted_count > 0:
            self.logger.info(
                "event=delete-document-chunks-postgresql kb_name=%s deleted_count=%d",
                table_name,
                deleted_count,
            )
            return True
        return False
