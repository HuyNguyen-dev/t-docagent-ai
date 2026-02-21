# DIMS-AI API Scopes

This document defines the available scopes for API access tokens in the DIMS-AI platform. Scopes control what actions and resources an access token can access.

## Quick Reference - Scopes Summary

| Scope | Category | Access Level | Description | Key Endpoints |
|-------|----------|--------------|-------------|---------------|
| **Core API** |
| `api` | Core API | System | Complete read and write access to entire API | All endpoints |
| `read_api` | Core API | Read | Read-only access to all API endpoints | All GET endpoints |
| **Agent Management** |
| `agent_admin` | Agent | Admin | Full administrative access to agents | POST/PUT/DELETE /agent |
| `agent_read` | Agent | Read | Read-only access to agent information | GET /agent |
| `agent_conversation` | Agent | Operational | Create and manage conversations with agents | POST /conversational-agent/chat |
| `agent_workflow` | Agent | Operational | Execute worker agent workflows | POST /worker-agent/chat |
| `agent_execution` | Agent | Operational | Execute sample agent workflows | POST /sample-agent/ainvoke |
| **Document Processing** |
| `document_admin` | Document | Admin | Full administrative access to document types and formats | POST/PUT/DELETE /document-type |
| `document_read` | Document | Read | Read-only access to documents and work items | GET /document-type |
| `document_processing` | Document | Operational | Process documents and train models | POST /document-format/train |
| `document_intelligence` | Document | Operational | AI-powered document analysis features | POST /document-intelligence |
| **Data Source Management** |
| `datasource_admin` | Data Source | Admin | Full administrative access to data sources | POST /datasource |
| `datasource_read` | Data Source | Read | Read-only access to data source information | GET /datasource |
| **LLM & AI** |
| `llm_access` | AI/LLM | Operational | Access to LLM completion and configuration services | POST /llm/ainvoke |
| **Action Packages** |
| `action_package_admin` | Action Package | Admin | Full administrative access to action packages | POST/PUT/DELETE /action-package |
| `action_package_read` | Action Package | Read | Read-only access to action packages | GET /action-package |
| **Conversations** |
| `conversation_admin` | Conversation | Admin | Full conversation management access | POST/PUT/DELETE /conversation |
| `conversation_read` | Conversation | Read | Read-only access to conversation data | GET /conversation/messages |
| `conversation_participate` | Conversation | Operational | Participate in conversations (scope mentioned but not implemented) | - |
| **Runbooks** |
| `runbook_admin` | Runbook | Admin | Full administrative access to runbooks | POST/PUT/DELETE /runbook |
| `runbook_read` | Runbook | Read | Read-only access to runbooks and templates | GET /runbook |
| **Work Items** |
| `work_item_admin` | Work Item | Admin | Full access to work item management | DELETE /work-item |
| `work_item_read` | Work Item | Read | Read-only access to work items | GET /work-item |
| `work_item_download` | Work Item | Operational | Download work item files and content | POST /work-item/file/download |
| **Knowledge Base** |
| `kb_admin` | Knowledge Base | Admin | Full administrative access to knowledge base | POST/PUT/DELETE /knowledge-base |
| **User Management** |
| `user_admin` | User | Admin | Full administrative access to user management | POST/PUT/DELETE /users |
| `user_read` | User | Read | Read-only access to user information (defined but not implemented) | - |
| **System & Tokens** |
| `system_info_read` | System | Read | Read-only access to system information (defined but not implemented) | - |
| `token_admin` | Token | Admin | Create and manage access tokens | POST/PUT/DELETE /tokens |
| `token_rotate` | Token | System | Allow tokens to rotate themselves (defined but not implemented) | - |

### Access Level Legend
- **System**: Full system access (equivalent to all scopes)
- **Admin**: Administrative operations (create, update, delete)
- **Operational**: Standard operations (execute, process, upload)
- **Read**: Read-only access (view, list, download)

## Core API Scopes

