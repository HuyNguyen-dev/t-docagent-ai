import io
import urllib

import orjson
from fastapi import Depends, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter

from helpers.jwt_auth import require_scopes_cached
from initializer import agent_handler
from schemas.agent import AgentDefaultRunBook, AgentInput, AgentUpdate
from schemas.response import BasicResponse
from utils.enums import AgentType, APIScope

router = APIRouter(prefix="/agent", dependencies=[])


@router.post(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_ADMIN)),
    ],
)
async def create_new_agent(
    response: Response,
    agent_input: AgentInput,
) -> BasicResponse:
    """
    Create a new agent.

    This endpoint allows for the creation of a new agent with specified configurations.

    **Required Scopes:** `agent_admin`
    """
    agent_id = await agent_handler.create_new_agent(agent_input=agent_input)
    if agent_id is None:
        resp = BasicResponse(
            status="failed",
            message="Create new agent failed",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="New agent created successfully",
            data=agent_id,
        )
        response.status_code = status.HTTP_201_CREATED
    return resp


@router.get(
    "/{agent_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_READ)),
    ],
)
async def get_agent_by_id(
    response: Response,
    agent_id: str,
) -> BasicResponse:
    """
    Retrieve an agent by its ID.

    Returns the details of a specific agent.

    **Required Scopes:** `agent_read`
    """
    agent_data = await agent_handler.get_agent_by_id(agent_id=agent_id)
    if agent_data is None:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to fetch agent with id: {agent_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Agent retrieved successfully",
            data=agent_data,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.put(
    "/{agent_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_ADMIN)),
    ],
)
async def update_agent_by_id(
    response: Response,
    agent_id: str,
    agent_update: AgentUpdate,
) -> BasicResponse:
    """
    Update an agent by its ID.

    This endpoint allows for updating the configuration of an existing agent.

    **Required Scopes:** `agent_admin`
    """
    new_agent_info = await agent_handler.update_agent_by_id(agent_id=agent_id, agent_update=agent_update)
    if new_agent_info is None:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to update agent with id: {agent_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        result = await agent_handler.refresh_all_conv_by_agent_id(new_agent_info)
        if result:
            resp = BasicResponse(
                status="success",
                message="Agent updated successfully",
                data=agent_id,
            )
            response.status_code = status.HTTP_200_OK
        else:
            resp = BasicResponse(
                status="failed",
                message="Failed to refresh all conversations",
                data=None,
            )
            response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return resp


@router.get(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_READ)),
    ],
)
async def get_all_agents(
    response: Response,
    q: str = "",
    agent_type: AgentType | None = None,
    page: int = 1,
    page_size: int = 10,
) -> BasicResponse:
    """
    Retrieve a paginated list of all agents.

    Supports searching by query, filtering by agent type, and pagination.

    **Required Scopes:** `agent_read`
    """
    agent_data = await agent_handler.get_all_agents(
        q=q,
        agent_type=agent_type,
        page=page,
        page_size=page_size,
    )
    if agent_data is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to fetch all agents",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="All agents retrieved successfully",
            data=agent_data.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/list/templates",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_READ)),
    ],
)
async def get_all_agent_templates(
    response: Response,
    q: str = "",
    page: int = 1,
    page_size: int = 10,
) -> BasicResponse:
    """
    Get all agent templates (agents with is_template=True).
    """
    result = await agent_handler.get_all_agent_templates(q=q, page=page, page_size=page_size)
    if not result:
        resp = BasicResponse(
            status="failed",
            message="No agent templates found.",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message="Fetch agent templates successfully.",
            data=result.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.put(
    "/{agent_id}/set-template",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_ADMIN)),
    ],
)
async def set_agent_template(
    response: Response,
    agent_id: str,
    is_template: bool,
) -> BasicResponse:
    """
    Set the is_template field of an agent.

    This endpoint allows updating the template status of an agent.

    **Required Scopes:** `agent_admin`
    """
    success = await agent_handler.set_agent_template(agent_id=agent_id, is_template=is_template)
    if not success:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to set template status for agent {agent_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Agent template status updated successfully",
            data={"agent_id": agent_id, "is_template": is_template},
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{agent_id}/conversations",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_READ)),
    ],
)
async def get_all_conversations_by_agent_id(
    response: Response,
    agent_id: str,
    agent_type: AgentType = AgentType.WORKER,
    q: str = "",
    page: int = 1,
    page_size: int = 10,
) -> BasicResponse:
    """
    Retrieve a paginated list of conversations associated with a specific agent.

    Supports searching by query, filtering by agent type, and pagination.

    **Required Scopes:** `agent_read`
    """
    convs = await agent_handler.get_all_conversations_by_agent_id(
        agent_id=agent_id,
        agent_type=agent_type,
        q=q,
        page=page,
        page_size=page_size,
    )
    if convs is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to fetch conversations",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Conversations retrieved successfully",
            data=convs.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{agent_id}/runbooks",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_READ)),
    ],
)
async def list_runbook_names_by_agent_id(
    response: Response,
    agent_id: str,
) -> BasicResponse:
    """
    List all runbook names for an agent.

    Returns a list of runbook names associated with a specific agent.

    **Required Scopes:** `agent_read`
    """
    runbook_names = await agent_handler.list_runbook_names_by_agent_id(agent_id=agent_id)
    if runbook_names is None:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to list runbooks for agent {agent_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Runbooks listed successfully",
            data=runbook_names,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.put(
    "/{agent_id}/default-runbook",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_ADMIN)),
    ],
)
async def set_default_version(
    response: Response,
    agent_id: str,
    default_runbook: AgentDefaultRunBook,
) -> BasicResponse:
    """
    Set the default version for a runbook associated with an agent.

    This endpoint allows specifying which version of a runbook should be considered the default.

    **Required Scopes:** `agent_admin`
    """
    success = await agent_handler.set_default_version(
        agent_id=agent_id,
        default_runbook=default_runbook,
    )
    if not success:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to set default version for runbook {default_runbook.name}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Default version set successfully",
            data={"name": default_runbook.name, "version": default_runbook.version},
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/list/by-type",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_READ)),
    ],
)
async def get_agents_by_type(
    response: Response,
    agent_type: AgentType,
    page: int = 1,
    page_size: int = 5,
) -> BasicResponse:
    """
    Get all agents filtered by type (Conversation/Worker).

    Returns a paginated list of agents, filtered by their type.

    **Required Scopes:** `agent_read`
    """
    agent_data = await agent_handler.get_agents_by_type(
        agent_type=agent_type,
        page=page,
        page_size=page_size,
    )
    if agent_data is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to fetch agents by type",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Agents by type retrieved successfully",
            data=agent_data.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.delete(
    "/{agent_id}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_ADMIN)),
    ],
)
async def delete_agent(
    response: Response,
    agent_id: str,
) -> BasicResponse:
    """
    Delete an agent by its ID.

    This endpoint allows for the permanent deletion of an agent.

    **Required Scopes:** `agent_admin`
    """
    success = await agent_handler.delete_agent(agent_id=agent_id)
    if not success:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to delete agent with id: {agent_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Agent and all related data deleted successfully",
            data={"agent_id": agent_id},
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{agent_id}/refresh-action-connections",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.AGENT_READ)),
    ],
)
async def refresh_action_connections(
    response: Response,
    agent_id: str,
) -> BasicResponse:
    """
    Refreshes the connection details of all action packages for the given agent.

    This endpoint triggers a refresh of all action package connections associated with a specific agent.

    **Required Scopes:** `agent_read`
    """
    action_packages = await agent_handler.refresh_action_connections(agent_id=agent_id)
    if action_packages is None:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to refresh action connections for agent with id: {agent_id}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Action connections refreshed successfully",
            data=action_packages,
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{agent_id}/export",
    response_model=BasicResponse,
)
async def export_agent(
    response: Response,
    agent_id: str,
    _: None = Depends(require_scopes_cached(APIScope.AGENT_ADMIN)),
) -> StreamingResponse | BasicResponse:
    """
    Export agent by ID.

    This endpoint allows for exporting the configuration and data of a specific agent.

    **Required Scopes:** `agent_admin`
    """
    export_data = await agent_handler.export_agent(agent_id)

    if export_data is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to export agent",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
        return resp

    json_content = export_data.model_dump(mode="json")
    file_stream = io.BytesIO(orjson.dumps(json_content))

    filename = f"agent_{agent_id}.json"

    encoded_filename = urllib.parse.quote(filename, safe="")
    content_disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_filename}"

    response.status_code = status.HTTP_200_OK
    return StreamingResponse(
        content=file_stream,
        media_type="application/json",
        headers={"Content-Disposition": content_disposition},
    )


@router.post("/import", response_model=BasicResponse)
async def import_agent(
    response: Response,
    agent_name: str,
    file: UploadFile,
    _: None = Depends(require_scopes_cached(APIScope.AGENT_ADMIN)),
) -> BasicResponse:
    """
    Import agent from a JSON file.

    This endpoint allows for importing an agent's configuration and data from a JSON file.

    **Required Scopes:** `agent_admin`
    """
    if not file.filename.endswith(".json"):
        resp = BasicResponse(
            status="failed",
            message="File must be a JSON file",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
        return resp

    result = await agent_handler.import_agent(agent_name, file)
    if not result:
        resp = BasicResponse(
            status="failed",
            message="Failed to import agent. ",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
        return resp

    resp = BasicResponse(
        status="success",
        message="Import agent successfully.",
        data=result,
    )
    response.status_code = status.HTTP_200_OK

    return resp
