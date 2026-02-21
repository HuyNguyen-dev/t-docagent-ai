import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import orjson
from fastapi import BackgroundTasks, UploadFile

from handlers.llm_configuration import LLMConfigurationHandler
from models.kb_document import KBDocument
from models.knowledge_base import KnowledgeBase
from models.tag import Tag
from schemas.chunks import ChunkInfo, ChunkingConfig, ChunkingConfigBase
from schemas.datasource import VectorDBConfig
from schemas.document import DocumentUpdate
from schemas.knowledge_base import (
    CreateKnowledgeBaseInput,
    DocumentWithKnowledgeBaseInfo,
    KnowledgeBaseConfig,
    KnowledgeBaseConfigUpdate,
    KnowledgeBaseCreateResponse,
    RetrievalMode,
)
from schemas.llm_configuration import LLMConfigurationInput
from schemas.model_config import MindsDbModelConfigs, ModelConfig
from schemas.response import Page
from schemas.tag import TagUpdate
from services import ChunkService, ConfigService, DocumentService, KnowledgeBaseService, ParseService, TagService
from utils.constants import DEFAULT_KB_INTAKE_FOLDER, TIMEZONE
from utils.enums import ChunkingMode, DataSourceType, ParserType
from utils.logger.custom_logging import LoggerMixin


