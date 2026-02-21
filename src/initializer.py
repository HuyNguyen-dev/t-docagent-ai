import asyncio
from typing import Literal

import httpx
from miniopy_async import Minio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import CollectionInvalid
from redis.asyncio import ConnectionPool, Redis
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.retry import Retry

from config import settings
from handlers.training_state_manager import TrainingStatusManager
from helpers.pubsub import RedisPubSubManager
from utils.constants import (
    HEARTBEAT_INTERVAL,
    HTTPX_TIMEOUT,
    NUM_RETRIES,
    SOCKET_CONNECT_TIMEOUT,
    SOCKET_TIMEOUT,
)


class LoggerInstance:
    def __new__(cls) -> "LoggerInstance":
        from utils.logger.custom_logging import LogHandler

        return LogHandler()


# instance creation
logger_instance = LoggerInstance()
logger = logger_instance.get_logger(__name__)


async def init_database(client: AsyncIOMotorClient, is_init_collection: bool = True) -> bool:
    from beanie import init_beanie

    from models import (
        ActionPackage,
        Agent,
        APIAuditLog,
        Conversation,
        DocumentContent,
        DocumentFormat,
        DocumentType,
        DocumentWorkItem,
        KBDocument,
        KnowledgeBase,
        LLMConfiguration,
        Message,
        Role,
        RunBook,
        Tag,
        Token,
        User,
    )
    from settings.mongodb.db_collections import COLLECTION_LIST

    default_database: AsyncIOMotorDatabase = client.get_default_database(default=settings.MONGODB_DATABASE_NAME)

    async def create_collection_with_validator(
        collection_name: str,
        validator: dict | None = None,
        validation_level: Literal["off", "strict", "moderate"] = "strict",
        validation_action: Literal["error", "warn"] = "error",
    ) -> bool:
        try:
            await default_database.create_collection(collection_name)
            if validator is not None:
                await default_database.command(
                    {
                        "collMod": collection_name,
                        "validator": validator,
                        "validationLevel": validation_level,
                        "validationAction": validation_action,
                    },
                )
        except CollectionInvalid as exc:
            logger.warning(
                'event=collection-existing collection=%s message="%s"',
                collection_name,
                str(exc),
            )
        except Exception:
            logger.exception("event=create-collection-failure")
            return False
        return True

    results = []
    if is_init_collection:
        try:
            async with asyncio.TaskGroup() as task_group:
                tasks = [
                    task_group.create_task(
                        create_collection_with_validator(
                            collection_name=collection["collection_name"],
                            validator=collection["validator"],
                        ),
                    )
                    for collection in COLLECTION_LIST
                ]

            logger.info(
                "event=init-collections-success count=%d",
                len(COLLECTION_LIST),
            )
            results = [task.result() for task in tasks]
        except* Exception as eg:
            # Handle ExceptionGroup from TaskGroup or other exceptions
            for exc in eg.exceptions if isinstance(eg, BaseExceptionGroup) else [eg]:
                logger.exception(
                    'event=init-collection-failed error="%s" message="Failed to initialize database collection"',
                    str(exc),
                )
                results.append(False)

    await init_beanie(
        database=default_database,
        document_models=[
            Agent,
            APIAuditLog,
            Conversation,
            DocumentType,
            DocumentFormat,
            DocumentWorkItem,
            DocumentContent,
            ActionPackage,
            RunBook,
            Message,
            KnowledgeBase,
            LLMConfiguration,
            User,
            KBDocument,
            Tag,
            Token,
            Role,
        ],
    )
    return all(results)


minio_client = Minio(
    endpoint=settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY.get_secret_value() if settings.MINIO_ACCESS_KEY else None,
    secret_key=settings.MINIO_SECRET_KEY.get_secret_value() if settings.MINIO_SECRET_KEY else None,
    secure=False,
)

# REDIS
retry_config = Retry(
    retries=NUM_RETRIES,
    supported_errors=(RedisConnectionError, RedisTimeoutError),
    backoff=ExponentialBackoff(),
)

pool = ConnectionPool(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD.get_secret_value() if settings.REDIS_PASSWORD else None,
    decode_responses=True,
    retry=retry_config,
    socket_timeout=SOCKET_TIMEOUT,
    socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
)

redis = Redis(
    connection_pool=pool,
    retry=retry_config,
    retry_on_timeout=True,
    socket_keepalive=True,
    health_check_interval=HEARTBEAT_INTERVAL,
)

redis_pubsub_manager = RedisPubSubManager(redis)

training_status_manager = TrainingStatusManager(redis=redis, redis_pubsub_manager=redis_pubsub_manager)

