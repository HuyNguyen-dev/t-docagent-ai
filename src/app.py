import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, RedirectResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient

from config import default_configs, settings
from initializer import init_database, logger_instance, redis_pubsub_manager, training_status_manager
from utils.constants import SLEEP_TIME

logger = logger_instance.get_logger(__name__)
api_config = default_configs.get("API", {})
logging_config = default_configs.get("LOGGING", {})
client = AsyncIOMotorClient(str(settings.MONGODB_DSN))


class IncludeAPIRouter:
    def __new__(cls) -> APIRouter:
        from routers.action_package import router as router_action_package
        from routers.agent import router as router_agent
        from routers.audit import router as router_audit
        from routers.auth import router as router_auth
        from routers.conversation import router as router_conversation
        from routers.conversational_agent import router as router_conversational_agent
        from routers.datasource import router as router_datasource
        from routers.document_format import router as router_document_format
        from routers.document_intelligence import router as router_document_intelligence
        from routers.document_type import router as router_document_type
        from routers.document_work_item import router as router_document_work_item
        from routers.health_check import router as router_health_check
        from routers.knowledge_base import router as router_kb
        from routers.llm import router as router_llm
        from routers.llm_configuration import router as router_llm_configuration
        from routers.onboarding import router as router_onboarding
        from routers.role import router as router_role
        from routers.runbook import router as router_runbook
        from routers.scope import router as router_scope
        from routers.token import router as router_token
        from routers.user import router as router_user
        from routers.worker_agent import router as router_worker_agent

        router = APIRouter(prefix="/api/v1")
        router.include_router(router_health_check, tags=["Health Check"])
        router.include_router(router_onboarding, tags=["System Onboarding"])

        # Add license management router
        from routers.license import router as router_license

        router.include_router(router_license, tags=["License Management"])
        router.include_router(router_auth, tags=["Authentication"])
        router.include_router(router_token, tags=["Access Token"])
        router.include_router(router_audit, tags=["Audit & Security"])
        router.include_router(router_scope, tags=["Scopes"])
        router.include_router(router_user, tags=["User"])
        router.include_router(router_role, tags=["Role"])
        router.include_router(router_action_package, tags=["Action Package"])
        router.include_router(router_agent, tags=["Agent"])
        router.include_router(router_conversation, tags=["Conversation"])
        router.include_router(router_conversational_agent, tags=["Conversational Agent"])
        router.include_router(router_document_type, tags=["Document Type"])
        router.include_router(router_llm, tags=["Large Language Model"])
        router.include_router(router_llm_configuration, tags=["LLM Configurations"])
        router.include_router(router_document_intelligence, tags=["Document Intelligence"])
        router.include_router(router_document_format, tags=["Document Format"])
        router.include_router(router_document_work_item, tags=["Document Work Item"])
        router.include_router(router_runbook, tags=["Runbook"])
        router.include_router(router_worker_agent, tags=["Worker Agent"])
        if settings.ENABLE_KNOWNLEDEGE_BASE:
            router.include_router(router_datasource, tags=["Data Source"])
            router.include_router(router_kb, tags=["Knowledge Base"])
        return router


def get_application(lifespan: AsyncGenerator | None = None) -> FastAPI:
    app_ = FastAPI(
        lifespan=lifespan,
        title=api_config["API_NAME"],
        description=api_config["API_DESCRIPTION"],
        version=api_config["API_VERSION"],
        debug=api_config["API_DEBUG_MODE"],
        default_response_class=ORJSONResponse,
    )
    app_.include_router(IncludeAPIRouter())

    # Add audit middleware BEFORE CORS (middleware stack is executed in reverse order)
    from middleware.api_audit import APIAuditMiddleware

    app_.add_middleware(APIAuditMiddleware)

    # Add license validation middleware AFTER audit but BEFORE CORS
    from middleware.license_validation import LicenseValidationMiddleware

    app_.add_middleware(LicenseValidationMiddleware)

    app_.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app_


background_tasks: list[asyncio.Task] = []


async def cleanup_stale_training_items() -> None:
    """Clean up stale training items on backend restart"""
    try:
        await asyncio.sleep(SLEEP_TIME)
        cleaned_count = await training_status_manager.cleanup_stale_training_items()
        if cleaned_count > 0:
            logger.info(
                "event=redis-failover-cleanup-completed "
                "cleaned_count=%d "
                'message="Redis failover cleanup completed on backend restart"',
                cleaned_count,
            )
        else:
            logger.info(
                'event=redis-failover-cleanup-skipped message="No stale training items found during Redis failover cleanup"',
            )
    except Exception:
        logger.exception(
            'event=redis-failover-cleanup-failed message="Failed to cleanup stale training items during backend restart"',
        )


@asynccontextmanager
async def app_lifespan(_: FastAPI) -> AsyncGenerator:
    # Code to execute when app is loading
    is_db_success = await init_database(client=client, is_init_collection=False)
    if is_db_success:
        logger.info(
            'event=init-db-database-success message="Initializing Database and all Collections successfully."',
        )
    else:
        logger.critical(
            'event=init-db-database-failure message="Database initialization failed - please check settings carefully"',
        )
    is_redis_success = await redis_pubsub_manager.connect()
    if is_redis_success:
        logger.info(
            'event=init-redis-success message="Redis connection initialized successfully."',
        )
    else:
        logger.critical(
            'event=init-redis-failure message="Redis initialization failed - please check settings carefully"',
        )
    task = asyncio.create_task(cleanup_stale_training_items())
    background_tasks.append(task)
    yield
    for task in background_tasks:
        task.cancel()

    logger.info(
        'event=app-shutdown message="Application shutdown completed - all connections closed"',
    )


app = get_application(lifespan=app_lifespan)


@app.get("/")
def docs_redirect() -> RedirectResponse:
    """Redirect to API documentation"""
    return RedirectResponse(url="/docs")


app.mount("/", StaticFiles(directory="src/static", html=True), name="static")


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/api/v1/health") == -1


if __name__ == "__main__":
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = logging_config["UVICORN_FORMATTER"]
    log_config["formatters"]["default"]["fmt"] = logging_config["UVICORN_FORMATTER"]
    log_config["formatters"]["access"]["datefmt"] = logging_config["DATE_FORMATTER"]
    log_config["formatters"]["default"]["datefmt"] = logging_config["DATE_FORMATTER"]
    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        log_config=log_config,
        workers=settings.UVICORN_WORKERS,
    )
