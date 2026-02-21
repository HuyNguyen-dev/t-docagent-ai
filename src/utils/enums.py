from enum import StrEnum
from typing import Union

from config import settings


class ParserType(StrEnum):
    """Parser types for document processing."""

    FILE = "file"
    URL = "url"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class LLMProvider(StrEnum):
    OPENAI = "openai"
    GOOGLE_AI = "googleai"
    AZURE_OPENAI = "azure-openai"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class ReasoningEffort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


REASONING_BUDGET = {
    ReasoningEffort.LOW: 1024,
    ReasoningEffort.MEDIUM: 8192,
    ReasoningEffort.HIGH: 24576,
}


class OpenAIModels(StrEnum):
    GPT_5 = "gpt-5"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5_NANO = "gpt-5-nano"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1 = "gpt-4.1"
    OPENAI_O_1 = "o1"
    OPENAI_O_3 = "o3"
    OPENAI_O_4_MINI = "o4-mini"
    OPENAI_O_3_MINI = "o3-mini"
    OPENAI_O_1_MINI = "o1-mini"
    GPT_3_5_TURBO = "gpt-3.5-turbo"

    # Embedding models
    TEXT_EMBEDDING_ADA_002 = "text-embedding-ada-002"
    TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"
    TEXT_EMBEDDING_3_LARGE = "text-embedding-3-large"


class GoogleAIModels(StrEnum):
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_2_0_FLASH_LITE = "gemini-2.0-flash-lite"

    # Embedding models
    GEMINI_EMBEDDING_001 = "gemini-embedding-001"


class AzureOpenAI(StrEnum):
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    OPENAI_O_1 = "openai-o1"
    OPENAI_O_3 = "openai-o3"
    OPENAI_O_3_MINI = "openai-o3-mini"
    OPENAI_O_1_MINI = "openai-o1-mini"
    OPENAI_O_4_MINI = "openai-o4-mini"
    GPT_3_5_TURBO = "gpt-3.5-turbo"

    # Embedding models
    EMBEDDING_ADA_002 = "text-embedding-ada-002"


class ModelType(StrEnum):
    OPENAI_GPT_5 = "openai-gpt-5"
    OPENAI_GPT_5_MINI = "openai-gpt-5-mini"
    OPENAI_GPT_5_NANO = "openai-gpt-5-nano"
    OPENAI_GPT_4O_MINI = "openai-gpt-4o-mini"
    OPENAI_GPT_4O = "openai-gpt-4o"
    OPENAI_GPT_4_1_MINI = "openai-gpt-4.1-mini"
    OPENAI_GPT_4_1 = "openai-gpt-4.1"
    OPENAI_O_1 = "openai-o1"
    OPENAI_O_3 = "openai-o3"
    OPENAI_O_4_MINI = "openai-o4-mini"
    OPENAI_O_3_MINI = "openai-o3-mini"
    OPENAI_O_1_MINI = "openai-o1-mini"
    OPENAI_GPT_3_5_TURBO = "openai-gpt-3.5-turbo"

    AZURE_OPENAI_GPT_4O_MINI = "azure-openai-gpt-4o-mini"
    AZURE_OPENAI_GPT_4O = "azure-openai-gpt-4o"
    AZURE_OPENAI_GPT_O_1 = "azure-openai-gpt-o1"
    AZURE_OPENAI_GPT_O_3 = "azure-openai-gpt-o3"
    AZURE_OPENAI_GPT_O_3_MINI = "azure-openai-gpt-o3-mini"
    AZURE_OPENAI_GPT_O_1_MINI = "azure-openai-gpt-o1-mini"
    AZURE_OPENAI_GPT_O_4_MINI = "azure-openai-gpt-o4-mini"
    AZURE_OPENAI_GPT_3_5_TURBO = "azure-openai-gpt-3.5-turbo"

    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_2_0_FLASH_LITE = "gemini-2.0-flash-lite"

    # Embedding models
    OPENAI_TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"
    OPENAI_TEXT_EMBEDDING_3_LARGE = "text-embedding-3-large"
    OPENAI_TEXT_EMBEDDING_ADA_002 = "text-embedding-ada-002"
    AZURE_OPENAI_EMBEDDING_ADA_002 = "azure-openai-embedding-ada-002"
    GEMINI_EMBEDDING_001 = "gemini-embedding-001"


