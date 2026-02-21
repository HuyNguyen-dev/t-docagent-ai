from schemas.user import UserStatus
from utils.enums import (
    AgentArchitecture,
    AgentReasoning,
    AgentType,
    ChunkingMode,
    DocumentContentState,
    DocumentFormatState,
    DocWorkItemStage,
    DocWorkItemState,
    InsertKBDocState,
    MCPTransport,
    MessageRole,
    RunBookType,
)

# document_type
DOCUMENT_TYPE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "document_type",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "doc_uri": {
                "bsonType": "string",
            },
            "created_at": {
                "bsonType": "date",
            },
            "created_by": {
                "bsonType": "string",
            },
            "last_updated": {
                "bsonType": "date",
            },
            "agent_validation": {
                "bsonType": "bool",
            },
            "auto_mapping": {
                "bsonType": "bool",
            },
            "fields": {
                "bsonType": "object",
                "properties": {
                    "properties": {
                        "bsonType": "array",
                        "additionalItems": True,
                        "items": {
                            "bsonType": "object",
                            "properties": {
                                "id": {
                                    "bsonType": "string",
                                },
                                "display_name": {
                                    "bsonType": "string",
                                },
                            },
                            "additionalProperties": True,
                            "required": [
                                "id",
                                "display_name",
                            ],
                        },
                    },
                    "required": {
                        "bsonType": "array",
                        "additionalItems": True,
                        "items": {
                            "bsonType": "string",
                        },
                    },
                },
                "additionalProperties": True,
                "required": [
                    "properties",
                    "required",
                ],
            },
            "tables": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "id": {
                            "bsonType": "string",
                        },
                        "display_name": {
                            "bsonType": "string",
                        },
                        "description": {
                            "bsonType": "string",
                        },
                        "columns": {
                            "bsonType": "object",
                            "properties": {
                                "properties": {
                                    "bsonType": "array",
                                    "additionalItems": True,
                                    "items": {
                                        "bsonType": "object",
                                        "properties": {
                                            "id": {
                                                "bsonType": "string",
                                            },
                                            "display_name": {
                                                "bsonType": "string",
                                            },
                                        },
                                        "additionalProperties": False,
                                        "required": [
                                            "id",
                                            "display_name",
                                        ],
                                    },
                                },
                                "required": {
                                    "bsonType": "array",
                                    "additionalItems": True,
                                    "items": {
                                        "bsonType": "string",
                                    },
                                },
                            },
                            "additionalProperties": True,
                            "required": [
                                "properties",
                                "required",
                            ],
                        },
                    },
                    "additionalProperties": True,
                    "required": [
                        "id",
                        "display_name",
                        "description",
                        "columns",
                    ],
                },
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "name",
            "doc_uri",
            "created_at",
            "created_by",
            "last_updated",
            "agent_validation",
            "auto_mapping",
        ],
    },
}

# document_format
DOCUMENT_FORMAT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "document_format",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "dt_id": {
                "bsonType": "string",
                "pattern": "^dt-.*$",
            },
            "doc_uri": {
                "bsonType": "string",
            },
            "state": {
                "bsonType": "string",
                "enum": DocumentFormatState.to_list(),
            },
            "created_at": {
                "bsonType": "date",
            },
            "created_by": {
                "bsonType": "string",
            },
            "last_updated": {
                "bsonType": "date",
            },
            "fields": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "id": {
                            "bsonType": "string",
                        },
                        "display_name": {
                            "bsonType": "string",
                        },
                        "mapped_to": {
                            "bsonType": "string",
                        },
                        "static_value": {
                            "bsonType": "string",
                        },
                        "additional_prompt": {
                            "bsonType": "string",
                        },
                    },
                    "additionalProperties": True,
                    "required": [
                        "id",
                        "display_name",
                        "mapped_to",
                        "static_value",
                        "additional_prompt",
                    ],
                },
            },
            "tables": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "id": {
                            "bsonType": "string",
                        },
                        "columns": {
                            "bsonType": "array",
                            "additionalItems": True,
                            "items": {
                                "bsonType": "object",
                                "properties": {
                                    "id": {
                                        "bsonType": "string",
                                    },
                                    "display_name": {
                                        "bsonType": "string",
                                    },
                                    "mapped_to": {
                                        "bsonType": "string",
                                    },
                                },
                                "additionalProperties": False,
                                "required": [
                                    "id",
                                    "display_name",
                                    "mapped_to",
                                ],
                            },
                        },
                    },
                    "additionalProperties": False,
                    "required": [
                        "id",
                        "columns",
                    ],
                },
            },
            "extraction_prompt": {
                "bsonType": "string",
            },
            "sample_table_rows": {
                "bsonType": "string",
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "name",
            "dt_id",
            "doc_uri",
            "state",
            "created_at",
            "created_by",
            "last_updated",
            "fields",
            "tables",
            "extraction_prompt",
            "sample_table_rows",
        ],
    },
}

