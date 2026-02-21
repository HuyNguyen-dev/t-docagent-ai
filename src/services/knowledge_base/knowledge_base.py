import asyncio
from datetime import datetime
from typing import Any

from config import settings
from handlers.llm_configuration import LLMConfigurationHandler
from initializer import mindsdb_client, pg_client, redis_pubsub_manager
from models.agent import Agent
from models.kb_document import KBDocument
from models.knowledge_base import KnowledgeBase
from models.tag import Tag
from schemas.chunks import ChunkInfo, ChunkingConfig
from schemas.datasource import PostgreSQLVectorConfig, VectorDBConfig
from schemas.document import KBDocumentDetailResponse
from schemas.knowledge_base import (
    CreateKnowledgeBaseInput,
    KnowledgeBaseConfig,
    KnowledgeBaseConfigUpdate,
    KnowledgeBaseCreateResponse,
    KnowledgeBaseDetailResponse,
    RetrievalMode,
)
from schemas.model_config import ModelConfig
from schemas.response import Page
from schemas.tag import TagListResponse, TagUpdate
from services.knowledge_base.document import DocumentService
from services.knowledge_base.parser import ParseService
from services.knowledge_base.tag import TagService
from services.knowledge_base.vector_db import VectorDBFactory
from utils.constants import KEY_SCHEMA_EMBEDDING_CONFIG, TIMEZONE
from utils.enums import (
    ChunkingMode,
    DataSourceType,
    EmbeddingModel,
    InsertKBDocState,
    ModelProvider,
    RedisChannelName,
    VectorType,
)
from utils.functions import decrypt_and_migrate
from utils.logger.custom_logging import LoggerMixin