### `api`
Grants complete read and write access to the entire DIMS-AI API, including all agents, documents, conversations, and management functions.

### `read_api`
Grants read-only access to all DIMS-AI API endpoints, allowing viewing but no modifications.

## Agent Management Scopes

### `agent_admin`
Grants full administrative access to agent management including:
- Create new agents
- Read agent configurations
- Update agent settings
- Delete agents
- Manage agent runbooks

**Endpoints covered:**
- `POST /agent`
- `GET /agent/{agent_id}`
- `PUT /agent/{agent_id}`
- `GET /agent`
- `DELETE /agent/{agent_id}`
- `GET /agent/{agent_id}/conversations`
- `GET /agent/{agent_id}/runbooks`
- `PUT /agent/{agent_id}/default-runbook`
- `GET /agent/list/by-type`

### `agent_read`
Grants read-only access to agent information and configurations.

**Endpoints covered:**
- `GET /agent/{agent_id}`
- `GET /agent`
- `GET /agent/{agent_id}/conversations`
- `GET /agent/{agent_id}/runbooks`
- `GET /agent/list/by-type`

### `agent_conversation`
Grants access to create and manage conversations with conversational agents.

**Endpoints covered:**
- `POST /conversational-agent/{conv_id}/chat`
- `GET /conversational-agent/{conv_id}/stream`

### `agent_workflow`
Grants permission to execute worker agent workflows.

**Endpoints covered:**
- `POST /worker-agent/{conv_id}/chat`
- `GET /worker-agent/{conv_id}/stream`

### `agent_execution`
Grants permission to execute sample agent workflows and invoke AI models.

**Endpoints covered:**
- `POST /sample-agent/ainvoke`
- `POST /sample-agent/astream`

## Document Processing Scopes

### `document_admin`
Grants full administrative access to document types and document formats.

**Endpoints covered:**
- `POST /document-type`
- `GET /document-type/{dt_id}`
- `PUT /document-type/{dt_id}`
- `DELETE /document-type/{dt_id}`
- `POST /document-type/{dt_id}/activate`
- `POST /document-type/validate-name`
- `POST /document-type/import`
- `GET /document-type/{dt_id}/export`
- `POST /document-format`
- `PUT /document-format/{df_id}`
- `DELETE /document-format/{df_id}`
- `PUT /document-format/state/update`

### `document_read`
Grants read-only access to document types, formats, and related information.

**Endpoints covered:**
- `GET /document-type` (with document_processing alternative)
- `GET /document-type/{dt_id}`
- `GET /document-type/{dt_id}/dashboard` (with document_processing alternative)
- `GET /document-type/list-names`
- `GET /document-type/{dt_id}/document-format`
- `GET /document-type/{dt_id}/training` (with document_processing alternative)
- `GET /document-type/{dt_id}/stream` (with document_processing alternative)
- `GET /document-format/{df_id}`

### `document_processing`
Grants permission to process documents and train models.

**Endpoints covered:**
- `GET /document-type` (alternative to document_read)
- `GET /document-type/{dt_id}/dashboard` (alternative to document_read)
- `GET /document-type/{dt_id}/training` (alternative to document_read)
- `GET /document-type/{dt_id}/stream` (alternative to document_read)
- `POST /document-format/{df_id}/train`
- `POST /document-intelligence/extract-document`

### `document_intelligence`
Grants access to AI-powered document analysis and annotation discovery features.

**Endpoints covered:**
- `POST /document-intelligence/discover-annotations`
- `POST /document-intelligence/extract-document`

## Data Source Management Scopes

### `datasource_admin`
Grants full administrative access to data source management including:
- Create new data sources
- Test data source connections

**Endpoints covered:**
- `POST /datasource`
- `POST /datasource/test`

### `datasource_read`
Grants read-only access to data source information.

**Endpoints covered:**
- `GET /datasource`
- `GET /datasource/{db_name}/tables`

## LLM and AI Scopes

### `llm_access`
Grants access to LLM completion services, model listings, and configuration management.