# document_content
DOCUMENT_CONTENT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "document_content",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "dwi_id": {
                "bsonType": "string",
                "pattern": "^dwi-.*$",
            },
            "created_at": {
                "bsonType": "date",
            },
            "state": {
                "bsonType": "string",
                "enum": DocumentContentState.to_list(),
            },
            "extracted_content": {
                "bsonType": "object",
                "properties": {
                    "fields": {
                        "bsonType": "object",
                        "additionalProperties": True,
                    },
                    "tables": {
                        "bsonType": "array",
                        "additionalItems": True,
                        "items": {
                            "bsonType": "object",
                            "properties": {
                                "id": {
                                    "bsonType": "string",
                                },
                                "columns": {
                                    "bsonType": "array",
                                    "additionalItems": True,
                                    "items": {
                                        "bsonType": "object",
                                        "additionalProperties": True,
                                    },
                                },
                            },
                            "additionalProperties": True,
                            "required": [
                                "id",
                                "columns",
                            ],
                        },
                    },
                },
                "additionalProperties": False,
                "required": [
                    "fields",
                    "tables",
                ],
            },
            "transformed_content": {
                "bsonType": "object",
                "properties": {
                    "fields": {
                        "bsonType": "object",
                        "additionalProperties": True,
                    },
                    "tables": {
                        "bsonType": "array",
                        "additionalItems": True,
                        "items": {
                            "bsonType": "object",
                            "properties": {
                                "id": {
                                    "bsonType": "string",
                                },
                                "columns": {
                                    "bsonType": "array",
                                    "additionalItems": True,
                                    "items": {
                                        "bsonType": "object",
                                        "additionalProperties": True,
                                    },
                                },
                            },
                            "additionalProperties": True,
                            "required": [
                                "id",
                                "columns",
                            ],
                        },
                    },
                    "computed_fields": {
                        "bsonType": "object",
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
                "required": [
                    "fields",
                    "tables",
                    "computed_fields",
                ],
            },
            "computed_content": {
                "bsonType": "object",
                "additionalProperties": True,
            },
            "metadata": {
                "bsonType": "object",
                "additionalProperties": True,
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "dwi_id",
            "created_at",
            "state",
            "extracted_content",
            "transformed_content",
            "computed_content",
            "metadata",
        ],
    },
}

# document_work_item
DOCUMENT_WORK_ITEM_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "document_work_item",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "df_id": {
                "bsonType": "string",
                "pattern": "^df-.*$",
            },
            "doc_uri": {
                "bsonType": "string",
            },
            "stage": {
                "bsonType": "string",
                "enum": DocWorkItemStage.to_list(),
            },
            "state": {
                "bsonType": "string",
                "enum": DocWorkItemState.to_list(),
            },
            "created_at": {
                "bsonType": "date",
            },
            "last_run": {
                "bsonType": "date",
            },
            "is_workflow": {
                "bsonType": "bool",
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "df_id",
            "doc_uri",
            "stage",
            "state",
            "created_at",
            "last_run",
            "is_workflow",
        ],
    },
}

