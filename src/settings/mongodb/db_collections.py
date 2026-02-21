from enum import StrEnum

from settings.mongodb.validators import (
    ACTION_PACKAGE_VALIDATOR,
    AGENT_VALIDATOR,
    API_AUDIT_LOG_VALIDATOR,
    CONVERSATION_VALIDATOR,
    DOCUMENT_CONTENT_VALIDATOR,
    DOCUMENT_FORMAT_VALIDATOR,
    DOCUMENT_TYPE_VALIDATOR,
    DOCUMENT_WORK_ITEM_VALIDATOR,
    KB_DOCUMENT_VALIDATOR,
    KNOWLEDGE_BASE_VALIDATOR,
    LLM_CONFIGURATION_VALIDATOR,
    MESSAGE_VALIDATOR,
    ROLE_VALIDATOR,
    RUNBOOK_VALIDATOR,
    TOKEN_VALIDATOR,
    USER_VALIDATOR,
)


class CollectionName(StrEnum):
    DOUCMENT_TYPE = "document_type"
    DOCUMENT_FORMAT = "document_format"
    DOCUMENT_CONTENT = "document_content"
    DOCUMENT_WORK_ITEM = "document_work_item"
    AGENT = "agent"
    ACTION_PACKAGE = "action_package"
    CONVERSATION = "conversation"
    MESSAGE = "message"
    RUN_BOOK = "run_book"
    LLM_CONFIGURATION = "llm_configuration"
    USER = "user"
    KNOWLEDGE_BASE = "knowledge_base"
    KB_DOCUMENT = "kb_document"
    TOKEN = "token"  # noqa: S105
    ROLE = "role"
    TAG = "tag"
    API_AUDIT_LOG = "api_audit_logs"


COLLECTION_LIST = [
    {
        "collection_name": CollectionName.DOUCMENT_TYPE.value,
        "validator": DOCUMENT_TYPE_VALIDATOR,
    },
    {
        "collection_name": CollectionName.DOCUMENT_FORMAT.value,
        "validator": DOCUMENT_FORMAT_VALIDATOR,
    },
    {
        "collection_name": CollectionName.DOCUMENT_CONTENT.value,
        "validator": DOCUMENT_CONTENT_VALIDATOR,
    },
    {
        "collection_name": CollectionName.DOCUMENT_WORK_ITEM.value,
        "validator": DOCUMENT_WORK_ITEM_VALIDATOR,
    },
    {
        "collection_name": CollectionName.AGENT.value,
        "validator": AGENT_VALIDATOR,
    },
    {
        "collection_name": CollectionName.ACTION_PACKAGE.value,
        "validator": ACTION_PACKAGE_VALIDATOR,
    },
    {
        "collection_name": CollectionName.RUN_BOOK.value,
        "validator": RUNBOOK_VALIDATOR,
    },
    {
        "collection_name": CollectionName.CONVERSATION.value,
        "validator": CONVERSATION_VALIDATOR,
    },
    {
        "collection_name": CollectionName.MESSAGE.value,
        "validator": MESSAGE_VALIDATOR,
    },
    {
        "collection_name": CollectionName.LLM_CONFIGURATION.value,
        "validator": LLM_CONFIGURATION_VALIDATOR,
    },
    {
        "collection_name": CollectionName.USER.value,
        "validator": USER_VALIDATOR,
    },
    {
        "collection_name": CollectionName.KNOWLEDGE_BASE.value,
        "validator": KNOWLEDGE_BASE_VALIDATOR,
    },
    {
        "collection_name": CollectionName.KB_DOCUMENT.value,
        "validator": KB_DOCUMENT_VALIDATOR,
    },
    {
        "collection_name": CollectionName.TOKEN.value,
        "validator": TOKEN_VALIDATOR,
    },
    {
        "collection_name": CollectionName.ROLE.value,
        "validator": ROLE_VALIDATOR,
    },
    {
        "collection_name": CollectionName.API_AUDIT_LOG.value,
        "validator": API_AUDIT_LOG_VALIDATOR,
    },
]
