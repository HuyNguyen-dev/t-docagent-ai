DEFAULT_SCOPES = [
    {
        "id": "core_api",
        "description": "Core API",
        "icon": "🔑",
        "scopes": [
            {
                "id": "read_api",
                "title": "Read API",
                "description": "Grants read-only access to all API endpoints.",
                "type": "read",
            },
            {
                "id": "api",
                "title": "Full API Access",
                "description": "Grants complete access to all API functionality. Use with caution.",
                "type": "system",
            },
        ],
    },
    {
        "id": "system_security",
        "description": "System & Security",
        "icon": "⚙️",
        "scopes": [  # Fixed: changed "scopes:" to "scopes":
            {
                "id": "system_info_read",
                "title": "View System Info",
                "description": "Allows reading general system information and configuration.",
                "type": "read",
            },
            {
                "id": "token_admin",
                "title": "Manage API Tokens",
                "description": "Allows creating, revoking, and managing all API tokens.",
                "type": "admin",
            },
            {
                "id": "token_rotate",
                "title": "Rotate Own Token",
                "description": "Allows the user to rotate their own API token for security.",
                "type": "normal",
            },
        ],
    },
    {
        "id": "user_management",
        "description": "User Management",
        "icon": "👤",
        "scopes": [
            {
                "id": "user_read",
                "title": "View Users",
                "description": "Grants read-only access to user information.",
                "type": "read",
            },
            {
                "id": "user_admin",
                "title": "Manage Users",
                "description": "Grants full administrative access to user accounts (create, edit, delete).",
                "type": "admin",
            },
        ],
    },
    {
        "id": "document_management",
        "description": "Document Management",
        "icon": "📄",
        "scopes": [
            {
                "id": "document_read",
                "title": "View Documents",
                "description": "Read-only access to documents and their metadata.",
                "type": "read",
            },
            {
                "id": "document_processing",
                "title": "Process Documents",
                "description": "Allows initiating document processing and ingestion pipelines.",
                "type": "normal",
            },
            {
                "id": "document_intelligence",
                "title": "Use Document Intelligence",
                "description": "Allows using AI-powered document intelligence features (e.g., extraction, analysis).",
                "type": "normal",
            },
            {
                "id": "document_admin",
                "title": "Manage Documents",
                "description": "Full administrative access to documents (upload, edit, delete).",
                "type": "admin",
            },
        ],
    },
    {
        "id": "work_items",
        "description": "Work Items",
        "icon": "📦",
        "scopes": [
            {
                "id": "work_item_read",
                "title": "View Work Items",
                "description": "Read-only access to work items.",
                "type": "read",
            },
            {
                "id": "work_item_download",
                "title": "Download Work Items",
                "description": "Allows downloading files or data associated with work items.",
                "type": "normal",
            },
            {
                "id": "work_item_admin",
                "title": "Manage Work Items",
                "description": "Full administrative access to work items.",
                "type": "admin",
            },
        ],
    },
    {
        "id": "agent_management",
        "description": "Agent Management",
        "icon": "🤖",
        "scopes": [
            {
                "id": "agent_read",
                "title": "View Agents",
                "description": "Read-only access to agent information and configurations.",
                "type": "read",
            },
            {
                "id": "agent_conversation",
                "title": "Interact with Agents",
                "description": "Allows starting and participating in conversations with agents.",
                "type": "normal",
            },
            {
                "id": "agent_workflow",
                "title": "Manage Agent Workflows",
                "description": "Allows creating and managing agent workflows.",
                "type": "normal",
            },
            {
                "id": "agent_execution",
                "title": "Execute Agent Actions",
                "description": "Permission to trigger and execute agent actions and workflows.",
                "type": "normal",
            },
            {
                "id": "agent_admin",
                "title": "Manage Agents",
                "description": "Full administrative access to agents (create, configure, delete).",
                "type": "admin",
            },
        ],
    },
    {
        "id": "runbook",
        "description": "RunBook",
        "icon": "📖",
        "scopes": [
            {
                "id": "runbook_read",
                "title": "View Runbooks",
                "description": "Read-only access to runbooks and their execution history.",
                "type": "read",
            },
            {
                "id": "runbook_admin",
                "title": "Manage Runbooks",
                "description": "Full administrative access to runbooks.",
                "type": "admin",
            },
        ],
    },
    {
        "id": "action_package",
        "description": "Action Package (MCP Servers)",
        "icon": "⚙️",
        "scopes": [
            {
                "id": "action_package_read",
                "title": "View Action Packages",
                "description": "Read-only access to action packages for automation.",
                "type": "read",
            },
            {
                "id": "action_package_admin",
                "title": "Manage Action Packages",
                "description": "Full administrative access to action packages.",
                "type": "admin",
            },
        ],
    },
    {
        "id": "conversations_chat",
        "description": "Conversations & Chat",
        "icon": "💬",
        "scopes": [
            {
                "id": "conversation_read",
                "title": "View Conversations",
                "description": "Read-only access to conversations.",
                "type": "read",
            },
            {
                "id": "conversation_participate",
                "title": "Participate in Conversations",
                "description": "Allows a user to send and receive messages in a conversation.",
                "type": "normal",
            },
            {
                "id": "conversation_admin",
                "title": "Manage Conversations",
                "description": "Administrative access to all conversations (e.g., view, delete).",
                "type": "admin",
            },
        ],
    },
    {
        "id": "data_knowledge",
        "description": "Data & Knowledge",
        "icon": "🧠",
        "scopes": [
            {
                "id": "datasource_read",
                "title": "View Data Sources",
                "description": "Read-only access to data source configurations.",
                "type": "read",
            },
            {
                "id": "datasource_admin",
                "title": "Manage Data Sources",
                "description": "Full administrative access to data sources (create, configure, delete).",
                "type": "admin",
            },
            {
                "id": "kb_admin",
                "title": "Manage Knowledge Base",
                "description": "Full administrative access to the knowledge base.",
                "type": "admin",
            },
        ],
    },
    {
        "id": "llm_configurations",
        "description": "LLM Configurations",
        "icon": "💡",
        "scopes": [
            {
                "id": "llm_access",
                "title": "LLM Access",
                "description": "Grants access to use the underlying Large Language Models for generation tasks.",
                "type": "system",
            },
        ],
    },
]