# agent
AGENT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "agent",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "description": {
                "bsonType": "string",
            },
            "version": {
                "bsonType": "string",
            },
            "dt_id": {
                "bsonType": "string",
            },
            "created_at": {
                "bsonType": "date",
            },
            "created_by": {
                "bsonType": "string",
            },
            "is_template": {
                "bsonType": "bool",
            },
            "type": {
                "bsonType": "string",
                "enum": AgentType.to_list(),
            },
            "run_book": {
                "bsonType": "object",
                "properties": {
                    "name": {
                        "bsonType": "string",
                    },
                    "version": {
                        "bsonType": "string",
                    },
                },
                "additionalProperties": False,
                "required": [
                    "name",
                    "version",
                ],
            },
            "action_packages": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "id": {
                            "bsonType": "string",
                            "pattern": "^ap-.*$",
                        },
                        "version": {
                            "bsonType": "string",
                        },
                        "action_selected": {
                            "bsonType": "array",
                            "additionalItems": True,
                            "items": {
                                "bsonType": "string",
                            },
                            "uniqueItems": True,
                        },
                    },
                    "additionalProperties": True,
                    "required": [
                        "id",
                        "version",
                        "action_selected",
                    ],
                },
            },
            "model": {
                "bsonType": "object",
                "properties": {
                    "provider": {
                        "bsonType": "string",
                    },
                    "name": {
                        "bsonType": "string",
                    },
                    "api_key": {
                        "bsonType": "string",
                    },
                    "deployment_name": {
                        "bsonType": "string",
                    },
                    "base_url": {
                        "bsonType": "string",
                    },
                    "api_version": {
                        "bsonType": "string",
                    },
                },
                "additionalProperties": False,
                "required": [
                    "provider",
                ],
            },
            "permissions": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "string",
                },
            },
            "advanced_options": {
                "bsonType": "object",
                "properties": {
                    "reasoning": {
                        "bsonType": "string",
                        "enum": AgentReasoning.to_list(),
                    },
                    "architecture": {
                        "bsonType": "string",
                        "enum": AgentArchitecture.to_list(),
                    },
                    "kb_names": {
                        "bsonType": "array",
                        "additionalItems": True,
                        "items": {
                            "bsonType": "string",
                        },
                        "uniqueItems": True,
                    },
                },
                "additionalProperties": True,
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "name",
            "description",
            "version",
            "created_at",
            "is_template",
            "type",
            "run_book",
            "action_packages",
            "model",
        ],
    },
}


# action_package
ACTION_PACKAGE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "action_package",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "description": {
                "bsonType": "string",
            },
            "transport": {
                "bsonType": "string",
                "enum": MCPTransport.to_list(),
            },
            "version": {
                "bsonType": "string",
            },
            "advanced_configs": {
                "bsonType": "object",
                "additionalProperties": True,
            },
            "created_at": {
                "bsonType": "date",
            },
            "last_updated": {
                "bsonType": "date",
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "name",
            "description",
            "transport",
            "version",
            "created_at",
            "last_updated",
        ],
    },
}

# conversation
CONVERSATION_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "conversation",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "agent_id": {
                "bsonType": "string",
                "pattern": "^agt-.*$",
            },
            "dwi_id": {
                "bsonType": "string",
            },
            "created_at": {
                "bsonType": "date",
            },
            "last_updated": {
                "bsonType": "date",
            },
            "user_collaboration": {
                "bsonType": "object",
                "properties": {
                    "hitl": {
                        "bsonType": "bool",
                    },
                    "reason": {
                        "bsonType": "string",
                    },
                },
                "additionalProperties": False,
                "required": [
                    "hitl",
                    "reason",
                ],
            },
            "files": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "uri": {
                            "bsonType": "string",
                        },
                        "created_at": {
                            "bsonType": "date",
                        },
                    },
                    "additionalProperties": True,
                    "required": [
                        "uri",
                        "created_at",
                    ],
                },
                "uniqueItems": True,
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "name",
            "agent_id",
            "created_at",
            "last_updated",
            "user_collaboration",
        ],
    },
}