class ModelObjectType(StrEnum):
    CHAT_LLM = "chat_llm"
    EMBEDDING = "embedding"
    RERANK = "rerank"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class DocWorkItemStage(StrEnum):
    TRAINING = "Training"
    EXTRACTION = "Extraction"
    VALIDATION = "Validation"
    PROCESSING = "Processing"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class DocWorkItemState(StrEnum):
    NEW = "New"
    QUEUED = "Queued"
    NEEDS_TRAINING = "Needs Training"
    IN_PROCESS = "In Process"
    COMPLETED = "Completed"
    FAILED = "Failed"
    SUCCESS = "Success"
    USER_COLLABORATION_NEEDED = "User Collaboration Needed"
    COMPLETED_WITH_MANUAL_INTERVENTION = "Completed with Manual Intervention"
    REQUIRES_FURTHER_REVIEW = "Requires Further Review"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class DocumentFormatState(StrEnum):
    IN_TRAINING = "In Training"
    IGNORE = "Ignore"
    ACTIVATE = "Activated"
    RETRAIN = "Retrain"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class DocumentContentState(StrEnum):
    IN_PROCESS = "IN_PROCESS"
    EXTRACTED = "EXTRACTED"
    TRANSFORMED = "TRANSFORMED"
    COMPUTED = "COMPUTED"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class ImageFormat(StrEnum):
    PNG = "PNG"
    JPEG = "JPEG"
    JPG = "JPEG"  # Alias for JPEG

    @classmethod
    def from_extension(cls, extension: str) -> str:
        """Get format from file extension.

        Args:
            extension: File extension with dot (e.g. '.png')

        Returns:
            str: Format name (e.g. 'PNG')
        """
        extension = extension.lower()
        format_map = {
            ".png": cls.PNG,
            ".jpg": cls.JPEG,
            ".jpeg": cls.JPEG,
        }
        return format_map.get(extension, cls.JPEG)


class ImageFileExtension(StrEnum):
    PNG = ".png"
    JPG = ".jpg"
    JPEG = ".jpeg"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]

    @classmethod
    def get_format(cls, extension: str) -> str:
        """Get format from file extension.

        Args:
            extension: File extension with dot (e.g. '.png')

        Returns:
            str: Format name (e.g. 'PNG')
        """
        return ImageFormat.from_extension(extension)


class TimeRangeFilter(StrEnum):
    LAST_24_HOURS = "last_24_hours"
    LAST_3_DAYS = "last_3_days"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_3_MONTHS = "last_3_months"
    LAST_6_MONTHS = "last_6_months"
    LAST_YEAR = "last_year"


