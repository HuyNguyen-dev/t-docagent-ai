from fastapi import Depends, Response, status
from fastapi.routing import APIRouter

from helpers.jwt_auth import require_scopes_cached
from initializer import runbook_handler
from schemas.response import BasicResponse
from schemas.runbook import RunbookInput, RunbookUpdate
from utils.enums import APIScope

router = APIRouter(prefix="/runbook", dependencies=[])


@router.post(
    "",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.RUNBOOK_ADMIN)),
    ],
)
async def create_runbook(
    response: Response,
    runbook_input: RunbookInput,
) -> BasicResponse:
    """
    Create a new runbook.

    This endpoint allows for the creation of a new runbook with specified content.

    **Required Scopes:** `runbook_admin`
    """
    runbook = await runbook_handler.create_runbook(runbook_input=runbook_input)
    if runbook is None:
        resp = BasicResponse(
            status="failed",
            message="Failed to create runbook",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Runbook created successfully",
            data=runbook,
        )
        response.status_code = status.HTTP_201_CREATED
    return resp


@router.put(
    "/{name}/content",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.RUNBOOK_ADMIN)),
    ],
)
async def edit_runbook(
    response: Response,
    name: str,
    runbook_update: RunbookUpdate,
) -> BasicResponse:
    """
    Edit a runbook's content.

    This endpoint allows for updating the content of an existing runbook.

    **Required Scopes:** `runbook_admin`
    """
    success = await runbook_handler.edit_runbook(
        name=name,
        runbook_update=runbook_update,
    )
    if not success:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to edit runbook {name}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Runbook edited successfully",
            data={"name": name},
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/{name}/version/{version}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.RUNBOOK_READ)),
    ],
)
async def get_runbook(
    response: Response,
    name: str,
    version: str,
) -> BasicResponse:
    """
    Get a runbook by name and version.

    This endpoint retrieves the content of a specific version of a runbook.

    **Required Scopes:** `runbook_read`
    """
    runbook = await runbook_handler.get_runbook(name=name, version=version)
    if runbook is None:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to get runbook {name}",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message="Runbook retrieved successfully",
            data=runbook.model_dump(),
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.delete(
    "/{name}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.RUNBOOK_ADMIN)),
    ],
)
async def delete_all_runbooks(
    response: Response,
    name: str,
) -> BasicResponse:
    """
    Delete all versions of a runbook.

    This endpoint allows for the permanent deletion of all versions of a specified runbook.

    **Required Scopes:** `runbook_admin`
    """
    success = await runbook_handler.delete_all_runbooks(name=name)
    if not success:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to delete runbooks for {name}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="All runbooks deleted successfully",
            data={"name": name},
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.delete(
    "/{name}/version/{version}",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.RUNBOOK_ADMIN)),
    ],
)
async def delete_runbook_by_version(
    response: Response,
    name: str,
    version: str,
) -> BasicResponse:
    """
    Delete a specific version of a runbook.

    This endpoint allows for the permanent deletion of a specific version of a runbook.

    **Required Scopes:** `runbook_admin`
    """
    success = await runbook_handler.delete_runbook_by_version(name=name, version=version)
    if not success:
        resp = BasicResponse(
            status="failed",
            message=f"Failed to delete runbook {name} version {version}",
            data=None,
        )
        response.status_code = status.HTTP_400_BAD_REQUEST
    else:
        resp = BasicResponse(
            status="success",
            message="Runbook version deleted successfully",
            data={"name": name, "version": version},
        )
        response.status_code = status.HTTP_200_OK
    return resp


@router.get(
    "/templates",
    response_model=BasicResponse,
    dependencies=[
        Depends(require_scopes_cached(APIScope.RUNBOOK_READ)),
    ],
)
async def get_all_runbook_templates(
    response: Response,
) -> BasicResponse:
    """
    Get all runbook templates (labels contains 'template').

    This endpoint retrieves a list of all runbook templates.

    **Required Scopes:** `runbook_read`
    """
    runbooks = await runbook_handler.get_all_runbook_template()
    if not runbooks:
        resp = BasicResponse(
            status="failed",
            message="No runbook templates found",
            data=None,
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    else:
        resp = BasicResponse(
            status="success",
            message="Runbook templates retrieved successfully",
            data=[rb.model_dump() for rb in runbooks],
        )
        response.status_code = status.HTTP_200_OK
    return resp
