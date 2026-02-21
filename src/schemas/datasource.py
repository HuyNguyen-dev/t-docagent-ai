from pydantic import BaseModel, Field, SecretStr

from utils.enums import DataSourceType, VectorType


class BaseDataSourceConfig(BaseModel):
    """Base configuration for data source connections."""

    db_name: str = Field(..., description="The name for the data source connection")
    host: str = Field(..., description="Database host address")
    port: int = Field(..., description="Database port number")
    user: str | None = Field(None, description="Database username")
    password: SecretStr | None = Field(None, description="Database password")


class PostgreSQLDataSourceConfig(BaseDataSourceConfig):
    """Configuration for PostgreSQL data source connection."""

    port: int = Field(5432, description="PostgreSQL port (default: 5432)")
    database: str = Field("postgres", description="PostgreSQL database name (default: 'postgres')")
    ssl_mode: str | None = Field(None, description="SSL mode for connection")


class MongoDBDataSourceConfig(BaseModel):
    """Configuration for MongoDB data source connection."""

    db_name: str = Field(..., description="The name for the data source connection")
    host: str = Field(..., description="MongoDB host address")
    port: int = Field(27017, description="MongoDB port (default: 27017)")
    username: str | None = Field(None, description="MongoDB username")
    password: SecretStr | None = Field(None, description="MongoDB password")
    database: str | None = Field(None, description="MongoDB database name")
    auth_mechanism: str = Field("DEFAULT", description="Authentication mechanism (default: 'DEFAULT')")


class ElasticsearchDataSourceConfig(BaseModel):
    """Configuration for Elasticsearch data source connection."""

    db_name: str = Field(..., description="The name for the data source connection")
    hosts: str = Field(..., description="Elasticsearch host(s) (e.g., '127.0.0.1:9200' or 'host1:9200,host2:9200')")
    user: str | None = Field(None, description="Elasticsearch username")
    password: SecretStr | None = Field(None, description="Elasticsearch password")
    index: str | None = Field(None, description="Default Elasticsearch index")
    ssl_verify: bool = Field(True, description="Whether to verify SSL certificates")


class BaseVectorConfig(BaseModel):
    """Base configuration for vector database connections."""

    db_name: str = Field(..., description="The name for the vector database connection")
    table_name: str = Field(..., description="The table name from the vector database connection")


class DataSourceConfig(BaseModel):
    """Union type for different data source configurations."""

    ds_type: DataSourceType = Field(..., description="Type of data source")
    config: PostgreSQLDataSourceConfig | MongoDBDataSourceConfig | ElasticsearchDataSourceConfig = Field(
        ...,
        description="Configuration for the data source",
    )


class DatasourceTestRequest(BaseModel):
    """Request model for testing data source connection."""

    db_name: str = Field(..., description="The name of the data source to test")


class DatasourceTablesResponse(BaseModel):
    """Response model for listing data source tables."""

    db_name: str = Field(..., description="The name of the data source")
    tables: list[str] = Field(..., description="List of table names")


class TableSchemaResponse(BaseModel):
    """Response model for table schema information."""

    table_name: str = Field(..., description="The name of the table")
    columns: list[dict] = Field(..., description="List of column information")


class CustomQueryRequest(BaseModel):
    """Request model for executing custom queries."""

    db_name: str = Field(..., description="The name of the data source")
    query: str = Field(..., description="SQL query to execute")


class DatasourceInfo(BaseModel):
    """Information about a data source."""

    name: str = Field(..., description="Data source name")
    engine: str = Field(..., description="Database engine type")
    status: str = Field(..., description="Connection status")


class PostgreSQLVectorConfig(BaseVectorConfig):
    """Configuration for PostgreSQL vector database connection."""

    host: str = Field(None, description="PostgreSQL host address")
    port: int = Field("5432", description="PostgreSQL port (default: 5432)")
    database: str = Field(None, description="PostgreSQL database name")
    user: str | None = Field(None, description="PostgreSQL username")
    password: SecretStr | None = Field(None, description="PostgreSQL password")
    ssl_mode: str | None = Field(None, description="SSL mode for connection")
    similarity_metric: str = Field("cosine", description="Similarity metric (default: 'cosine')")


class MilvusVectorConfig(BaseVectorConfig):
    """Configuration for Milvus vector database connection."""

    uri: str = Field("./milvus_local.db", description="Milvus URI (default: './milvus_local.db')")
    token: str = Field("", description="Milvus authentication token")
    create_embedding_dim: int = Field(3, description="Embedding dimension for creation (default: 3)")
    create_auto_id: bool = Field(True, description="Auto-generate IDs (default: True)")


class PineconeVectorConfig(BaseVectorConfig):
    """Configuration for Pinecone vector database connection."""

    api_key: str = Field(..., description="Pinecone API key")


class ChromaVectorConfig(BaseVectorConfig):
    """Configuration for Chroma vector database connection."""

    host: str = Field(..., description="Chroma host address")
    port: int = Field(..., description="Chroma port number")
    distance: str = Field("cosine", description="Distance metric: l2/cosine/ip (default: cosine)")


class VectorDBConfig(BaseModel):
    """Configuration for vector database connections."""

    ds_type: VectorType = Field(..., description="Type of vector database")
    config: PostgreSQLVectorConfig | ChromaVectorConfig = Field(
        ...,
        description="Configuration for the vector database",
    )