class KnowledgeBaseHandler(LoggerMixin):
    """Main handler for knowledge base operations using composition of services."""

    def __init__(self, llm_handler: LLMConfigurationHandler) -> None:
        super().__init__()
        self._llm_handler = llm_handler
        self._config_service = ConfigService(self._llm_handler)
        self._parsing_service = ParseService(self._llm_handler)
        self._chunk_service = ChunkService()
        self._document_service = DocumentService(self._parsing_service, self._chunk_service, self._llm_handler)
        self._tag_service = TagService()
        self._kb_service = KnowledgeBaseService(self._llm_handler, self._document_service, self._tag_service)

    # Configuration methods
    async def set_config(self, config_input: LLMConfigurationInput) -> bool:
        """Set the MindsDB configuration for embedding and reranking models."""
        return await self._config_service.set_config(config_input)

    async def get_config(self) -> MindsDbModelConfigs | None:
        """Get the current MindsDB configuration."""
        return await self._config_service.get_config()

    async def set_default_llm(self, llm_config: ModelConfig) -> bool:
        """Set the default LLM configuration for the MindsDB client."""
        return await self._config_service.set_default_llm(llm_config)

    async def preview_chunk(
        self,
        chunking_mode: ChunkingMode,
        chunk_length: int,
        chunk_overlap: int,
        file: UploadFile | None = None,
        url: str | None = None,
    ) -> list[dict] | None:
        """Extract content from only the first 3 pages of a PDF document."""
        parser_type = ParserType.FILE if file is not None else ParserType.URL
        file_bytes = None
        if file is not None:
            path_file = file.filename
            parser_type = ParserType.FILE
            file_bytes = await file.read()
        else:
            path_file = url
            parser_type = ParserType.URL

        return await self._parsing_service.preview_chunk(
            parser_type,
            path_file,
            chunking_mode,
            chunk_length,
            chunk_overlap,
            file_bytes,
        )

    async def preview_chunk_in_update(
        self,
        kb_id: str,
        chunking_mode: ChunkingMode,
        doc_id: str,
        chunk_length: int,
        chunk_overlap: int,
    ) -> list[dict] | None:
        """Extract content from only the first 3 pages of a PDF document."""
        return await self._document_service.preview_chunk_in_update(
            kb_id,
            doc_id,
            chunking_mode,
            chunk_length,
            chunk_overlap,
        )

    async def list_all(self) -> list[str] | None:
        """List all knowledge bases."""
        return await self._kb_service.list_all()

    async def list_for_agents(self) -> list[str] | None:
        """List all knowledge bases."""
        return await self._kb_service.list_for_agents()

    async def get_all_tags(self) -> list[str] | None:
        """Get all unique tags from knowledge bases."""
        return await self._kb_service.get_all_tags()

    async def get_kb_detail(self, kb_id: str) -> KnowledgeBase | None:
        """Get detailed information for a specific knowledge base."""
        return await self._kb_service.get_kb_detail(kb_id)

    async def _create_from_file_background(
        self,
        new_kb: CreateKnowledgeBaseInput,
        file_path: str,
        file_bytes: bytes | None = None,
    ) -> None:
        await self._kb_service.create_from_file(new_kb=new_kb, file_path=file_path, file_bytes=file_bytes)

    async def create_from_file(
        self,
        new_kb_input: str,
        file: UploadFile,
        background_tasks: BackgroundTasks,
    ) -> KnowledgeBaseCreateResponse:
        """Create a knowledge base with the specified name."""

        # --- Parse & initialize base metadata ---
        new_kb_dict = orjson.loads(new_kb_input)
        new_kb = CreateKnowledgeBaseInput(**new_kb_dict)
        new_kb.id = f"kb-{uuid4()}"
        new_kb.kb_doc_id = f"kb_doc-{uuid4()}"

        intake_folder = f"{DEFAULT_KB_INTAKE_FOLDER}/{new_kb.kb_name}" if DEFAULT_KB_INTAKE_FOLDER else None

        # --- Build chunking config ---
        chunking_config = ChunkingConfig(
            chunk_length=new_kb.chunk_length,
            chunk_overlap=new_kb.chunk_overlap,
            chunking_mode=new_kb.chunking_mode,
        )

        # --- Upload document to MinIO (or other storage) ---
        file_name = f"{new_kb.kb_name}_{file.filename}"
        object_path = await self._document_service.document.upload_document(
            file=file,
            intake_folder=intake_folder,
            original_filename=file_name,
        )

        file_bytes = await self._document_service.document.get_data_bytes_document(
            object_path=object_path,
        )

        # --- Background task for heavy processing ---
        background_tasks.add_task(
            self._create_from_file_background,
            new_kb,
            object_path,
            file_bytes,
        )

        # --- Build Knowledge Base configuration ---
        retrieval_mode = new_kb.config.retrieval_mode
        search_mode = RetrievalMode(
            top_k=retrieval_mode.top_k,
            relevance_enabled=retrieval_mode.relevance_enabled,
            relevance_threshold=retrieval_mode.relevance_threshold,
            hybrid_weight=retrieval_mode.hybrid_weight,
            rerank_enabled=retrieval_mode.rerank_enabled,
            search_method=retrieval_mode.search_method,
            hybrid_alpha_search_enabled=retrieval_mode.hybrid_alpha_search_enabled,
        )

        kb_config = KnowledgeBaseConfig(
            embedding_model="",  # Will be updated after embedding selection
            retrieval_mode=search_mode,
        )

        # --- Create KnowledgeBase record ---
        created_kb = KnowledgeBase(
            id=new_kb.id,
            name=new_kb.kb_name,
            description=new_kb.description,
            tags=new_kb.tags,
            documents=[new_kb.kb_doc_id],
            engine=new_kb.engine,
            data_source_type=DataSourceType.FILE,
            config=kb_config,
        )
        await created_kb.create()

        # --- Create Document record ---
        new_doc = KBDocument(
            id=new_kb.kb_doc_id,
            name=file_name,
            kb_name=new_kb.kb_name,
            chunking_mode=chunking_config.chunking_mode.value,
            chunking_config=ChunkingConfigBase(
                chunk_length=chunking_config.chunk_length,
                chunk_overlap=chunking_config.chunk_overlap,
            ),
            words_count=0,
            metadata={"source": object_path},
        )
        await new_doc.create()

        # --- Build Response ---
        return KnowledgeBaseCreateResponse(
            id=new_kb.id,
            name=new_kb.kb_name,
            tags=new_kb.tags,
            description=new_kb.description,
            engine=new_kb.engine.value,
            document_name=file.filename,
            document_id=new_kb.kb_doc_id,
            chunking_mode=new_kb.chunking_mode,
            chunking_length=new_kb.chunk_length,
            chunking_overlap=new_kb.chunk_overlap,
            settings=new_kb.config.model_dump(),
            created_at=datetime.now(TIMEZONE),
        )

    async def create_from_url(
        self,
        new_kb_input: str,
        url_name: str,
        url: str,
        background_tasks: BackgroundTasks,
    ) -> KnowledgeBaseCreateResponse:
        """Create a knowledge base with the specified name."""

        # --- Parse & initialize base metadata ---
        new_kb_dict = orjson.loads(new_kb_input)
        new_kb = CreateKnowledgeBaseInput(**new_kb_dict)
        new_kb.id = f"kb-{uuid4()}"
        new_kb.kb_doc_id = f"kb_doc-{uuid4()}"

        # --- Build chunking config ---
        chunking_config = ChunkingConfig(
            chunk_length=new_kb.chunk_length,
            chunk_overlap=new_kb.chunk_overlap,
            chunking_mode=new_kb.chunking_mode,
        )

        # --- Upload document to MinIO (or other storage) ---
        file_name = f"{new_kb.kb_name}_{url_name}"

        # --- Background task for heavy processing ---
        background_tasks.add_task(
            self._create_from_file_background,
            new_kb,
            url,
        )

        # --- Build Knowledge Base configuration ---
        retrieval_mode = new_kb.config.retrieval_mode
        search_mode = RetrievalMode(
            top_k=retrieval_mode.top_k,
            relevance_enabled=retrieval_mode.relevance_enabled,
            relevance_threshold=retrieval_mode.relevance_threshold,
            hybrid_weight=retrieval_mode.hybrid_weight,
            rerank_enabled=retrieval_mode.rerank_enabled,
            search_method=retrieval_mode.search_method,
            hybrid_alpha_search_enabled=retrieval_mode.hybrid_alpha_search_enabled,
        )

        kb_config = KnowledgeBaseConfig(
            embedding_model="",  # Will be updated after embedding selection
            retrieval_mode=search_mode,
        )

        # --- Create KnowledgeBase record ---
        created_kb = KnowledgeBase(
            id=new_kb.id,
            name=new_kb.kb_name,
            description=new_kb.description,
            tags=new_kb.tags,
            documents=[new_kb.kb_doc_id],
            engine=new_kb.engine,
            data_source_type=DataSourceType.URL,
            config=kb_config,
        )
        await created_kb.create()

        # --- Create Document record ---
        new_doc = KBDocument(
            id=new_kb.kb_doc_id,
            name=file_name,
            kb_name=new_kb.kb_name,
            chunking_mode=chunking_config.chunking_mode.value,
            chunking_config=ChunkingConfigBase(
                chunk_length=chunking_config.chunk_length,
                chunk_overlap=chunking_config.chunk_overlap,
            ),
            words_count=0,
            metadata={"source": url},
        )
        await new_doc.create()

        # --- Build Response ---
        return KnowledgeBaseCreateResponse(
            id=new_kb.id,
            name=new_kb.kb_name,
            tags=new_kb.tags,
            description=new_kb.description,
            engine=new_kb.engine.value,
            document_name=file_name,
            document_id=new_kb.kb_doc_id,
            chunking_mode=new_kb.chunking_mode,
            chunking_length=new_kb.chunk_length,
            chunking_overlap=new_kb.chunk_overlap,
            settings=new_kb.config.model_dump(),
            created_at=datetime.now(TIMEZONE),
        )

    async def create_empty_kb(self, kb_name: str, description: str) -> bool:
        """Create a knowledge base with the specified name."""
        return await self._kb_service.create_empty_kb(kb_name, description)

    async def create_from_external(
        self,
        kb_name: str,
        description: str,
        vector_db_config: VectorDBConfig | None = None,
    ) -> bool:
        """Create a knowledge base with the specified name."""
        return await self._kb_service.create_from_external(kb_name, description, vector_db_config)

    async def _insert_file_content_background(
        self,
        kb_id: str,
        new_kb_doc_id: str,
        file_bytes: bytes,
        object_path: str,
        parser_type: str,
        config: ChunkingConfig | None = None,
    ) -> tuple[bool, str]:
        await self._kb_service.insert_file_content(kb_id, new_kb_doc_id, file_bytes, object_path, parser_type, config)

    async def insert_file_content(
        self,
        kb_id: str,
        file: UploadFile,
        background_tasks: BackgroundTasks,
        parser_type: str,
        config: str | None = None,
    ) -> str:
        """Insert parsed data into the knowledge base using existing KB configuration."""
        new_kb_doc_id = f"kb_doc-{uuid4()!s}"
        kb_name = await self.get_kb_name_by_id(kb_id)
        intake_folder = f"{DEFAULT_KB_INTAKE_FOLDER}/{kb_name}" if DEFAULT_KB_INTAKE_FOLDER else None
        config = ChunkingConfig(**orjson.loads(config))
        file_name = await self._generate_unique_name(file_path=file.filename, kb_name=kb_name, chunking_config=config)
        if file_name is None:
            return None
        object_path = await self._document_service.document.upload_document(
            file=file,
            intake_folder=intake_folder,
            original_filename=file_name,
        )
        file_bytes = await self._document_service.document.get_data_bytes_document(object_path=object_path)
        background_tasks.add_task(
            self._insert_file_content_background,
            kb_id,
            new_kb_doc_id,
            file_bytes,
            object_path,
            parser_type,
            config,
        )
        new_doc = KBDocument(
            id=new_kb_doc_id,
            name=file_name,
            kb_name=kb_name,
            chunking_mode=config.chunking_mode.value,
            chunking_config=ChunkingConfigBase(
                chunk_length=config.chunk_length,
                chunk_overlap=config.chunk_overlap,
            ),
            words_count=0,
            metadata={"source": object_path},
        )
        await new_doc.create()
        return new_kb_doc_id

    async def _insert_url_content_background(
        self,
        kb_id: str,
        new_kb_doc_id: str,
        parser_type: str,
        url: str,
        config: ChunkingConfig | None = None,
    ) -> tuple[bool, str]:
        await self._kb_service.insert_url_content(kb_id, new_kb_doc_id, parser_type, url, config)

    async def insert_url_content(
        self,
        kb_id: str,
        background_tasks: BackgroundTasks,
        parser_type: str,
        url_name: str,
        url: str,
        config: str | None = None,
    ) -> str:
        """Insert parsed data into the knowledge base using existing KB configuration."""
        new_kb_doc_id = f"kb_doc-{uuid4()!s}"
        kb_name = await self.get_kb_name_by_id(kb_id)

        config = ChunkingConfig(**orjson.loads(config))
        file_name = await self._generate_unique_name(file_path=url_name, kb_name=kb_name, chunking_config=config)
        if file_name is None:
            return None
        background_tasks.add_task(
            self._insert_url_content_background,
            kb_id,
            new_kb_doc_id,
            parser_type,
            url,
            config,
        )
        new_doc = KBDocument(
            id=new_kb_doc_id,
            name=file_name,
            kb_name=kb_name,
            chunking_mode=config.chunking_mode.value,
            chunking_config=ChunkingConfigBase(
                chunk_length=config.chunk_length,
                chunk_overlap=config.chunk_overlap,
            ),
            words_count=0,
            metadata={"source": url},
        )
        await new_doc.create()
        return new_kb_doc_id

    async def insert_from_database(
        self,
        kb_name: str,
        db_name: str,
        table_name: str,
        columns_name: list[str] | None = None,
    ) -> bool:
        """Create a knowledge base from a database configuration."""
        return await self._kb_service.insert_from_database(kb_name, db_name, table_name, columns_name)

    async def delete(self, kb_id: str) -> bool:
        """Delete a knowledge base by its name."""
        # Try to find by ID first, then by name
        return await self._kb_service.delete(kb_id)

    async def get_kb_name_by_id(self, kb_id: str) -> str | None:
        """Get knowledge base name by ID."""
        kb_in_db = await self._kb_service._get_kb_from_db(kb_id)
        return kb_in_db.name

    async def update_kb(
        self,
        kb_id: str,
        tags: list[str] | None = None,
        description: str | None = None,
        config: KnowledgeBaseConfigUpdate | None = None,
        is_active: bool | None = None,
    ) -> bool:
        """Update a knowledge base configuration and properties."""
        return await self._kb_service.update_kb(kb_id, tags, description, config, is_active)

    async def query(
        self,
        kb_name: str,
        query: str,
        retrieval_mode: RetrievalMode | None = None,
    ) -> tuple[list[ChunkInfo], set[str]]:
        """Query a knowledge base by its name."""
        return await self._kb_service.query(kb_name, query, retrieval_mode)

    async def kb_dashboard(
        self,
        page: int = 1,
        page_size: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> Page | None:
        """Get comprehensive dashboard information for all knowledge bases with optional tag filtering and keyword search."""
        return await self._kb_service.kb_dashboard(page=page, page_size=page_size, tags=tags, search=search)

    async def get_all_kb_documents(self, kb_name: str) -> list[KBDocument] | None:
        """Get all documents for a specific knowledge base."""
        return await self._kb_service._get_all_kb_documents(kb_name)

    async def list_kb_documents(
        self,
        kb_id: str,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
    ) -> Page | None:
        """List documents for a KB with MongoDB search/filter/pagination."""
        return await self._kb_service.list_kb_documents(kb_id, page, page_size, search)

    async def get_kb_document(self, kb_id: str, doc_id: str) -> DocumentWithKnowledgeBaseInfo | None:
        """Get a specific knowledge base document by ID."""
        return await self._document_service.get_kb_document(kb_id, doc_id)

    async def get_all_chunks_with_paging(
        self,
        kb_id: str,
        doc_id: str,
        search: str,
        page: int,
        page_size: int,
    ) -> Page | None:
        """Get all chunks for a specific document with pagination support using pgvector."""
        return await self._chunk_service.get_all_chunks_with_paging(
            kb_id,
            doc_id,
            search,
            page,
            page_size,
        )

    async def update_kb_document(
        self,
        kb_id: str,
        doc_id: str,
        update_data: DocumentUpdate,
        background_tasks: BackgroundTasks | None = None,
    ) -> bool:
        """Update a knowledge base document.

        If background_tasks is provided, the update runs asynchronously in the background
        and this method returns True immediately; otherwise, it runs synchronously.
        """
        kb_in_db = await self._kb_service._get_kb_from_db(kb_id)
        if background_tasks is not None:
            background_tasks.add_task(
                self._document_service.update_kb_document,
                kb_in_db,
                doc_id,
                update_data,
                self._llm_handler,
            )
            return True
        return await self._document_service.update_kb_document(kb_in_db, doc_id, update_data, self._llm_handler)

    async def delete_kb_document(self, kb_id: str, doc_id: str) -> bool:
        """Delete a knowledge base document by ID."""
        return await self._document_service.delete_kb_document(kb_id, doc_id)

    async def add_chunk(self, kb_id: str, doc_id: str, content: str) -> bool:
        """Add a new chunk to a document in the knowledge base."""
        return await self._chunk_service.add_chunk(kb_id, doc_id, content)

    async def delete_chunks(self, kb_id: str, doc_id: str, chunk_ids: list[str]) -> bool:
        """Delete multiple chunks from a document in the knowledge base."""
        return await self._chunk_service.delete_chunks(kb_id, doc_id, chunk_ids)

    async def update_chunk(self, kb_id: str, doc_id: str, chunk_id: str, content: str) -> bool:
        """Update a chunk in a document in the knowledge base."""
        return await self._chunk_service.update_chunk(kb_id, doc_id, chunk_id, content)

    async def create_tag(self, name: str) -> Tag | None:
        """Create a new tag."""
        return await self._tag_service.create_tag(name)

    async def get_tag_by_id(self, tag_id: str) -> Tag | None:
        """Get a tag by ID."""
        return await self._tag_service.get_tag_by_id(tag_id)

    async def list_tags(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        active_only: bool = True,
    ) -> Page | None:
        """List tags with pagination and optional search."""
        return await self._tag_service.list_tags(page, page_size, search, active_only)

    async def update_tag(self, tag_id: str, tag_update: TagUpdate) -> Tag | None:
        """Update an existing tag."""
        return await self._tag_service.update_tag(tag_id, tag_update)

    async def delete_tag(self, tag_id: str) -> bool:
        """Delete a tag."""
        return await self._tag_service.delete_tag(tag_id)

    async def get_all_active_tags(self) -> list[str] | None:
        """Get all active tag names for dropdown selection."""
        return await self._tag_service.get_all_active_tags()

    async def _generate_unique_name(self, file_path: str, kb_name: str, chunking_config: ChunkingConfig) -> str | None:
        filename_path = Path(file_path)
        file_name = filename_path.stem
        extension = filename_path.suffix

        # Ensure extension starts with a dot
        if not extension.startswith("."):
            extension = "." + extension

        base_name = f"{kb_name}_{file_name}"

        # Query existing documents with the same base name and kb_name
        existing_docs = await KBDocument.find(
            {
                "name": {"$regex": f"^{re.escape(base_name)}", "$options": "i"},
                "kb_name": kb_name,
            },
        ).to_list()

        for kb_doc in existing_docs:
            if (
                kb_doc.chunking_mode == chunking_config.chunking_mode
                and kb_doc.chunking_config.chunk_length == chunking_config.chunk_length
                and kb_doc.chunking_config.chunk_overlap == chunking_config.chunk_overlap
            ):
                self.logger.error(
                    "event=file-already-in-kb "
                    'message="File %s is already parsed and saved in KB with the same '
                    'chunk configuration. Please modify the chunk config."',
                    file_name,
                )
                return None

        # Determine version number
        if existing_docs:
            versions = [
                int(doc.name.split("-v")[-1].split(".")[0])  # Extract version before extension
                for doc in existing_docs
                if "-v" in doc.name
            ]
            next_version = max(versions) + 1 if versions else 1
            unique_name = f"{base_name}-v{next_version}{extension}"
        else:
            unique_name = f"{base_name}{extension}"

        return unique_name