mindsdb_client = None
pg_client = None

if settings.ENABLE_KNOWNLEDEGE_BASE:
    from helpers.mindsdb_client import MindsDBClient
    from helpers.pgvector_client import PGVectorClient

    pg_client = PGVectorClient()
    http_client = httpx.AsyncClient(timeout=HTTPX_TIMEOUT)
    mindsdb_client = MindsDBClient(pg_client, http_client)


async def create_handlers() -> dict:
    from handlers.action_package import ActionPackageHandler
    from handlers.agent import AgentHandler
    from handlers.agents.conversation import ConversationalAgentHandler
    from handlers.agents.worker import WorkerAgentHandler
    from handlers.audit import AuditHandler
    from handlers.basic_agent import BasicAgent
    from handlers.conversation import ConversationHandler
    from handlers.document_format import DocumentFormatHandler
    from handlers.document_intelligence import DocumentIntelligenceHandler
    from handlers.document_type import DocumentTypeHandler
    from handlers.document_work_item import DocumentWorkItemHandler
    from handlers.llm_configuration import LLMConfigurationHandler
    from handlers.onboarding import OnboardingHandler
    from handlers.runbook import RunbookHandler
    from handlers.scope import ScopeHandler
    from handlers.user import RoleHandler, UserHandler

    client = AsyncIOMotorClient(str(settings.MONGODB_DSN))
    is_db_success = await init_database(client=client)
    if is_db_success:
        logger.info(
            'event=init-db-database-success message="Initializing Database and all Collections successfully."',
        )
    else:
        logger.critical(
            "event=init-db-database-failure "
            'message="An error occurred. When initializing the Database and Collections, '
            'the process has not been completed. Please check the settings carefully"',
        )

    ap_handler = ActionPackageHandler()
    agent_handler = AgentHandler()
    audit_handler = AuditHandler()
    conv_handler = ConversationHandler()
    conv_agent_handler = ConversationalAgentHandler()
    llm_handler = LLMConfigurationHandler()
    df_handler = DocumentFormatHandler()
    dt_handler = DocumentTypeHandler()
    di_handler = await DocumentIntelligenceHandler.create()
    dwi_handler = DocumentWorkItemHandler()
    runbook_handler = RunbookHandler()
    sample_agent = BasicAgent()
    worker_agent_handler = WorkerAgentHandler()
    onboarding_handler = OnboardingHandler()
    scope_handler = ScopeHandler()
    user_handler = UserHandler()
    role_handler = RoleHandler()
    kb_handler = None
    data_source_handler = None

    if settings.ENABLE_KNOWNLEDEGE_BASE:
        from handlers.datasource import DatasourceHandler
        from handlers.knowledge_base import KnowledgeBaseHandler

        kb_handler = KnowledgeBaseHandler(llm_handler=llm_handler)
        data_source_handler = DatasourceHandler()

    return {
        "ap_handler": ap_handler,
        "audit_handler": audit_handler,
        "agent_handler": agent_handler,
        "conv_handler": conv_handler,
        "conv_agent_handler": conv_agent_handler,
        "df_handler": df_handler,
        "di_handler": di_handler,
        "dt_handler": dt_handler,
        "dwi_handler": dwi_handler,
        "llm_handler": llm_handler,
        "runbook_handler": runbook_handler,
        "sample_agent": sample_agent,
        "worker_agent_handler": worker_agent_handler,
        "data_source_handler": data_source_handler,
        "kb_handler": kb_handler,
        "onboarding_handler": onboarding_handler,
        "scope_handler": scope_handler,
        "user_handler": user_handler,
        "role_handler": role_handler,
    }


_handlers = asyncio.run(create_handlers())

ap_handler = _handlers["ap_handler"]
agent_handler = _handlers["agent_handler"]
audit_handler = _handlers["audit_handler"]
conv_handler = _handlers["conv_handler"]
conv_agent_handler = _handlers["conv_agent_handler"]
df_handler = _handlers["df_handler"]
di_handler = _handlers["di_handler"]
dt_handler = _handlers["dt_handler"]
dwi_handler = _handlers["dwi_handler"]
llm_handler = _handlers["llm_handler"]
runbook_handler = _handlers["runbook_handler"]
sample_agent = _handlers["sample_agent"]
worker_agent_handler = _handlers["worker_agent_handler"]
onboarding_handler = _handlers["onboarding_handler"]
scope_handler = _handlers["scope_handler"]
user_handler = _handlers["user_handler"]
role_handler = _handlers["role_handler"]
kb_handler = _handlers["kb_handler"]
data_source_handler = _handlers["data_source_handler"]