class AgentType(StrEnum):
    CONVERSATION = "Conversation"
    WORKER = "Worker"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class AgentArchitecture(StrEnum):
    REACT = "ReAct"
    PLANING = "Planing"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class AgentReasoning(StrEnum):
    DISABLED = "disabled"
    ENABLED = "enabled"
    VERBOSE = "verbose"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class RunBookType(StrEnum):
    CHAT = "CHAT"
    TEXT = "TEXT"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class MCPTransport(StrEnum):
    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class RedisChannelName(StrEnum):
    DOCUMENT_TYPE = "document_type"
    CONVERSATION = "conversation"
    KB = "knowledge_base"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class LLMEventType(StrEnum):
    ON_TOOL_START = "on_tool_start"
    ON_TOOL_END = "on_tool_end"
    ON_CHAT_MODEL_START = "on_chat_model_start"
    ON_CHAT_MODEL_STREAM = "on_chat_model_stream"
    ON_CHAT_MODEL_END = "on_chat_model_end"
    ON_CHAIN_START = "on_chain_start"
    ON_CHAIN_STREAM = "on_chain_stream"
    ON_CHAIN_END = "on_chain_end"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class DataSourceType(StrEnum):
    """Supported data source types."""

    FILE = "file"
    URL = "url"
    WEBSITE = "website"
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"
    ELASTICSEARCH = "elasticsearch"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class VectorType(StrEnum):
    """Supported vector database types."""

    POSTGRESQL = "postgresql"
    CHROMA = "chroma"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class KnowledgeBaseSearchMethod(StrEnum):
    """Search methods for different knowledge base engines."""

    SEMANTIC = "semantic"
    FULL_TEXT = "full_text"
    HYBRID = "hybrid"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class ModelProvider(StrEnum):
    """Model providers for embedding and reranking models."""

    OPENAI = "openai"
    GOOGLE_AI = "googleai"
    AZURE_OPENAI = "azure-openai"
    COHERE = "cohere"
    HUGGINGFACE = "huggingface"
    ANTHROPIC = "anthropic"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class EmbeddingModel(StrEnum):
    """Common embedding models with their dimensions."""

    # Embedding models
    OPENAI_TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"
    OPENAI_TEXT_EMBEDDING_3_LARGE = "text-embedding-3-large"
    OPENAI_TEXT_EMBEDDING_ADA_002 = "text-embedding-ada-002"
    AZURE_OPENAI_EMBEDDING_ADA_002 = "azure-openai-embedding-ada-002"
    GEMINI_EMBEDDING_001 = "gemini-embedding-001"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]

    @classmethod
    def get_dimensions(cls, model_name: str) -> int:
        """Get the embedding dimensions for a given model."""
        dimensions_map = {
            cls.OPENAI_TEXT_EMBEDDING_3_SMALL: 1536,
            cls.OPENAI_TEXT_EMBEDDING_3_LARGE: 3072,
            cls.OPENAI_TEXT_EMBEDDING_ADA_002: 1536,
            cls.AZURE_OPENAI_EMBEDDING_ADA_002: 1536,
            cls.GEMINI_EMBEDDING_001: 3072,
        }
        return dimensions_map.get(model_name, 3072)

    @classmethod
    def get_provider(cls, model_name: str) -> str:
        """Get the provider for a given model."""
        dimensions_map = {
            cls.OPENAI_TEXT_EMBEDDING_3_SMALL: ModelProvider.OPENAI,
            cls.OPENAI_TEXT_EMBEDDING_3_LARGE: ModelProvider.OPENAI,
            cls.OPENAI_TEXT_EMBEDDING_ADA_002: ModelProvider.OPENAI,
            cls.AZURE_OPENAI_EMBEDDING_ADA_002: ModelProvider.AZURE_OPENAI,
            cls.GEMINI_EMBEDDING_001: ModelProvider.GOOGLE_AI,
        }
        return dimensions_map.get(model_name, ModelProvider.OPENAI)

    @classmethod
    def get_api_key(cls, model_name: str) -> str:
        """Get the api key for a given model."""
        dimensions_map = {
            cls.OPENAI_TEXT_EMBEDDING_3_SMALL: settings.OPENAI_API_KEY.get_secret_value(),
            cls.OPENAI_TEXT_EMBEDDING_3_LARGE: settings.OPENAI_API_KEY.get_secret_value(),
            cls.OPENAI_TEXT_EMBEDDING_ADA_002: settings.OPENAI_API_KEY.get_secret_value(),
            cls.AZURE_OPENAI_EMBEDDING_ADA_002: settings.AZURE_OPENAI_API_KEY.get_secret_value(),
            cls.GEMINI_EMBEDDING_001: settings.GOOGLE_API_KEY.get_secret_value(),
        }
        return dimensions_map.get(model_name, settings.OPENAI_API_KEY.get_secret_value())


class RerankingModel(StrEnum):
    """Common reranking models."""

    OPENAI_GPT_3_5_TURBO = "gpt-3.5-turbo"

    AZURE_OPENAI_GPT_3_5_TURBO = "azure-openai-gpt-3.5-turbo"

    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_2_0_FLASH_LITE = "gemini-2.0-flash-lite"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]

    @classmethod
    def get_provider(cls, model_name: str) -> str:
        """Get the provider for a given model."""
        dimensions_map = {
            cls.OPENAI_GPT_3_5_TURBO: ModelProvider.OPENAI,
            cls.AZURE_OPENAI_GPT_3_5_TURBO: ModelProvider.AZURE_OPENAI,
            cls.GEMINI_2_5_PRO: ModelProvider.GOOGLE_AI,
            cls.GEMINI_2_5_FLASH: ModelProvider.GOOGLE_AI,
            cls.GEMINI_2_5_FLASH_LITE: ModelProvider.GOOGLE_AI,
            cls.GEMINI_2_0_FLASH: ModelProvider.GOOGLE_AI,
            cls.GEMINI_2_0_FLASH_LITE: ModelProvider.GOOGLE_AI,
        }
        return dimensions_map.get(model_name, ModelProvider.OPENAI)


