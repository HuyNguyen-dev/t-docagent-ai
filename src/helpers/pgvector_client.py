import re

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from config import settings
from utils.logger.custom_logging import LoggerMixin

# SQLAlchemy Base
Base = declarative_base()


class PGVectorClient(LoggerMixin):
    """Async Client for interacting with PostgreSQL + pgvector"""

    def __init__(self) -> None:
        super().__init__()
        self.engine = None
        self.session_local = None
        self._initialize_connection()

    def _initialize_connection(self) -> None:
        """Initialize Async SQLAlchemy engine and session"""
        try:
            self.engine = create_async_engine(
                settings.pgvector_dsn,
                poolclass=NullPool,
                echo=False,
                future=True,
            )

            self.session_local = sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )

            self.logger.info("event=async-engine-initialized message='Async engine initialized'")
        except Exception:
            self.logger.exception("event=async-engine-init-failed message='Failed to init async engine'")
            raise

    async def _is_valid_table_name(self, table_name: str) -> bool:
        """Validate table name to prevent SQL injection"""
        pattern = r"^[a-zA-Z_][a-zA-Z0-9_-]*$"
        return bool(re.match(pattern, table_name)) and len(table_name) <= 63

    async def table_exists(self, table_name: str) -> bool:
        """Check if a table exists asynchronously"""
        if not await self._is_valid_table_name(table_name):
            return False

        query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = :table_name
            )
        """)

        async with self.engine.connect() as conn:
            result = await conn.execute(query, {"table_name": table_name})
            return result.scalar()

    async def create_vector_table(self, table_name: str, vector_dimension: int) -> bool:
        try:
            create_extension_sql = "CREATE EXTENSION IF NOT EXISTS vector"
            create_textsearch_sql = "CREATE EXTENSION IF NOT EXISTS pg_trgm"

            create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS "{table_name}" (
                    id TEXT PRIMARY KEY,
                    content TEXT,
                    metadata JSONB,
                    embeddings vector({vector_dimension}),
                    -- cột tsvector cho BM25 search
                    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """

            # Index cho BM25
            create_index_sql = f"""
                CREATE INDEX IF NOT EXISTS {table_name}_tsv_idx
                ON "{table_name}" USING GIN (tsv)
            """

            async with self.engine.begin() as conn:
                await conn.execute(text(create_extension_sql))
                await conn.execute(text(create_textsearch_sql))
                await conn.execute(text(create_table_sql))
                await conn.execute(text(create_index_sql))

            self.logger.info(
                'event=vector-table-created message="Vector + BM25 table created" table_name=%s vector_dimension=%d',
                table_name,
                vector_dimension,
            )
        except Exception:
            self.logger.exception(
                'event=vector-table-creation-failed message="Failed to create vector + BM25 table" table_name=%s',
                table_name,
            )
            return False
        return True

    async def drop_table(self, table_name: str) -> bool:
        """Drop a table safely"""
        try:
            if not await self._is_valid_table_name(table_name):
                return False

            drop_sql = f'DROP TABLE IF EXISTS "{table_name}"'
            async with self.engine.begin() as conn:
                await conn.execute(text(drop_sql))

        except Exception:
            self.logger.exception("event=drop-table-failed table=%s", table_name)
            return False
        return True

    async def delete_chunks_by_metadata(self, table_name: str, metadata_key: str, metadata_value: str) -> int:
        """Delete rows by metadata key-value"""
        try:
            if not await self._is_valid_table_name(table_name):
                return -1

            delete_sql = text(f"""
                DELETE FROM "{table_name}"
                WHERE metadata->>:key = :val
            """)  # noqa: S608

            async with self.engine.begin() as conn:
                result = await conn.execute(delete_sql, {"key": metadata_key, "val": metadata_value})
                return result.rowcount
        except Exception:
            self.logger.exception("event=delete-chunks-failed table=%s", table_name)
            return -1

    async def delete_chunks_by_ids(self, table_name: str, chunk_ids: list[str]) -> int:
        """Delete rows by list of ids"""
        try:
            if not await self._is_valid_table_name(table_name):
                return -1

            async with self.engine.begin() as conn:
                ids_str = ", ".join([f":id{i}" for i in range(len(chunk_ids))])
                delete_sql = text(f"DELETE FROM {table_name} WHERE id IN ({ids_str})")  # noqa: S608

                params = {f"id{i}": val for i, val in enumerate(chunk_ids)}
                result = await conn.execute(delete_sql, params)

                return result.rowcount or 0

        except Exception:
            self.logger.exception("event=delete-chunks-failed table=%s", table_name)
            return -1

    async def get_table_size(self, table_name: str) -> dict | None:
        """Get row count and size info"""
        try:
            if not await self._is_valid_table_name(table_name):
                return None

            size_sql = text("""
                SELECT
                    pg_size_pretty(pg_total_relation_size(:t)) as total_size,
                    pg_size_pretty(pg_relation_size(:t)) as table_size
            """)

            count_sql = text(f"""SELECT COUNT(*) as row_count FROM "{table_name}" """)  # noqa: S608

            async with self.engine.connect() as conn:
                result = await conn.execute(size_sql, {"t": table_name})
                size_info = dict(result.mappings().first())

                count_res = await conn.execute(count_sql)
                size_info["row_count"] = count_res.scalar()

            size_info["table_name"] = table_name

        except Exception:
            self.logger.exception("event=get-table-size-failed table=%s", table_name)
            return None
        return size_info

    async def search_by_keyword(
        self,
        table_name: str,
        keyword: str,
        limit: int = 10,
        search_in: str = "content",
    ) -> pd.DataFrame | None:
        """Search with ILIKE for full phrase + individual words"""
        try:
            if not await self._is_valid_table_name(table_name):
                return None

            keyword = keyword.strip()
            if not keyword:
                query = text(f"""
                    SELECT id, content, metadata, created_at, updated_at
                    FROM "{table_name}"
                    ORDER BY updated_at DESC
                    LIMIT :limit
                """)  # noqa: S608
                async with self.engine.connect() as conn:
                    result = await conn.execute(query, {"limit": limit})
                    rows = [dict(r) for r in result.mappings()]
                return pd.DataFrame(rows)

            words = [keyword]
            words.extend([w for w in keyword.split() if w.strip()])

            where_clauses = [f"{search_in} ILIKE :kw{i}" for i in range(len(words))]
            where_sql = " OR ".join(where_clauses)

            params = {f"kw{i}": f"%{w}%" for i, w in enumerate(words)}
            params["limit"] = limit

            # Tạo query SQL
            query = text(f"""
                SELECT id, content, metadata, created_at, updated_at
                FROM "{table_name}"
                WHERE {where_sql}
                ORDER BY updated_at DESC
                LIMIT :limit
            """)  # noqa: S608

            async with self.engine.connect() as conn:
                result = await conn.execute(query, params)
                rows = [dict(r) for r in result.mappings()]

            return pd.DataFrame(rows)

        except Exception:
            self.logger.exception("event=search-failed table=%s", table_name)
            return None

    async def cleanup_orphaned_tables(self, valid_table_names: list[str]) -> dict:
        """Drop all orphaned tables ending with '_vector'"""
        try:
            list_sql = text("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename LIKE '%_vector%'
            """)

            async with self.engine.connect() as conn:
                result = await conn.execute(list_sql)
                all_tables = [r[0] for r in result]

            orphaned = [t for t in all_tables if t not in valid_table_names]
            dropped = []
            errors = []

            for t in orphaned:
                if await self.drop_table(t):
                    dropped.append(t)
                else:
                    errors.append(t)

            return {
                "total_tables": len(all_tables),
                "orphaned": orphaned,
                "dropped": dropped,
                "errors": errors,
            }
        except Exception as e:
            self.logger.exception("event=cleanup-failed")
            return {"error": str(e)}

    async def get_database_health(self) -> dict:
        """Get database health info"""
        try:
            health = {
                "status": "healthy",
                "tables": [],
                "errors": [],
            }

            list_sql = text("""
                SELECT
                    tablename,
                    pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename LIKE '%_vector%'
            """)

            async with self.engine.connect() as conn:
                result = await conn.execute(list_sql)
                tables = [dict(r) for r in result.mappings()]

            for t in tables:
                size_info = await self.get_table_size(t["tablename"])
                if size_info:
                    t.update(size_info)
                health["tables"].append(t)

            if not tables:
                health["status"] = "warning"
                health["errors"].append("No vector tables found")

        except Exception as e:
            self.logger.exception("event=health-check-failed")
            return {"status": "error", "error": str(e)}
        return health

    async def hybrid_search_alpha(
        self,
        table_name: str,
        query_text: str,
        query_vector: list[float],
        alpha: float,
        limit: int = 10,
        enable_reranking: bool = False,
        rerank_candidates: int | None = None,
    ) -> pd.DataFrame | None:
        """
        Hybrid search: BM25 (full-text) + vector similarity with optional reranking.

        Args:
            table_name: Name of the vector table
            query_text: Text query for BM25 search
            query_vector: Query embedding vector for similarity calculation
            alpha: Weight for BM25 vs vector (1.0 = only BM25, 0.0 = only vector)
            limit: Number of final results to return
            enable_reranking: Whether to apply vector-based reranking
            rerank_candidates: Number of candidates to retrieve before reranking (default: limit * 3)

        Returns:
            DataFrame with search results, optionally reranked based on vector similarity
        """
        try:
            if not await self._is_valid_table_name(table_name):
                return None

            # Determine how many candidates to retrieve for reranking
            search_limit = limit
            if enable_reranking:
                search_limit = rerank_candidates or (limit * 3)

            sql = text(f"""
                WITH bm25 AS (
                    SELECT id, ts_rank_cd(tsv, q) AS bm25_score
                    FROM "{table_name}", to_tsquery('simple', :q) q
                ),
                vec AS (
                    SELECT id, 1 - (embeddings <=> :vec) AS vec_score
                    FROM "{table_name}"
                )
                SELECT d.id, d.content, d.metadata, d.embeddings,
                    COALESCE(b.bm25_score, 0) AS bm25_score,
                    COALESCE(v.vec_score, 0) AS vec_score,
                    (:alpha * COALESCE(b.bm25_score, 0) +
                        (1 - :alpha) * COALESCE(v.vec_score, 0)) AS hybrid_score
                FROM "{table_name}" d
                LEFT JOIN bm25 b ON d.id = b.id
                LEFT JOIN vec v ON d.id = v.id
                ORDER BY hybrid_score DESC
                LIMIT :search_limit;
            """)  # noqa: S608

            # Convert query_vector to string format for PostgreSQL/pgvector
            vec_str = f"[{','.join(map(str, query_vector))}]"
            query_text = await self._safe_tsquery_text(query_text)
            async with self.engine.connect() as conn:
                result = await conn.execute(
                    sql,
                    {
                        "q": query_text.replace(" ", " & "),
                        "vec": vec_str,
                        "alpha": alpha,
                        "search_limit": search_limit,
                    },
                )
                rows = [dict(r) for r in result.mappings()]

            results_df = pd.DataFrame(rows)

            # Apply vector-based reranking if enabled
            if enable_reranking and not results_df.empty:
                results_df = await self._apply_vector_reranking(
                    results_df,
                    query_vector,
                    limit,
                    alpha,
                )

        except Exception:
            self.logger.exception("event=hybrid-search-alpha-failed table=%s", table_name)
            return None
        return results_df

    async def _apply_vector_reranking(
        self,
        results_df: pd.DataFrame,
        query_vector: list[float],
        limit: int,
        rerank_weight: float,
    ) -> pd.DataFrame:
        """
        Apply vector-based reranking to search results.

        Args:
            results_df: DataFrame with search results including embeddings
            query_vector: Query vector for similarity calculation
            limit: Number of final results to return
            alpha: Original hybrid search weight
            rerank_weight: Weight for rerank score vs original score

        Returns:
            DataFrame with reranked results
        """
        try:
            import numpy as np

            if results_df.empty or "embeddings" not in results_df.columns:
                return results_df.head(limit)

            # Handle case where query_vector might be a string representation of array
            if isinstance(query_vector, str):
                # Parse string representation like "[0.1, 0.2, 0.3]"
                query_vector = np.fromstring(query_vector.strip("[]"), sep=",", dtype=np.float32)
            else:
                query_vector = np.array(query_vector, dtype=np.float32)
            rerank_scores = []

            for _, row in results_df.iterrows():
                try:
                    # Parse embeddings (assuming they're stored as arrays)
                    doc_embedding = row["embeddings"]
                    if isinstance(doc_embedding, str):
                        # If stored as string, parse it
                        doc_embedding = np.fromstring(doc_embedding.strip("[]"), sep=",", dtype=np.float32)
                    elif isinstance(doc_embedding, list):
                        doc_embedding = np.array(doc_embedding, dtype=np.float32)
                    else:
                        # If it's already a numpy array or similar
                        doc_embedding = np.array(doc_embedding, dtype=np.float32)

                    # Calculate cosine similarity
                    dot_product = np.dot(query_vector, doc_embedding)
                    query_norm = np.linalg.norm(query_vector)
                    doc_norm = np.linalg.norm(doc_embedding)

                    if query_norm > 0 and doc_norm > 0:
                        cosine_similarity = dot_product / (query_norm * doc_norm)
                        # Convert to 0-1 scale (from -1 to 1)
                        rerank_score = (cosine_similarity + 1) / 2
                    else:
                        rerank_score = 0.0

                    rerank_scores.append(rerank_score)

                except Exception as e:
                    self.logger.warning(
                        "event=rerank-score-calculation-failed row_id=%s error=%s",
                        row.get("id", "unknown"),
                        str(e),
                    )
                    rerank_scores.append(0.0)

            # Add rerank scores to dataframe
            results_df = results_df.copy()
            results_df["rerank_score"] = rerank_scores

            # Calculate final scores: weighted combination
            results_df["final_score"] = (1 - rerank_weight) * results_df["hybrid_score"] + rerank_weight * results_df[
                "rerank_score"
            ]

            # Sort by final score and return top results
            results_df = results_df.sort_values("final_score", ascending=False).head(limit)

            # Remove embeddings column to reduce response size (optional)
            if "embeddings" in results_df.columns:
                results_df = results_df.drop("embeddings", axis=1)

            self.logger.info(
                "event=vector-reranking-applied candidates=%d final_results=%d avg_rerank_score=%.3f rerank_weight=%.2f",
                len(rerank_scores),
                len(results_df),
                np.mean(rerank_scores),
                rerank_weight,
            )

        except Exception:
            self.logger.exception(
                "event=vector-reranking-failed ",
            )
            # Fallback to original results
            return results_df.head(limit)
        return results_df

    async def search_with_filter_and_paging(
        self,
        table_name: str,
        keyword: str,
        metadata_filter: dict | None = None,
        page: int = 1,
        page_size: int = 10,
        search_in: str = "content",
    ) -> dict | None:
        rows = []
        try:
            if not await self._is_valid_table_name(table_name):
                return None

            offset = (page - 1) * page_size

            where_conditions = []
            params = {"limit": page_size, "offset": offset}

            if keyword and keyword.strip():
                if search_in == "content":
                    where_conditions.append("content ILIKE :keyword")
                    params["keyword"] = f"%{keyword}%"
                elif search_in == "metadata":
                    where_conditions.append("metadata::text ILIKE :keyword")
                    params["keyword"] = f"%{keyword}%"

            if metadata_filter:
                for key, value in metadata_filter.items():
                    where_conditions.append(f"metadata->>:filter_key_{key} = :filter_value_{key}")
                    params[f"filter_key_{key}"] = key
                    params[f"filter_value_{key}"] = str(value)

            where_clause = ""
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)

            count_sql = text(f"""
                SELECT COUNT(*) as total_count
                FROM "{table_name}"
                {where_clause}
            """)  # noqa: S608

            main_sql = text(f"""
                SELECT id, content, metadata, created_at
                FROM "{table_name}"
                {where_clause}
                ORDER BY (metadata->>'index')::int
                LIMIT :limit OFFSET :offset
            """)  # noqa: S608

            async with self.engine.connect() as conn:
                count_result = await conn.execute(count_sql, params)
                total_count = count_result.scalar() or 0

                main_result = await conn.execute(main_sql, params)
                rows = [dict(r) for r in main_result.mappings()]

            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0

        except Exception:
            self.logger.exception("event=search-with-filter-and-paging-failed table=%s", table_name)
            return None
        return {
            "items": rows,
            "metadata": {
                "page": page,
                "page_size": page_size,
                "total_items": total_count,
                "total_pages": total_pages,
            },
        }

    async def _safe_tsquery_text(self, text: str) -> str:
        text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return " ".join(text.split())
