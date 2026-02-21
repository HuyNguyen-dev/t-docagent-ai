from abc import ABC, abstractmethod
from typing import ClassVar

from initializer import mindsdb_client
from schemas.datasource import (
    DataSourceConfig,
    DataSourceType,
    ElasticsearchDataSourceConfig,
    MongoDBDataSourceConfig,
    PostgreSQLDataSourceConfig,
)
from utils.logger.custom_logging import LoggerMixin


class DatasourceCreator(ABC, LoggerMixin):
    """Abstract base class for datasource creators."""

    @abstractmethod
    async def create_datasource(self, config: any) -> bool:
        """Abstract method to create a datasource."""


class PostgreSQLDatasourceCreator(DatasourceCreator):
    """Creator for PostgreSQL datasources."""

    async def create_datasource(self, config: PostgreSQLDataSourceConfig) -> bool:
        """Create a PostgreSQL data source connection."""
        self.logger.info(
            "event=postgresql-datasource-creation "
            "db_name=%s "
            "host=%s "
            "port=%s "
            "database=%s "
            'message="Creating PostgreSQL data source"',
            config.db_name,
            config.host,
            config.port,
            config.database,
        )

        success = await mindsdb_client.create_postgresql_datasource(
            db_name=config.db_name,
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.user,
            password=config.password,
            ssl_mode=config.ssl_mode,
        )

        if success:
            self.logger.info(
                'event=postgresql-datasource-created db_name=%s message="PostgreSQL data source created successfully"',
                config.db_name,
            )
        else:
            self.logger.error(
                'event=postgresql-datasource-creation-failed db_name=%s message="Failed to create PostgreSQL data source"',
                config.db_name,
            )

        return success


class MongoDBDatasourceCreator(DatasourceCreator):
    """Creator for MongoDB datasources."""

    async def create_datasource(self, config: MongoDBDataSourceConfig) -> bool:
        """Create a MongoDB data source connection."""
        self.logger.info(
            'event=mongodb-datasource-creation db_name=%s host=%s port=%s message="Creating MongoDB data source"',
            config.db_name,
            config.host,
            config.port,
        )

        success = await mindsdb_client.create_mongodb_datasource(
            db_name=config.db_name,
            host=config.host,
            port=config.port,
            username=config.username,
            password=config.password,
            database=config.database,
            auth_mechanism=config.auth_mechanism,
        )

        if success:
            self.logger.info(
                'event=mongodb-datasource-created db_name=%s message="MongoDB data source created successfully"',
                config.db_name,
            )
        else:
            self.logger.error(
                'event=mongodb-datasource-creation-failed db_name=%s message="Failed to create MongoDB data source"',
                config.db_name,
            )

        return success


class ElasticsearchDatasourceCreator(DatasourceCreator):
    """Creator for Elasticsearch datasources."""

    async def create_datasource(self, config: ElasticsearchDataSourceConfig) -> bool:
        """Create an Elasticsearch data source connection."""
        self.logger.info(
            'event=elasticsearch-datasource-creation db_name=%s hosts=%s message="Creating Elasticsearch data source"',
            config.db_name,
            config.hosts,
        )

        success = await mindsdb_client.create_elasticsearch_datasource(
            db_name=config.db_name,
            hosts=config.hosts,
            user=config.user,
            password=config.password,
            index=config.index,
            ssl_verify=config.ssl_verify,
        )

        if success:
            self.logger.info(
                'event=elasticsearch-datasource-created db_name=%s message="Elasticsearch data source created successfully"',
                config.db_name,
            )
        else:
            self.logger.error(
                'event=elasticsearch-datasource-creation-failed db_name=%s message="Failed to create Elasticsearch data source"',
                config.db_name,
            )

        return success


class DatasourceFactory:
    """Factory class for creating datasource creators."""

    _creators: ClassVar[dict] = {
        DataSourceType.POSTGRESQL: PostgreSQLDatasourceCreator,
        DataSourceType.MONGODB: MongoDBDatasourceCreator,
        DataSourceType.ELASTICSEARCH: ElasticsearchDatasourceCreator,
    }

    @classmethod
    def create_creator(cls, ds_type: DataSourceType) -> DatasourceCreator | None:
        """Create a datasource creator based on the datasource type."""
        creator_class = cls._creators.get(ds_type)
        if not creator_class:
            return None
        return creator_class()


class DatasourceHandler(LoggerMixin):
    """Handler for data source operations."""

    async def create(self, ds_config: DataSourceConfig) -> bool:
        """Create a data source based on the configuration type using factory pattern."""
        config = ds_config.config
        ds_type = ds_config.ds_type

        # Use factory to create the appropriate creator
        creator = DatasourceFactory.create_creator(ds_type)
        if creator is None:
            self.logger.error(
                'event=datasource-creation-error ds_type=%s message="Unsupported to this vector type"',
                ds_config.ds_type,
            )
            return False
        return await creator.create_datasource(config)

    async def test_connection(self, db_name: str) -> bool:
        """Test the connection to a data source."""
        self.logger.info(
            'event=datasource-test db_name=%s message="Testing data source connection"',
            db_name,
        )

        success = await mindsdb_client.test_datasource_connection(db_name)

        if success:
            self.logger.info(
                'event=datasource-test-success db_name=%s message="Data source connection test successful"',
                db_name,
            )
        else:
            self.logger.error(
                'event=datasource-test-failed db_name=%s message="Data source connection test failed"',
                db_name,
            )

        return success

    async def list_all(self) -> list[str] | None:
        """List all available data sources."""
        self.logger.info('event=datasource-list message="Listing data sources"')

        datasources = await mindsdb_client.list_database()

        if datasources:
            self.logger.info(
                'event=datasource-list-success count=%s message="Data sources listed successfully"',
                len(datasources),
            )
        else:
            self.logger.info(
                'event=datasource-list-empty message="No data sources found"',
            )

        return datasources

    async def get_tables(self, db_name: str) -> list[str] | None:
        """Get list of tables from a data source."""
        self.logger.info(
            'event=datasource-tables db_name=%s message="Getting tables from data source"',
            db_name,
        )

        table_names = await mindsdb_client.get_datasource_tables(db_name)
        if table_names:
            self.logger.info(
                'event=datasource-tables-success db_name=%s count=%s message="Tables retrieved successfully"',
                db_name,
                len(table_names),
            )
        else:
            self.logger.warning(
                'event=datasource-tables-empty db_name=%s message="No tables found in data source"',
                db_name,
            )

        return table_names