class UserRole(StrEnum):
    """Enumeration of available user roles."""

    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"
    CUSTOM = "custom"


class UserStatus(StrEnum):
    """Enumeration of user status values."""

    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"


class FileType(StrEnum):  # Inherit from StrEnum
    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"

    @classmethod
    def from_extension(cls, extension: str) -> Union["FileType", None]:
        """
        Gets the FileType from an extension string, case-insensitively.
        This method works exactly the same as before.
        """
        if not extension:
            return None

        normalized_ext = extension.lstrip(".").lower()

        # Look up works because the members are string-comparable
        for member in cls:
            if member == normalized_ext:  # No .value needed here!
                return member

        return None


class ChunkingMode(StrEnum):
    """Chunking modes for document processing."""

    SEMANTIC = "semantic"
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"
    CHARACTER = "character"
    RECURSIVE_CHARACTER = "recursive_character"
    AGENTIC = "agentic"

    @classmethod
    def to_list(cls) -> list:
        return [mode.value for mode in cls]


class APIScope(StrEnum):
    # Core API
    API = "api"
    READ_API = "read_api"

    # System
    SYSTEM_INFO_READ = "system_info_read"
    TOKEN_ADMIN = "token_admin"  # noqa: S105
    TOKEN_ROTATE = "token_rotate"  # noqa: S105

    # User Management
    USER_ADMIN = "user_admin"
    USER_READ = "user_read"

    # Document Management
    DOCUMENT_ADMIN = "document_admin"
    DOCUMENT_READ = "document_read"
    DOCUMENT_PROCESSING = "document_processing"
    DOCUMENT_INTELLIGENCE = "document_intelligence"

    # Work Item
    WORK_ITEM_ADMIN = "work_item_admin"
    WORK_ITEM_READ = "work_item_read"
    WORK_ITEM_DOWNLOAD = "work_item_download"

    # Action Package (MCP Servers)
    ACTION_PACKAGE_ADMIN = "action_package_admin"
    ACTION_PACKAGE_READ = "action_package_read"

    # Agent Management
    AGENT_ADMIN = "agent_admin"
    AGENT_READ = "agent_read"
    AGENT_CONVERSATION = "agent_conversation"
    AGENT_WORKFLOW = "agent_workflow"
    AGENT_EXECUTION = "agent_execution"

    # Runbook
    RUNBOOK_ADMIN = "runbook_admin"
    RUNBOOK_READ = "runbook_read"

    # Conversation Chat
    CONVERSATION_ADMIN = "conversation_admin"
    CONVERSATION_READ = "conversation_read"
    CONVERSATION_PARTICIPATE = "conversation_participate"

    # Knowledge Base
    KB_ADMIN = "kb_admin"
    KB_READ = "conversation_read"

    # Data Source
    DATASOURCE_ADMIN = "datasource_admin"
    DATASOURCE_READ = "datasource_read"

    LLM_ACCESS = "llm_access"

    # Audit & Security
    AUDIT_READ = "audit_read"
    AUDIT_ADMIN = "audit_admin"
    SECURITY_ADMIN = "security_admin"
    SYSTEM_MONITOR = "system_monitor"


class EmailType(StrEnum):
    INVITATION = "invitation"
    RESET_PASSWORD = "reset-password"  # noqa: S105
    HITL_REASON = "hitl-reason"
    SUCCESS = "success"


class DocumentExtension(StrEnum):
    DOCX = ".docx"
    DOC = ".doc"
    HTML = ".html"
    PDF = ".pdf"
    TXT = ".txt"

    EXCEL_NEW = ".xlsx"
    EXCEL_OLD = ".xls"
    CSV = ".csv"

    QNA = "qna"

    @classmethod
    def to_string(cls) -> str:
        return ", ".join(ext.value[1:] for ext in cls)


class DocumentSourceType(StrEnum):
    DOC_FILE = "doc_file"
    URL = "url"
    QNA = "qna"


class TableIngestionMode(StrEnum):
    DEFAULT = "default"
    QNA = "qna"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class InsertKBDocState(StrEnum):
    IN_PROCESS = "In Process"
    FAILED = "Failed"
    SUCCESS = "Success"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]


class WorkItemDownloadType(StrEnum):
    SOURCE = "source"
    CONTENT = "content"
    LOGS = "logs"
    ALL = "all"

    @classmethod
    def to_list(cls) -> list:
        return [ext.value for ext in cls]
