import asyncio
from typing import Any

import httpx
import mindsdb_sdk
import pandas as pd
from mindsdb_sdk.knowledge_bases import KnowledgeBase
from pydantic import SecretStr
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from handlers.llm_configuration import LLMConfigurationHandler
from helpers.llm.embedding import EmbeddingService
from helpers.pgvector_client import PGVectorClient
from initializer import redis_pubsub_manager
from models.kb_document import KBDocument
from schemas.chunks import ChunkInfo
from schemas.knowledge_base import KnowledgeBaseConfig, RetrievalMode
from schemas.model_config import MindsDbModelConfigs, ModelConfig
from utils.constants import DEFAULT_EMBEDDING_BATCH_SIZE, KEY_SCHEMA_EMBEDDING_CONFIG, MAX_RETRIES, RETRY_BACKOFF
from utils.enums import InsertKBDocState, KnowledgeBaseSearchMethod, RedisChannelName
from utils.logger.custom_logging import LoggerMixin


class MindsDBClient(LoggerMixin):
    """Client for interacting with MindsDB knowledge base."""

    def __init__(self, pg_client: PGVectorClient, http_client: httpx.AsyncClient) -> None:
        super().__init__()
        self.server = None
        self._initialize_connection()
        self.pg_client = pg_client
        self.http_client = http_client

    def _initialize_connection(self) -> None:
        try:
            self.server = mindsdb_sdk.connect(settings.MINDSDB_API_URL)
        except Exception:
            self.logger.exception("event=mindsdb-connection-error")
            raise

    @retry(
        retry=retry_if_exception_type(httpx.RequestError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def execute_query(self, query: str) -> pd.DataFrame:
        """
        Execute SQL query using REST API with httpx.

        Args:
            query: SQL query string to execute

        Returns:
            DataFrame containing query results
        """
        try:
            url = f"{settings.MINDSDB_API_URL}/api/sql/query"
            response = await self.http_client.post(
                url,
                json={"query": query},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                data = response.json()
                # Convert response to DataFrame
                if isinstance(data, dict) and "data" in data:
                    return pd.DataFrame(data["data"], columns=data.get("column_names", []))
                if isinstance(data, list):
                    return pd.DataFrame(data)
                return pd.DataFrame(data)
            self.logger.error(
                "event=query-http-failed status_code=%s response=%s",
                response.status_code,
                response.text,
            )
            return pd.DataFrame()

        except Exception as e:
            self.logger.exception(
                "event=query-http-exception message='Failed to execute query via HTTP'",
                exc_info=e,
            )
            return pd.DataFrame()

    async def set_config(self, config: MindsDbModelConfigs) -> None:
        """
        Set the configuration for the MindsDB client.
        """
        try:
            if config.embedding_model:
                await asyncio.to_thread(
                    self.server.config.set_default_embedding_model,
                    **config.embedding_model.model_dump(),
                )
                self.logger.info(
                    "event=embedding-model-config-set "
                    "provider=%s "
                    "model_name=%s "
                    'message="Embedding model configuration set successfully"',
                    config.embedding_model.provider,
                    config.embedding_model.model_name,
                )

            if config.reranking_model:
                await asyncio.to_thread(
                    self.server.config.set_default_reranking_model,
                    **config.reranking_model.model_dump(),
                )
                self.logger.info(
                    "event=reranking-model-config-set "
                    "provider=%s "
                    "model_name=%s "
                    'message="Reranking model configuration set successfully"',
                    config.reranking_model.provider,
                    config.reranking_model.model_name,
                )

            self.logger.info(
                'event=config-set-success message="MindsDB configuration set successfully"',
            )

        except Exception as e:
            self.logger.exception(
                'event=config-set-failed message="Failed to set MindsDB configuration"',
                exc_info=e,
            )
            raise

    async def get_config(self) -> MindsDbModelConfigs | None:
        """
        Get the current configuration for the MindsDB client.

        Returns:
            MindsDbModelConfigs object with current configuration or None if failed.
        """
        try:
            # Get current embedding model configuration
            embedding_config = None
            try:
                embedding_model = await asyncio.to_thread(
                    self.server.config.get_default_embedding_model,
                )
                if embedding_model:
                    embedding_config = ModelConfig(
                        provider=embedding_model.get("provider", ""),
                        model_name=embedding_model.get("model_name", ""),
                        api_key="***",  # Mask sensitive data
                    )
            except Exception as exc:
                # No embedding model configured
                self.logger.warning(
                    'event=embedding-model-config-not-found message="No embedding model configured or error occurred"',
                    exc_info=exc,
                )

            # Get current reranking model configuration
            reranking_config = None
            try:
                reranking_model = await asyncio.to_thread(
                    self.server.config.get_default_reranking_model,
                )
                if reranking_model:
                    reranking_config = ModelConfig(
                        provider=reranking_model.get("provider", ""),
                        model_name=reranking_model.get("model_name", ""),
                        api_key="***",  # Mask sensitive data
                    )
            except Exception as exc:
                # No reranking model configured
                self.logger.warning(
                    'event=reranking-model-config-not-found message="No reranking model configured or error occurred"',
                    exc_info=exc,
                )

            config = MindsDbModelConfigs(
                embedding_model=embedding_config,
                reranking_model=reranking_config,
            )

            self.logger.info(
                "event=config-get-success "
                "has_embedding=%s "
                "has_reranking=%s "
                'message="Retrieved MindsDB configuration successfully"',
                embedding_config is not None,
                reranking_config is not None,
            )

        except Exception as e:
            self.logger.exception(
                'event=config-get-failed message="Failed to get MindsDB configuration"',
                exc_info=e,
            )
            return None
        return config

    async def set_default_llm(self, llm_config: ModelConfig) -> bool:
        """
        Set the default LLM configuration for the MindsDB client using settings from config.
        """
        try:
            await asyncio.to_thread(
                self.server.config.set_default_llm,
                **llm_config.model_dump(),
            )

            self.logger.info(
                'event=default-llm-set-success provider=%s model_name=%s message="Default LLM configuration set successfully"',
                llm_config.provider,
                llm_config.model_name,
            )
        except Exception as e:
            self.logger.exception(
                'event=default-llm-set-failed message="Failed to set default LLM configuration"',
                exc_info=e,
            )
            return False
        return True

    async def get_kb(self, kb_name: str) -> KnowledgeBase | None:
        """
        Retrieve a knowledge base by its name.

        Args:
            kb_name: The name of the knowledge base to retrieve.

        Returns:
            KnowledgeBase object if found, None otherwise.
        """
        try:
            if self.server is None:
                return None

            kb_list = await asyncio.to_thread(self.server.knowledge_bases.list)
            for kb in kb_list:
                if kb_name == kb.name:
                    return kb
        except Exception as e:
            self.logger.exception(
                'event=knowledge-base-retrieval-failed kb_name=%s message="Failed to retrieve knowledge base"',
                kb_name,
                exc_info=e,
            )
            return None
        return None

    async def list_kb(
        self,
    ) -> list[str]:
        try:
            query = "SHOW KNOWLEDGE_BASES;"
            result = await self.execute_query(query)

            if not result.empty:
                return result["NAME"].tolist()
        except Exception as e:
            self.logger.exception(
                'event=list-knowledge-bases-failed message="Failed to list knowledge bases"',
                exc_info=e,
            )
        return []

    async def create_kb(
        self,
        kb_name: str,
        model_configs: ModelConfig | None = None,
        content_columns: list[str] | None = None,
        metadata_columns: list[str] | None = None,
        vector_db_name: str | None = None,
        table_name: str | None = None,
    ) -> bool | None:
        """
        Create a new knowledge base.
        Args:
            kb_name: The name of the knowledge base to create.
            content_columns: List of content columns for the knowledge base.
            metadata_columns: Additional metadata for the knowledge base.
        Returns:
            True object if creation is successful, None otherwise.
        """
        try:
            existed_kb_names = await self.list_kb()
            if kb_name not in existed_kb_names:
                if vector_db_name and model_configs:
                    # Build USING clause with all parameters
                    using_params = [
                        # Add embedding model config
                        f"""
                        embedding_model = {{
                            'provider': '{model_configs.provider}',
                            'model_name': '{model_configs.model_name}',
                            'api_key': '{model_configs.api_key}'
                        }}""",
                        # Add storage config
                        f"storage = {vector_db_name}.{table_name}",
                    ]

                    # Add content columns
                    if content_columns:
                        using_params.append(f"content_columns = {content_columns}")

                    # Add metadata columns
                    if metadata_columns:
                        using_params.append(f"metadata_columns = {metadata_columns}")

                    sql = f"""
                        CREATE KNOWLEDGE_BASE {kb_name}
                        USING
                            {",".join(using_params)};
                        """
                    await self.execute_query(sql)
                else:
                    # Create without custom storage
                    using_parts = []

                    if content_columns:
                        content_cols_str = str(content_columns)
                        using_parts.append(f"content_columns = {content_cols_str}")

                    if metadata_columns:
                        metadata_cols_str = str(metadata_columns)
                        using_parts.append(f"metadata_columns = {metadata_cols_str}")

                    sql = f"CREATE KNOWLEDGE_BASE {kb_name}"
                    if using_parts:
                        sql += f"\nUSING {', '.join(using_parts)}"
                    sql += ";"

                    await self.execute_query(sql)
                return True
        except Exception:
            self.logger.exception(
                'event="create-knowledge-base-was-failed" kb_name=%s ',
                kb_name,
            )
            return None
        return True

    async def insert_kb(
        self,
        kb_name: str,
        content_data: pd.DataFrame | dict[str, Any],
        kb_id: str | None = None,
        doc_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        max_concurrent_batches: int = 3,
    ) -> bool | None:
        """Insert parsed data into the knowledge base with simple TaskGroup concurrency."""
        try:
            if self.server is None:
                return None
            self.logger.info(
                (
                    "event=knowledge-base-insert parsed_data_keys=%s metadata_keys=%s "
                    'max_concurrent_batches=%d message="Inserting data into knowledge base"'
                ),
                list(content_data.keys()),
                list(metadata.keys()) if metadata else "None",
                max_concurrent_batches,
            )

            kb = await self.get_kb(kb_name)
            if kb is None:
                self.logger.error(
                    'event=knowledge-base-insert-failed kb_name=%s message="Knowledge base does not exist"',
                    kb_name,
                )
                return False

            df = pd.DataFrame(content_data) if isinstance(content_data, dict) else content_data
            total_rows = len(df)

            if total_rows <= DEFAULT_EMBEDDING_BATCH_SIZE:
                # Small dataset, insert directly
                await self._insert_single_batch(kb, df, kb_id, doc_id)
                if kb_id is not None and doc_id is not None:
                    message = {
                        "doc_id": doc_id,
                        "loading_percent": 1,
                    }

                    channel = f"{RedisChannelName.KB}:{kb_id}"
                    await redis_pubsub_manager.publish(channel, message)
                self.logger.info(
                    'event=knowledge-base-inserted kb_name=%s rows=%d message="Data inserted successfully"',
                    kb_name,
                    total_rows,
                )
                return True

            # Large dataset, use TaskGroup for concurrent insertion
            return await self._insert_with_taskgroup(
                kb,
                df,
                kb_name,
                DEFAULT_EMBEDDING_BATCH_SIZE,
                max_concurrent_batches,
                kb_id,
                doc_id,
            )

        except Exception as e:
            self.logger.exception(
                'event=knowledge-base-insert-failed kb_name=%s message="Failed to insert data"',
                kb_name,
                exc_info=e,
            )
            return False

    async def _insert_single_batch(
        self,
        kb: KnowledgeBase,
        df: pd.DataFrame,
        kb_id: str | None = None,
        doc_id: str | None = None,
    ) -> bool:
        """Insert a single batch with retry and timeout handling."""
        for attempt in range(MAX_RETRIES):
            try:
                await asyncio.wait_for(asyncio.to_thread(kb.insert, df), timeout=1000)
            except TimeoutError:
                self.logger.warning(
                    'event=batch-insert-timeout attempt=%d message="Batch insert timed out"',
                    attempt + 1,
                )
            except Exception as e:
                self.logger.warning(
                    'event=batch-insert-error attempt=%d error="%s"',
                    attempt + 1,
                    str(e),
                )
            else:
                self.logger.debug(
                    'event=batch-insert-success attempt=%d message="Batch inserted successfully"',
                    attempt + 1,
                )
                return True  # stop retrying

            # Retry delay (only if failed)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF[attempt])
            else:
                self.logger.error(
                    'event=batch-insert-failed retries=%d message="Failed to insert batch after retries"',
                    MAX_RETRIES,
                )
                if kb_id is not None and doc_id is not None:
                    message = {
                        "doc_id": doc_id,
                        "status": InsertKBDocState.FAILED,
                    }

                    channel = f"{RedisChannelName.KB}:{kb_id}"
                    await redis_pubsub_manager.publish(channel, message)
                    kb_doc = await KBDocument.get(doc_id)
                    if kb_doc:
                        kb_doc.state = InsertKBDocState.FAILED
                        await kb_doc.save()
                    else:
                        self.logger.warning(
                            "event=kb-doc-not-found doc_id=%s kb_id=%s",
                            doc_id,
                            kb_id,
                        )
        return True

    async def _insert_with_taskgroup(
        self,
        kb: KnowledgeBase,
        df: pd.DataFrame,
        kb_name: str,
        batch_size: int,
        max_concurrent_batches: int,
        kb_id: str | None = None,
        doc_id: str | None = None,
    ) -> bool:
        """Concurrent batch insertion using asyncio.TaskGroup with early stop on failure."""
        success = True  # Default flag

        # Split DataFrame into batches
        total_rows = len(df)
        batches = [df.iloc[i : i + batch_size].copy() for i in range(0, total_rows, batch_size)]

        self.logger.info(
            'event=taskgroup-start kb_name=%s total_batches=%d message="Starting TaskGroup insertion"',
            kb_name,
            len(batches),
        )

        semaphore = asyncio.Semaphore(max_concurrent_batches)
        lock = asyncio.Lock()
        completed_insert = 0

        async def insert_batch_with_semaphore(batch_df: pd.DataFrame) -> None:
            nonlocal completed_insert
            async with semaphore:
                success_batch = await self._insert_single_batch(kb, batch_df, kb_id, doc_id)
                if not success_batch:
                    msg = "Batch insert failed"
                    raise RuntimeError(msg)

                async with lock:
                    completed_insert += 1
                    loading_percent = completed_insert / len(batches)
                    if kb_id and doc_id:
                        message = {
                            "doc_id": doc_id,
                            "loading_percent": loading_percent,
                        }
                        channel = f"{RedisChannelName.KB}:{kb_id}"
                        await redis_pubsub_manager.publish(channel, message)

        try:
            # Create batches
            batches = []
            total_rows = len(df)
            for i in range(0, total_rows, batch_size):
                batch_end = min(i + batch_size, total_rows)
                batch_df = df.iloc[i:batch_end].copy()
                batches.append(batch_df)

            self.logger.info(
                'event=taskgroup-start kb_name=%s total_batches=%d message="Starting TaskGroup insertion"',
                kb_name,
                len(batches),
            )

            # Use semaphore to limit concurrent batches
            semaphore = asyncio.Semaphore(max_concurrent_batches)
            lock = asyncio.Lock()
            completed_insert = 0

            async def insert_batch_with_semaphore(batch_df: pd.DataFrame) -> any:
                nonlocal completed_insert
                async with semaphore:
                    success = await self._insert_single_batch(kb, batch_df, kb_id, doc_id)
                    if success:
                        async with lock:
                            completed_insert += 1
                            loading_percent = completed_insert / len(batches)
                            if kb_id is not None and doc_id is not None:
                                message = {
                                    "doc_id": doc_id,
                                    "loading_percent": loading_percent,
                                }

                                channel = f"{RedisChannelName.KB}:{kb_id}"
                                await redis_pubsub_manager.publish(channel, message)

            # Use TaskGroup for structured concurrency
            async with asyncio.TaskGroup() as tg:
                for batch in batches:
                    tg.create_task(insert_batch_with_semaphore(batch))

            self.logger.info(
                'event=taskgroup-success kb_name=%s total_batches=%d message="All batches inserted successfully"',
                kb_name,
                len(batches),
            )

        except* RuntimeError:
            success = False
            self.logger.exception(
                'event=taskgroup-failed kb_name=%s message="Batch insertion stopped early due to failure"',
                kb_name,
            )

        except* Exception:
            success = False
            self.logger.exception(
                'event=taskgroup-error kb_name=%s message="Unexpected error during TaskGroup insertion"',
                kb_name,
            )

        return success

    async def delete_kb(self, kb_name: str) -> bool:
        """
        Delete a knowledge base by its name.

        Args:
            kb_name: The name of the knowledge base to delete.

        Returns:
            True if deletion is successful, False otherwise.
        """
        try:
            kb = await self.get_kb(kb_name)
            if kb:
                query = f"DROP KNOWLEDGE_BASE {kb_name};"
                await self.execute_query(query)
                query = f"DROP DATABASE {kb_name};"
                await self.execute_query(query)
                self.logger.info(
                    'event=knowledge-base-deleted kb_name=%s message="Knowledge base deleted successfully"',
                    kb_name,
                )
                return True
            self.logger.error(
                'event=knowledge-base-deletion-failed kb_name=%s message="Knowledge base does not exist"',
                kb_name,
            )
        except Exception as e:
            self.logger.exception(
                'event=knowledge-base-deletion-failed kb_name=%s message="Failed to delete knowledge base"',
                kb_name,
                exc_info=e,
            )
        return False

    async def query_kb(
        self,
        kb_name: str,
        query: str,
        config: KnowledgeBaseConfig,
        llm_handler: LLMConfigurationHandler,
        retrieval_mode: RetrievalMode | None = None,
    ) -> list[ChunkInfo]:
        """
        Query a knowledge base with context expansion to provide more comprehensive results.

        This method performs the initial query and then retrieves additional chunks
        from the same sections/headings to provide better context for the LLM.
        """
        if query == "":
            return []
        chunks = []
        try:
            # Get knowledge base
            kb = await self.get_kb(kb_name)
            if not kb:
                self.logger.error(
                    'event=knowledge-base-not-found kb_name=%s message="Knowledge base not found"',
                    kb_name,
                )
                return []

            embedding_model = config.embedding_model
            if retrieval_mode is not None:
                search_mode = retrieval_mode.search_method
                limit = retrieval_mode.top_k
                relevance = retrieval_mode.relevance_threshold if retrieval_mode.relevance_enabled else 0.0
                enable_rerank = retrieval_mode.rerank_enabled
                enable_search_alpha = retrieval_mode.hybrid_alpha_search_enabled
                hybrid_weight = retrieval_mode.hybrid_weight
            else:
                search_mode = config.retrieval_mode.search_method
                limit = config.retrieval_mode.top_k
                relevance = config.retrieval_mode.relevance_threshold if config.retrieval_mode.relevance_enabled else 0.0
                enable_rerank = config.retrieval_mode.rerank_enabled
                enable_search_alpha = config.retrieval_mode.hybrid_alpha_search_enabled
                hybrid_weight = config.retrieval_mode.hybrid_weight

            if search_mode == KnowledgeBaseSearchMethod.SEMANTIC:
                semantic_query = f"""
                SELECT * from {kb_name}
                WHERE
                    content = '{query}'
                    AND reranking = {enable_rerank}
                    AND relevance >= {relevance}
                LIMIT {limit};
                """  # noqa: S608
                semantic_search = await self.execute_query(semantic_query)
                if semantic_search.empty:
                    return []
                try:
                    chunk_contents = semantic_search["chunk_content"]
                    metadatas = semantic_search["metadata"]
                except Exception:
                    if "error" in semantic_search["type"].to_list():
                        self.logger.exception(
                            "event=retrieval-error message=%s",
                            semantic_search.get("error_message", "Unknown error"),
                        )

                    return []
            elif search_mode == KnowledgeBaseSearchMethod.HYBRID:
                if enable_search_alpha:
                    owner_config = await llm_handler.get_owner_llm_config()
                    embedding_service = EmbeddingService(
                        emb=embedding_model,
                    ).create_embedding(
                        **llm_handler.get_llm_config_by_key(
                            owner_config=owner_config,
                            key=KEY_SCHEMA_EMBEDDING_CONFIG,
                        ),
                    )
                    query_vector = await embedding_service.aembed_query(text=query)
                    search = await self.pg_client.hybrid_search_alpha(
                        table_name=kb_name,
                        query_text=query,
                        query_vector=query_vector,
                        alpha=hybrid_weight,
                        enable_reranking=enable_search_alpha,
                        limit=limit,
                        rerank_candidates=limit,
                    )
                    if search is not None and search.empty:
                        return []
                    if search is None:
                        return []
                    chunk_contents = search["content"]
                    metadatas = search["metadata"]
                else:
                    hybrid_sql = f"""
                    SELECT * from {kb_name}
                    WHERE
                        content = '{query}'
                        AND hybrid_search = true
                        AND reranking = {enable_rerank}
                        AND relevance >= {relevance}
                    LIMIT {limit};
                    """  # noqa: S608
                    hybrid_search = await self.execute_query(hybrid_sql)
                    if hybrid_search.empty:
                        return []
                    try:
                        hybrid_search = hybrid_search.head(limit)
                        chunk_contents = hybrid_search["chunk_content"]
                        metadatas = hybrid_search["metadata"]
                    except Exception:
                        if "error" in hybrid_search["type"].to_list():
                            self.logger(f"event=retrieval-error message={hybrid_search['error_message']}")
                        return []
            elif search_mode == KnowledgeBaseSearchMethod.FULL_TEXT:
                search = await self.pg_client.search_by_keyword(table_name=kb_name, keyword=query, limit=limit)
                if search is not None and search.empty:
                    return []
                if search is None:
                    return []
                chunk_contents = search["content"]
                metadatas = search["metadata"]

            index = -1
            for chunk, metadata in zip(chunk_contents, metadatas, strict=False):
                index = index + 1
                citation = self._extract_citation(metadata)
                chunk_info = ChunkInfo(
                    index=index,
                    content=chunk,
                    citation=citation,
                )
                chunks.append(chunk_info)

            self.logger.info(
                'event=context-expansion-success kb_name=%s chunk_contents=%d message="Successfully expanded context"',
                kb_name,
                len(chunk_contents),
            )

        except Exception:
            self.logger.exception(
                'event=knowledge-base-query-with-context-failed kb_name=%s message="Failed to query knowledge base with context"',
                kb_name,
            )
        return chunks

    def _extract_citation(self, metadata: dict) -> str | None:
        """
        Extract citation from metadata.
        """
        return metadata["source"] if metadata["source"] is not None else None

    async def create_database(
        self,
        db_name: str,
        engine: str,
        databse_config: dict[str, Any],
    ) -> bool:
        """
        Create a new database connection.

        Args:
            db_name: The name of the database.
            db_type: The type of the database (e.g., 'mysql', 'postgres').
            host: The host of the database.
            port: The port of the database.
            user: The username for the database.
            password: The password for the database.

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            existed_db_names = await self.list_database()
            if db_name not in existed_db_names:
                query = f"""
                CREATE DATABASE {db_name}
                WITH ENGINE = '{engine}',
                PARAMETERS = {databse_config};
                """
                await self.execute_query(query)
                self.logger.info(
                    'event=database-connected db_name=%s message="Database connected successfully"',
                    db_name,
                )
                return True
            self.logger.error(
                'event=database-connection-failed db_name=%s message="Knowledge base is already exist"',
                db_name,
            )
        except Exception as e:
            self.logger.exception(
                'event=database-connection-failed db_name=%s message="Failed to connect to database"',
                db_name,
                exc_info=e,
            )
        return False

    async def list_database(
        self,
    ) -> list[str]:
        try:
            query = "SHOW DATABASES;"
            result = await self.execute_query(query)

            if not result.empty:
                # Try different possible column names
                for col in ["name", "NAME", "Database", "database"]:
                    if col in result.columns:
                        return result[col].tolist()
        except Exception as e:
            self.logger.exception(
                'event=list-databases-failed message="Failed to list databases"',
                exc_info=e,
            )
        return []

    async def get_database(
        self,
        db_name: str,
    ) -> dict | None:
        """
        Retrieve a database by its name.

        Args:
            db_name: The name of the database to retrieve.

        Returns:
            Database info dictionary if found, None otherwise.
        """
        try:
            existed_db_names = await self.list_database()
            if db_name in existed_db_names:
                query = "SHOW DATABASES;"
                result = await self.execute_query(query)

                if not result.empty:
                    for _, row in result.iterrows():
                        row_name = row.get("name") or row.get("NAME") or row.get("Database") or row.get("database")
                        if row_name == db_name:
                            return row.to_dict()
        except Exception as e:
            self.logger.exception(
                'event=database-retrieval-failed db_name=%s message="Failed to retrieve database"',
                db_name,
                exc_info=e,
            )
        return None

    async def insert_from_database(
        self,
        kb_name: str,
        db_name: str,
        table_name: str,
        columns_name: list[str] | None = None,
    ) -> bool:
        """
        Create a knowledge base from a database table.

        Args:
            kb_name: The name of the knowledge base to create.
            db_name: The name of the database to connect to.
            table_name: The name of the table to use as data source.
            columns_name: Optional dictionary mapping column names to their types/roles.

        Returns:
            True if creation is successful, False otherwise.
        """
        try:
            database = await self.get_database(db_name)
            if not database:
                self.logger.error(
                    'event=knowledge-base-creation-from-db-failed kb_name=%s db_name=%s message="Database not found"',
                    kb_name,
                    db_name,
                )
                return False

            # Build SQL query with optional column selection
            if columns_name:
                columns_str = ", ".join(columns_name)
                query = f"SELECT {columns_str} FROM {db_name}.{table_name};"  # noqa: S608
            else:
                query = f"SELECT * FROM {db_name}.{table_name};"  # noqa: S608

            self.logger.info(
                "event=knowledge-base-query-execution "
                "kb_name=%s "
                "db_name=%s "
                "table_name=%s "
                "query=%s "
                'message="Executing database query"',
                kb_name,
                db_name,
                table_name,
                query,
            )

            data = await self.execute_query(query)

            # Convert all values to strings
            data = data.astype(str)

            await self.insert_kb(
                kb_name=kb_name,
                content_data=data,
            )

            self.logger.info(
                "event=knowledge-base-creation-from-db-success "
                "kb_name=%s "
                "db_name=%s "
                "table_name=%s "
                'message="Knowledge base created successfully from database"',
                kb_name,
                db_name,
                table_name,
            )

        except Exception as e:
            self.logger.exception(
                "event=knowledge-base-creation-from-db-failed "
                "kb_name=%s "
                "db_name=%s "
                "table_name=%s "
                'message="Failed to create knowledge base from database"',
                kb_name,
                db_name,
                table_name,
                exc_info=e,
            )
            return False
        return True

    async def create_mongodb_datasource(
        self,
        db_name: str,
        host: str,
        port: int = 27017,
        username: str | None = None,
        password: SecretStr | None = None,
        database: str | None = None,
        auth_mechanism: str = "DEFAULT",
    ) -> bool:
        """
        Create a MongoDB data source connection.

        Args:
            db_name: The name for the data source connection.
            host: MongoDB host address.
            port: MongoDB port (default: 27017).
            username: MongoDB username.
            password: MongoDB password.
            database: MongoDB database name.
            auth_mechanism: Authentication mechanism (default: "DEFAULT").

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            # Build MongoDB connection parameters
            db = await self.get_database(db_name)
            if db:
                self.logger.warning(
                    'event=failed-to-create-mongo-datasource db_name=%s message="Mongo data source is already exist "',
                    db_name,
                )
                return False
            parameters = {
                "host": host,
                "port": port,
                "authMechanism": auth_mechanism,
            }

            if username:
                parameters["username"] = username
            if password:
                parameters["password"] = password.get_secret_value()
            if database:
                parameters["database"] = database

            # Create the data source using MindsDB SQL
            query = f"""
            CREATE DATABASE {db_name}
            WITH ENGINE = "mongodb"
            PARAMETERS = {parameters};
            """

            self.logger.info(
                'event=mongodb-datasource-creation db_name=%s host=%s port=%s message="Creating MongoDB data source"',
                db_name,
                host,
                port,
            )

            await self.execute_query(query)

            self.logger.info(
                'event=mongodb-datasource-created db_name=%s message="MongoDB data source created successfully"',
                db_name,
            )

        except Exception as e:
            self.logger.exception(
                'event=mongodb-datasource-creation-failed db_name=%s host=%s message="Failed to create MongoDB data source"',
                db_name,
                host,
                exc_info=e,
            )
            return False
        return True

    async def create_postgresql_datasource(
        self,
        db_name: str,
        host: str,
        port: int = 5432,
        database: str = "postgres",
        user: str | None = None,
        password: SecretStr | None = None,
        schema: str | None = None,
        ssl_mode: str | None = None,
    ) -> bool:
        """
        Create a PostgreSQL data source connection.

        Args:
            db_name: The name for the data source connection.
            host: PostgreSQL host address.
            port: PostgreSQL port (default: 5432).
            database: PostgreSQL database name (default: "postgres").
            user: PostgreSQL username.
            password: PostgreSQL password.
            schema: PostgreSQL schema name.
            ssl_mode: SSL mode for connection.

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            # Build PostgreSQL connection parameters
            db = await self.get_database(db_name)
            if db:
                self.logger.warning(
                    'event=failed-to-create-postgres-datasource db_name=%s message="Postgres data source is already exist "',
                    db_name,
                )
                return False
            parameters = {
                "host": host,
                "port": port,
                "database": database,
            }

            if user:
                parameters["user"] = user
            if password:
                parameters["password"] = password.get_secret_value()
            if schema:
                parameters["schema"] = schema
            if ssl_mode:
                parameters["sslmode"] = ssl_mode

            # Create the data source using MindsDB SQL
            query = f"""
            CREATE DATABASE {db_name}
            WITH ENGINE = 'postgres',
            PARAMETERS = {parameters};
            """

            self.logger.info(
                "event=postgresql-datasource-creation "
                "db_name=%s "
                "host=%s "
                "port=%s "
                "database=%s "
                'message="Creating PostgreSQL data source"',
                db_name,
                host,
                port,
                database,
            )

            await self.execute_query(query)
            self.logger.info(
                'event=postgresql-datasource-created db_name=%s message="PostgreSQL data source created successfully"',
                db_name,
            )

        except Exception as e:
            self.logger.exception(
                "event=postgresql-datasource-creation-failed "
                "db_name=%s "
                "host=%s "
                'message="Failed to create PostgreSQL data source"',
                db_name,
                host,
                exc_info=e,
            )
            return False
        return True

    async def create_elasticsearch_datasource(
        self,
        db_name: str,
        hosts: str | list[str],
        user: str | None = None,
        password: SecretStr | None = None,
        index: str | None = None,
        ssl_verify: bool = True,
    ) -> bool:
        """
        Create an Elasticsearch data source connection.

        Args:
            db_name: The name for the data source connection.
            hosts: Elasticsearch host(s) (e.g., "127.0.0.1:9200" or ["host1:9200", "host2:9200"]).
            user: Elasticsearch username.
            password: Elasticsearch password.
            index: Default Elasticsearch index.
            ssl_verify: Whether to verify SSL certificates.

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            # Build Elasticsearch connection parameters
            db = await self.get_database(db_name)
            if db:
                self.logger.warning(
                    "event=failed-to-create-elasticsearch-datasource "
                    "db_name=%s "
                    'message="Elasticsearch data source is already exist "',
                    db_name,
                )
                return False
            parameters = {
                "hosts": hosts if isinstance(hosts, str) else ",".join(hosts),
                "ssl_verify": ssl_verify,
            }

            if user:
                parameters["user"] = user
            if password:
                parameters["password"] = password.get_secret_value()
            if index:
                parameters["index"] = index

            # Create the data source using MindsDB SQL
            query = f"""
            CREATE DATABASE {db_name}
            WITH ENGINE = 'elasticsearch',
            PARAMETERS = {parameters};
            """

            self.logger.info(
                'event=elasticsearch-datasource-creation db_name=%s hosts=%s message="Creating Elasticsearch data source"',
                db_name,
                hosts,
            )

            await self.execute_query(query)
            self.logger.info(
                'event=elasticsearch-datasource-created db_name=%s message="Elasticsearch data source created successfully"',
                db_name,
            )
        except Exception as e:
            self.logger.exception(
                "event=elasticsearch-datasource-creation-failed "
                "db_name=%s "
                "hosts=%s "
                'message="Failed to create Elasticsearch data source"',
                db_name,
                hosts,
                exc_info=e,
            )
            return False
        return True

    async def test_datasource_connection(self, db_name: str) -> bool:
        """
        Test the connection to a data source.

        Args:
            db_name: The name of the data source to test.

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            database = await self.get_database(db_name)
            if not database:
                self.logger.error(
                    'event=datasource-test-failed db_name=%s message="Data source not found"',
                    db_name,
                )
                return False

            # Try a simple query to test the connection
            test_query = f"SELECT * FROM {db_name} LIMIT 1;"  # noqa: S608
            await self.execute_query(test_query)
            self.logger.info(
                'event=datasource-test-success db_name=%s message="Data source connection test successful"',
                db_name,
            )

        except Exception as e:
            self.logger.exception(
                'event=datasource-test-failed db_name=%s message="Data source connection test failed"',
                db_name,
                exc_info=e,
            )
            return False
        return True

    async def get_datasource_tables(self, db_name: str) -> list[str] | None:
        """
        Get list of tables from a data source.

        Args:
            db_name: The name of the data source.

        Returns:
            List of table names or None if failed.
        """
        try:
            database = await self.get_database(db_name)
            if not database:
                return None

            query = f"SHOW TABLES FROM {db_name};"
            result = await self.execute_query(query)

            if not result.empty:
                # Try different possible column names
                for col in ["table_name", "TABLE_NAME", "Tables_in_" + db_name, "name", "NAME"]:
                    if col in result.columns:
                        table_names = result[col].tolist()
                        self.logger.info(
                            'event=datasource-tables-retrieved db_name=%s table_count=%s "',
                            db_name,
                            len(table_names),
                        )
                        return table_names

            self.logger.warning(
                'event=datasource-no-tables db_name=%s message="No tables found in data source"',
                db_name,
            )

        except Exception as e:
            self.logger.exception(
                'event=datasource-tables-retrieval-failed db_name=%s message="Failed to retrieve tables from data source"',
                db_name,
                exc_info=e,
            )
            return None
        return []

    async def create_postgresql_vector_datasource(
        self,
        db_name: str,
        host: str,
        port: int = 15432,
        database: str = "postgres",
        user: str | None = None,
        password: SecretStr | None = None,
        schema: str | None = None,
        ssl_mode: str | None = None,
        similarity_metric: str = "cosine",
    ) -> bool:
        """
        Create a PostgreSQL vector database connection.

        Args:
            db_name: The name for the vector database connection.
            host: PostgreSQL host address.
            port: PostgreSQL port (default: 5432).
            database: PostgreSQL database name (default: "postgres").
            user: PostgreSQL username.
            password: PostgreSQL password.
            schema: PostgreSQL schema name.
            ssl_mode: SSL mode for connection.
            vector_extension: Vector extension to use (default: "pgvector").
            embedding_dimension: Dimension of embeddings.
            similarity_metric: Similarity metric (default: "cosine").

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            # Build PostgreSQL vector connection parameters
            is_existed_db = await self.get_database(db_name)
            if is_existed_db:
                self.logger.warning(
                    'event=postgresql-vector-datasource-creation-failed db_name=%s message="Database is already existed "',
                    db_name,
                )
                return False
            parameters = {
                "host": host,
                "port": port,
                "database": database,
                "similarity_metric": similarity_metric,
            }

            if user:
                parameters["user"] = user
            if password:
                parameters["password"] = password
            if schema:
                parameters["schema"] = schema
            if ssl_mode:
                parameters["sslmode"] = ssl_mode

            # Create the vector database using MindsDB SQL
            query = f"""
            CREATE DATABASE {db_name}
            WITH ENGINE = 'pgvector',
            PARAMETERS = {parameters};
            """

            self.logger.info(
                "event=postgresql-vector-datasource-creation "
                "db_name=%s "
                "host=%s "
                "port=%s "
                "database=%s "
                'message="Creating PostgreSQL vector database"',
                db_name,
                host,
                port,
                database,
            )

            await self.execute_query(query)
            self.logger.info(
                'event=postgresql-vector-datasource-created db_name=%s message="PostgreSQL vector database created successfully"',
                db_name,
            )

        except Exception as e:
            self.logger.exception(
                "event=postgresql-vector-datasource-creation-failed "
                "db_name=%s "
                "host=%s "
                'message="Failed to create PostgreSQL vector database"',
                db_name,
                host,
                exc_info=e,
            )
            return False
        return True

    async def create_chroma_vector_datasource(
        self,
        db_name: str,
        host: str,
        port: int,
        distance: str = "cosine",
    ) -> bool:
        """
        Create a Chroma vector database connection.

        Args:
            db_name: The name for the vector database connection.
            host: Chroma host address.
            port: Chroma port number.
            distance: Distance metric: l2/cosine/ip (default: cosine).

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            is_existed_db = await self.get_database(db_name)
            if is_existed_db:
                self.logger.warning(
                    'event=chroma-vector-datasource-creation-failed db_name=%s message="Database is already existed "',
                    db_name,
                )
                return False
            # Build Chroma connection parameters
            parameters = {
                "host": host,
                "port": port,
                "distance": distance,
            }

            # Create the vector database using MindsDB SQL
            query = f"""
            CREATE DATABASE {db_name}
            WITH ENGINE = 'chroma',
            PARAMETERS = {parameters};
            """

            self.logger.info(
                "event=chroma-vector-datasource-creation "
                "db_name=%s "
                "host=%s "
                "port=%s "
                "distance=%s "
                'message="Creating Chroma vector database"',
                db_name,
                host,
                port,
                distance,
            )

            await self.execute_query(query)
            self.logger.info(
                'event=chroma-vector-datasource-created db_name=%s message="Chroma vector database created successfully"',
                db_name,
            )

        except Exception as e:
            self.logger.exception(
                "event=chroma-vector-datasource-creation-failed "
                "db_name=%s "
                "host=%s "
                "port=%s "
                'message="Failed to create Chroma vector database"',
                db_name,
                host,
                port,
                exc_info=e,
            )
            return False
        return True

    async def delete_datasource(self, db_name: str) -> bool:
        try:
            db = await self.get_database(db_name)
            if db:
                query = f"DROP DATABASE {db_name};"
                await self.execute_query(query)
                self.logger.info(
                    'event=delete-datasource db_name=%s message="Delete datasource successfully"',
                    db_name,
                )
                return True
            self.logger.info(
                'event=delete-datasource db_name=%s message="Datasource does not exist"',
                db_name,
            )
        except Exception:
            self.logger.exception(
                'event=delete-datasource db_name=%s message="Failed to delete datasource"',
                db_name,
            )
        return False

    async def custom_query(self, query: str) -> pd.DataFrame:
        result = await asyncio.to_thread(self.server.query, query)
        return result.fetch()