# message
MESSAGE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "message",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "conv_id": {
                "bsonType": "string",
            },
            "created_at": {
                "bsonType": "date",
            },
            "user_id": {
                "bsonType": "string",
            },
            "role": {
                "bsonType": "string",
                "enum": MessageRole.to_list(),
            },
            "payload": {
                "bsonType": "object",
                "properties": {
                    "text": {
                        "bsonType": "string",
                    },
                    "thinking": {
                        "bsonType": "string",
                    },
                    "action": {
                        "bsonType": "object",
                        "properties": {
                            "name": {
                                "bsonType": "string",
                            },
                            "status": {
                                "bsonType": "string",
                            },
                            "metadata": {
                                "bsonType": "object",
                                "additionalProperties": True,
                            },
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": True,
                "required": [
                    "text",
                ],
            },
            "metadata": {
                "bsonType": "object",
                "properties": {
                    "attachments": {
                        "bsonType": "array",
                        "additionalItems": True,
                        "items": {
                            "bsonType": "object",
                            "properties": {
                                "name": {
                                    "bsonType": "string",
                                },
                                "uri": {
                                    "bsonType": "string",
                                },
                                "mime_type": {
                                    "bsonType": "string",
                                },
                            },
                            "additionalProperties": True,
                            "required": [
                                "name",
                                "uri",
                                "mime_type",
                            ],
                        },
                    },
                },
                "additionalProperties": True,
                "required": [
                    "attachments",
                ],
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "conv_id",
            "created_at",
            "role",
            "payload",
            "metadata",
        ],
    },
}

RUNBOOK_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "run_book",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "version": {
                "bsonType": "string",
            },
            "prompt": {
                "bsonType": "string",
            },
            "created_at": {
                "bsonType": "date",
            },
            "last_updated": {
                "bsonType": "date",
            },
            "type": {
                "bsonType": "string",
                "enum": RunBookType.to_list(),
            },
            "labels": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "string",
                },
            },
            "tags": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "string",
                },
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "name",
            "version",
            "prompt",
            "created_at",
            "last_updated",
            "type",
            "labels",
            "tags",
        ],
    },
}

LLM_CONFIGURATION_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "llm_configuration",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "user_id": {
                "bsonType": "string",
            },
            "openai_api_key": {
                "bsonType": "string",
            },
            "google_api_key": {
                "bsonType": "string",
            },
            "azure_openai": {
                "bsonType": "array",
                "additionalItems": True,
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "name": {
                            "bsonType": "string",
                        },
                        "base_url": {
                            "bsonType": "string",
                        },
                        "deployment_name": {
                            "bsonType": "string",
                        },
                        "api_key": {
                            "bsonType": "string",
                        },
                        "api_version": {
                            "bsonType": "string",
                        },
                    },
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "base_url",
                        "deployment_name",
                        "api_key",
                        "api_version",
                    ],
                },
            },
            "schema_discovery": {
                "bsonType": "object",
                "properties": {
                    "provider": {
                        "bsonType": "string",
                    },
                    "name": {
                        "bsonType": "string",
                    },
                    "api_key": {
                        "bsonType": "string",
                    },
                    "deployment_name": {
                        "bsonType": "string",
                    },
                    "base_url": {
                        "bsonType": "string",
                    },
                    "api_version": {
                        "bsonType": "string",
                    },
                },
                "additionalProperties": True,
                "required": [
                    "provider",
                    "name",
                ],
            },
            "extraction": {
                "bsonType": "object",
                "properties": {
                    "provider": {
                        "bsonType": "string",
                    },
                    "name": {
                        "bsonType": "string",
                    },
                    "api_key": {
                        "bsonType": "string",
                    },
                    "deployment_name": {
                        "bsonType": "string",
                    },
                    "base_url": {
                        "bsonType": "string",
                    },
                    "api_version": {
                        "bsonType": "string",
                    },
                },
                "additionalProperties": True,
                "required": [
                    "provider",
                    "name",
                ],
            },
            "embedding": {
                "bsonType": "object",
                "properties": {
                    "provider": {
                        "bsonType": "string",
                    },
                    "name": {
                        "bsonType": "string",
                    },
                    "api_key": {
                        "bsonType": "string",
                    },
                    "deployment_name": {
                        "bsonType": "string",
                    },
                    "base_url": {
                        "bsonType": "string",
                    },
                    "api_version": {
                        "bsonType": "string",
                    },
                },
                "additionalProperties": True,
                "required": [
                    "provider",
                    "name",
                ],
            },
            "rerank": {
                "bsonType": "object",
                "properties": {
                    "provider": {
                        "bsonType": "string",
                    },
                    "name": {
                        "bsonType": "string",
                    },
                    "api_key": {
                        "bsonType": "string",
                    },
                    "deployment_name": {
                        "bsonType": "string",
                    },
                    "base_url": {
                        "bsonType": "string",
                    },
                    "api_version": {
                        "bsonType": "string",
                    },
                },
                "additionalProperties": True,
                "required": [
                    "provider",
                    "name",
                ],
            },
            "langsmith": {
                "bsonType": "object",
                "properties": {
                    "name": {
                        "bsonType": "string",
                    },
                    "is_tracing": {
                        "bsonType": "bool",
                    },
                    "api_key": {
                        "bsonType": "string",
                    },
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "user_id",
            "openai_api_key",
            "google_api_key",
            "azure_openai",
            "schema_discovery",
            "extraction",
            "embedding",
            "rerank",
            "langsmith",
        ],
    },
}
# token
TOKEN_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "token",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "token_hash": {
                "bsonType": "string",
            },
            "user_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "description": {
                "bsonType": ["string", "null"],
            },
            "scopes": {
                "bsonType": "array",
                "items": {
                    "bsonType": "string",
                },
            },
            "created_at": {
                "bsonType": "date",
            },
            "expires_at": {
                "bsonType": ["date", "null"],
            },
            "last_used_at": {
                "bsonType": ["date", "null"],
            },
            "is_active": {
                "bsonType": "bool",
            },
        },
        "required": [
            "token_hash",
            "user_id",
            "name",
            "scopes",
            "created_at",
            "is_active",
        ],
    },
}

