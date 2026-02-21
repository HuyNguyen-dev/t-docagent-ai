from typing import ClassVar

from initializer import mindsdb_client
from schemas.datasource import ChromaVectorConfig, PostgreSQLVectorConfig
from services.knowledge_base.base import VectorDBCreator
from utils.enums import VectorType


class PostgreSQLVectorDBCreator(VectorDBCreator):
    """Creator for PostgreSQL vector databases."""

    async def create_vector_datasource(self, config: PostgreSQLVectorConfig) -> bool:
        """Create a PostgreSQL vector database connection."""
        self.logger.info(
            "event=postgresql-vector-datasource-creation "
            "db_name=%s "
            "host=%s "
            "port=%s "
            "database=%s "
            'message="Creating PostgreSQL vector database"',
            config.db_name,
            config.host,
            config.port,
            config.database,
        )

        success = await mindsdb_client.create_postgresql_vector_datasource(
            db_name=config.db_name,
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.user,
            password=config.password if isinstance(config.password, str) else config.password.get_secret_value(),
            ssl_mode=config.ssl_mode,
            similarity_metric=config.similarity_metric,
        )

        if success:
            self.logger.info(
                'event=postgresql-vector-datasource-created db_name=%s message="PostgreSQL vector database created successfully"',
                config.db_name,
            )
        else:
            self.logger.error(
                "event=postgresql-vector-datasource-creation-failed "
                "db_name=%s "
                'message="Failed to create PostgreSQL vector database"',
                config.db_name,
            )

        return success


class ChromaVectorDBCreator(VectorDBCreator):
    """Creator for Chroma vector databases."""

    async def create_vector_datasource(self, config: ChromaVectorConfig) -> bool:
        """Create a Chroma vector database connection."""
        self.logger.info(
            'event=chroma-vector-datasource-creation db_name=%s port=%s distance=%s message="Creating Chroma vector database"',
            config.db_name,
            config.port,
            config.distance,
        )

        success = await mindsdb_client.create_chroma_vector_datasource(
            db_name=config.db_name,
            host=config.host,
            port=config.port,
            distance=config.distance,
        )

        if success:
            self.logger.info(
                'event=chroma-vector-datasource-created db_name=%s message="Chroma vector database created successfully"',
                config.db_name,
            )
        else:
            self.logger.error(
                'event=chroma-vector-datasource-creation-failed db_name=%s message="Failed to create Chroma vector database"',
                config.db_name,
            )

        return success


class VectorDBFactory:
    """Factory class for creating vector database creators."""

    _creators: ClassVar[dict] = {
        VectorType.POSTGRESQL: PostgreSQLVectorDBCreator,
        VectorType.CHROMA: ChromaVectorDBCreator,
    }

    @classmethod
    def create_creator(cls, vector_type: VectorType) -> VectorDBCreator | None:
        """Create a vector database creator based on the vector type."""
        creator_class = cls._creators.get(vector_type)
        if not creator_class:
            return None
        return creator_class()
