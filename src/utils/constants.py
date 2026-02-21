from datetime import UTC
from pathlib import Path

from config import APP_HOME
from utils.enums import APIScope, EmbeddingModel, ModelType, UserRole

TIMEZONE = UTC
INVALID_DISPLAY_NAME_MSG = "display_name must not be empty and must contain non-space characters"

DEFAULT_BUCKET = "dims"
DEFAULT_INTAKE_FOLDER = "in"
DEFAULT_WORKSPACE_ID = "dev"

DEFAULT_KB_INTAKE_FOLDER = "kb"
DEFAULT_WORK_ITEMS_FOLDER = "work-items"
DEFAULT_MCP_SCRIPT_FILE_FOLDER = "script-files"
DEFAULT_EXTRACTION_FILE_FOLDER = "extraction-files"
DEFAULT_CONVERSATION_FILE_FOLDER = "conversation-files"
DEFAULT_STANDARDIO_MCP_FOLDER = "stdio_mcp"

DATA_CHART_DIR = Path(APP_HOME).joinpath("src", "data", "charts")
DATA_CHART_DIR.mkdir(exist_ok=True)

# LLM
DEFAULT_VISION_LLM_MODEL = ModelType.GEMINI_2_5_FLASH
DEFAULT_LLM_MODEL = ModelType.GEMINI_2_5_PRO
DEFAULT_TEMPERATURE = 0.7
TRIMMING_MESSAGE_RATIO = 0.7
DEFAULT_MESSAGE_LENGTH = 10
DEFAULT_MAX_TOKEN = 1024

# Error messages
INVALID_FILE_TYPE_MSG = "Please check the upload file type only support zip file"

IMAGE_MODE = "RGBA"

DEFAULT_COLUMN_IDS = ["id", "doc_name", "df_name", "stage", "state", "created_at", "last_run"]
DEFAULT_COLUMN_NAMES = ["ID", "Document Name", "Format Name", "Stage", "State", "Date Added", "Last Run"]

# REDIS
SOCKET_TIMEOUT = 20
SOCKET_CONNECT_TIMEOUT = 20
HEARTBEAT_INTERVAL = 30
NUM_RETRIES = 3

# Agent
DEFAULT_FUNCTION_INTERRUPT = "user_collaboration_needed"
DEFAULT_FUNCTION_CHART_GENERATION = "execute_python_chart_generation"
FRIENDLY_QUESTION = "FRIENDLY"

# TRAINING
TRAINING_PREFIX = "dwi:"
TRAINING_POSTFIX = ":status"
SLEEP_TIME = 5

# LLM Configuration
KEY_EXTRACTION_CONFIG = "extraction"
KEY_SCHEMA_DISCOVERY_CONFIG = "schema_discovery"
KEY_SCHEMA_EMBEDDING_CONFIG = "embedding"
KEY_SCHEMA_RERANK_CONFIG = "rerank"

DEFAULT_EMBEDDING_BATCH_SIZE = 50

# Knowledge Base Configuration
DEFAULT_EMBEDDING_MODEL = EmbeddingModel.GEMINI_EMBEDDING_001
DEFAULT_CHUNK_LENGTH = 600
DEFAULT_CHUNK_OVERLAP = 0
DEFAULT_TOP_K = 10
DEFAULT_RELEVANCE_THRESHOLD = 0.6
DEFAULT_HYBRID_WEIGHT = 0.7
DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_PAGE_SIZE = 100
HTTPX_TIMEOUT = 1000
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 10, 15]

ROLE_SCOPES = {
    UserRole.OWNER: {APIScope.API},  # Full access to everything
    UserRole.ADMIN: {
        APIScope.READ_API,
        APIScope.SYSTEM_INFO_READ,
        APIScope.USER_ADMIN,
        APIScope.DOCUMENT_ADMIN,
        APIScope.WORK_ITEM_ADMIN,
        APIScope.ACTION_PACKAGE_ADMIN,
        APIScope.AGENT_ADMIN,
        APIScope.RUNBOOK_ADMIN,
        APIScope.CONVERSATION_ADMIN,
        APIScope.KB_ADMIN,
        APIScope.DATASOURCE_ADMIN,
        APIScope.LLM_ACCESS,
    },
    UserRole.USER: {
        APIScope.READ_API,
        APIScope.SYSTEM_INFO_READ,
        APIScope.USER_READ,
        APIScope.DOCUMENT_READ,
        APIScope.WORK_ITEM_READ,
        APIScope.ACTION_PACKAGE_READ,
        APIScope.AGENT_READ,
        APIScope.AGENT_CONVERSATION,
        APIScope.RUNBOOK_READ,
    },
}

# Scope inheritance rules
SCOPE_INHERITANCE = {
    APIScope.API: "all",  # Special case - includes everything
    APIScope.READ_API: [
        APIScope.SYSTEM_INFO_READ,
        APIScope.USER_READ,
        APIScope.DOCUMENT_READ,
        APIScope.WORK_ITEM_READ,
        APIScope.ACTION_PACKAGE_READ,
        APIScope.AGENT_READ,
        APIScope.RUNBOOK_READ,
        APIScope.CONVERSATION_READ,
    ],
    APIScope.TOKEN_ADMIN: [APIScope.TOKEN_ROTATE],
    APIScope.USER_ADMIN: [APIScope.USER_READ],
    APIScope.DOCUMENT_ADMIN: [
        APIScope.DOCUMENT_READ,
        APIScope.DOCUMENT_INTELLIGENCE,
        APIScope.DOCUMENT_PROCESSING,
    ],
    APIScope.WORK_ITEM_ADMIN: [APIScope.WORK_ITEM_READ],
    APIScope.ACTION_PACKAGE_ADMIN: [APIScope.ACTION_PACKAGE_READ],
    APIScope.AGENT_ADMIN: [
        APIScope.AGENT_READ,
        APIScope.AGENT_CONVERSATION,
        APIScope.AGENT_EXECUTION,
        APIScope.AGENT_WORKFLOW,
    ],
    APIScope.RUNBOOK_ADMIN: [APIScope.RUNBOOK_READ],
    APIScope.CONVERSATION_ADMIN: [
        APIScope.CONVERSATION_READ,
        APIScope.CONVERSATION_PARTICIPATE,
    ],
    APIScope.KB_ADMIN: [
        APIScope.KB_READ,
    ],
    APIScope.DATASOURCE_ADMIN: [APIScope.DATASOURCE_READ],
}

DEFAULT_ROLES = [
    {
        "name": UserRole.OWNER,
        "description": "System owner with full access to all features",
        "icon": "👑",
        "scopes": list(ROLE_SCOPES[UserRole.OWNER]),
        "is_system_role": True,
    },
    {
        "name": UserRole.ADMIN,
        "description": "Administrator with extensive management capabilities",
        "icon": "🔧",
        "scopes": list(ROLE_SCOPES[UserRole.ADMIN]),
        "is_system_role": True,
    },
    {
        "name": UserRole.USER,
        "description": "Regular user with standard access permissions",
        "icon": "👤",
        "scopes": list(ROLE_SCOPES[UserRole.USER]),
        "is_system_role": True,
    },
]

SKIP_PATHS = {
    "/docs",
    "/openapi.json",
    "/favicon.ico",
    "/health",
    "/metrics",
    "/static",
    "/_internal",
}

SKIP_EXTENSIONS = {
    "html",
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".woff",
    ".woff2",
    ".ttf",
}
