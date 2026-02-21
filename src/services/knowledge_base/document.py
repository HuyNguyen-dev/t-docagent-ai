from datetime import datetime

import pandas as pd

from handlers.document import DocumentHandler
from handlers.llm_configuration import LLMConfigurationHandler
from initializer import mindsdb_client, redis_pubsub_manager
from models.kb_document import KBDocument
from models.knowledge_base import KnowledgeBase
from schemas.chunks import ChunkingConfig
from schemas.document import DocumentUpdate
from schemas.knowledge_base import DocumentWithKnowledgeBaseInfo
from services.knowledge_base.chunk import ChunkService
from services.knowledge_base.parser import ParserStrategyFactory, ParseService
from utils.constants import KEY_SCHEMA_EMBEDDING_CONFIG, TIMEZONE
from utils.enums import ChunkingMode, InsertKBDocState, ParserType, RedisChannelName, VectorType
from utils.logger.custom_logging import LoggerMixin


class DocumentService(LoggerMixin):
    """Service for managing knowledge base documents."""

    def __init__(self, parsing_service: ParseService, chunk_service: ChunkService, llm_handler: LLMConfigurationHandler) -> None:
        super().__init__()
        self._parsing_service = parsing_service
        self._chunk_service = chunk_service
        self._llm_handler = llm_handler
        self.document = DocumentHandler()
        self._pubsub = redis_pubsub_manager

    async def _publish_update_event(self, kb_id: str, doc_id: str, status: InsertKBDocState) -> None:
        """Publish update status using same schema as KB insert events and persist state on document."""
        message = {
            "doc_id": doc_id,
            "status": status,
        }
        channel = f"{RedisChannelName.KB}:{kb_id}"
        try:
            await self._pubsub.publish(channel, message)
            kb_doc = await KBDocument.get(doc_id)
            if kb_doc:
                kb_doc.state = status
                await kb_doc.save()
        except Exception:
            self.logger.warning(
                "event=publish-update-event-failed kb_id=%s doc_id=%s status=%s",
                kb_id,
                doc_id,
                status,
            )

    async def get_kb_document(self, kb_id: str, doc_id: str) -> DocumentWithKnowledgeBaseInfo | None:
        """Get a specific knowledge base document by ID."""
        kb_in_db = await KnowledgeBase.get(kb_id)
        if not kb_in_db:
            self.logger.error(
                'event=kb-not-found kb_id=%s message="Knowledge base not found in MongoDB"',
                kb_id,
            )
            return None
        doc = await KBDocument.get(doc_id)
        if not doc:
            self.logger.warning(
                'event=kb-document-not-found doc_id=%s message="Knowledge base document not found"',
                doc_id,
            )
            return None

        self.logger.info(
            'event=kb-document-retrieved doc_id=%s message="Successfully retrieved knowledge base document"',
            doc_id,
        )

        return DocumentWithKnowledgeBaseInfo(
            id=kb_in_db.id,
            name=kb_in_db.name,
            tags=kb_in_db.tags,
            description=kb_in_db.description,
            engine=kb_in_db.engine,
            document_name=doc.name,
            document_id=doc.id,
            chunking_mode=doc.chunking_mode.value if isinstance(doc.chunking_mode, ChunkingMode) else str(doc.chunking_mode),
            chunking_length=doc.chunking_config.chunk_length if doc.chunking_config else 0,
            chunking_overlap=doc.chunking_config.chunk_overlap if doc.chunking_config else 0,
            settings=kb_in_db.config.model_dump() if kb_in_db.config else {},
            created_at=doc.upload_time,
            state=doc.state,
        )

    async def get_all_kb_documents(self, kb_name: str, kb_in_db: KnowledgeBase) -> list[KBDocument] | None:
        """Get all documents for a specific knowledge base."""
        kb = await mindsdb_client.get_kb(kb_name)
        if not kb or not kb_in_db:
            self.logger.error(
                'event=get-all-documents-kb-not-found kb_name=%s message="Knowledge base not found in MongoDB or MindsDB"',
                kb_name,
            )
            return None

        # Get all documents for this knowledge base
        documents = []
        if kb_in_db.documents:
            for doc_id in kb_in_db.documents:
                try:
                    doc = await KBDocument.get(doc_id)
                    if doc:
                        documents.append(doc)
                except Exception as doc_error:
                    self.logger.warning(
                        'event=document-fetch-warning kb_name=%s doc_id=%s message="Could not fetch document: %s"',
                        kb_name,
                        doc_id,
                        str(doc_error),
                    )
                    continue

        self.logger.info(
            'event=get-all-kb-documents-success kb_name=%s message="Successfully retrieved all documents for knowledge base"',
            kb_name,
        )
        return documents

    async def delete_documents(self, object_paths: list[str]) -> bool:
        """Delete documents from MinIO."""
        return await self.document.delete_documents(object_paths=object_paths)

    async def create_presigned_urls(self, object_names: list[str]) -> dict[str, str] | None:
        """Create presigned URLs for documents."""
        return await self.document.create_presigned_urls(object_names=object_names)

    async def get_data_bytes_document(self, object_path: str) -> bytes | None:
        """Get document data bytes from MinIO."""
        return await self.document.get_data_bytes_document(object_path=object_path)

    async def update_kb_document(
        self,
        kb: KnowledgeBase,
        doc_id: str,
        update_data: DocumentUpdate,
        llm_handler: LLMConfigurationHandler,
    ) -> bool:
        """Update a knowledge base document."""
        # Get the document first
        doc = await KBDocument.get(doc_id)
        if not doc:
            self.logger.error(
                'event=update-kb-document-not-found doc_id=%s message="Document not found for update"',
                doc_id,
            )
            return False

        # Push start event
        await self._publish_update_event(kb_id=kb.id, doc_id=doc_id, status=InsertKBDocState.IN_PROCESS)

        # Build update dictionary with only provided fields
        update_dict = {}

        if update_data.name is not None:
            update_dict["name"] = update_data.name

        if update_data.chunking_config is not None:
            update_dict["chunking_config"] = update_data.chunking_config

        if update_data.chunking_mode is not None:
            update_dict["chunking_mode"] = update_data.chunking_mode

        # If chunking mode changed, we need to delete and reindex all chunks
        if (update_data.chunking_mode is not None and doc.chunking_mode != update_data.chunking_mode) or (
            update_data.chunking_config is not None
            and (
                doc.chunking_config.chunk_length != update_data.chunking_config.chunk_length
                or doc.chunking_config.chunk_overlap != update_data.chunking_config.chunk_overlap
            )
        ):
            self.logger.info(
                "event=chunking-mode-changed doc_id=%s ",
                doc_id,
            )

            # Find the knowledge base containing this document
            kb_name = kb.name
            if kb_name:
                # Delete existing chunks from MindsDB and PostgreSQL
                source_path = doc.metadata.get("source") if doc.metadata else None
                if source_path:
                    # Delete from PostgreSQL
                    if kb.engine == VectorType.POSTGRESQL:
                        await self._chunk_service._delete_document_chunks_from_postgresql(
                            kb_name,
                            source_path,
                            doc.name,
                        )
                    else:
                        # Delete from MindsDB
                        await self._chunk_service._delete_document_chunks_from_mindsdb(kb_name, doc.name)

                    # Reindex the document with the new chunking mode
                    embedding_config = None
                    if update_data.chunking_mode is not None and update_data.chunking_mode == ChunkingMode.SEMANTIC:
                        owner_config = await llm_handler.get_owner_llm_config()
                        embedding_model = llm_handler.get_llm_config_by_key(
                            owner_config=owner_config,
                            key=KEY_SCHEMA_EMBEDDING_CONFIG,
                        )
                        embedding_config = embedding_model
                    reindex_success = await self._reindex_document_after_chunking_change(
                        doc_id=doc_id,
                        kb_name=kb_name,
                        source_path=source_path,
                        new_config=ChunkingConfig(
                            chunking_mode=update_data.chunking_mode
                            if update_data.chunking_mode is not None
                            else doc.chunking_mode,
                            chunk_length=update_data.chunking_config.chunk_length
                            if update_data.chunking_config is not None
                            else doc.chunking_config.chunk_length,
                            chunk_overlap=update_data.chunking_config.chunk_overlap
                            if update_data.chunking_config is not None
                            else doc.chunking_config.chunk_overlap,
                            embedding_config=embedding_config,
                        ),
                    )

                    if not reindex_success:
                        self.logger.warning(
                            'event=reindex-failed doc_id=%s kb_name=%s message="Failed to reindex document "',
                            doc_id,
                            kb_name,
                        )
                        await self._publish_update_event(kb_id=kb.id, doc_id=doc_id, status=InsertKBDocState.FAILED)
                    else:
                        await self._publish_update_event(kb_id=kb.id, doc_id=doc_id, status=InsertKBDocState.IN_PROCESS)
                else:
                    self.logger.warning(
                        'event=no-source-path-for-reindex doc_id=%s message="No source path found"',
                        doc_id,
                    )
                    await self._publish_update_event(kb_id=kb.id, doc_id=doc_id, status=InsertKBDocState.FAILED)
            else:
                self.logger.warning(
                    'event=kb-not-found-for-reindex doc_id=%s message="Knowledge base not found"',
                    doc_id,
                )
                await self._publish_update_event(kb_id=kb.id, doc_id=doc_id, status=InsertKBDocState.FAILED)

        if update_data.metadata is not None:
            update_dict["metadata"] = update_data.metadata

        # Always update the upload_time timestamp
        update_dict["upload_time"] = datetime.now(TIMEZONE)

        if not update_dict:
            self.logger.warning(
                'event=update-kb-document-no-changes doc_id=%s message="No changes provided for update"',
                doc_id,
            )
            return True

        # Update the document
        await doc.update({"$set": update_dict})

        self.logger.info(
            'event=update-kb-document-success doc_id=%s message="Knowledge base document updated successfully"',
            doc_id,
        )
        await self._publish_update_event(kb_id=kb.id, doc_id=doc_id, status=InsertKBDocState.SUCCESS)
        return True

    async def delete_kb_document(self, kb_id: str, doc_id: str) -> bool:
        """Delete a knowledge base document by ID."""
        doc = await KBDocument.get(doc_id)

        if not doc:
            self.logger.warning(
                'event=delete-kb-document-not-found doc_id=%s message="Document not found for deletion"',
                doc_id,
            )
            return False

        # Get document info for logging
        doc_name = getattr(doc, "name", "unknown")
        source_path = doc.metadata.get("source") if doc.metadata else None

        if not source_path:
            self.logger.warning(
                'event=delete-document-no-source doc_id=%s doc_name=%s message="Document has no source path in metadata"',
                doc_id,
                doc_name,
            )
            # Still delete from MongoDB even if no source path
            await doc.delete()
            return True

        # Step 1: Find the knowledge base that contains this document
        kb_in_db = await KnowledgeBase.get(kb_id)
        if not kb_in_db:
            self.logger.warning(
                'event=delete-kb-document-not-found doc_id=%s message="Document not found for deletion"',
                doc_id,
            )
            # Still delete from MongoDB even if kb_in_db
            await doc.delete()
            return True

        if doc_id in kb_in_db.documents:
            kb_in_db.documents.remove(doc_id)
            await kb_in_db.save()

        # Step 2: Delete by filtering on source metadata
        if kb_in_db.engine == VectorType.POSTGRESQL:
            await self._chunk_service._delete_document_chunks_from_postgresql(kb_in_db.name, source_path, doc_name)
        else:
            await self._chunk_service._delete_document_chunks_from_mindsdb(kb_in_db.name, doc_name)

        # Step 3: Check if MinIO file can be safely deleted
        await self._delete_minio_file(source_path)

        # Step 4: Delete from MongoDB
        await doc.delete()

        self.logger.info(
            "event=delete-kb-document-success doc_id=%s",
            doc_id,
        )
        return True

    async def _reindex_document_after_chunking_change(
        self,
        doc_id: str,
        kb_name: str,
        source_path: str,
        new_config: ChunkingConfig,
    ) -> bool:
        """Reindex a document after chunking mode change."""
        self.logger.info(
            'event=reindex-document-start doc_id=%s kb_name=%s source=%s new_mode=%s message="Starting document reindexing"',
            doc_id,
            kb_name,
            source_path,
            new_config.chunking_mode.value,
        )

        # Get the document
        doc = await KBDocument.get(doc_id)
        if not doc:
            self.logger.error(
                'event=reindex-document-not-found doc_id=%s message="Document not found for reindexing"',
                doc_id,
            )
            return False

        # Get the knowledge base
        kb_in_db = await KnowledgeBase.find_one({"name": kb_name})
        if not kb_in_db:
            self.logger.error(
                'event=reindex-kb-not-found kb_name=%s message="Knowledge base not found for reindexing"',
                kb_name,
            )
            return False

        self.logger.info(
            "event=reindex-document-needed doc_id=%s ",
            doc_id,
        )

        # 1. Re-parsing the original file with new chunking mode
        file_bytes = await self.get_data_bytes_document(object_path=doc.metadata["source"])
        if not file_bytes:
            self.logger.error(
                'event=reindex-document-no-file doc_id=%s message="Could not get document file bytes"',
                doc_id,
            )
            return False
        parser_type = ParserType.FILE
        parser = ParserStrategyFactory.create_parser(file_path=source_path, parser_type=parser_type)
        if not parser:
            self.logger.error(
                'event=parser-strategy-not-found message="No parser strategy found"',
            )
            return False
        df = await parser.parse(
            file_bytes=file_bytes,
            file_path=source_path,
            chunking_config=new_config,
            llm_handler=self._llm_handler,
        )
        df = pd.DataFrame(df)
        # 2. Inserting the new chunks into MindsDB/PostgreSQL
        success = await mindsdb_client.insert_kb(
            kb_name=kb_name,
            content_data=df,
            kb_id=kb_in_db.id,
            doc_id=doc_id,
        )
        if not success:
            self.logger.error(
                'event=knowledge-base-insert-failed message="Failed to insert data into knowledge base"',
            )
            return False
        return True

    async def _delete_minio_file(self, source_path: str) -> None:
        await self.document.delete_documents(object_paths=[source_path])

    async def preview_chunk_in_update(
        self,
        kb_id: str,
        doc_id: str,
        chunking_mode: ChunkingMode,
        chunk_length: int,
        chunk_overlap: int,
    ) -> list[dict] | None:
        doc = await KBDocument.get(doc_id)
        if not doc:
            self.logger.warning(
                'event=kb-document-not-found kb_id=%s doc_id=%s message="Document not found for previewing chunks"',
                kb_id,
                doc_id,
            )
            return None

        # Get document info for logging
        doc_name = getattr(doc, "name", "unknown")
        source_path = doc.metadata.get("source") if doc.metadata else None

        if not source_path:
            self.logger.warning(
                'event=document-no-source kb_id=%s doc_id=%s doc_name=%s message="Document has no source path in metadata"',
                kb_id,
                doc_id,
                doc_name,
            )
            return None

        # 1. Re-parsing the original file with new chunking mode

        parser_type = ParserType.FILE if not source_path.startswith(("http://", "https://")) else ParserType.URL
        if not source_path.startswith(("http://", "https://")):
            parser_type = ParserType.FILE
            file_bytes = await self.get_data_bytes_document(object_path=source_path)
            file_path = doc.name
            if not file_bytes:
                self.logger.error(
                    'event=reindex-document-no-file kb_id=%s doc_id=%s message="Could not get document file bytes"',
                    kb_id,
                    doc_id,
                )
                return None
        else:
            parser_type = ParserType.URL
            file_path = source_path

        preview_chunks = await self._parsing_service.preview_chunk(
            parser_type=parser_type,
            file_bytes=file_bytes,
            file_path=file_path,
            chunking_mode=chunking_mode,
            chunk_length=chunk_length,
            chunk_overlap=chunk_overlap,
        )
        self.logger.info(
            "event=preview-chunk-success kb_id=%s doc_id=%s doc_name=%s total_chunks=%s chunk_length=%s chunk_overlap=%s",
            kb_id,
            doc_id,
            doc_name,
            len(preview_chunks),
            chunk_length,
            chunk_overlap,
        )

        return preview_chunks