# user
USER_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "user",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "email": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "role": {
                "bsonType": "string",
            },
            "status": {
                "enum": [status.value for status in UserStatus],
            },
            "password_hash": {
                "bsonType": ["string", "null"],
            },
            "created_at": {
                "bsonType": "date",
            },
            "updated_at": {
                "bsonType": "date",
            },
            "last_seen_at": {
                "bsonType": ["date", "null"],
            },
            "is_active": {
                "bsonType": "bool",
            },
        },
        "required": [
            "email",
            "name",
            "role",
            "status",
            "created_at",
            "updated_at",
            "is_active",
        ],
    },
}

# role
ROLE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "role",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "description": {
                "bsonType": "string",
            },
            "icon": {
                "bsonType": "string",
            },
            "scopes": {
                "bsonType": "array",
                "items": {
                    "bsonType": "string",
                },
            },
            "created_at": {
                "bsonType": "date",
            },
            "created_by": {
                "bsonType": "string",
            },
            "is_system_role": {
                "bsonType": "bool",
            },
        },
        "required": [
            "name",
            "description",
            "icon",
            "scopes",
            "created_at",
            "created_by",
            "is_system_role",
        ],
    },
}

# API Audit Log
API_AUDIT_LOG_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "api_audit_log",
        "properties": {
            "_id": {
                "bsonType": "string",
                "description": "Unique audit log identifier",
            },
            "timestamp": {
                "bsonType": "date",
                "description": "When the API call was made",
            },
            "request_id": {
                "bsonType": "string",
                "description": "Unique request identifier",
            },
            "user_id": {
                "bsonType": "string",
                "description": "User ID for session auth",
            },
            "token_id": {
                "bsonType": ["string", "null"],
                "description": "Token ID for token auth",
            },
            "auth_type": {
                "bsonType": "string",
                "enum": ["SESSION", "TOKEN", "NONE", "INVALID", "ERROR"],
                "description": "Type of authentication used",
            },
            "endpoint": {
                "bsonType": "string",
                "description": "API endpoint accessed",
            },
            "method": {
                "bsonType": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
                "description": "HTTP method used",
            },
            "path_params": {
                "bsonType": ["object", "null"],
                "description": "URL path parameters",
            },
            "query_params": {
                "bsonType": ["object", "null"],
                "description": "Query string parameters",
            },
            "status_code": {
                "bsonType": "int",
                "minimum": 100,
                "maximum": 599,
                "description": "HTTP response status code",
            },
            "response_size": {
                "bsonType": ["int", "null"],
                "minimum": 0,
                "description": "Response size in bytes",
            },
            "processing_time_ms": {
                "bsonType": ["int", "null"],
                "minimum": 0,
                "description": "Request processing time in milliseconds",
            },
            "ip_address": {
                "bsonType": ["string", "null"],
                "description": "Client IP address (IPv4 or IPv6)",
            },
            "user_agent": {
                "bsonType": ["string", "null"],
                "maxLength": 2048,
                "description": "Client user agent string",
            },
            "referer": {
                "bsonType": ["string", "null"],
                "maxLength": 2048,
                "description": "HTTP referer header",
            },
            "scopes_used": {
                "bsonType": "array",
                "items": {
                    "bsonType": "string",
                },
                "uniqueItems": True,
                "description": "API scopes that were checked/used",
            },
            "risk_level": {
                "bsonType": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "Assessed risk level of the request",
            },
            "is_suspicious": {
                "bsonType": "bool",
                "description": "Whether this request was flagged as suspicious",
            },
            "error_code": {
                "bsonType": ["string", "null"],
                "maxLength": 100,
                "description": "Error code if request failed",
            },
            "error_message": {
                "bsonType": ["string", "null"],
                "maxLength": 1000,
                "description": "Error message if request failed",
            },
        },
        "required": [
            "_id",
            "timestamp",
            "request_id",
            "auth_type",
            "endpoint",
            "method",
            "status_code",
            "scopes_used",
            "risk_level",
            "is_suspicious",
        ],
        "additionalProperties": False,
    },
}