class KnowledgeBaseService(LoggerMixin):
    """Service for managing knowledge base operations."""

    def __init__(
        self,
        llm_handler: LLMConfigurationHandler,
        document_service: DocumentService,
        tag_service: TagService,
    ) -> None:
        super().__init__()
        self._document_service = document_service
        self._llm_handler = llm_handler
        self._tag_service = tag_service

    async def _get_kb_from_db(self, kb_id: str) -> KnowledgeBase | None:
        """Get knowledge base name by ID."""
        kb = await KnowledgeBase.get(kb_id)
        if not kb:
            self.logger.warning(
                'event=knowledge-base-not-found kb_id=%s message="Knowledge base not found by ID"',
                kb_id,
            )
            return None
        return kb

    async def create_vectordb(self, vector_db_config: VectorDBConfig) -> bool:
        """Create a vector database based on the configuration type using factory pattern."""
        config = vector_db_config.config
        vector_type = vector_db_config.ds_type

        # Use factory to create the appropriate creator
        creator = VectorDBFactory.create_creator(vector_type)
        if creator is None:
            self.logger.error(
                'event=vectordb-creation-error vector_type=%s message="Unsupported to this vector type"',
                vector_db_config.ds_type,
            )
            return False
        return await creator.create_vector_datasource(config)

    async def delete_vectordb(self, db_name: str) -> bool:
        """Delete a vector database."""
        try:
            await mindsdb_client.delete_datasource(db_name)
            await pg_client.drop_table(db_name)
        except Exception:
            self.logger.exception(
                "event=db_name-deletion-error db_name=%s ",
                db_name,
            )
            return False
        return True

    async def list_all(self) -> list[str] | None:
        """List all knowledge bases."""
        # Get names from MindsDB
        kbs_mindsdb = await mindsdb_client.list_kb()

        kbs_in_db = await KnowledgeBase.find_all().to_list()
        db_names = {kb.name for kb in kbs_in_db}

        mindsdb_names = set(kbs_mindsdb)

        # Should get all to prevent existed name from mindsdb
        intersected_names = db_names.union(mindsdb_names)

        return list(set(intersected_names))

    async def list_for_agents(self) -> list[str] | None:
        """List all knowledge bases for agents."""
        # Get names from MindsDB
        kbs_mindsdb = await mindsdb_client.list_kb()

        kbs_in_db = await KnowledgeBase.find_all().to_list()
        db_names = {kb.name for kb in kbs_in_db}

        mindsdb_names = set(kbs_mindsdb)
        intersected_names = db_names.intersection(mindsdb_names)

        return list(intersected_names)

    async def get_kb_detail(self, kb_id: str) -> KnowledgeBase | None:
        """Get detailed information for a specific knowledge base."""
        # Check both MongoDB and MindsDB
        kb_in_db = await self._get_kb_from_db(kb_id)
        if not kb_in_db:
            self.logger.warning(
                'event=kb-detail-not-found kb_name=%s message="Knowledge base not found in MongoDB"',
                kb_in_db.name,
            )
            return None
        kb = await mindsdb_client.get_kb(kb_in_db.name)
        if not kb:
            self.logger.warning(
                'event=kb-detail-not-found kb_name=%s message="Knowledge base not found in MindsDB"',
                kb_in_db.name,
            )
            return None

        self.logger.info(
            'event=kb-detail-success kb_name=%s message="Successfully retrieved knowledge base details"',
            kb_in_db.name,
        )

        return kb_in_db

    async def create_from_file(
        self,
        new_kb: CreateKnowledgeBaseInput,
        file_bytes: bytes | None,
        file_path: str | None,
    ) -> None:
        """Create a knowledge base and insert a document into it."""
        kb_name = new_kb.kb_name
        self.logger.info('event=knowledge-base-create message="Creating knowledge base" kb_name=%s', kb_name)
        model_configs = None
        vector_db_config = None
        success = False

        try:
            model_configs = await self._get_default_model_configs()

            if new_kb.engine == VectorType.POSTGRESQL:
                vector_db_config = await self._create_pgvector_table_and_db(new_kb, model_configs)
                if not vector_db_config:
                    await self._handle_failure(new_kb.id, new_kb.kb_doc_id, kb_name, cleanup_vector=False)
                    return

            is_created_kb = await self._create_mindsdb_kb(new_kb, model_configs, vector_db_config)
            if not is_created_kb:
                await self._handle_failure(new_kb.id, new_kb.kb_doc_id, kb_name)
                return

            self.logger.info('event=knowledge-base-created kb_name=%s message="Knowledge base created successfully"', kb_name)

            chunking_config = await self._build_chunking_config(new_kb)

            is_inserted = await self.insert(
                doc_id=new_kb.kb_doc_id,
                kb_name=kb_name,
                file_bytes=file_bytes,
                file_path=file_path,
                parser_type=new_kb.parser_type,
                chunking_config=chunking_config,
            )
            if not is_inserted:
                self.logger.error('event=kb-insert-failed kb_name=%s message="Insert failed"', kb_name)
                await self._handle_failure(new_kb.id, new_kb.kb_doc_id, kb_name)
                return

            await self._update_mongo_embedding_model(new_kb.id, model_configs.model_name)

            await self._push_status_event(new_kb.id, new_kb.kb_doc_id, InsertKBDocState.SUCCESS)
            success = True

        except Exception:
            self.logger.exception('event=knowledge-base-create-error kb_name=%s message="Unhandled exception"', kb_name)
            await self._handle_failure(new_kb.id, new_kb.kb_doc_id, kb_name)

        finally:
            if not success:
                await self._safe_cleanup(new_kb, kb_name)

    async def _create_pgvector_table_and_db(
        self,
        new_kb: CreateKnowledgeBaseInput,
        model_configs: ModelConfig,
    ) -> VectorDBConfig | None:
        """Create a PostgreSQL vector table and register a vector database."""
        kb_name = new_kb.kb_name
        try:
            is_created_table = await pg_client.create_vector_table(
                table_name=kb_name,
                vector_dimension=EmbeddingModel.get_dimensions(model_configs.model_name),
            )
            if not is_created_table:
                self.logger.error("event=pgvector-table-create-failed kb_name=%s", kb_name)
                return None

            vector_db_config = VectorDBConfig(
                ds_type=new_kb.engine,
                config=PostgreSQLVectorConfig(
                    host=settings.PGVECTOR_HOST,
                    password=settings.PGVECTOR_PASSWORD.get_secret_value(),
                    port=settings.PGVECTOR_PORT,
                    database=settings.PGVECTOR_DATABASE,
                    user=settings.PGVECTOR_USERNAME,
                    similarity_metric="cosine",
                    ssl_mode=settings.PGVECTOR_SSL_MODE,
                    db_name=kb_name,
                    table_name=kb_name,
                ),
            )

            created = await self.create_vectordb(vector_db_config)
            if not created:
                self.logger.error("event=vectordb-create-failed kb_name=%s", kb_name)
                return None

        except Exception as e:
            self.logger.exception("event=pgvector-setup-error kb_name=%s", kb_name, exc_info=e)
            return None
        return vector_db_config

    async def _create_mindsdb_kb(
        self,
        new_kb: CreateKnowledgeBaseInput,
        model_configs: ModelConfig,
        vector_db_config: VectorDBConfig | None,
    ) -> bool:
        """Create a knowledge base in MindsDB."""
        try:
            if vector_db_config:
                return await mindsdb_client.create_kb(
                    kb_name=new_kb.kb_name,
                    model_configs=model_configs,
                    vector_db_name=vector_db_config.config.db_name,
                    table_name=vector_db_config.config.table_name,
                    content_columns=["content"],
                    metadata_columns=["metadata"],
                )
            return await mindsdb_client.create_kb(
                kb_name=new_kb.kb_name,
                model_configs=model_configs,
                content_columns=["content"],
                metadata_columns=["metadata"],
            )
        except Exception:
            self.logger.exception("event=mindsdb-create-failed kb_name=%s", new_kb.kb_name)
            return False

    async def _build_chunking_config(self, new_kb: CreateKnowledgeBaseInput) -> ChunkingConfig:
        """Build chunking config and embedding model settings."""
        embedding_config = None
        if new_kb.chunking_mode == ChunkingMode.SEMANTIC:
            owner_config = await self._llm_handler.get_owner_llm_config()
            embedding_model = self._llm_handler.get_llm_config_by_key(
                owner_config=owner_config,
                key=KEY_SCHEMA_EMBEDDING_CONFIG,
            )
            embedding_config = embedding_model

        return ChunkingConfig(
            chunk_length=new_kb.chunk_length,
            chunk_overlap=new_kb.chunk_overlap,
            chunking_mode=new_kb.chunking_mode,
            embedding_config=embedding_config,
        )

    async def _update_mongo_embedding_model(self, kb_id: str, model_name: str) -> None:
        """Update embedding model info in MongoDB."""
        try:
            await KnowledgeBase.find_one(KnowledgeBase.id == kb_id).update(
                {"$set": {"config.embedding_model": model_name}},
            )
        except Exception:
            self.logger.exception("event=mongodb-update-failed kb_id=%s", kb_id)

    async def _handle_failure(self, kb_id: str, doc_id: str, kb_name: str, cleanup_vector: bool = True) -> None:
        """Generic failure handler to push status and clean document."""
        try:
            await self._push_status_event(kb_id, doc_id, InsertKBDocState.FAILED)
            if cleanup_vector:
                await self.delete_vectordb(kb_name)
        except Exception as e:
            self.logger.warning("event=kb-failure-cleanup-error kb_name=%s error=%s", kb_name, e)

    async def _safe_cleanup(self, new_kb: CreateKnowledgeBaseInput, kb_name: str) -> None:
        """Final cleanup called in finally block."""
        try:
            await self.delete_vectordb(kb_name)
            await KBDocument.find_one(KBDocument.id == new_kb.kb_doc_id).delete()
        except Exception as e:
            self.logger.warning("event=final-cleanup-failed kb_name=%s error=%s", kb_name, e)

    async def create_empty_kb(self, kb_name: str, description: str) -> tuple[bool, str]:
        """Create a knowledge base with the specified name."""
        self.logger.debug(
            'event=knowledge-base-create kb_name=%s message="Creating knowledge base"',
            kb_name,
        )
        model_configs = await self._get_default_model_configs()
        kb_config = KnowledgeBaseConfig(
            retrieval_mode=RetrievalMode(),
            embedding_model=model_configs.model_name,
        )
        is_created_kb = await mindsdb_client.create_kb(
            kb_name=kb_name,
            model_configs=model_configs,
            content_columns=["content"],
            metadata_columns=["metadata"],
        )
        if not is_created_kb:
            self.logger.error(
                'event=knowledge-base-create-failed kb_name=%s message="Failed to create knowledge base"',
                kb_name,
            )
            return False, None
        self.logger.debug(
            'event=knowledge-base-created kb_name=%s message="Knowledge base created successfully"',
            kb_name,
        )

        new_kb = KnowledgeBase(
            name=kb_name,
            description=description,
            documents=[],
            engine=VectorType.CHROMA,
            data_source_type=DataSourceType.FILE,
            config=kb_config,
        )
        try:
            await new_kb.create()
        except Exception as mongo_error:
            self.logger.exception(
                'event=knowledge-base-mongodb-create-failed kb_name=%s message="Failed to create MongoDB record"',
                kb_name,
                exc_info=mongo_error,
            )
            # Clean up previously created resources
            await self.delete_vectordb(kb_name)
            return False, None

        return True, new_kb.id

    async def create_from_external(
        self,
        kb_name: str,
        description: str,
        vector_db_config: VectorDBConfig | None = None,
    ) -> KnowledgeBaseCreateResponse | None:
        """Create a knowledge base with the specified name."""
        try:
            self.logger.debug(
                'event=knowledge-base-create kb_name=%s message="Creating knowledge base"',
                kb_name,
            )
            vector_created = await self.create_vectordb(vector_db_config=vector_db_config)
            if not vector_created:
                self.logger.error(
                    'event=knowledge-base-create-failed kb_name=%s message="Failed to create knowledge base"',
                    kb_name,
                )
                return None
            # default config
            model_configs = await self._get_default_model_configs()
            success = await mindsdb_client.create_kb(
                kb_name=kb_name,
                model_configs=model_configs,
                vector_db_name=vector_db_config.config.db_name,
                table_name=vector_db_config.config.table_name,
                content_columns=["content"],
                metadata_columns=["metadata"],
            )
            if not success:
                self.logger.error(
                    'event=knowledge-base-create-failed kb_name=%s message="Failed to create knowledge base"',
                    kb_name,
                )
                return None
            self.logger.debug(
                'event=knowledge-base-created kb_name=%s message="Knowledge base created successfully"',
                kb_name,
            )

            # Create and save KnowledgeBase record to MongoDB
            kb_config = KnowledgeBaseConfig(retrieval_mode=RetrievalMode())
            new_kb = KnowledgeBase(
                name=kb_name,
                description=description,
                engine=vector_db_config.ds_type,
                documents=[],
                config=kb_config,
                data_source_type=vector_db_config.ds_type,
            )
            await new_kb.insert()

            self.logger.debug(
                'event=knowledge-base-saved kb_name=%s message="Knowledge base and document saved to database"',
                kb_name,
            )
            # Create response data
            response_data = KnowledgeBaseCreateResponse(
                id=new_kb.id,
                name=new_kb.name,
                tags=new_kb.tags,
                description=new_kb.description,
                engine=new_kb.engine.value,
                settings=new_kb.config.model_dump(),
                created_at=new_kb.created_at,
            )

        except Exception as e:
            self.logger.exception(
                'event=knowledge-base-create-error kb_name=%s message="Error creating knowledge base"',
                kb_name,
                exc_info=e,
            )
            # Cleanup: delete vector database if created
            if vector_db_config:
                await self.delete_vectordb(vector_db_config.config.db_name)
            # Cleanup: delete MongoDB records if created
            try:
                kb_in_db = await KnowledgeBase.find_one({"name": kb_name})
                if kb_in_db:
                    # Delete associated documents
                    for doc_id in kb_in_db.documents:
                        await KBDocument.get(doc_id).delete()
                    # Delete knowledge base
                    await kb_in_db.delete()
            except Exception as cleanup_error:
                self.logger.warning(
                    'event=cleanup-error kb_name=%s message="Failed to cleanup database records"',
                    kb_name,
                    exc_info=cleanup_error,
                )
            return None
        return response_data

    async def update_kb(
        self,
        kb_id: str,
        tags: list[str] | None = None,
        description: str | None = None,
        config: KnowledgeBaseConfigUpdate | None = None,
        is_active: bool | None = None,
    ) -> bool:
        """Update a knowledge base configuration and properties."""
        # Step 1: Check both MongoDB and MindsDB
        kb_in_db = await self._get_kb_from_db(kb_id)
        kb = await mindsdb_client.get_kb(kb_in_db.name)
        if not kb or not kb_in_db:
            self.logger.error(
                'event=update-kb-not-found kb_name=%s message="Knowledge base not found in MongoDB or MindsDB"',
                kb_in_db.name,
            )
            return False

        update_success = await self._update_mongodb_kb(kb_in_db, tags, description, config, is_active)
        if not update_success:
            return False

        self.logger.info(
            'event=update-kb-success kb_name=%s message="Knowledge base updated successfully"',
            kb_in_db.name,
        )
        return True

    async def _update_mongodb_kb(
        self,
        kb: KnowledgeBase,
        tags: list[str] | None = None,
        description: str | None = None,
        config: KnowledgeBaseConfigUpdate | None = None,
        is_active: bool | None = None,
    ) -> bool:
        """Update knowledge base in MongoDB."""
        # Build update dictionary with only provided fields
        update_data = {}

        if tags is not None:
            update_data["tags"] = tags
        elif tags is None:
            update_data["tags"] = []

        if description is not None:
            update_data["description"] = description

        if config is not None:
            update_data["config"] = KnowledgeBaseConfig(**config.model_dump())

        if is_active is not None:
            update_data["is_active"] = is_active

        # Always update the updated_at timestamp
        update_data["updated_at"] = datetime.now(TIMEZONE)

        if not update_data:
            self.logger.warning(
                'event=update-kb-no-changes kb_name=%s message="No changes provided for update"',
                kb.name,
            )
            return True

        # Update the knowledge base
        await kb.update({"$set": update_data})

        self.logger.info(
            'event=update-mongodb-kb-success kb_name=%s message="MongoDB knowledge base updated successfully"',
            kb.name,
        )

        return True

    async def delete(self, kb_id: str) -> bool:
        """Delete a knowledge base by its name."""
        # Step 1: Check both MongoDB and MindsDB
        kb_in_db = await self._get_kb_from_db(kb_id)
        kb = await mindsdb_client.get_kb(kb_in_db.name)
        if not kb:
            self.logger.error(
                'event=delete-kb-not-found kb_name=%s message="Knowledge base not found in MongoDB or MindsDB"',
                kb_in_db.name,
            )
            return False

        # Step 2: Delete from MindsDB
        if not await self._delete_from_mindsdb(kb_in_db):
            return False

        # Step 3: Delete from PostgreSQL (if applicable)
        await self._delete_from_postgresql(kb_in_db)

        # Step 4: Delete from MinIO
        await self._delete_from_minio(kb_in_db)

        # Step 5: Delete related documents
        await self._delete_related_documents(kb_in_db)

        # Step 6: Delete from MongoDB
        await self._delete_from_mongodb(kb_in_db)

        await self._remove_kb_name_from_agents(kb_in_db.name)

        self.logger.info(
            'event=knowledge-base-deleted kb_name=%s message="KB deleted successfully from both MindsDB and MongoDB"',
            kb_in_db.name,
        )
        return True

    async def _delete_from_mindsdb(self, kb: KnowledgeBase) -> bool:
        """Delete knowledge base from MindsDB."""
        # Delete the knowledge base
        kb_success = await mindsdb_client.delete_kb(kb_name=kb.name)
        if not kb_success:
            self.logger.error(
                'event=knowledge-base-mindsdb-delete-failed kb_name=%s message="Failed to delete kb from MindsDB"',
                kb.name,
            )
            return False

        # Delete the vector datasource
        if kb.engine == VectorType.POSTGRESQL:
            datasource_name = self._get_datasource_name(kb)
            datasource_success = await mindsdb_client.delete_datasource(db_name=datasource_name)
            if not datasource_success:
                self.logger.warning(
                    'event=datasource-delete-warning kb_name=%s datasource=%s message="Failed to delete vector datasource"',
                    kb.name,
                    datasource_name,
                )

        return True

    def _get_datasource_name(self, kb: KnowledgeBase) -> str:
        """Get the datasource name based on vector type."""
        if kb.engine == VectorType.POSTGRESQL:
            return kb.name
        return f"{kb.name}_chromadb"

    async def _delete_related_documents(self, kb: KnowledgeBase) -> None:
        """Delete all documents associated with the knowledge base."""
        if not kb.documents:
            return
        await KBDocument.find({"_id": {"$in": kb.documents}}).delete()
        self.logger.info(
            'event=kb-documents-deleted kb_name=%s message="Deleted documents from MongoDB"',
            kb.name,
        )

    async def _delete_from_mongodb(self, kb: KnowledgeBase) -> None:
        """Delete knowledge base from MongoDB."""
        await kb.delete()
        self.logger.info(
            'event=knowledge-base-mongodb-deleted kb_name=%s message="Knowledge base deleted from MongoDB successfully"',
            kb.name,
        )

    async def _delete_from_postgresql(self, kb: KnowledgeBase) -> None:
        """Delete knowledge base table from PostgreSQL."""
        # Only delete from PostgreSQL if the engine is PostgreSQL
        if kb.engine != VectorType.POSTGRESQL:
            return

        # Get the table name (same as knowledge base name)
        table_name = kb.name

        success = await pg_client.drop_table(table_name)

        if success:
            self.logger.info(
                'event=postgresql-table-deleted kb_name=%s table_name=%s message="PostgreSQL table deleted successfully"',
                kb.name,
                table_name,
            )
        else:
            self.logger.warning(
                'event=postgresql-table-delete-failed kb_name=%s table_name=%s message="Failed to delete PostgreSQL table"',
                kb.name,
                table_name,
            )

    async def _delete_from_minio(self, kb: KnowledgeBase) -> None:
        """Delete files from MinIO if they are not used by other knowledge bases."""
        if not kb.documents:
            return

        # Get all document details to find their MinIO paths
        document_paths = []
        for doc_id in kb.documents:
            try:
                doc = await KBDocument.get(doc_id)
                if doc and hasattr(doc, "metadata") and doc.metadata:
                    # Extract MinIO path from document metadata
                    minio_path = doc.metadata.get("source")
                    if minio_path:
                        document_paths.append(minio_path)
            except Exception:
                self.logger.warning(
                    "event=document-metadata-fetch-warning kb_name=%s doc_id=%s",
                    kb.name,
                    doc_id,
                )
                continue

        if not document_paths:
            return

        # Delete unused files from MinIO
        success = await self._document_service.delete_documents(object_paths=document_paths)
        if success:
            self.logger.info(
                'event=minio-files-deleted kb_name=%s unused files from MinIO"',
                kb.name,
            )
        else:
            self.logger.warning(
                'event=minio-files-delete-failed kb_name=%s message="Failed to delete some files from MinIO"',
                kb.name,
            )

    async def _remove_kb_name_from_agents(self, kb_name: str) -> None:
        await Agent.find(
            Agent.advanced_options.kb_names == kb_name,
        ).update_many(
            {"$pull": {"advanced_options.kb_names": kb_name}},
        )

    async def kb_dashboard(
        self,
        page: int = 1,
        page_size: int = 20,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> Page | None:
        """Get comprehensive dashboard information for all knowledge bases with optional tag filtering and keyword search."""

        filters: list[dict[str, Any]] = []

        if tags:
            filters.append({"tags": {"$in": tags}})

        if search and search.strip():
            search_regex = {"$regex": search.strip(), "$options": "i"}
            filters.append(
                {
                    "$or": [
                        {"name": search_regex},
                        {"description": search_regex},
                        {"tags": search_regex},
                    ],
                },
            )

        query = {"$and": filters} if filters else {}

        # Pagination
        total_items = await KnowledgeBase.find(query).count()
        total_pages = (total_items + page_size - 1) // page_size
        skip = (page - 1) * page_size

        kbs_in_db = await KnowledgeBase.find(query).sort("-created_at").skip(skip).limit(page_size).to_list()
        kbs_mindsdb = await mindsdb_client.list_kb()

        knowledge_bases = []
        total_documents = total_chunks = 0
        vector_types: dict[str, int] = {}
        data_sources: dict[str, int] = {}

        async def process_kb(
            kb_in_db: KnowledgeBase,
        ) -> tuple[KnowledgeBaseDetailResponse, int, int, str, str] | None:
            """Process one KB: fetch detail + calculate chunk count."""
            if kb_in_db.name not in kbs_mindsdb:
                return None

            kb = await self.get_kb_detail(kb_in_db.id)
            if not kb:
                return None

            chunk_count = 0
            if kb_in_db.documents:
                async with asyncio.TaskGroup() as tg_inner:
                    tasks = [tg_inner.create_task(self._fetch_doc_words(kb_in_db.name, doc_id)) for doc_id in kb_in_db.documents]
                chunk_count = sum(task.result() for task in tasks if task.result())

            kb_detail = KnowledgeBaseDetailResponse(
                id=kb.id,
                name=kb.name,
                tags=kb.tags,
                description=kb.description,
                engine=kb.engine,
                document_count=len(kb.documents),
                chunk_count=chunk_count,
                is_active=kb.is_active,
                created_at=kb.created_at,
                last_updated=kb.updated_at,
            )

            return kb_detail, len(kb.documents), chunk_count, kb.engine, kb.data_source_type

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(process_kb(kb)) for kb in kbs_in_db]

        for task in tasks:
            result = task.result()
            if not result:
                continue

            kb_detail, doc_count, chunk_count, engine, data_source = result
            knowledge_bases.append(kb_detail)
            total_documents += doc_count
            total_chunks += chunk_count

            vector_types[engine] = vector_types.get(engine, 0) + 1
            data_sources[data_source] = data_sources.get(data_source, 0) + 1

        # Create page response
        page_response = Page(
            items=knowledge_bases,
            metadata={
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "vector_types": vector_types,
                "data_sources": data_sources,
            },
        )

        # Logging
        applied_filters = []
        if tags:
            applied_filters.append(f"tags={tags}")
        if search and search.strip():
            applied_filters.append(f"search='{search.strip()}'")

        filter_msg = f" filtered by {', '.join(applied_filters)}" if applied_filters else ""
        self.logger.info(
            'event=kb-dashboard-success total_kbs=%d message="Dashboard generated%s"',
            len(knowledge_bases),
            filter_msg,
        )

        return page_response

    async def _fetch_doc_words(self, kb_name: str, doc_id: str) -> int:
        """Helper: fetch document word count safely."""
        try:
            doc = await KBDocument.get(doc_id)
            return getattr(doc, "words_count", 0) or 0
        except Exception as e:
            self.logger.warning(
                'event=document-fetch-warning kb_name=%s doc_id=%s message="%s"',
                kb_name,
                doc_id,
                str(e),
            )
            return 0

    async def _get_all_kb_documents(self, kb_name: str) -> list[KBDocument]:
        """Get all documents for a specific knowledge base concurrently."""
        kb_in_db = await self._get_kb_from_db(kb_name)
        if not kb_in_db or not kb_in_db.documents:
            return []

        async def fetch_doc(doc_id: str) -> KBDocument | None:
            """Helper to fetch a single document safely."""
            try:
                doc = await KBDocument.get(doc_id)
            except Exception as e:
                self.logger.warning(
                    'event=document-fetch-warning kb_name=%s doc_id=%s message="%s"',
                    kb_name,
                    doc_id,
                    str(e),
                )
                return None
            return doc

        documents: list[KBDocument] = []
        async with asyncio.TaskGroup() as tg:
            tasks: list[asyncio.Task[KBDocument | None]] = [tg.create_task(fetch_doc(doc_id)) for doc_id in kb_in_db.documents]

        for task in tasks:
            doc = task.result()
            if doc is not None:
                documents.append(doc)

        return documents

    async def list_kb_documents(
        self,
        kb_id: str,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
    ) -> Page | None:
        """List documents for a Knowledge Base (KB) with pagination and optional search."""

        # Get KB metadata
        kb_in_db = await self._get_kb_from_db(kb_id)
        if not kb_in_db or not kb_in_db.documents:
            return Page(
                items=[],
                metadata={
                    "page": page,
                    "page_size": page_size,
                    "total_items": 0,
                    "total_pages": 0,
                },
            )

        # ---- Build query ----
        query: dict[str, Any] = {"_id": {"$in": kb_in_db.documents}}

        if search := search.strip() if search else None:
            regex = {"$regex": search, "$options": "i"}
            query["$or"] = [
                {"name": regex},
                {"_id": regex},
                {"metadata.source": regex},
            ]

        # ---- Count total ----
        total_items = await KBDocument.find(query).count()
        if total_items == 0:
            return Page(
                items=[],
                metadata={
                    "page": page,
                    "page_size": page_size,
                    "total_items": 0,
                    "total_pages": 0,
                },
            )

        # ---- Pagination ----
        total_pages = max((total_items + page_size - 1) // page_size, 1)
        skip_items = max(0, (page - 1) * page_size)

        # ---- Query documents ----
        docs = await KBDocument.find(query).skip(skip_items).limit(page_size).to_list()

        # ---- Transform to response ----
        documents = [
            KBDocumentDetailResponse(
                id=doc.id,
                name=doc.name,
                chunking_mode=getattr(doc.chunking_mode, "value", str(doc.chunking_mode)),
                words_count=doc.words_count,
                upload_time=getattr(doc, "upload_time", None),
                state=doc.state,
                metadata=getattr(doc, "metadata", {}) or {},
            )
            for doc in docs
        ]

        # ---- Build paginated response ----
        return Page(
            items=documents,
            metadata={
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        )

    async def insert_from_database(
        self,
        kb_name: str,
        db_name: str,
        table_name: str,
        columns_name: list[str] | None = None,
    ) -> bool:
        """Create a knowledge base from a database configuration."""
        kb_in_db = await self._get_kb_from_db(kb_name)
        kb = await mindsdb_client.get_kb(kb_name)
        if not kb or not kb_in_db:
            self.logger.error(
                'event=knowledge-base-insert-failed message="knowledge base is not found"',
            )
            return False
        self.logger.info(
            "event=knowledge-base-create "
            "kb_name=%s "
            "db_name=%s "
            "table_name=%s "
            "columns_name=%s "
            'message="Creating knowledge base from database"',
            kb_name,
            db_name,
            table_name,
            columns_name or "ALL",
        )

        success = await mindsdb_client.insert_from_database(
            kb_name=kb_name,
            db_name=db_name,
            table_name=table_name,
            columns_name=columns_name,
        )

        if not success:
            self.logger.error(
                "event=knowledge-base-create-failed "
                "kb_name=%s "
                "db_name=%s "
                "table_name=%s "
                'message="Failed to create knowledge base from database"',
                kb_name,
                db_name,
                table_name,
            )
            return False

        self.logger.info(
            "event=knowledge-base-created "
            "kb_name=%s "
            "db_name=%s "
            "table_name=%s "
            'message="Knowledge base created successfully from database"',
            kb_name,
            db_name,
            table_name,
        )

        return True

    async def insert(
        self,
        doc_id: str,
        kb_name: str,
        file_bytes: str,
        file_path: str,
        parser_type: str,
        chunking_config: ChunkingConfig,
    ) -> bool:
        """Insert parsed data into a knowledge base."""

        try:
            # ---- Validate Knowledge Base ----
            kb = await mindsdb_client.get_kb(kb_name)
            if not kb:
                self.logger.error(
                    "event=knowledge-base-insert-failed kb_name=%s message='Knowledge base not found'",
                    kb_name,
                )
                return False

            # ---- Update KB Document List ----
            current_kb = await KnowledgeBase.find_one({"name": kb_name})
            if current_kb:
                if not current_kb.documents:
                    current_kb.documents = []
                if doc_id not in current_kb.documents:
                    current_kb.documents.append(doc_id)
                    await current_kb.save()
                    self.logger.info(
                        "event=kb-document-added kb_name=%s doc_id=%s message='Document added to KB'",
                        kb_name,
                        doc_id,
                    )

            # ---- Parse File ----
            parsing_service = ParseService(self._llm_handler)
            parsing_result = await parsing_service.parse_file(
                file_bytes=file_bytes,
                file_path=file_path,
                parser_type=parser_type,
                chunking_config=chunking_config,
            )

            if not parsing_result:
                self.logger.warning(
                    "event=file-parse-failed kb_name=%s file_path=%s message='No data returned from parsing'",
                    kb_name,
                    file_path,
                )
                return False

            df, word_count = parsing_result

            # ---- Insert into KB ----
            success = await mindsdb_client.insert_kb(
                kb_name=kb_name,
                content_data=df,
                kb_id=current_kb.id,
                doc_id=doc_id,
            )

            if not success:
                self.logger.error(
                    "event=knowledge-base-insert-failed kb_name=%s message='Failed to insert data into knowledge base'",
                    kb_name,
                )
                return False

            # ---- Update Document Metadata ----
            metadata_dict = {}
            if not df.empty and "metadata" in df.columns and isinstance(df["metadata"].iloc[0], dict):
                metadata_dict = df["metadata"].iloc[0]

            update_data = {
                "$set": {
                    "words_count": word_count,
                    "metadata": {
                        "source": metadata_dict.get("source", "unknown"),
                        "total_chunks": metadata_dict.get("total_chunks", 0),
                    },
                },
            }

            await KBDocument.find_one(KBDocument.id == doc_id).update(update_data)

            self.logger.info(
                "event=knowledge-base-insert-success kb_name=%s doc_id=%s message='Data inserted successfully'",
                kb_name,
                doc_id,
            )

        except Exception:
            self.logger.exception(
                "event=knowledge-base-insert-error kb_name=%s doc_id=%s message='Unexpected error: %s'",
                kb_name,
                doc_id,
            )
            return False
        return True

    async def insert_file_content(
        self,
        kb_id: str,
        new_kb_doc_id: str,
        file_bytes: bytes,
        object_path: str,
        parser_type: str,
        config: ChunkingConfig | None = None,
    ) -> tuple[bool, str | None]:
        """Insert parsed data into the knowledge base using existing KB configuration."""

        try:
            current_kb = await self._get_kb_from_db(kb_id)
            if not current_kb:
                self.logger.error(
                    "event=knowledge-base-not-found kb_id=%s message='Knowledge base not found'",
                    kb_id,
                )
                await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.FAILED)
                return False, None

            # ---- Add doc to KnowledgeBase ----
            if not current_kb.documents:
                current_kb.documents = []
            if new_kb_doc_id not in current_kb.documents:
                current_kb.documents.append(new_kb_doc_id)
                await current_kb.save()
                self.logger.info(
                    "event=kb-document-added kb_name=%s doc_id=%s message='Document added to KB'",
                    current_kb.name,
                    new_kb_doc_id,
                )

            # ---- Handle embedding model configuration ----
            if config:
                if config.chunking_mode == ChunkingMode.SEMANTIC:
                    config.embeddings_model = getattr(current_kb.config, "embedding_model", None)
            else:
                config = ChunkingConfig()  # fallback to a default config

            # ---- Parse file ----
            parsing_service = ParseService(self._llm_handler)
            parsing_data = await parsing_service.parse_file(
                file_bytes=file_bytes,
                file_path=object_path,
                parser_type=parser_type,
                chunking_config=config,
            )

            if not parsing_data:
                self.logger.warning(
                    "event=file-parse-failed kb_id=%s doc_id=%s message='Parsing returned no data'",
                    kb_id,
                    new_kb_doc_id,
                )
                await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.FAILED)
                return False, None

            df, word_count = parsing_data

            # ---- Insert into MindsDB ----
            success = await mindsdb_client.insert_kb(
                kb_name=current_kb.name,
                content_data=df,
                kb_id=current_kb.id,
                doc_id=new_kb_doc_id,
            )
            if not success:
                self.logger.error(
                    "event=knowledge-base-insert-failed kb_name=%s message='Insert to MindsDB failed'",
                    current_kb.name,
                )
                await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.FAILED)
                return False, None

            # ---- Extract metadata ----
            metadata_dict = {}
            if not df.empty and "metadata" in df.columns and isinstance(df["metadata"].iloc[0], dict):
                metadata_dict = df["metadata"].iloc[0]

            # ---- Update MongoDB document ----
            await KBDocument.find_one(KBDocument.id == new_kb_doc_id).update(
                {
                    "$set": {
                        "words_count": word_count,
                        "metadata": {
                            "source": metadata_dict.get("source", "unknown"),
                        },
                    },
                },
            )

            # ---- Finalize ----
            await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.SUCCESS)
            self.logger.info(
                "event=knowledge-base-insert-success kb_name=%s doc_id=%s message='Inserted successfully'",
                current_kb.name,
                new_kb_doc_id,
            )

        except Exception:
            self.logger.exception(
                "event=knowledge-base-insert-error kb_id=%s doc_id=%s message='Unexpected error: %s'",
                kb_id,
                new_kb_doc_id,
            )
            await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.FAILED)
            return False, None
        return True, new_kb_doc_id

    async def insert_url_content(
        self,
        kb_id: str,
        new_kb_doc_id: str,
        parser_type: str,
        url: str,
        config: ChunkingConfig | None = None,
    ) -> tuple[bool, str | None]:
        """Insert parsed data into the knowledge base using existing KB configuration."""

        try:
            current_kb = await self._get_kb_from_db(kb_id)
            if not current_kb:
                self.logger.error(
                    "event=knowledge-base-not-found kb_id=%s message='Knowledge base not found'",
                    kb_id,
                )
                await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.FAILED)
                return False, None

            # ---- Add doc to KnowledgeBase ----
            if not current_kb.documents:
                current_kb.documents = []
            if new_kb_doc_id not in current_kb.documents:
                current_kb.documents.append(new_kb_doc_id)
                await current_kb.save()
                self.logger.info(
                    "event=kb-document-added kb_name=%s doc_id=%s message='Document added to KB'",
                    current_kb.name,
                    new_kb_doc_id,
                )

            # ---- Handle embedding model configuration ----
            if config:
                if config.chunking_mode == ChunkingMode.SEMANTIC:
                    config.embeddings_model = getattr(current_kb.config, "embedding_model", None)
            else:
                config = ChunkingConfig()  # fallback to a default config

            # ---- Parse file ----
            parsing_service = ParseService(self._llm_handler)
            parsing_data = await parsing_service.parse_file(
                file_path=url,
                parser_type=parser_type,
                chunking_config=config,
            )

            if not parsing_data:
                self.logger.warning(
                    "event=file-parse-failed kb_id=%s doc_id=%s message='Parsing returned no data'",
                    kb_id,
                    new_kb_doc_id,
                )
                await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.FAILED)
                return False, None

            df, word_count = parsing_data

            # ---- Insert into MindsDB ----
            success = await mindsdb_client.insert_kb(
                kb_name=current_kb.name,
                content_data=df,
                kb_id=current_kb.id,
                doc_id=new_kb_doc_id,
            )
            if not success:
                self.logger.error(
                    "event=knowledge-base-insert-failed kb_name=%s message='Insert to MindsDB failed'",
                    current_kb.name,
                )
                await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.FAILED)
                return False, None

            # ---- Extract metadata ----
            metadata_dict = {}
            if not df.empty and "metadata" in df.columns and isinstance(df["metadata"].iloc[0], dict):
                metadata_dict = df["metadata"].iloc[0]

            # ---- Update MongoDB document ----
            await KBDocument.find_one(KBDocument.id == new_kb_doc_id).update(
                {
                    "$set": {
                        "words_count": word_count,
                        "metadata": {
                            "source": metadata_dict.get("source", "unknown"),
                        },
                    },
                },
            )

            # ---- Finalize ----
            await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.SUCCESS)
            self.logger.info(
                "event=knowledge-base-insert-success kb_name=%s doc_id=%s message='Inserted successfully'",
                current_kb.name,
                new_kb_doc_id,
            )

        except Exception:
            self.logger.exception(
                "event=knowledge-base-insert-error kb_id=%s doc_id=%s message='Unexpected error: %s'",
                kb_id,
                new_kb_doc_id,
            )
            await self._push_status_event(kb_id, new_kb_doc_id, InsertKBDocState.FAILED)
            return False, None
        return True, new_kb_doc_id

    async def query(
        self,
        kb_name: str,
        query: str,
        retrieval_mode: RetrievalMode | None = None,
    ) -> tuple[list[ChunkInfo], dict[str, str]] | tuple[None, None]:
        """Query a knowledge base by its name and return matching chunks with presigned citation URLs."""

        try:
            # ---- Validate Knowledge Base ----
            kb_in_db = await KnowledgeBase.find_one(KnowledgeBase.name == kb_name)
            kb = await mindsdb_client.get_kb(kb_name)

            if not kb or not kb_in_db:
                self.logger.error(
                    "event=query-kb-not-found kb_name=%s message='Knowledge base not found in MongoDB or MindsDB'",
                    kb_name,
                )
                return None, None

            # ---- Query MindsDB ----
            chunks = await mindsdb_client.query_kb(
                kb_name=kb_name.lower(),
                query=query,
                config=kb_in_db.config,
                llm_handler=self._llm_handler,
                retrieval_mode=retrieval_mode,
            )

            if not chunks:
                self.logger.warning(
                    "event=knowledge-base-query-empty kb_name=%s message='No matching chunks found'",
                    kb_name,
                )
                return chunks, {}

            # ---- Generate presigned citation URLs concurrently ----
            # Use a set to deduplicate citations before generating URLs
            citation_files = {chunk.citation for chunk in chunks if chunk.citation}
            if not citation_files:
                self.logger.info(
                    "event=knowledge-base-query-success kb_name=%s message='Query successful (no citations found)'",
                    kb_name,
                )
                return chunks, {}

            # Fetch all presigned URLs at once
            citation_urls = await self._document_service.create_presigned_urls(
                object_names=list(citation_files),
            )

            # ---- Map citations back to chunks ----
            for chunk in chunks:
                if chunk.citation in citation_urls:
                    chunk.citation = {chunk.citation: citation_urls[chunk.citation]}

            self.logger.info(
                "event=knowledge-base-query-success "
                "kb_name=%s total_chunks=%d total_citations=%d message='Query completed successfully'",
                kb_name,
                len(chunks),
                len(citation_urls),
            )

        except Exception:
            self.logger.exception(
                "event=knowledge-base-query-error kb_name=%s message='Unexpected error during query: %s'",
                kb_name,
            )
            return None, None
        return chunks, citation_urls

    async def _get_default_model_configs(self) -> ModelConfig:
        """Get default model configuration for knowledge base creation."""
        owner_config = await self._llm_handler.get_owner_llm_config()
        llm_config = self._llm_handler.get_llm_config_by_key(
            owner_config=owner_config,
            key=KEY_SCHEMA_EMBEDDING_CONFIG,
        )
        return ModelConfig(
            model_name=llm_config["llm_name"],
            provider="google" if llm_config["provider"] == ModelProvider.GOOGLE_AI else "openai",
            api_key=decrypt_and_migrate(llm_config["api_key"]),
        )

    async def get_all_tags(self) -> list[str] | None:
        """Get all unique tags from knowledge bases."""
        return await self._tag_service.get_all_tags_from_kb()

    async def create_tag(self, tag_input: str) -> Tag | None:
        """Create a new tag."""
        return await self._tag_service.create_tag(tag_input)

    async def get_tag_by_id(self, tag_id: str) -> Tag | None:
        """Get a tag by ID."""
        return await self._tag_service.get_tag_by_id(tag_id)

    async def list_tags(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        active_only: bool = True,
    ) -> TagListResponse | None:
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

    async def _push_status_event(self, kb_id: str, doc_id: str, status: InsertKBDocState) -> None:
        message = {
            "doc_id": doc_id,
            "status": status,
        }

        channel = f"{RedisChannelName.KB}:{kb_id}"
        await redis_pubsub_manager.publish(channel, message)
        kb_doc = await KBDocument.get(doc_id)
        if kb_doc:
            kb_doc.state = status
            await kb_doc.save()
        else:
            self.logger.warning(
                "event=kb-doc-not-found doc_id=%s kb_id=%s",
                doc_id,
                kb_id,
            )