**Endpoints covered:**
- `GET /llm/list-models`
- `POST /llm/ainvoke`
- `POST /llm/astream`
- `GET /llm-configuration`
- `POST /llm-configuration`
- `PUT /llm-configuration/{config_id}`
- `DELETE /llm-configuration/{config_id}`

## Action Package Scopes

### `action_package_admin`
Grants full administrative access to action packages including create, update, and delete.

**Endpoints covered:**
- `POST /action-package/create/streamable-http`
- `POST /action-package/create/stdio`
- `PUT /action-package/{ap_id}/streamable-http`
- `PUT /action-package/{ap_id}/stdio`
- `DELETE /action-package/{ap_id}`

### `action_package_read`
Grants read-only access to action packages.

**Endpoints covered:**
- `GET /action-package/{ap_id}`
- `GET /action-package`

## Conversation Management Scopes

### `conversation_admin`
Grants full access to conversation management including create, update, and delete.

**Endpoints covered:**
- `POST /conversation`
- `PUT /conversation/{conv_id}/name`
- `DELETE /conversation/{conv_id}`

### `conversation_read`
Grants read-only access to conversation data.

**Endpoints covered:**
- `GET /conversation/{conv_id}/messages`

### `conversation_participate`
Grants permission to participate in conversations and send messages (defined but not implemented in current codebase).

## Runbook Management Scopes

### `runbook_admin`
Grants full administrative access to runbooks including create, edit, and delete.

**Endpoints covered:**
- `POST /runbook`
- `PUT /runbook/{name}/content`
- `DELETE /runbook/{name}`
- `DELETE /runbook/{name}/version/{version}`

### `runbook_read`
Grants read-only access to runbooks and templates.

**Endpoints covered:**
- `GET /runbook/{name}/version/{version}`
- `GET /runbook/templates`

## Work Item Management Scopes

### `work_item_admin`
Grants full access to document work item management.

**Endpoints covered:**
- `DELETE /work-item`

### `work_item_read`
Grants read-only access to work items and their status.

**Endpoints covered:**
- `GET /work-item/{dwi_id}`

### `work_item_download`
Grants permission to download work item files and content.

**Endpoints covered:**
- `POST /work-item/{dwi_id}/file/download`
- `POST /work-item/{dwi_id}/content/download`
- `POST /work-item/{dwi_id}/logs/download`

## Knowledge Base Management Scopes

### `kb_admin`
Grants full administrative access to knowledge base management including:
- Configure embedding and reranking models
- Manage vector database settings
- Upload and process documents
- Create and manage collections

**Endpoints covered:**
- `POST /knowledge-base/config/set`
- `GET /knowledge-base/config/get`
- `POST /knowledge-base/vector-db/set`
- `GET /knowledge-base/vector-db/get`
- `POST /knowledge-base/collection/create`
- `GET /knowledge-base/collection/list`
- `POST /knowledge-base/collection/{collection_name}/upload`
- `POST /knowledge-base/collection/{collection_name}/query`
- `DELETE /knowledge-base/collection/{collection_name}/delete`
- `POST /knowledge-base/collection/{collection_name}/add-urls`

## User Management Scopes

### `user_admin`
Grants full administrative access to user management including create, update, delete users and roles.

**Endpoints covered:**
- `POST /users`
- `GET /users`
- `PUT /users/{user_id}`
- `DELETE /users/{user_id}`
- `GET /users/{user_id}`
- `POST /users/roles`

### `user_read`
Grants read-only access to user information (defined in enum but not implemented).

## System Monitoring Scopes

### `system_info_read`
Grants read-only access to system information and configurations (defined in enum but not implemented).

## Token Management Scopes

### `token_admin`
Grants permission to create and manage access tokens.

**Endpoints covered:**
- `POST /tokens`
- `GET /tokens`
- `GET /tokens/{token_id}`
- `PUT /tokens/{token_id}`
- `DELETE /tokens/{token_id}`