# knowledge_base
KNOWLEDGE_BASE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "knowledge_base",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "tags": {
                "bsonType": "array",
                "items": {
                    "bsonType": "string",
                },
            },
            "engine": {
                "bsonType": "string",
            },
            "documents": {
                "bsonType": "array",
                "items": {
                    "bsonType": "string",
                },
            },
            "config": {
                "bsonType": "object",
                "properties": {
                    "embedding_model": {
                        "bsonType": "string",
                    },
                    "retrieval_mode": {
                        "bsonType": "object",
                        "properties": {
                            "search_method": {
                                "bsonType": "string",
                            },
                            "rerank_enabled": {
                                "bsonType": "bool",
                            },
                            "top_k": {
                                "bsonType": "int",
                            },
                            "relevance_enabled": {
                                "bsonType": "bool",
                            },
                            "relevance_threshold": {
                                "bsonType": "double",
                            },
                            "hybrid_alpha_search_enabled": {
                                "bsonType": "bool",
                            },
                            "hybrid_weight": {
                                "bsonType": "double",
                            },
                        },
                        "additionalProperties": False,
                        "required": [
                            "search_method",
                            "rerank_enabled",
                            "top_k",
                            "relevance_enabled",
                            "relevance_threshold",
                            "hybrid_alpha_search_enabled",
                            "hybrid_weight",
                        ],
                    },
                },
                "additionalProperties": False,
                "required": [
                    "embedding_model",
                    "retrieval_mode",
                ],
            },
            "data_source_type": {
                "bsonType": "string",
            },
            "created_at": {
                "bsonType": "date",
            },
            "updated_at": {
                "bsonType": "date",
            },
            "created_by": {
                "bsonType": "string",
            },
            "is_active": {
                "bsonType": "bool",
            },
        },
        "additionalProperties": True,
        "required": [
            "_id",
            "name",
            "engine",
            "documents",
            "config",
            "data_source_type",
            "created_at",
            "updated_at",
            "created_by",
            "is_active",
        ],
    },
}

# document
KB_DOCUMENT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "document",
        "properties": {
            "_id": {
                "bsonType": "string",
            },
            "name": {
                "bsonType": "string",
            },
            "kb_name": {
                "bsonType": "string",
            },
            "chunking_mode": {
                "bsonType": "string",
                "enum": ChunkingMode.to_list(),
            },
            "chunking_config": {
                "bsonType": "object",
                "properties": {
                    "chunk_length": {
                        "bsonType": "int",
                    },
                    "chunk_overlap": {
                        "bsonType": "int",
                    },
                },
                "additionalProperties": False,
                "required": [
                    "chunk_length",
                    "chunk_overlap",
                ],
            },
            "words_count": {
                "bsonType": "int",
            },
            "state": {
                "bsonType": "string",
                "enum": InsertKBDocState.to_list(),
            },
            "upload_time": {
                "bsonType": "date",
            },
            "metadata": {
                "bsonType": "object",
            },
        },
        "additionalProperties": False,
        "required": [
            "_id",
            "name",
            "kb_name",
            "chunking_mode",
            "words_count",
            "upload_time",
            "metadata",
        ],
    },
}