### `token_rotate`
Grants permission for tokens to rotate themselves (defined in enum but not implemented).

## RBAC Integration with Scopes

### Role-Based Access Control (RBAC) + Scopes Architecture

This system combines **Role-Based Access Control (RBAC)** with **scope-based permissions** for maximum flexibility and security.

#### **How It Works:**
1. **Users** are assigned **Roles**
2. **Roles** have predefined **Scope Sets**
3. **Additional Scopes** can be granted to users beyond their role
4. **Final Permission** = Role Scopes + Additional Scopes

#### **Permission Resolution:**
```
User Permissions = Role.scopes ∪ User.additional_scopes
```

### System Roles and Default Scopes

#### **Owner**
**Default Scopes:**
```
api
```
**Description:** Ultimate system authority with complete access to all functionality, including user management, system configuration, and platform administration.

**Additional Capabilities:**
- Create, modify, and delete users and roles
- System configuration and security settings
- Platform-wide administrative functions
- Audit log access and compliance management
- Data export and backup operations

**Typical Use Cases:**
- Initial platform setup and configuration
- Managing organizational access and permissions
- System maintenance and security administration
- Compliance and audit oversight

#### **Admin**
**Default Scopes:**
```
agent_admin, agent_read, agent_conversation, agent_workflow, agent_execution,
document_admin, document_read, document_processing, document_intelligence,
action_package_admin, action_package_read, conversation_admin, conversation_read,
runbook_admin, runbook_read, work_item_admin, work_item_read, work_item_download,
llm_access, kb_admin, datasource_admin, datasource_read, read_api, token_admin
```
**Description:** Administrative access to manage platform features and content without user management capabilities.

**Key Responsibilities:**
- Manage AI agents, documents, and workflows
- Configure and operate platform features
- Monitor system performance and health
- Manage content and processing pipelines
- Support user operations and troubleshooting

**Typical Use Cases:**
- Setting up and configuring agents and document types
- Managing document processing workflows
- Training and deploying AI models
- Monitoring system operations and performance
- Supporting user requests and issues

#### **User**
**Default Scopes:**
```
read_api, agent_read, agent_conversation, agent_workflow, agent_execution,
document_read, document_processing, document_intelligence, work_item_read, 
work_item_download, action_package_read, conversation_read, runbook_read,
llm_access, datasource_read
```
**Description:** Standard user access for daily operations, interactions with AI agents, and document processing.

**Key Capabilities:**
- Interact with AI agents and create conversations
- Process documents using AI intelligence
- Access and download work items
- View system information and status
- Read-only access to configurations

**Typical Use Cases:**
- Daily interactions with AI agents
- Document processing and analysis
- Reviewing work items and results
- Integrating with APIs for operations
- Monitoring personal usage and activity

### Advanced RBAC Features

#### **Hierarchical Roles**
```
Owner > Admin > User
```

#### **Role Inheritance**
Higher roles inherit permissions from lower roles plus additional capabilities:
- **Owner**: Has `api` scope (includes all permissions) + user management capabilities
- **Admin**: Inherits User permissions + administrative scopes for platform management
- **User**: Base operational permissions for daily platform usage

#### **Permission Escalation via Additional Scopes**
Users can be granted additional scopes beyond their role for specific needs:

**Example - User with Admin Document Access:**
```
User Role: read_api, agent_conversation, ... (standard user scopes)
Additional Scopes: [document_admin, work_item_admin]
Final Permissions: User scopes + document_admin + work_item_admin
```

**Example - Admin with Token Management:**
```
Admin Role: agent_admin, document_admin, ... (standard admin scopes)
Additional Scopes: [token_admin]
Final Permissions: Admin scopes + token_admin
```

#### **Temporary Access Patterns**
Grant time-limited additional scopes for specific projects:

**Project-based Access:**
- User gets `agent_admin` scope for AI development project
- Admin gets `token_admin` scope for integration setup
- Automatic scope expiration after project completion

### Scope Hierarchy and Combinations

#### **Scope Categories by Access Level:**

**Read-Only Scopes:**
```
read_api, agent_read, document_read, conversation_read, work_item_read, 
action_package_read, runbook_read, system_info_read, datasource_read,
user_read
```

**Operational Scopes:**
```
agent_conversation, agent_workflow, agent_execution, llm_access, 
document_processing, document_intelligence, work_item_download,
conversation_participate
```

**Administrative Scopes:**
```
agent_admin, document_admin, action_package_admin, conversation_admin, 
runbook_admin, work_item_admin, token_admin, datasource_admin,
kb_admin, user_admin
```

**System-Level Scopes:**
```
api, token_rotate
```

## Implementation Guidelines

### Database Schema for RBAC + Scopes

#### **Users Collection**
```json
{
  "_id": "user_123",
  "username": "john.doe",
  "email": "john@company.com",
  "role": "user",
  "additional_scopes": ["agent_admin", "runbook_admin"],
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

#### **Roles Collection**
```json
{
  "_id": "admin",
  "name": "Admin",
  "description": "Administrative access to manage platform features and content",
  "scopes": [
    "agent_admin", "document_admin", "action_package_admin", "conversation_admin",
    "runbook_admin", "work_item_admin", "llm_access", "llm_streaming",
    "document_processing", "document_upload", "document_intelligence",
    "agent_execution", "read_api", "system_health", "token_self_manage",
    "datasource_admin", "datasource_read"
  ],
  "is_system_role": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### **Access Tokens Collection**
```json
{
  "_id": "token_456",
  "token_hash": "sha256_hash_of_token",
  "user_id": "user_123",
  "name": "API Integration Token",
  "scopes": ["read_api", "agent_conversation"],
  "expires_at": "2024-12-31T23:59:59Z",
  "last_used_at": "2024-01-15T10:30:00Z",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Permission Resolution Logic

```python
from typing import Set, List
from enum import Enum

class Role(Enum):
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"

# Role to scopes mapping
ROLE_SCOPES = {
    Role.OWNER: {APIScope.API},  # Full access to everything
    Role.ADMIN: {
        APIScope.AGENT_ADMIN, APIScope.AGENT_READ, APIScope.AGENT_CONVERSATION, APIScope.AGENT_WORKFLOW, APIScope.AGENT_EXECUTION,
        APIScope.DOCUMENT_ADMIN, APIScope.DOCUMENT_READ, APIScope.DOCUMENT_PROCESSING, APIScope.DOCUMENT_INTELLIGENCE,
        APIScope.ACTION_PACKAGE_ADMIN, APIScope.ACTION_PACKAGE_READ, APIScope.CONVERSATION_ADMIN, APIScope.CONVERSATION_READ,
        APIScope.RUNBOOK_ADMIN, APIScope.RUNBOOK_READ, APIScope.WORK_ITEM_ADMIN, APIScope.WORK_ITEM_READ, APIScope.WORK_ITEM_DOWNLOAD,
        APIScope.LLM_ACCESS, APIScope.KB_ADMIN, APIScope.DATASOURCE_ADMIN, APIScope.DATASOURCE_READ, 
        APIScope.READ_API, APIScope.TOKEN_ADMIN
    },
    Role.USER: {
        APIScope.READ_API, APIScope.AGENT_READ, APIScope.AGENT_CONVERSATION, APIScope.AGENT_WORKFLOW, APIScope.AGENT_EXECUTION,
        APIScope.DOCUMENT_READ, APIScope.DOCUMENT_PROCESSING, APIScope.DOCUMENT_INTELLIGENCE,
        APIScope.WORK_ITEM_READ, APIScope.WORK_ITEM_DOWNLOAD, APIScope.ACTION_PACKAGE_READ, APIScope.CONVERSATION_READ,
        APIScope.RUNBOOK_READ, APIScope.LLM_ACCESS, APIScope.DATASOURCE_READ
    }
}

def get_user_permissions(user_role: Role, additional_scopes: List[str] = None) -> Set[str]:
    """
    Calculate final user permissions by combining role scopes with additional scopes.
    """
    role_scopes = ROLE_SCOPES.get(user_role, set())
    additional_scopes = set(additional_scopes or [])
    
    # Special handling for 'api' scope (includes all scopes)
    if APIScope.API in role_scopes or APIScope.API in additional_scopes:
        return {APIScope.API}  # Return just 'api' as it includes everything
    
    return role_scopes.union(additional_scopes)

def has_required_scopes(user_scopes: Set[str], required_scopes: List[str]) -> bool:
    """
    Check if user has all required scopes.
    """
    # If user has 'api' scope, they have access to everything
    if APIScope.API in user_scopes:
        return True
    
    # Check if user has all required scopes
    return all(scope in user_scopes for scope in required_scopes)
```

### Token-Based Authorization

```python
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user_scopes(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Set[str]:
    """
    Extract and validate user scopes from access token.
    """
    token = credentials.credentials
    
    # Validate token and get user info
    token_data = await validate_access_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Get user from database
    user = await get_user_by_id(token_data["user_id"])
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Calculate user permissions
    user_role = Role(user["role"])
    additional_scopes = user.get("additional_scopes", [])
    token_scopes = token_data.get("scopes", [])  # Token-specific scopes
    
    # Token scopes are intersection of user permissions and token scopes
    user_permissions = get_user_permissions(user_role, additional_scopes)
    
    # If token has 'api' scope, use user's full permissions
    if APIScope.API in token_scopes:
        return user_permissions
    
    # Otherwise, token scopes are limited to what's specified
    return user_permissions.intersection(set(token_scopes))

def require_scopes_cached(*required_scopes: APIScope):
    """
    Decorator to require specific scopes for endpoint access.
    """
    def decorator(func):
        async def wrapper(*args, user_scopes: Set[str] = Depends(get_current_user_scopes), **kwargs):
            if not has_required_scopes(user_scopes, list(required_scopes)):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient scopes. Required: {required_scopes}"
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage example
@router.post("/agent")
@require_scopes_cached(APIScope.AGENT_ADMIN)
async def create_agent(agent_data: AgentInput):
    # Implementation
    pass

@router.get("/agent/{agent_id}")
@require_scopes_cached(APIScope.AGENT_READ)
async def get_agent(agent_id: str):
    # Implementation
    pass
```

### Advanced Authorization Features

#### **Resource-Based Access Control**
```python
def require_resource_access(resource_type: str, permission: APIScope):
    """
    Check both scope and resource-level permissions.
    """
    def decorator(func):
        async def wrapper(*args, user_scopes: Set[str] = Depends(get_current_user_scopes), **kwargs):
            # First check scopes
            if not has_required_scopes(user_scopes, [permission]):
                raise HTTPException(status_code=403, detail="Insufficient scopes")
            
            # Then check resource-level permissions
            resource_id = kwargs.get(f"{resource_type}_id")
            if resource_id and not await check_resource_access(user_id, resource_type, resource_id):
                raise HTTPException(status_code=403, detail="No access to this resource")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@router.get("/agent/{agent_id}")
@require_resource_access("agent", APIScope.AGENT_READ)
async def get_agent(agent_id: str):
    # Implementation
    pass
```

#### **Conditional Scopes**
```python
def require_any_scope_cached(*required_scopes: APIScope):
    """
    Require ANY of the specified scopes (OR logic).
    """
    def decorator(func):
        async def wrapper(*args, user_scopes: Set[str] = Depends(get_current_user_scopes), **kwargs):
            if APIScope.API not in user_scopes and not any(scope in user_scopes for scope in required_scopes):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Need one of these scopes: {required_scopes}"
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@router.get("/documents")
@require_any_scope_cached(APIScope.DOCUMENT_READ, APIScope.DOCUMENT_ADMIN, APIScope.DOCUMENT_PROCESSING)
async def list_documents():
    # Implementation
    pass
```

### Scope Validation and Inheritance

```python
# Scope inheritance rules
SCOPE_INHERITANCE = {
    APIScope.API: "all",  # Special case - includes everything
    APIScope.AGENT_ADMIN: [APIScope.AGENT_READ],
    APIScope.DOCUMENT_ADMIN: [APIScope.DOCUMENT_READ],
    APIScope.ACTION_PACKAGE_ADMIN: [APIScope.ACTION_PACKAGE_READ],
    APIScope.CONVERSATION_ADMIN: [APIScope.CONVERSATION_READ],
    APIScope.RUNBOOK_ADMIN: [APIScope.RUNBOOK_READ],
    APIScope.WORK_ITEM_ADMIN: [APIScope.WORK_ITEM_READ],
    APIScope.DATASOURCE_ADMIN: [APIScope.DATASOURCE_READ],
    APIScope.USER_ADMIN: [APIScope.USER_READ],
}

def expand_scopes(scopes: Set[str]) -> Set[str]:
    """
    Expand scopes to include inherited scopes.
    """
    expanded = set(scopes)
    
    for scope in scopes:
        if scope in SCOPE_INHERITANCE:
            if SCOPE_INHERITANCE[scope] == "all":
                # Return all available scopes
                return set(ROLE_SCOPES[Role.OWNER])
            expanded.update(SCOPE_INHERITANCE[scope])
    
    return expanded
```

### Error Handling

```python
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

class AuthorizationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )

class AuthenticationError(HTTPException):
    def __init__(self, detail: str = "Invalid or missing authentication"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )

# Usage in middleware
# @app.middleware("http") # Assuming 'app' is your FastAPI instance
# async def auth_middleware(request: Request, call_next):
#     try:
#         response = await call_next(request)
#         return response
#     except AuthenticationError as e:
#         return JSONResponse(
#             status_code=e.status_code,
#             content={"error": "authentication_failed", "message": e.detail}
#         )
#     except AuthorizationError as e:
#         return JSONResponse(
#             status_code=e.status_code,
#             content={"error": "authorization_failed", "message": e.detail}
#         )
```

### Token Management APIs

```python
# Assuming 'router' is defined elsewhere and 'TokenCreateRequest', 'create_token', 'get_user_tokens', 'revoke_user_token' are available
# from schemas.token import TokenCreateRequest
# from handlers.token import create_token, get_user_tokens, revoke_user_token
# from helpers.jwt_auth import get_current_user

@router.post("/auth/tokens")
@require_scopes_cached(APIScope.TOKEN_SELF_MANAGE)
async def create_access_token(
    token_request: TokenCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new access token with specified scopes."""
    # Validate requested scopes against user permissions
    user_permissions = get_user_permissions(
        Role(current_user["role"]),
        current_user.get("additional_scopes", [])
    )
    
    requested_scopes = set(token_request.scopes)
    if not requested_scopes.issubset(user_permissions):
        raise HTTPException(
            status_code=400,
            detail="Cannot create token with scopes you don't have"
        )
    
    # Create token
    token = await create_token(
        user_id=current_user["_id"],
        scopes=list(requested_scopes),
        expires_in=token_request.expires_in,
        name=token_request.name
    )
    
    return {"token": token, "scopes": list(requested_scopes)}

@router.get("/auth/tokens")
@require_scopes_cached(APIScope.TOKEN_SELF_MANAGE)
async def list_user_tokens(current_user: dict = Depends(get_current_user)):
    """List all tokens for current user."""
    return await get_user_tokens(current_user["_id"])

@router.delete("/auth/tokens/{token_id}")
@require_scopes_cached(APIScope.TOKEN_SELF_MANAGE)
async def revoke_token(token_id: str, current_user: dict = Depends(get_current_user)):
    """Revoke a specific token."""
    await revoke_user_token(current_user["_id"], token_id)
    return {"message": "Token revoked successfully"}
```
